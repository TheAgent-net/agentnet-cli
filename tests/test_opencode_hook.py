import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from agentnet_cli.cli.main import app
from agentnet_cli.tools import opencode_hook, skillfire

runner = CliRunner()
_ENV = skillfire.SUBAGENT_ENV
_CACHE = "agentnet_cli.tools.skillfire.session.cache_path"
_POPEN = "agentnet_cli.tools.skillfire.worker.subprocess.Popen"
_WHICH = "agentnet_cli.tools.skillfire.worker.shutil.which"


def _cache(outcome, final=True):
    return json.dumps({"outcome": outcome, "final": final})


def _outcome(list_block, content):
    from agentnet_cli.tools.skillfire import render

    return render.compose_outcome(list_block, content)


# ── run_opencode_pre (chat.message: spawn worker) ─────────────────────────────
def test_opencode_pre_spawns_worker(tmp_path, monkeypatch):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "s.json")
    monkeypatch.setattr(_WHICH, lambda n: "/usr/bin/agentnet")
    captured = {}
    monkeypatch.setattr(_POPEN, lambda args, **kw: captured.setdefault("args", args) or MagicMock())
    opencode_hook.run_opencode_pre("sess-1", "add jwt auth to my api", limit=5, timeout=3.0)
    args = captured["args"]
    assert "skill-hook" in args and "--fetch" in args
    assert "add jwt auth to my api" in args and "sess-1" in args  # reuses the shared worker
    assert args[args.index("--classifier") + 1] == "opencode"  # carried as the harness label


def test_opencode_pre_skips_own_fallback(monkeypatch):
    # Our own [AgentNet] fallback text must never re-spawn the worker.
    monkeypatch.delenv(_ENV, raising=False)
    called = MagicMock()
    monkeypatch.setattr(_POPEN, called)
    opencode_hook.run_opencode_pre("s", "[AgentNet] Relevant skills below...", limit=5, timeout=3.0)
    called.assert_not_called()


def test_opencode_pre_spawns_one_across_duplicates(tmp_path, monkeypatch):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "s.json")
    monkeypatch.setattr(_WHICH, lambda n: "/usr/bin/agentnet")
    spawns = []
    monkeypatch.setattr(_POPEN, lambda args, **kw: spawns.append(args) or MagicMock())
    for _ in range(2):
        opencode_hook.run_opencode_pre("sess-1", "same prompt", limit=5, timeout=3.0)
    assert len(spawns) == 1  # spawn-once claim held


def test_opencode_pre_no_spawn_inside_subagent(monkeypatch):
    monkeypatch.setenv(_ENV, "1")
    called = MagicMock()
    monkeypatch.setattr(_POPEN, called)
    opencode_hook.run_opencode_pre("s", "x", limit=5, timeout=3.0)
    called.assert_not_called()


# ── run_opencode_peek (system.transform: toast list + inlined system text) ────
def test_opencode_peek_emits_toast_and_inlines_skill(tmp_path, monkeypatch, capsys):
    # The methodology must be INLINED (opencode sandboxes external-file reads), and the user-facing
    # list must be split out for the toast (the system-prompt injection is invisible to the user).
    skillmd = tmp_path / "SKILL.md"
    skillmd.write_text("# Multi-stage Dockerfile\nUse two stages: builder then a slim runtime.")
    content = (
        "multi-stage-dockerfile — Create optimized Dockerfiles\n\n"
        f"The full skill methodology is on disk at:\n  {skillmd}\nRead it and follow it."
    )
    cache = tmp_path / "s.json"
    cache.write_text(_cache(_outcome("multi-stage-dockerfile (65%) — docker skill", content)))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    opencode_hook.run_opencode_peek("sess", limit=5, timeout=3.0)
    out = capsys.readouterr().out
    assert "\x1e" in out
    toast, system = out.split("\x1e", 1)
    assert "multi-stage-dockerfile (65%)" in toast  # user-facing list -> toast
    assert "Use two stages: builder then a slim runtime." in system  # SKILL.md INLINED
    assert "on disk at" not in system  # no external-file pointer (opencode can't read it)
    assert skillfire.session.emit_marker(cache).exists()  # steer claim taken


def test_opencode_peek_toasts_list_before_final(tmp_path, monkeypatch, capsys):
    # Phase-1 (list, non-final): toast the list mid-turn for visibility, but DON'T steer yet
    # (no methodology to apply) — the steer claim is preserved for when content lands.
    cache = tmp_path / "s.json"
    cache.write_text(_cache(_outcome("docker (60%) — docker skill", ""), final=False))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    opencode_hook.run_opencode_peek("sess", limit=5, timeout=3.0)
    toast, system = capsys.readouterr().out.split("\x1e", 1)
    assert "docker (60%)" in toast   # user sees the list mid-turn
    assert system == ""              # nothing to steer with yet (non-final)
    assert cache.with_suffix(".toasted").exists()          # toast claimed
    assert not skillfire.session.emit_marker(cache).exists()  # steer claim preserved for final


def test_opencode_peek_toasts_phase1_then_steers_on_final(tmp_path, monkeypatch, capsys):
    # The full sequence: list toasts once (phase-1), then methodology steers once (phase-2).
    monkeypatch.delenv(_ENV, raising=False)
    cache = tmp_path / "s.json"
    monkeypatch.setattr(_CACHE, lambda s: cache)
    skillmd = tmp_path / "SKILL.md"
    skillmd.write_text("Use two stages: builder then a slim runtime.")
    content = f"docker-skill — desc\n\nThe full skill methodology is on disk at:\n  {skillmd}\nRead it."

    # phase 1 (non-final) -> toast only
    cache.write_text(_cache(_outcome("docker (60%) — docker", ""), final=False))
    opencode_hook.run_opencode_peek("sess", limit=5, timeout=3.0)
    t1, s1 = capsys.readouterr().out.split("\x1e", 1)
    assert "docker (60%)" in t1 and s1 == ""

    # phase 2 (final) -> steer only (toast already claimed)
    cache.write_text(_cache(_outcome("docker (60%) — docker", content), final=True))
    opencode_hook.run_opencode_peek("sess", limit=5, timeout=3.0)
    t2, s2 = capsys.readouterr().out.split("\x1e", 1)
    assert t2 == ""  # already toasted in phase 1
    assert "Use two stages: builder then a slim runtime." in s2  # methodology inlined + steered


def test_opencode_peek_silent_when_not_ready(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "nope.json")
    opencode_hook.run_opencode_peek("sess", limit=5, timeout=3.0)
    assert capsys.readouterr().out == ""


def test_opencode_peek_emits_once_across_inferences(tmp_path, monkeypatch, capsys):
    # system.transform fires every inference; exactly one must inject (emit-once claim).
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    outs = []
    for _ in range(3):
        opencode_hook.run_opencode_peek("sess", limit=5, timeout=3.0)
        outs.append(capsys.readouterr().out)
    assert sum(bool(o) for o in outs) == 1


def test_opencode_peek_silent_inside_subagent(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(_ENV, "1")
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo"))
    monkeypatch.setattr(_CACHE, lambda s: cache)
    opencode_hook.run_opencode_peek("sess", limit=5, timeout=3.0)
    assert capsys.readouterr().out == ""


# ── run_opencode_post (session.idle: toast the skill list) ────────────────────
def test_opencode_post_toasts_the_list(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "s.json"
    cache.write_text(_cache(_outcome("docker-skill (60%) — builds dockerfiles", "some methodology")))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    opencode_hook.run_opencode_post("sess", limit=5, timeout=0.3)
    out = capsys.readouterr().out
    assert "docker-skill (60%)" in out  # user-facing list for the toast
    assert "\x1e" not in out  # post has no system-prompt injection (turn is over)


def test_opencode_post_skips_when_already_steered(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo"))
    skillfire.session.emit_marker(cache).touch()
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    opencode_hook.run_opencode_post("sess", limit=5, timeout=0.15)
    assert capsys.readouterr().out == ""


def test_opencode_post_silent_when_absent(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "nope.json")
    opencode_hook.run_opencode_post("sess", limit=5, timeout=0.15)
    assert capsys.readouterr().out == ""


# ── CLI dispatch ──────────────────────────────────────────────────────────────
def test_cli_opencode_hook_peek(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    cache.write_text(_cache("STEER-TOKEN"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    result = runner.invoke(app, ["opencode-hook", "--peek", "--session", "c"])
    assert result.exit_code == 0 and "STEER-TOKEN" in result.stdout


def test_cli_opencode_hook_pre_spawns(tmp_path, monkeypatch):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "s.json")
    monkeypatch.setattr(_WHICH, lambda n: "/usr/bin/agentnet")
    captured = {}
    monkeypatch.setattr(_POPEN, lambda args, **kw: captured.setdefault("args", args) or MagicMock())
    result = runner.invoke(
        app, ["opencode-hook", "--pre", "--session", "c", "--query", "review my sql migration"]
    )
    assert result.exit_code == 0
    assert "review my sql migration" in captured["args"]
    assert captured["args"][captured["args"].index("--classifier") + 1] == "opencode"

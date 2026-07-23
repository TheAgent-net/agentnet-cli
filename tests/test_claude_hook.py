import io
import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from agentnet_cli.cli.main import app
from agentnet_cli.infra.package_paths import bundled_claude_marketplace
from agentnet_cli.tools import claude_hook, skillfire

runner = CliRunner()

_ENV = skillfire.SUBAGENT_ENV
_CACHE = "agentnet_cli.tools.skillfire.session.cache_path"
_POPEN = "agentnet_cli.tools.skillfire.worker.subprocess.Popen"
_WHICH = "agentnet_cli.tools.skillfire.worker.shutil.which"


def _cache(outcome, final=True):
    """Cached outcome. ``final=False`` = phase-1 list only (not yet actionable)."""
    return json.dumps({"outcome": outcome, "final": final})


def _stdin(monkeypatch, obj):
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.sys.stdin", io.StringIO(json.dumps(obj)))


# ── run_claude_pre (UserPromptSubmit: spawn the worker) ───────────────────────
def test_pre_spawns_detached_worker_with_prompt(tmp_path, monkeypatch):
    monkeypatch.delenv(_ENV, raising=False)
    _stdin(monkeypatch, {"session_id": "s9", "prompt": "help me query a vector db"})
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "s.json")
    monkeypatch.setattr(_WHICH, lambda n: "/usr/bin/agentnet")
    captured = {}
    monkeypatch.setattr(_POPEN, lambda args, **kw: captured.setdefault("args", args) or MagicMock())
    claude_hook.run_claude_pre(limit=5, timeout=3.0)
    args = captured["args"]
    assert "skill-hook" in args and "--fetch" in args
    assert "help me query a vector db" in args and "s9" in args
    assert args[args.index("--classifier") + 1] == "claude"


def test_pre_spawns_one_worker_across_duplicate_hooks(tmp_path, monkeypatch):
    # settings.json + plugin => two parallel UserPromptSubmit hooks; only one worker may spawn.
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "s.json")
    monkeypatch.setattr(_WHICH, lambda n: "/usr/bin/agentnet")
    spawns = []
    monkeypatch.setattr(_POPEN, lambda args, **kw: spawns.append(args) or MagicMock())
    for _ in range(2):  # two duplicate invocations for the same prompt
        _stdin(monkeypatch, {"session_id": "s9", "prompt": "same prompt"})
        claude_hook.run_claude_pre(limit=5, timeout=3.0)
    assert len(spawns) == 1  # spawn-once claim held


def test_pre_silent_on_empty_prompt(monkeypatch):
    monkeypatch.delenv(_ENV, raising=False)
    _stdin(monkeypatch, {"session_id": "s", "prompt": "   "})
    called = MagicMock()
    monkeypatch.setattr(_POPEN, called)
    claude_hook.run_claude_pre(limit=5, timeout=3.0)
    called.assert_not_called()


def test_pre_no_spawn_inside_subagent(monkeypatch):
    monkeypatch.setenv(_ENV, "1")
    _stdin(monkeypatch, {"session_id": "s", "prompt": "x"})
    called = MagicMock()
    monkeypatch.setattr(_POPEN, called)
    claude_hook.run_claude_pre(limit=5, timeout=3.0)
    called.assert_not_called()  # no fork bomb


# ── run_claude_peek (PostToolUse: forced mid-run steer, once) ─────────────────
def test_peek_forces_block_and_claims_once(tmp_path, monkeypatch, capsys):
    # PostToolUse uses decision:block (forced mid-run steer), not soft additionalContext.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("USE skill Foo"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_peek(limit=5, timeout=3.0)
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "block"
    assert "USE skill Foo" in out["reason"]
    assert "systemMessage" in out  # guaranteed-display channel always present alongside reason
    assert skillfire.session.emit_marker(cache).exists()  # atomic steer claim taken


def test_peek_system_message_carries_the_bare_list(tmp_path, monkeypatch, capsys):
    # systemMessage is Claude Code's platform-guaranteed display channel (never sent to the model),
    # so it should carry exactly the clean list — no [AgentNet] framing, no instructions.
    from agentnet_cli.tools.skillfire import render

    outcome = render.compose_outcome("AgentNet found these skills:\n\nA — x", "")
    cache = tmp_path / "s.json"
    cache.write_text(_cache(outcome))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_peek(limit=5, timeout=3.0)
    out = json.loads(capsys.readouterr().out)
    assert out["systemMessage"] == "AgentNet found these skills:\n\nA — x"
    assert "[AgentNet]" not in out["systemMessage"]  # no instruction framing, just the list


def test_peek_wording_never_claims_hidden_from_user(tmp_path, monkeypatch, capsys):
    # Claude Code prints the whole `reason` to the user's terminal transcript (native CLI
    # behavior), so a claim that a section is hidden from the user is a checkable lie that reads
    # as an injection signature. Claude's own wording (skillfire.render used read-only, not the
    # shared steer.py wrapper) must never assert that — and drops the "AGENT ONLY" framing
    # entirely rather than just softening it, naming the temp path directly instead.
    from agentnet_cli.tools.skillfire import render

    content = (
        "foo-skill — does foo\n\nThe full skill methodology is on disk at:\n"
        "  /tmp/fake-skill-dir/SKILL.md\nRead it and follow it as you continue."
    )
    outcome_with_content = render.compose_outcome("AgentNet found these skills:\n\nA — x", content)
    cache = tmp_path / "s.json"
    cache.write_text(_cache(outcome_with_content))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_peek(limit=5, timeout=3.0)
    out = json.loads(capsys.readouterr().out)
    reason = out["reason"]
    assert "does not see it" not in reason
    assert "do not show the user" not in reason
    assert "AGENT ONLY" not in reason  # dropped entirely, not just relabeled
    assert "A — x" in reason  # the list is still shared with the user
    assert "fetched to a temp file at" in reason
    assert "/tmp/fake-skill-dir/SKILL.md" in reason  # path named directly, not duplicated wording


def test_peek_wording_list_only_no_content(tmp_path, monkeypatch, capsys):
    # A list-only outcome (promoted to final with no methodology reachable) gets the "continue,
    # applying what those skills suggest" tail — no path, no AGENT ONLY mention at all.
    from agentnet_cli.tools.skillfire import render

    outcome_list_only = render.compose_outcome("AgentNet found these skills:\n\nA — x", "")
    cache = tmp_path / "s.json"
    cache.write_text(_cache(outcome_list_only))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_peek(limit=5, timeout=3.0)
    reason = json.loads(capsys.readouterr().out)["reason"]
    assert "A — x" in reason
    assert "applying what those skills suggest" in reason
    assert "fetched to a temp file" not in reason
    assert "AGENT ONLY" not in reason


def test_peek_wording_brokered_fallback_has_no_path(tmp_path, monkeypatch, capsys):
    # The brokered-A2A recommendation has no on-disk SKILL.md — _apply_tail must fall back to
    # embedding the recommendation directly rather than claim a path that doesn't exist.
    from agentnet_cli.tools.skillfire import render

    broker_content = (
        "Recommended by the AgentNet Skills Agent (nothing is installed locally — do not look "
        "for these files on disk):\nUse the multi-stage-dockerfile pattern."
    )
    outcome = render.compose_outcome("AgentNet found these skills:\n\nA — x", broker_content)
    cache = tmp_path / "s.json"
    cache.write_text(_cache(outcome))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_peek(limit=5, timeout=3.0)
    reason = json.loads(capsys.readouterr().out)["reason"]
    assert "apply this recommendation" in reason
    assert "Use the multi-stage-dockerfile pattern" in reason
    assert "fetched to a temp file" not in reason  # no real path to name


def test_peek_noop_when_already_steered(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("x"))
    skillfire.session.emit_marker(cache).touch()  # a prior peek/post already claimed the steer
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_peek(limit=5, timeout=3.0)
    assert capsys.readouterr().out == ""


def test_peek_steers_once_across_duplicate_hooks(tmp_path, monkeypatch, capsys):
    # settings.json + plugin => two parallel PostToolUse hooks; only one may emit.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("USE skill Foo"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    outs = []
    for _ in range(2):  # two duplicate invocations for the same tool call
        _stdin(monkeypatch, {"session_id": "s"})
        claude_hook.run_claude_peek(limit=5, timeout=3.0)
        outs.append(capsys.readouterr().out)
    assert sum(bool(o) for o in outs) == 1  # exactly one steered


def test_peek_skips_non_final_outcome(tmp_path, monkeypatch, capsys):
    # Regression: the phase-1 list has no methodology. Steering on it hands the agent nothing to
    # apply, so the peek must wait for the content upgrade instead of burning the one steer.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("AgentNet found these skills:\n- Foo", final=False))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_peek(limit=5, timeout=3.0)
    assert capsys.readouterr().out == ""            # no steer
    assert not skillfire.session.emit_marker(cache).exists()  # and the claim is still available


def test_peek_noop_when_not_ready(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "nope.json")
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_peek(limit=5, timeout=3.0)
    assert capsys.readouterr().out == ""


def test_peek_silent_inside_subagent(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(_ENV, "1")
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo"))
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_peek(limit=5, timeout=3.0)
    assert capsys.readouterr().out == ""


# ── run_claude_post (Stop: fallback for no-tool answers) ──────────────────────
def test_post_accepts_non_final_as_last_chance(tmp_path, monkeypatch, capsys):
    # Stop is the final surface for the turn — take the list rather than surfacing nothing.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("LIST ONLY", final=False))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_post(limit=5, timeout=0.2)
    out = json.loads(capsys.readouterr().out)
    assert "LIST ONLY" in out["hookSpecificOutput"]["additionalContext"]


def test_post_folds_in_and_claims_once(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("USE skill Foo"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_post(limit=5, timeout=0.3)
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "block"
    assert out["hookSpecificOutput"]["hookEventName"] == "Stop"
    assert "USE skill Foo" in out["hookSpecificOutput"]["additionalContext"]
    assert "systemMessage" in out  # top-level, alongside hookSpecificOutput, not nested inside it
    assert skillfire.session.emit_marker(cache).exists()  # claim taken => a re-fired Stop no-ops


def test_post_system_message_carries_the_bare_list(tmp_path, monkeypatch, capsys):
    from agentnet_cli.tools.skillfire import render

    outcome = render.compose_outcome("AgentNet found these skills:\n\nA — x", "")
    cache = tmp_path / "s.json"
    cache.write_text(_cache(outcome))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_post(limit=5, timeout=0.3)
    out = json.loads(capsys.readouterr().out)
    assert out["systemMessage"] == "AgentNet found these skills:\n\nA — x"


def test_post_wording_never_claims_hidden_from_user(tmp_path, monkeypatch, capsys):
    from agentnet_cli.tools.skillfire import render

    content = (
        "foo-skill — does foo\n\nThe full skill methodology is on disk at:\n"
        "  /tmp/fake-skill-dir/SKILL.md\nRead it and follow it as you continue."
    )
    outcome_with_content = render.compose_outcome("AgentNet found these skills:\n\nA — x", content)
    cache = tmp_path / "s.json"
    cache.write_text(_cache(outcome_with_content))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_post(limit=5, timeout=0.3)
    out = json.loads(capsys.readouterr().out)
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "does not see it" not in context
    assert "do not show the user" not in context
    assert "AGENT ONLY" not in context
    assert "A — x" in context
    assert "fetched to a temp file at" in context
    assert "/tmp/fake-skill-dir/SKILL.md" in context
    assert context.startswith("[AgentNet] Found relevant skills")
    assert "Before finishing" in context  # post's fallback framing, distinct from peek's


def test_post_skips_when_peek_already_steered(tmp_path, monkeypatch, capsys):
    # Stop defers to the forced mid-run peek (avoids a double steer) via the shared emit claim.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("USE skill Foo"))
    skillfire.session.emit_marker(cache).touch()  # peek already claimed the steer
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_post(limit=5, timeout=0.3)
    assert capsys.readouterr().out == ""  # peek already forced the steer


def test_post_silent_when_cache_absent(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "nope.json")
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_post(limit=5, timeout=0.15)  # bounded — never blocks
    assert capsys.readouterr().out == ""


def test_post_silent_inside_subagent(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(_ENV, "1")
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo"))
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    claude_hook.run_claude_post(limit=5, timeout=0.3)
    assert capsys.readouterr().out == ""


# ── CLI dispatch ──────────────────────────────────────────────────────────────
def test_cli_post_reads_cache(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    cache.write_text(_cache("MYSLATE-TOKEN"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    result = runner.invoke(
        app, ["skill-hook", "--post", "--timeout", "0.3"],
        input=json.dumps({"session_id": "s"}),
    )
    assert result.exit_code == 0 and "MYSLATE-TOKEN" in result.stdout


def test_cli_peek_reads_cache(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    cache.write_text(_cache("PEEK-TOKEN"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    result = runner.invoke(
        app, ["skill-hook", "--peek"], input=json.dumps({"session_id": "s"})
    )
    assert result.exit_code == 0 and "PEEK-TOKEN" in result.stdout


def test_cli_pre_spawns(tmp_path, monkeypatch):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_POPEN, lambda *a, **k: MagicMock())
    monkeypatch.setattr(_WHICH, lambda n: "agentnet")
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "s.json")
    result = runner.invoke(
        app, ["skill-hook", "--pre"], input=json.dumps({"session_id": "s", "prompt": "pdf"})
    )
    assert result.exit_code == 0


# ── plugin wiring ─────────────────────────────────────────────────────────────
def test_plugin_registers_all_three_hooks():
    hooks_path = bundled_claude_marketplace() / "plugin" / "hooks" / "hooks.json"
    hooks = json.loads(hooks_path.read_text())["hooks"]

    def has(event: str, cmd: str) -> bool:
        return any(
            any(h.get("command") == cmd for h in b.get("hooks", []))
            for b in hooks.get(event, [])
        )

    assert has("UserPromptSubmit", "agentnet skill-hook --pre")
    assert has("PostToolUse", "agentnet skill-hook --peek")
    assert has("Stop", "agentnet skill-hook --post")

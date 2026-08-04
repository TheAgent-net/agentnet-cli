import io
import json
from unittest.mock import MagicMock

import yaml
from typer.testing import CliRunner

from agentnet_cli.cli.main import app
from agentnet_cli.connectors import hermes_hook as conn
from agentnet_cli.tools import hermes_hook, skillfire

runner = CliRunner()
_ENV = skillfire.SUBAGENT_ENV
_CACHE = "agentnet_cli.tools.skillfire.session.cache_path"
_POPEN = "agentnet_cli.tools.skillfire.worker.start_detached_process"
_WHICH = "agentnet_cli.tools.skillfire.worker.agentnet_invocation"


def _cache(outcome, final=True):
    return json.dumps({"outcome": outcome, "final": final})


def _stdin(monkeypatch, obj):
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.sys.stdin", io.StringIO(json.dumps(obj)))


def _payload(**kw):
    """Hermes shell-hook payload shape: event-specific kwargs live under `extra`."""
    base = {"hook_event_name": "pre_llm_call", "session_id": "s1", "cwd": "/tmp", "extra": {}}
    base.update(kw)
    return base


# ── pre_llm_call -> --pre (spawn the shared worker) ──────────────────────────
def test_hermes_pre_spawns_worker(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "s.json")
    monkeypatch.setattr(_WHICH, lambda: ["/usr/bin/agentnet"])
    captured = {}
    monkeypatch.setattr(_POPEN, lambda args, **kw: captured.setdefault("args", args) or MagicMock())
    _stdin(monkeypatch, _payload(extra={"user_message": "add jwt auth to my api"}))
    hermes_hook.run_hermes_pre(limit=6, timeout=3.0)
    assert json.loads(capsys.readouterr().out) == {}  # never injects here
    args = captured["args"]
    assert "skill-hook" in args and "--fetch" in args
    assert "add jwt auth to my api" in args and "s1" in args
    assert args[args.index("--classifier") + 1] == "hermes"  # gate on the user's Hermes model


def test_hermes_pre_reads_user_message_from_extra(monkeypatch, capsys):
    # The prompt lives in extra.user_message, not at the top level.
    monkeypatch.delenv(_ENV, raising=False)
    called = MagicMock()
    monkeypatch.setattr(_POPEN, called)
    _stdin(monkeypatch, _payload(extra={}))  # no user_message
    hermes_hook.run_hermes_pre(limit=6, timeout=3.0)
    called.assert_not_called()
    assert json.loads(capsys.readouterr().out) == {}


def test_hermes_pre_skips_own_continuation(monkeypatch, capsys):
    # pre_verify's message comes back as a synthetic user turn -> must not re-spawn.
    monkeypatch.delenv(_ENV, raising=False)
    called = MagicMock()
    monkeypatch.setattr(_POPEN, called)
    _stdin(monkeypatch, _payload(extra={"user_message": "[AgentNet] Relevant skills found..."}))
    hermes_hook.run_hermes_pre(limit=6, timeout=3.0)
    called.assert_not_called()


def test_hermes_pre_spawns_once_across_duplicates(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "s.json")
    monkeypatch.setattr(_WHICH, lambda: ["/usr/bin/agentnet"])
    spawns = []
    monkeypatch.setattr(_POPEN, lambda args, **kw: spawns.append(args) or MagicMock())
    for _ in range(2):
        _stdin(monkeypatch, _payload(extra={"user_message": "same prompt"}))
        hermes_hook.run_hermes_pre(limit=6, timeout=3.0)
        capsys.readouterr()
    assert len(spawns) == 1


# ── pre_tool_call -> --peek (hard nudge) ─────────────────────────────────────
def test_hermes_peek_blocks_with_claude_shape(tmp_path, monkeypatch, capsys):
    # Hermes natively accepts the Claude-Code {"decision":"block","reason":...} shape and hands
    # `reason` back to the model as the tool's error.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("USE skill Foo"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, _payload(hook_event_name="pre_tool_call", tool_name="write_file"))
    hermes_hook.run_hermes_peek(limit=6, timeout=3.0)
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "block"
    assert "USE skill Foo" in out["reason"]
    assert skillfire.session.emit_marker(cache).exists()


def test_hermes_peek_allows_non_final(tmp_path, monkeypatch, capsys):
    # Phase-1 list only -> nothing to apply; allow and wait for the content upgrade.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("list only", final=False))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, _payload(hook_event_name="pre_tool_call", tool_name="write_file"))
    hermes_hook.run_hermes_peek(limit=6, timeout=3.0)
    assert json.loads(capsys.readouterr().out) == {}
    assert not skillfire.session.emit_marker(cache).exists()


def test_hermes_peek_blocks_once(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    outs = []
    for _ in range(2):
        _stdin(monkeypatch, _payload(hook_event_name="pre_tool_call", tool_name="write_file"))
        hermes_hook.run_hermes_peek(limit=6, timeout=3.0)
        outs.append(json.loads(capsys.readouterr().out))
    assert sum(1 for o in outs if o.get("decision") == "block") == 1


# ── pre_verify -> --post (fallback) ──────────────────────────────────────────
def test_hermes_post_continues_the_turn(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("USE skill Foo"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, _payload(hook_event_name="pre_verify", extra={"attempt": 0}))
    hermes_hook.run_hermes_post(limit=6, timeout=0.3)
    out = json.loads(capsys.readouterr().out)
    assert out["action"] == "continue"
    assert "USE skill Foo" in out["message"]


def test_hermes_post_is_idempotent_on_attempt(tmp_path, monkeypatch, capsys):
    # pre_verify re-fires after each nudge; without this guard it would burn max_verify_nudges.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, _payload(hook_event_name="pre_verify", extra={"attempt": 1}))
    hermes_hook.run_hermes_post(limit=6, timeout=0.2)
    assert json.loads(capsys.readouterr().out) == {}


def test_hermes_post_skips_when_already_steered(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo"))
    skillfire.session.emit_marker(cache).touch()
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, _payload(hook_event_name="pre_verify", extra={"attempt": 0}))
    hermes_hook.run_hermes_post(limit=6, timeout=0.2)
    assert json.loads(capsys.readouterr().out) == {}


# ── recursion guard ──────────────────────────────────────────────────────────
def test_hermes_hooks_silent_inside_subagent(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(_ENV, "1")
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo"))
    monkeypatch.setattr(_CACHE, lambda s: cache)
    for fn in (hermes_hook.run_hermes_pre, hermes_hook.run_hermes_peek, hermes_hook.run_hermes_post):
        _stdin(monkeypatch, _payload(extra={"user_message": "x"}))
        fn(limit=6, timeout=0.2)
        assert json.loads(capsys.readouterr().out) == {}


# ── CLI dispatch ─────────────────────────────────────────────────────────────
def test_cli_hermes_hook_peek(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    cache.write_text(_cache("BLOCK-TOKEN"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    result = runner.invoke(
        app, ["hermes-hook", "--peek"],
        input=json.dumps(_payload(hook_event_name="pre_tool_call", tool_name="write_file")),
    )
    assert result.exit_code == 0 and "BLOCK-TOKEN" in result.stdout and "block" in result.stdout


# ── connector: config.yaml hooks block + consent allowlist ───────────────────
def _patch_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(conn, "_config_path", lambda *a, **k: tmp_path / "config.yaml")
    monkeypatch.setattr(conn, "_allowlist_path", lambda *a, **k: tmp_path / "shell-hooks-allowlist.json")


def test_connector_install_idempotent_then_uninstall(tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    changed, _ = conn.install()
    assert changed
    hooks = yaml.safe_load((tmp_path / "config.yaml").read_text())["hooks"]
    for event, flag in [("pre_llm_call", "--pre"), ("pre_tool_call", "--peek"),
                        ("pre_verify", "--post")]:
        assert any(flag in e["command"] for e in hooks[event])
        assert all(e["timeout"] == conn._TIMEOUT for e in hooks[event])

    # consent: our three commands are pre-approved (non-TTY runs silently skip unapproved hooks)
    approvals = json.loads((tmp_path / "shell-hooks-allowlist.json").read_text())["approvals"]
    assert {a["event"] for a in approvals} == set(conn._HOOKS)

    assert conn.install()[0] is False  # idempotent

    assert conn.uninstall()[0] is True
    assert not yaml.safe_load((tmp_path / "config.yaml").read_text()).get("hooks")
    assert json.loads((tmp_path / "shell-hooks-allowlist.json").read_text())["approvals"] == []


def test_connector_preserves_user_hooks_and_approvals(tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "config.yaml").write_text(yaml.dump({
        "model": "anthropic/claude-sonnet-4.6",
        "hooks": {"pre_tool_call": [{"command": "~/my-guard.sh", "timeout": 5}]},
    }))
    (tmp_path / "shell-hooks-allowlist.json").write_text(json.dumps(
        {"approvals": [{"event": "pre_tool_call", "command": "~/my-guard.sh"}]}
    ))

    conn.install()
    data = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert data["model"] == "anthropic/claude-sonnet-4.6"  # unrelated config untouched
    cmds = [e["command"] for e in data["hooks"]["pre_tool_call"]]
    assert "~/my-guard.sh" in cmds and any("hermes-hook --peek" in c for c in cmds)

    conn.uninstall()
    data = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert [e["command"] for e in data["hooks"]["pre_tool_call"]] == ["~/my-guard.sh"]
    approvals = json.loads((tmp_path / "shell-hooks-allowlist.json").read_text())["approvals"]
    assert approvals == [{"event": "pre_tool_call", "command": "~/my-guard.sh"}]


def test_connector_only_claims_its_own_command():
    # Ownership must be parsed, not substring-matched: a user hook that merely mentions our command
    # would otherwise be replaced on install and have its consent revoked on uninstall.
    assert conn._is_agentnet_cmd("agentnet hermes-hook --pre")
    assert conn._is_agentnet_cmd("/usr/local/bin/agentnet hermes-hook --peek")  # absolute path
    assert not conn._is_agentnet_cmd('/opt/wrapper.sh --run "agentnet hermes-hook --pre"')
    assert not conn._is_agentnet_cmd("agentnet-helper hermes-hook --pre")  # different binary
    assert not conn._is_agentnet_cmd("agentnet skill-hook --pre")  # the Claude hook, not ours
    assert not conn._is_agentnet_cmd("agentnet")
    assert not conn._is_agentnet_cmd(None)


def test_connector_preserves_a_user_hook_that_mentions_our_command(tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    wrapper = '/opt/wrapper.sh --run "agentnet hermes-hook --pre"'
    (tmp_path / "config.yaml").write_text(yaml.dump(
        {"hooks": {"pre_llm_call": [{"command": wrapper, "timeout": 5}]}}
    ))
    conn.install()
    cmds = [e["command"] for e in
            yaml.safe_load((tmp_path / "config.yaml").read_text())["hooks"]["pre_llm_call"]]
    assert wrapper in cmds  # not swallowed as ours
    conn.uninstall()
    cmds = [e["command"] for e in
            yaml.safe_load((tmp_path / "config.yaml").read_text())["hooks"]["pre_llm_call"]]
    assert cmds == [wrapper]  # survives disconnect


def test_connector_leaves_malformed_allowlist_alone(tmp_path, monkeypatch):
    _patch_paths(monkeypatch, tmp_path)
    (tmp_path / "shell-hooks-allowlist.json").write_text("{not json")
    conn.install()
    # Clobbering it would silently disable the user's other approved hooks.
    assert (tmp_path / "shell-hooks-allowlist.json").read_text() == "{not json"

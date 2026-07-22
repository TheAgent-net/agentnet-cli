import io
import json
from unittest.mock import MagicMock

from typer.testing import CliRunner

from agentnet_cli.cli.main import app
from agentnet_cli.connectors import cursor_hook as conn
from agentnet_cli.tools import cursor_hook, hook

runner = CliRunner()
_ENV = hook._SUBAGENT_ENV
_CACHE = "agentnet_cli.tools.hook._cache_path"
_POPEN = "agentnet_cli.tools.cursor_hook.subprocess.Popen"
_WHICH = "agentnet_cli.tools.cursor_hook.shutil.which"


def _cache(outcome, final=True):
    """Cached outcome. ``final=False`` = phase-1 list only (not yet actionable)."""
    return json.dumps({"outcome": outcome, "final": final})


def _stdin(monkeypatch, obj):
    monkeypatch.setattr("agentnet_cli.tools.hook.sys.stdin", io.StringIO(json.dumps(obj)))


# ── run_cursor_pre (beforeSubmitPrompt: spawn worker, allow submission) ───────
def test_cursor_pre_spawns_and_allows(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "s.json")
    monkeypatch.setattr(_WHICH, lambda n: "/usr/bin/agentnet")
    captured = {}
    monkeypatch.setattr(_POPEN, lambda args, **kw: captured.setdefault("args", args) or MagicMock())
    _stdin(monkeypatch, {"conversation_id": "c1", "prompt": "add jwt auth to my api"})
    cursor_hook.run_cursor_pre(limit=5, timeout=3.0)
    assert json.loads(capsys.readouterr().out) == {"continue": True}
    args = captured["args"]
    assert "skill-hook" in args and "--fetch" in args
    assert "add jwt auth to my api" in args and "c1" in args  # reuses the shared worker
    assert args[args.index("--classifier") + 1] == "cursor"  # gate on the Cursor model


def test_cursor_pre_skips_own_followup(monkeypatch, capsys):
    # The stop-followup comes back through beforeSubmitPrompt tagged [AgentNet] -> never re-spawn.
    monkeypatch.delenv(_ENV, raising=False)
    called = MagicMock()
    monkeypatch.setattr(_POPEN, called)
    _stdin(monkeypatch, {"conversation_id": "c1", "prompt": "[AgentNet] Relevant skills below..."})
    cursor_hook.run_cursor_pre(limit=5, timeout=3.0)
    called.assert_not_called()
    assert json.loads(capsys.readouterr().out) == {"continue": True}


def test_cursor_pre_spawns_one_across_duplicates(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "s.json")
    monkeypatch.setattr(_WHICH, lambda n: "/usr/bin/agentnet")
    spawns = []
    monkeypatch.setattr(_POPEN, lambda args, **kw: spawns.append(args) or MagicMock())
    for _ in range(2):  # duplicate registrations for the same prompt
        _stdin(monkeypatch, {"conversation_id": "c1", "prompt": "same prompt"})
        cursor_hook.run_cursor_pre(limit=5, timeout=3.0)
        capsys.readouterr()
    assert len(spawns) == 1  # spawn-once claim held


def test_cursor_pre_no_spawn_inside_subagent(monkeypatch, capsys):
    monkeypatch.setenv(_ENV, "1")
    called = MagicMock()
    monkeypatch.setattr(_POPEN, called)
    _stdin(monkeypatch, {"conversation_id": "c", "prompt": "x"})
    cursor_hook.run_cursor_pre(limit=5, timeout=3.0)
    called.assert_not_called()
    assert json.loads(capsys.readouterr().out) == {"continue": True}


# ── run_cursor_peek (preToolUse: hard nudge — deny-once) ──────────────────────
def test_cursor_peek_denies_with_message(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("USE skill Foo"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"conversation_id": "c", "tool_name": "Write"})
    cursor_hook.run_cursor_peek(limit=5, timeout=3.0)
    out = json.loads(capsys.readouterr().out)
    assert out["permission"] == "deny"
    assert "USE skill Foo" in out["agent_message"] and out["agent_message"].startswith("[AgentNet]")
    assert out["user_message"]
    assert hook._emit_marker(cache).exists()  # steer claim taken


def test_cursor_peek_allows_non_final_outcome(tmp_path, monkeypatch, capsys):
    # Regression: denying on the phase-1 list cancels a real tool call and gives the agent nothing
    # to apply. Must allow and wait for the content upgrade.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("AgentNet found these skills:\n- Foo", final=False))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"conversation_id": "c", "tool_name": "Write"})
    cursor_hook.run_cursor_peek(limit=5, timeout=3.0)
    assert capsys.readouterr().out == ""            # tool allowed
    assert not hook._emit_marker(cache).exists()    # steer claim preserved


def test_cursor_peek_allows_when_not_ready(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "nope.json")
    _stdin(monkeypatch, {"conversation_id": "c", "tool_name": "Write"})
    cursor_hook.run_cursor_peek(limit=5, timeout=3.0)
    assert capsys.readouterr().out == ""  # no output -> Cursor allows the tool


def test_cursor_peek_denies_once_across_duplicates(tmp_path, monkeypatch, capsys):
    # Two tool calls (or duplicate hooks): deny exactly one, then allow -> no soft-lock.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    outs = []
    for _ in range(2):
        _stdin(monkeypatch, {"conversation_id": "c", "tool_name": "Write"})
        cursor_hook.run_cursor_peek(limit=5, timeout=3.0)
        outs.append(capsys.readouterr().out)
    assert sum(bool(o) for o in outs) == 1


def test_cursor_peek_silent_inside_subagent(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(_ENV, "1")
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo"))
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"conversation_id": "c", "tool_name": "Write"})
    cursor_hook.run_cursor_peek(limit=5, timeout=3.0)
    assert capsys.readouterr().out == ""


# ── run_cursor_post (stop: followup fallback) ─────────────────────────────────
def test_cursor_post_followup(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("USE skill Foo"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"conversation_id": "c", "status": "completed", "loop_count": 0})
    cursor_hook.run_cursor_post(limit=5, timeout=0.3)
    out = json.loads(capsys.readouterr().out)
    assert "USE skill Foo" in out["followup_message"]
    assert out["followup_message"].startswith("[AgentNet]")  # loop guard sentinel


def test_cursor_post_skips_when_already_steered(tmp_path, monkeypatch, capsys):
    # A tool-using task hard-nudged mid-run -> stop must not also fire a followup.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo"))
    hook._emit_marker(cache).touch()
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    _stdin(monkeypatch, {"conversation_id": "c", "status": "completed", "loop_count": 0})
    cursor_hook.run_cursor_post(limit=5, timeout=0.15)
    assert capsys.readouterr().out == ""


def test_cursor_post_silent_when_absent(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: tmp_path / "nope.json")
    _stdin(monkeypatch, {"conversation_id": "c", "status": "completed", "loop_count": 0})
    cursor_hook.run_cursor_post(limit=5, timeout=0.15)
    assert capsys.readouterr().out == ""


# ── CLI dispatch ──────────────────────────────────────────────────────────────
def test_cli_cursor_hook_peek(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    cache.write_text(_cache("DENY-TOKEN"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(_CACHE, lambda s: cache)
    result = runner.invoke(
        app, ["cursor-hook", "--peek"],
        input=json.dumps({"conversation_id": "c", "tool_name": "Write"}),
    )
    assert result.exit_code == 0 and "DENY-TOKEN" in result.stdout and "deny" in result.stdout


# ── connector: ~/.cursor/hooks.json install / uninstall ───────────────────────
def test_connector_only_claims_its_own_command():
    # Parsed ownership, not a prefix: never swallow an unrelated user hook on install/uninstall.
    assert conn._is_agentnet_cmd("agentnet cursor-hook --pre")
    assert conn._is_agentnet_cmd("/usr/local/bin/agentnet cursor-hook --peek")
    assert not conn._is_agentnet_cmd("agentnet cursor-hook-wrapper --pre")  # different sub-command
    assert not conn._is_agentnet_cmd("agentnet-helper cursor-hook --pre")  # different binary
    assert not conn._is_agentnet_cmd("agentnet skill-hook --pre")  # the Claude hook, not ours
    assert not conn._is_agentnet_cmd("agentnet")
    assert not conn._is_agentnet_cmd(None)


def test_connector_install_idempotent_then_uninstall(tmp_path, monkeypatch):
    hooks_path = tmp_path / ".cursor" / "hooks.json"
    monkeypatch.setattr("agentnet_cli.connectors.cursor_hook._hooks_path", lambda: hooks_path)

    changed, _ = conn.install()
    assert changed
    data = json.loads(hooks_path.read_text())
    assert data["version"] == 1
    for event, cmd in [("beforeSubmitPrompt", "--pre"), ("preToolUse", "--peek"), ("stop", "--post")]:
        assert any(cmd in e["command"] for e in data["hooks"][event])

    assert conn.install()[0] is False  # idempotent

    changed3, _ = conn.uninstall()
    assert changed3
    assert not json.loads(hooks_path.read_text()).get("hooks")


def test_connector_install_preserves_existing_hooks(tmp_path, monkeypatch):
    hooks_path = tmp_path / ".cursor" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(json.dumps(
        {"version": 1, "hooks": {"stop": [{"command": "user-thing", "type": "command"}]}}
    ))
    monkeypatch.setattr("agentnet_cli.connectors.cursor_hook._hooks_path", lambda: hooks_path)
    conn.install()
    stop = json.loads(hooks_path.read_text())["hooks"]["stop"]
    assert any(e["command"] == "user-thing" for e in stop)  # existing kept
    assert any("cursor-hook --post" in e["command"] for e in stop)  # ours added
    conn.uninstall()
    stop2 = json.loads(hooks_path.read_text())["hooks"]["stop"]
    assert [e["command"] for e in stop2] == ["user-thing"]  # only ours removed

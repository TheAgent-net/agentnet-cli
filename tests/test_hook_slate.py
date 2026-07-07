import io
import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from agentnet_cli.cli.main import app
from agentnet_cli.infra.package_paths import bundled_claude_marketplace
from agentnet_cli.tools import hook
from agentnet_cli.tools.slate import extract_query, format_slate, parse_slate

runner = CliRunner()

# Shape of GET /discover/ — a bare list[DiscoveryResult]
DISCOVER = [
    {
        "agent_id": "a1", "name": "PDF Pro", "description": "parse pdfs",
        "url": "https://x", "score": 9.4, "skills": [{"name": "ocr"}], "kind": "agent",
    },
    {
        "agent_id": "a2", "name": "DocAI", "description": "docs",
        "url": "https://y", "score": 7, "skills": [], "kind": "skill",
    },
]
_CREDS = "agentnet_cli.tools.hook._resolve_credentials"
_DISCOVER = "agentnet_cli.marketplace.client.PlatformClient.discover_agents"
_ENVELOPE = '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"AgentNet X"}}'


# ── slate.py ──────────────────────────────────────────────────────────────
def test_extract_query():
    assert extract_query({"query": "pdf"}) == "pdf"
    assert extract_query({"q": "  weather "}) == "weather"
    assert extract_query({"url": "http://x", "prompt": "summarize"}) == ""  # WebFetch-style


def test_parse_slate_is_deterministic():
    items = parse_slate(DISCOVER)
    assert [i.name for i in items] == ["PDF Pro", "DocAI"]
    assert items[0].skills == ["ocr"] and items[0].kind == "agent"
    assert items[1].kind == "skill"
    # not a bare list -> nothing (no key-guessing)
    assert parse_slate({"agents": DISCOVER}) == []
    assert parse_slate("nope") == []


def test_format_slate_no_sponsored_no_price():
    text = format_slate(parse_slate(DISCOVER))
    assert "PDF Pro" in text and "DocAI" in text
    assert "[SPONSORED]" not in text
    assert "/req" not in text and "$" not in text
    assert "score 9.4" in text and "skills: ocr" in text


def test_format_slate_empty():
    assert format_slate([]) == ""


# ── hook.build_additional_context ─────────────────────────────────────────
def _ctx(query="pdf parsing", discover=DISCOVER):
    with patch(_CREDS, return_value=("tok", "https://pf")), patch(_DISCOVER, return_value=discover):
        return hook.build_additional_context(query, limit=5, timeout=3.0)


def test_build_context_happy():
    data = json.loads(_ctx())
    assert data["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "PDF Pro" in data["hookSpecificOutput"]["additionalContext"]


def test_build_context_best_effort():
    assert hook.build_additional_context("", limit=5, timeout=3.0) == ""  # empty query
    with patch(_CREDS, return_value=None):
        assert hook.build_additional_context("pdf", limit=5, timeout=3.0) == ""  # no token
    assert _ctx(discover=[]) == ""  # empty results
    with patch(_CREDS, return_value=("t", "p")), patch(_DISCOVER, side_effect=RuntimeError("x")):
        assert hook.build_additional_context("pdf", limit=5, timeout=3.0) == ""  # error


# ── pre / fetch / post cache flow ─────────────────────────────────────────
def test_fetch_writes_cache(tmp_path):
    cache = tmp_path / "slate.json"
    with (
        patch("agentnet_cli.tools.hook._cache_path", return_value=cache),
        patch(_CREDS, return_value=("t", "p")),
        patch(_DISCOVER, return_value=DISCOVER),
    ):
        hook.run_fetch(session="s1", query="pdf", limit=5, timeout=3.0)
    assert cache.exists()
    assert "PDF Pro" in json.loads(cache.read_text())["hookSpecificOutput"]["additionalContext"]


def test_post_injects_cached_and_cleans_up(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "slate.json"
    cache.write_text(_ENVELOPE)
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s, q: cache)
    monkeypatch.setattr(
        "agentnet_cli.tools.hook.sys.stdin",
        io.StringIO(json.dumps({"session_id": "s", "tool_input": {"query": "pdf"}})),
    )
    hook.run_post(limit=5, timeout=0.3)
    assert "AgentNet X" in capsys.readouterr().out
    assert not cache.exists()  # cleaned up


def test_post_silent_when_cache_absent(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s, q: tmp_path / "nope.json")
    monkeypatch.setattr(
        "agentnet_cli.tools.hook.sys.stdin",
        io.StringIO(json.dumps({"session_id": "s", "tool_input": {"query": "pdf"}})),
    )
    hook.run_post(limit=5, timeout=0.15)  # bounded — never blocks
    assert capsys.readouterr().out == ""


def test_pre_spawns_detached_worker(monkeypatch):
    monkeypatch.setattr(
        "agentnet_cli.tools.hook.sys.stdin",
        io.StringIO(json.dumps({"session_id": "s9", "tool_input": {"query": "vector db"}})),
    )
    monkeypatch.setattr("agentnet_cli.tools.hook.shutil.which", lambda n: "/usr/bin/agentnet")
    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        return MagicMock()

    monkeypatch.setattr("agentnet_cli.tools.hook.subprocess.Popen", fake_popen)
    hook.run_pre(limit=5, timeout=3.0)
    args = captured["args"]
    assert "--fetch" in args and "vector db" in args and "s9" in args


def test_pre_silent_on_empty_query(monkeypatch):
    monkeypatch.setattr("agentnet_cli.tools.hook.sys.stdin", io.StringIO('{"tool_input":{}}'))
    called = MagicMock()
    monkeypatch.setattr("agentnet_cli.tools.hook.subprocess.Popen", called)
    hook.run_pre(limit=5, timeout=3.0)
    called.assert_not_called()


# ── credentials ───────────────────────────────────────────────────────────
def test_resolve_credentials_from_env(monkeypatch):
    monkeypatch.setenv("AGENTNET_TOKEN", "envtok")
    with patch("agentnet_cli.infra.config.load_config", return_value=None):
        assert hook._resolve_credentials() == ("envtok", "https://app.agentnet.market")


def test_resolve_credentials_none_without_token(monkeypatch):
    monkeypatch.delenv("AGENTNET_TOKEN", raising=False)
    with patch("agentnet_cli.infra.config.load_config", return_value=None):
        assert hook._resolve_credentials() is None


# ── CLI dispatch ──────────────────────────────────────────────────────────
def test_cli_post_reads_cache(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    cache.write_text(_ENVELOPE)
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s, q: cache)
    result = runner.invoke(
        app,
        ["hook-slate", "--post", "--slate-timeout", "0.3"],
        input=json.dumps({"session_id": "s", "tool_input": {"query": "pdf"}}),
    )
    assert result.exit_code == 0 and "AgentNet X" in result.stdout


def test_cli_pre_spawns(monkeypatch):
    monkeypatch.setattr("agentnet_cli.tools.hook.subprocess.Popen", lambda *a, **k: MagicMock())
    monkeypatch.setattr("agentnet_cli.tools.hook.shutil.which", lambda n: "agentnet")
    result = runner.invoke(
        app, ["hook-slate", "--pre"],
        input=json.dumps({"session_id": "s", "tool_input": {"query": "pdf"}}),
    )
    assert result.exit_code == 0


# ── plugin wiring ─────────────────────────────────────────────────────────
def test_plugin_registers_pre_and_post_hooks():
    hooks_path = bundled_claude_marketplace() / "plugin" / "hooks" / "hooks.json"
    hooks = json.loads(hooks_path.read_text())["hooks"]

    def has(event: str, cmd: str) -> bool:
        return any(
            "WebSearch" in b.get("matcher", "")
            and any(h.get("command") == cmd for h in b.get("hooks", []))
            for b in hooks.get(event, [])
        )

    assert has("PreToolUse", "agentnet hook-slate --pre")
    assert has("PostToolUse", "agentnet hook-slate --post")

import json
from unittest.mock import patch

from typer.testing import CliRunner

from agentnet_cli.cli.main import app
from agentnet_cli.infra.package_paths import bundled_claude_marketplace
from agentnet_cli.tools import hook

runner = CliRunner()

EVENT = json.dumps({"tool_name": "WebSearch", "tool_input": {"query": "pdf parsing"}})

SLATE = [
    {"name": "PDF Pro", "description": "parse pdfs", "sponsored": True, "score": 9, "url": "https://x"},
    {"name": "DocAI", "description": "docs", "score": 7},
]

_CREDS = "agentnet_cli.tools.hook._resolve_credentials"
_DISCOVER = "agentnet_cli.marketplace.client.PlatformClient.discover_agents"


def _build(event=EVENT, slate=SLATE, **kwargs):
    with patch(_CREDS, return_value=("tok", "https://pf")), patch(_DISCOVER, return_value=slate):
        return hook.build_additional_context(event, **kwargs)


def test_happy_path_emits_posttooluse_envelope():
    out = _build()
    data = json.loads(out)
    assert data["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    ctx = data["hookSpecificOutput"]["additionalContext"]
    assert "AgentNet" in ctx and "PDF Pro" in ctx and "DocAI" in ctx
    assert ctx.count("[SPONSORED]") == 1  # only the sponsored entry is labeled


def test_no_token_is_silent():
    with patch(_CREDS, return_value=None):
        assert hook.build_additional_context(EVENT) == ""


def test_empty_query_is_silent():
    event = json.dumps({"tool_name": "WebSearch", "tool_input": {"foo": "bar"}})
    assert _build(event=event) == ""


def test_missing_tool_input_is_silent():
    assert _build(event=json.dumps({"tool_name": "WebSearch"})) == ""


def test_malformed_stdin_is_silent():
    assert hook.build_additional_context("not json at all") == ""
    assert hook.build_additional_context("[1, 2, 3]") == ""


def test_empty_slate_is_silent():
    assert _build(slate=[]) == ""


def test_platform_failure_is_silent():
    with (
        patch(_CREDS, return_value=("tok", "https://pf")),
        patch(_DISCOVER, side_effect=RuntimeError("boom")),
    ):
        assert hook.build_additional_context(EVENT) == ""


def test_resolve_credentials_from_env(monkeypatch):
    monkeypatch.setenv("AGENTNET_TOKEN", "envtok")
    with patch("agentnet_cli.infra.config.load_config", return_value=None):
        assert hook._resolve_credentials() == ("envtok", "https://app.agentnet.market")


def test_resolve_credentials_none_without_token(monkeypatch):
    monkeypatch.delenv("AGENTNET_TOKEN", raising=False)
    with patch("agentnet_cli.infra.config.load_config", return_value=None):
        assert hook._resolve_credentials() is None


def test_cli_prints_envelope_to_stdout():
    with patch(_CREDS, return_value=("tok", "https://pf")), patch(_DISCOVER, return_value=SLATE):
        result = runner.invoke(app, ["hook-slate"], input=EVENT)
    assert result.exit_code == 0
    assert "PostToolUse" in result.stdout and "AgentNet" in result.stdout


def test_cli_silent_and_zero_exit_without_token():
    with patch(_CREDS, return_value=None):
        result = runner.invoke(app, ["hook-slate"], input=EVENT)
    assert result.exit_code == 0
    assert result.stdout.strip() == ""


def test_plugin_registers_posttooluse_hook():
    """The bundled Claude plugin wires WebSearch through `agentnet hook-slate`."""
    hooks_path = bundled_claude_marketplace() / "plugin" / "hooks" / "hooks.json"
    data = json.loads(hooks_path.read_text())
    post = data["hooks"]["PostToolUse"]
    assert any(
        "WebSearch" in block.get("matcher", "")
        and any(h.get("command") == "agentnet hook-slate" for h in block.get("hooks", []))
        for block in post
    )

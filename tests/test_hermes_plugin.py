import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentnet_cli.hermes_plugin import handlers, register
from agentnet_cli.hermes_plugin.schemas import SCHEMAS

EXPECTED_TOOL_NAMES = [
    "agentnet_discover",
    "agentnet_discover_agents",
    "agentnet_get_agent",
    "agentnet_use_agent",
    "agentnet_continue_session",
    "agentnet_settle_session",
    "agentnet_wallet",
    "agentnet_wallet_topup",
]


def test_schemas_has_all_tools():
    assert len(SCHEMAS) == 8
    names = [s["name"] for s in SCHEMAS]
    assert names == EXPECTED_TOOL_NAMES


def test_schemas_use_parameters_not_input_schema():
    for schema in SCHEMAS:
        assert "parameters" in schema, f"{schema['name']} missing 'parameters'"
        assert "inputSchema" not in schema, f"{schema['name']} should not have 'inputSchema'"
        assert "description" in schema
        assert "name" in schema


def test_handler_no_token(monkeypatch):
    monkeypatch.delenv("AGENTNET_TOKEN", raising=False)
    monkeypatch.setattr("agentnet_cli.hermes_plugin.handlers.load_config", lambda: None)
    result = json.loads(handlers.agentnet_discover({"query": "test"}))
    assert "error" in result
    assert "register" in result["error"].lower()


def test_handler_returns_json(monkeypatch):
    mock_handlers = MagicMock()
    mock_handlers.discover.return_value = {"listings": []}
    monkeypatch.setattr(
        "agentnet_cli.hermes_plugin.handlers._get_handlers",
        lambda: mock_handlers,
    )
    result = handlers.agentnet_discover({"query": "weather"})
    parsed = json.loads(result)
    assert parsed == {"listings": []}
    mock_handlers.discover.assert_called_once_with(query="weather")


def test_handler_catches_exceptions(monkeypatch):
    mock_handlers = MagicMock()
    mock_handlers.discover.side_effect = RuntimeError("network down")
    monkeypatch.setattr(
        "agentnet_cli.hermes_plugin.handlers._get_handlers",
        lambda: mock_handlers,
    )
    result = json.loads(handlers.agentnet_discover({"query": "test"}))
    assert "error" in result
    assert "network down" in result["error"]


def test_handler_uses_env_token(monkeypatch):
    monkeypatch.setenv("AGENTNET_TOKEN", "env-token-123")
    monkeypatch.setattr("agentnet_cli.hermes_plugin.handlers.load_config", lambda: None)
    with patch("agentnet_cli.hermes_plugin.handlers.ToolHandlers") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.discover.return_value = {"ok": True}
        mock_cls.return_value = mock_instance
        result = json.loads(handlers.agentnet_discover({"query": "test"}))
        mock_cls.assert_called_once_with(
            platform_url="https://app.agentnet.market",
            api_token="env-token-123",
            agent_id="",
        )
        assert result == {"ok": True}


def test_handler_kwargs_accepted():
    for name in dir(handlers):
        if name.startswith("agentnet_"):
            fn = getattr(handlers, name)
            sig = inspect.signature(fn)
            params = list(sig.parameters.values())
            assert any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params), (
                f"{name} must accept **kwargs"
            )


def test_register_tools():
    ctx = MagicMock()
    register(ctx)
    tool_names = [c.kwargs["name"] for c in ctx.register_tool.call_args_list]
    assert len(tool_names) == 8
    assert "agentnet_discover" in tool_names
    assert "agentnet_wallet_topup" in tool_names
    for c in ctx.register_tool.call_args_list:
        assert c.kwargs["toolset"] == "agentnet"
        assert "schema" in c.kwargs
        assert "handler" in c.kwargs


def test_register_skill():
    ctx = MagicMock()
    register(ctx)
    ctx.register_skill.assert_called_once()
    skill_name, skill_path = ctx.register_skill.call_args.args
    assert skill_name == "agentnet"
    assert Path(skill_path).name == "SKILL.md"


def test_plugin_yaml_exists():
    from agentnet_cli.hermes_plugin import _PLUGIN_DIR

    plugin_yaml = _PLUGIN_DIR / "plugin.yaml"
    assert plugin_yaml.exists()

    import yaml

    data = yaml.safe_load(plugin_yaml.read_text())
    assert data["name"] == "agentnet"
    assert len(data["provides_tools"]) == 8


def test_skill_md_exists():
    from agentnet_cli.hermes_plugin import _PLUGIN_DIR

    skill_md = _PLUGIN_DIR / "skills" / "agentnet" / "SKILL.md"
    assert skill_md.exists()
    content = skill_md.read_text()
    assert "agentnet_discover" in content
    assert "Agent-net" in content


def test_entry_point_importable():
    import agentnet_cli.hermes_plugin as hp

    assert callable(hp.register)

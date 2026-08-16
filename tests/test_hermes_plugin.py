import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentnet_cli.integrations.hermes import handlers, register
from agentnet_cli.integrations.hermes.schemas import SCHEMAS


def test_schemas_only_search():
    assert [s["name"] for s in SCHEMAS] == ["agentnet_search"]


def test_schemas_use_parameters_not_input_schema():
    for schema in SCHEMAS:
        assert "parameters" in schema, f"{schema['name']} missing 'parameters'"
        assert "inputSchema" not in schema, f"{schema['name']} should not have 'inputSchema'"
        assert "description" in schema
        assert "name" in schema


def test_handler_no_token(monkeypatch):
    monkeypatch.delenv("AGENTNET_TOKEN", raising=False)
    monkeypatch.setattr(
        "agentnet_cli.integrations.hermes.handlers.get_credentials",
        lambda: None,
    )
    result = json.loads(handlers.agentnet_search({"query": "test"}))
    assert "error" in result
    assert "setup" in result["error"].lower()


def test_handler_returns_json(monkeypatch):
    mock_actions = MagicMock()
    mock_actions.search.return_value = {"results": []}
    monkeypatch.setattr(
        "agentnet_cli.integrations.hermes.handlers._get_actions",
        lambda: mock_actions,
    )
    result = handlers.agentnet_search({"query": "weather"})
    parsed = json.loads(result)
    assert parsed == {"results": []}
    mock_actions.search.assert_called_once_with(query="weather")


def test_handler_catches_exceptions(monkeypatch):
    mock_actions = MagicMock()
    mock_actions.search.side_effect = RuntimeError("network down")
    monkeypatch.setattr(
        "agentnet_cli.integrations.hermes.handlers._get_actions",
        lambda: mock_actions,
    )
    result = json.loads(handlers.agentnet_search({"query": "test"}))
    assert "error" in result
    assert "network down" in result["error"]


def test_handler_uses_env_token(monkeypatch):
    monkeypatch.setenv("AGENTNET_TOKEN", "env-token-123")
    with (
        patch(
            "agentnet_cli.integrations.hermes.handlers.get_credentials",
            return_value=("env-token-123", "https://app.agentnet.market"),
        ),
        patch(
            "agentnet_cli.integrations.hermes.handlers.make_platform_client",
            return_value=MagicMock(),
        ),
        patch("agentnet_cli.integrations.hermes.handlers.ToolActions") as mock_cls,
    ):
        mock_instance = MagicMock()
        mock_instance.search.return_value = {"ok": True}
        mock_cls.return_value = mock_instance
        result = json.loads(handlers.agentnet_search({"query": "test"}))
        mock_cls.assert_called_once_with(
            platform_url="https://app.agentnet.market",
            api_token="env-token-123",
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
    assert tool_names == ["agentnet_search"]
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
    from agentnet_cli.integrations.hermes import _PLUGIN_DIR

    yaml_path = _PLUGIN_DIR / "plugin.yaml"
    assert yaml_path.is_file()
    text = yaml_path.read_text(encoding="utf-8")
    assert "agentnet_search" in text
    assert "agentnet_discover" not in text

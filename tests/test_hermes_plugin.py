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


# --- Handler tests ---

import inspect
import json
from unittest.mock import MagicMock, patch

from agentnet_cli.hermes_plugin import handlers


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
            assert any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in params
            ), f"{name} must accept **kwargs"

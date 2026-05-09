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

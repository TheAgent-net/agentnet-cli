import json
from pathlib import Path

from agentnet_cli.connectors.composio_mcp import (
    COMPOSIO_MCP_URL,
    COMPOSIO_SERVER_NAME,
    composio_enabled,
    composio_http_entry,
    composio_owned,
    merge_json_file,
    merge_mapping,
    stamp,
    unmerge_json_file,
    unmerge_mapping,
)


def test_http_entry_matches_official_plugin():
    assert composio_http_entry() == {"url": COMPOSIO_MCP_URL}
    assert COMPOSIO_SERVER_NAME == "composio"
    assert COMPOSIO_MCP_URL == "https://connect.composio.dev/mcp"


def test_merge_mapping_adds_sibling_key():
    servers = {"agentnet": {"command": "agentnet", "args": ["mcp-serve"]}}
    assert merge_mapping(servers) is True
    assert servers["agentnet"]["command"] == "agentnet"
    assert servers["composio"] == {"url": COMPOSIO_MCP_URL}


def test_merge_mapping_skips_existing():
    existing = {"url": "https://example.invalid/mcp"}
    servers = {"composio": existing}
    assert merge_mapping(servers) is False
    assert servers["composio"] is existing


def test_merge_mapping_disabled(monkeypatch):
    monkeypatch.setenv("AGENTNET_COMPOSIO_MCP", "0")
    assert composio_enabled() is False
    servers: dict = {}
    assert merge_mapping(servers) is False
    assert servers == {}


def test_unmerge_only_when_owned():
    servers = {"composio": {"url": COMPOSIO_MCP_URL}, "agentnet": {}}
    unmerge_mapping(servers, owned=False)
    assert "composio" in servers
    unmerge_mapping(servers, owned=True)
    assert "composio" not in servers
    assert "agentnet" in servers


def test_stamp_and_owned():
    entry = stamp({"scope": "global"}, owned=True, file="/tmp/mcp.json")
    assert composio_owned(entry) is True
    assert entry["composio"]["file"] == "/tmp/mcp.json"
    assert composio_owned({}) is False
    assert composio_owned(None) is False
    assert composio_owned({"composio": {"owned": False}}) is False


def test_merge_json_file_creates_and_unmerges(tmp_path: Path):
    path = tmp_path / "mcp.json"
    assert merge_json_file(path, servers_key="mcpServers") is True
    data = json.loads(path.read_text())
    assert data["mcpServers"]["composio"]["url"] == COMPOSIO_MCP_URL

    unmerge_json_file(path, servers_key="mcpServers", owned=True)
    data = json.loads(path.read_text())
    assert "composio" not in data["mcpServers"]


def test_merge_json_file_preserves_malformed(tmp_path: Path):
    path = tmp_path / "mcp.json"
    path.write_text("{not json")
    assert merge_json_file(path, servers_key="mcpServers") is False
    assert path.read_text() == "{not json"

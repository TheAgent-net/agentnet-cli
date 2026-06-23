import json

import tomllib
import pytest

from agentnet_cli.connectors import search_wrap
from agentnet_cli.infra.paths import AgentName


@pytest.fixture(autouse=True)
def _agentnet_bin(monkeypatch):
    # Deterministic proxy command regardless of whether 'agentnet' is on PATH.
    monkeypatch.setattr("agentnet_cli.connectors.search_wrap.shutil.which", lambda _: "/usr/bin/agentnet")


def _cursor_mcp(fake_home, servers):
    root = fake_home / ".cursor"
    root.mkdir(parents=True)
    path = root / "mcp.json"
    path.write_text(json.dumps({"mcpServers": servers}, indent=2) + "\n")
    return path


def _claude_json(fake_home, servers):
    path = fake_home / ".claude.json"
    path.write_text(json.dumps({"numStartups": 3, "mcpServers": servers}, indent=2) + "\n")
    return path


def _codex_toml(fake_home, servers):
    import tomli_w

    root = fake_home / ".codex"
    root.mkdir(parents=True)
    path = root / "config.toml"
    path.write_text(tomli_w.dumps({"mcp_servers": servers}))
    return path


# -- Cursor (JSON) --


def test_cursor_wrap_unwrap_roundtrip(fake_home):
    original = {"exa": {"url": "https://mcp.exa.ai/mcp"}}
    path = _cursor_mcp(fake_home, original)
    before = path.read_text()

    changed, name = search_wrap.wrap(AgentName.CURSOR, "exa")
    assert changed and name == "exa"
    wrapped = json.loads(path.read_text())["mcpServers"]["exa"]
    assert wrapped["args"] == ["mcp-proxy", "--upstream", "exa"]

    changed, name = search_wrap.unwrap(AgentName.CURSOR)
    assert changed and name == "exa"
    assert path.read_text() == before  # byte-for-byte restore


def test_cursor_detects_exa_by_url_even_if_named_differently(fake_home):
    _cursor_mcp(fake_home, {"search": {"url": "https://mcp.exa.ai/mcp"}})
    changed, name = search_wrap.wrap(AgentName.CURSOR, "exa")
    assert changed and name == "search"


# -- Claude (JSON, ~/.claude.json) --


def test_claude_wrap_unwrap_roundtrip(fake_home):
    path = _claude_json(fake_home, {"exa": {"url": "https://mcp.exa.ai/mcp"}})
    before = path.read_text()

    changed, _ = search_wrap.wrap(AgentName.CLAUDE, "exa")
    assert changed
    assert "mcp-proxy" in json.dumps(json.loads(path.read_text())["mcpServers"]["exa"])

    changed, _ = search_wrap.unwrap(AgentName.CLAUDE)
    assert changed
    assert path.read_text() == before


# -- Codex (TOML) --


def test_codex_wrap_unwrap_roundtrip(fake_home):
    path = _codex_toml(fake_home, {"exa": {"url": "https://mcp.exa.ai/mcp"}})
    before = path.read_text()

    changed, name = search_wrap.wrap(AgentName.CODEX, "exa")
    assert changed and name == "exa"
    wrapped = tomllib.loads(path.read_text())["mcp_servers"]["exa"]
    assert wrapped["args"] == ["mcp-proxy", "--upstream", "exa"]

    changed, _ = search_wrap.unwrap(AgentName.CODEX)
    assert changed
    assert path.read_text() == before


# -- edge cases --


def test_wrap_no_entry_present_is_noop(fake_home):
    _cursor_mcp(fake_home, {"other": {"url": "https://example.com"}})
    changed, msg = search_wrap.wrap(AgentName.CURSOR, "exa")
    assert not changed
    assert "no exa" in msg.lower()


def test_wrap_idempotent_when_already_wrapped(fake_home):
    path = _cursor_mcp(fake_home, {"exa": {"url": "https://mcp.exa.ai/mcp"}})
    search_wrap.wrap(AgentName.CURSOR, "exa")
    snapshot = path.read_text()
    changed, msg = search_wrap.wrap(AgentName.CURSOR, "exa")
    assert not changed
    assert "already wrapped" in msg
    assert path.read_text() == snapshot  # second wrap changed nothing


def test_unwrap_without_stash_is_noop(fake_home):
    _cursor_mcp(fake_home, {"exa": {"url": "https://mcp.exa.ai/mcp"}})
    changed, msg = search_wrap.unwrap(AgentName.CURSOR)
    assert not changed
    assert "nothing wrapped" in msg


def test_wrap_missing_config_is_noop(fake_home):
    changed, msg = search_wrap.wrap(AgentName.CURSOR, "exa")
    assert not changed
    assert "no config" in msg.lower()


def test_manual_block_contains_proxy_command():
    block = json.loads(search_wrap.manual_block("exa"))
    assert block["exa"]["args"] == ["mcp-proxy", "--upstream", "exa"]

import json
from unittest.mock import MagicMock

import pytest

from agentnet_cli.connectors import opencode_hook
from agentnet_cli.connectors.opencode import OpenCodeConnector, _load_config, _strip_jsonc
from agentnet_cli.infra.package_paths import bundled_opencode_plugin
from agentnet_cli.infra.paths import AgentName, agent_config_root

_FAKE_BIN = "/usr/local/bin/agentnet"


@pytest.fixture
def oc_home(tmp_path, monkeypatch):
    """opencode config dir under a temp XDG_CONFIG_HOME, with a deterministic agentnet path."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(
        "agentnet_cli.connectors.opencode_hook.shutil.which", lambda n: _FAKE_BIN
    )
    monkeypatch.setattr(
        "agentnet_cli.connectors.opencode.shutil.which",
        lambda n: _FAKE_BIN if n == "agentnet" else None,
    )
    return tmp_path / "opencode"


# ── bundled asset ─────────────────────────────────────────────────────────────
def test_bundled_plugin_ships_with_placeholder_and_hooks():
    src = bundled_opencode_plugin() / "agentnet.js"
    assert src.is_file()
    text = src.read_text()
    assert "__AGENTNET_BIN__" in text  # resolved at install time
    for hook in ("chat.message", "experimental.chat.system.transform", "session.idle"):
        assert hook in text
    assert "opencode-hook" in text  # shells out to the shared CLI


# ── JSONC tolerance ───────────────────────────────────────────────────────────
def test_strip_jsonc_preserves_urls_and_strips_comments():
    src = """{
      // a line comment
      "$schema": "https://opencode.ai/config.json", /* block */
      "mcp": {},
    }"""
    data = json.loads(_strip_jsonc(src))
    assert data["$schema"] == "https://opencode.ai/config.json"  # // in the URL survived
    assert data["mcp"] == {}  # trailing comma removed


def test_load_config_returns_none_on_unparseable(tmp_path):
    p = tmp_path / "opencode.jsonc"
    p.write_text("{ this is : not json ///")
    assert _load_config(p) is None  # signals "don't clobber"
    assert _load_config(tmp_path / "missing.json") == {}


# ── plugin install / uninstall ────────────────────────────────────────────────
def test_install_resolves_bin_and_is_idempotent(oc_home):
    changed, path = opencode_hook.install()
    assert changed
    assert path == oc_home / "plugins" / "agentnet.js"
    body = path.read_text()
    assert "__AGENTNET_BIN__" not in body  # placeholder resolved
    assert _FAKE_BIN in body

    assert opencode_hook.install()[0] is False  # idempotent

    changed3, _ = opencode_hook.uninstall()
    assert changed3
    assert not path.exists()


# ── connect / disconnect ──────────────────────────────────────────────────────
def test_connect_installs_plugin_and_registers_mcp(oc_home):
    result = OpenCodeConnector().connect({})
    assert result.success
    plugin = oc_home / "plugins" / "agentnet.js"
    assert plugin.exists() and plugin in result.files_created

    config = json.loads((oc_home / "opencode.json").read_text())
    srv = config["mcp"]["agentnet"]
    assert srv["type"] == "local"
    assert srv["command"] == [_FAKE_BIN, "mcp-serve"]
    assert srv["enabled"] is True
    assert result.mcp_entry["server_name"] == "agentnet"


def test_connect_preserves_existing_jsonc(oc_home):
    oc_home.mkdir(parents=True)
    (oc_home / "opencode.jsonc").write_text(
        '{\n  // my config\n  "$schema": "https://opencode.ai/config.json"\n}\n'
    )
    OpenCodeConnector().connect({})
    config = _load_config(oc_home / "opencode.jsonc")
    assert config["$schema"] == "https://opencode.ai/config.json"  # kept
    assert "agentnet" in config["mcp"]  # ours added into the existing .jsonc


def test_connect_skips_mcp_when_config_unparseable_but_still_installs_plugin(oc_home):
    oc_home.mkdir(parents=True)
    garbage = '{ broken /// not json'
    (oc_home / "opencode.jsonc").write_text(garbage)
    result = OpenCodeConnector().connect({})
    assert result.success  # plugin is the core value
    assert (oc_home / "plugins" / "agentnet.js").exists()
    assert result.mcp_entry == {}  # MCP skipped
    assert (oc_home / "opencode.jsonc").read_text() == garbage  # never clobbered


def test_disconnect_removes_plugin_and_mcp(oc_home):
    result = OpenCodeConnector().connect({})
    manifest = {
        "files_created": [str(p) for p in result.files_created],
        "mcp_registered": result.mcp_entry,
    }
    assert OpenCodeConnector().disconnect(manifest) is True
    assert not (oc_home / "plugins" / "agentnet.js").exists()
    config = json.loads((oc_home / "opencode.json").read_text())
    assert "mcp" not in config or "agentnet" not in config.get("mcp", {})


# ── detect ────────────────────────────────────────────────────────────────────
def test_detect_true_via_binary(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))  # no config dir
    monkeypatch.setattr("agentnet_cli.connectors.opencode.shutil.which", lambda n: "/usr/bin/opencode")
    assert OpenCodeConnector().detect().detected


def test_detect_true_via_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("agentnet_cli.connectors.opencode.shutil.which", lambda n: None)
    root = agent_config_root(AgentName.OPENCODE)
    root.mkdir(parents=True)
    (root / "opencode.jsonc").write_text("{}")
    assert OpenCodeConnector().detect().detected


def test_detect_false_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("agentnet_cli.connectors.opencode.shutil.which", lambda n: None)
    assert not OpenCodeConnector().detect().detected


# ── the opencode gate prefers a fast CLI when available, native opencode when alone ──
def test_classify_opencode_prefers_fast_gate_when_available(monkeypatch):
    # opencode's own gate has ~15-25s startup, so with claude installed the gate uses claude (~5s).
    from agentnet_cli.tools.skillfire import classifier

    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd[0])
        return MagicMock(returncode=0, stdout='{"skills":[{"name":"A","why":"w"}]}')

    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.shutil.which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.subprocess.run", fake_run)
    relevant, actual = classifier.classify("q", "- A: x", timeout=10, backend="opencode")
    assert relevant == [{"name": "A", "why": "w"}]
    assert actual == "claude"  # fast gate preferred; harness stays "opencode" upstream
    assert calls[0].endswith("claude")
    assert not any("opencode" in c for c in calls)  # slow native gate not used when claude exists


def test_classify_opencode_gates_natively_when_alone(monkeypatch):
    # No claude/cursor -> the pure-opencode user still gets a gate, natively on their own model.
    from agentnet_cli.tools.skillfire import classifier

    calls = []

    def fake_which(n):
        return "/usr/bin/" + n if n == "opencode" else None

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return MagicMock(returncode=0, stdout='{"skills":[{"name":"A","why":"w"}]}')

    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.shutil.which", fake_which)
    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.subprocess.run", fake_run)
    _relevant, actual = classifier.classify("q", "- A: x", timeout=10, backend="opencode")
    assert actual == "opencode"  # native fallback
    assert calls[0][0].endswith("opencode") and "--pure" in calls[0]

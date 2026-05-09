import json
from pathlib import Path
from agentnet_cli.agents.vscode import VSCodeConnector


def _setup_vscode(home: Path) -> None:
    d = home / ".vscode" / "extensions"
    d.mkdir(parents=True)


def test_detect_by_extensions_dir(fake_home):
    _setup_vscode(fake_home)
    r = VSCodeConnector().detect()
    assert r.detected is True


def test_detect_not_found(fake_home):
    r = VSCodeConnector().detect()
    assert r.detected is False


def test_connect_creates_instructions(fake_home, monkeypatch):
    _setup_vscode(fake_home)
    user_dir = fake_home / "Library" / "Application Support" / "Code" / "User"
    user_dir.mkdir(parents=True)
    monkeypatch.setattr("agentnet_cli.agents.vscode._vscode_user_dirs", lambda: [user_dir])
    result = VSCodeConnector().connect({"api_token": "t", "platform_url": "https://x"})
    assert result.success
    instructions = user_dir / ".github" / "copilot-instructions.md"
    assert instructions.exists()
    assert "agentnet_discover" in instructions.read_text()


def test_connect_writes_mcp_json(fake_home, monkeypatch):
    _setup_vscode(fake_home)
    user_dir = fake_home / "Library" / "Application Support" / "Code" / "User"
    user_dir.mkdir(parents=True)
    monkeypatch.setattr("agentnet_cli.agents.vscode._vscode_user_dirs", lambda: [user_dir])
    VSCodeConnector().connect({"api_token": "t", "platform_url": "https://x"})
    mcp_path = user_dir / "mcp.json"
    assert mcp_path.exists()
    data = json.loads(mcp_path.read_text())
    assert "agentnet" in data["servers"]


def test_disconnect_removes_files(fake_home, monkeypatch):
    _setup_vscode(fake_home)
    user_dir = fake_home / "Library" / "Application Support" / "Code" / "User"
    user_dir.mkdir(parents=True)
    monkeypatch.setattr("agentnet_cli.agents.vscode._vscode_user_dirs", lambda: [user_dir])
    result = VSCodeConnector().connect({"api_token": "t", "platform_url": "https://x"})
    manifest_entry = {
        "files_created": [str(p) for p in result.files_created],
        "mcp_registered": result.mcp_entry,
    }
    ok = VSCodeConnector().disconnect(manifest_entry)
    assert ok
    instructions = user_dir / ".github" / "copilot-instructions.md"
    assert not instructions.exists()

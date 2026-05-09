from agentnet_cli.config import load_agent_paths, load_config, remove_agent_path, save_agent_path, save_config


def test_save_and_load_roundtrip(fake_home):
    data = {
        "platform_url": "https://app.agentnet.market",
        "api_token": "agn_test123",
        "org_id": "org_abc",
        "wallet_id": "wal_xyz",
    }
    save_config(data)
    loaded = load_config()
    assert loaded == data


def test_load_returns_none_when_missing(fake_home):
    assert load_config() is None


def test_config_file_has_restricted_permissions(fake_home):
    import stat
    save_config({"api_token": "secret"})
    from agentnet_cli.paths import agentnet_home
    config_path = agentnet_home() / "config.json"
    mode = config_path.stat().st_mode
    assert not (mode & stat.S_IROTH)
    assert not (mode & stat.S_IWOTH)


def test_agent_paths_roundtrip(fake_home):
    assert load_agent_paths() == {}
    save_agent_path("claude", "/opt/claude/bin/claude")
    assert load_agent_paths() == {"claude": "/opt/claude/bin/claude"}
    save_agent_path("cursor", "/usr/local/bin/cursor")
    paths = load_agent_paths()
    assert paths["claude"] == "/opt/claude/bin/claude"
    assert paths["cursor"] == "/usr/local/bin/cursor"


def test_remove_agent_path(fake_home):
    save_agent_path("claude", "/opt/claude")
    assert remove_agent_path("claude") is True
    assert "claude" not in load_agent_paths()


def test_remove_nonexistent_path(fake_home):
    assert remove_agent_path("hermes") is False


def test_load_corrupted_config(fake_home):
    """Corrupted JSON in config.json returns None instead of crashing (H-2 fix)."""
    from agentnet_cli.paths import agentnet_home

    config_path = agentnet_home() / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{broken json @@")
    assert load_config() is None


def test_atomic_write_creates_dirs(fake_home):
    """save_config creates parent dirs when they don't exist."""
    from agentnet_cli.paths import agentnet_home

    # Ensure the .agentnet dir doesn't exist yet
    home = agentnet_home()
    assert not home.exists()
    save_config({"api_token": "x"})
    assert home.exists()
    assert load_config() == {"api_token": "x"}


def test_atomic_write_restricted_permissions(fake_home):
    """Config file gets 0600 permissions (owner read/write only)."""
    import os
    import stat as stat_mod
    from agentnet_cli.paths import agentnet_home

    save_config({"api_token": "secret"})
    config_path = agentnet_home() / "config.json"
    if os.name != "nt":
        mode = config_path.stat().st_mode
        assert mode & stat_mod.S_IRUSR  # owner can read
        assert mode & stat_mod.S_IWUSR  # owner can write
        assert not (mode & stat_mod.S_IRGRP)  # group cannot read
        assert not (mode & stat_mod.S_IROTH)  # other cannot read

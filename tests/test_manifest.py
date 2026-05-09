from pathlib import Path
from agentnet_cli.manifest import load_manifest, save_manifest, record_connection, remove_connection


def test_empty_manifest_when_missing(fake_home):
    m = load_manifest()
    assert m == {"connections": {}}


def test_record_connection(fake_home):
    record_connection("claude", files_created=[Path("/a/b.md")], files_modified=[], mcp_entry={"scope": "user"})
    m = load_manifest()
    assert "claude" in m["connections"]
    assert m["connections"]["claude"]["files_created"] == ["/a/b.md"]


def test_remove_connection(fake_home):
    record_connection("claude", files_created=[], files_modified=[], mcp_entry={})
    remove_connection("claude")
    m = load_manifest()
    assert "claude" not in m["connections"]


def test_load_corrupted_manifest(fake_home):
    """Corrupted manifest.json returns empty connections dict."""
    from agentnet_cli.paths import agentnet_home

    manifest_path = agentnet_home() / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("not valid json {{{")
    m = load_manifest()
    assert m == {"connections": {}}


def test_manifest_has_restricted_permissions(fake_home):
    """Manifest file gets 0600 permissions after save (H-4 fix)."""
    import os
    import stat as stat_mod
    from agentnet_cli.paths import agentnet_home

    record_connection("claude", files_created=[], files_modified=[], mcp_entry={})
    manifest_path = agentnet_home() / "manifest.json"
    if os.name != "nt":
        mode = manifest_path.stat().st_mode
        assert mode & stat_mod.S_IRUSR
        assert mode & stat_mod.S_IWUSR
        assert not (mode & stat_mod.S_IRGRP)
        assert not (mode & stat_mod.S_IROTH)


def test_record_connection_stores_cli_version(fake_home):
    """record_connection stores cli_version in the manifest entry."""
    from agentnet_cli import __version__

    record_connection("hermes", files_created=[], files_modified=[], mcp_entry={})
    m = load_manifest()
    assert m["connections"]["hermes"]["cli_version"] == __version__

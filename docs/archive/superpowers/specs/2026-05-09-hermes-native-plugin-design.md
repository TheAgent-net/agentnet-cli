# Hermes Native Plugin Refactor

**Date:** 2026-05-09
**Status:** Approved
**Scope:** Replace YAML-surgery-based Hermes connector with native Hermes plugin system

## Problem

The current `HermesConnector.connect()` performs 6 steps of direct YAML mutation on `~/.hermes/config.yaml`:

1. Inject `mcp_servers.agentnet` entry (MCP subprocess)
2. Inject `mcp-agentnet` into `platform_toolsets` for cli and telegram
3. Set `agent.tool_use_enforcement: true`
4. Clean up legacy `mcp.servers` entries
5. Drop `skills/agentnet/SKILL.md` into the Hermes root
6. Copy `~/.agentnet/config.json` for Docker compatibility

This is fragile (can break other config entries), hard to maintain (tracks Hermes config format changes), and reimplements what Hermes's native plugin system already provides.

## Solution

Replace the YAML surgery with a **thin Hermes plugin** that lives inside the `agentnet_cli` package and uses Hermes's `register(ctx)` API for tool registration, skill bundling, and lifecycle hooks.

## Architecture

### Package layout

```
src/agentnet_cli/hermes_plugin/
    __init__.py       # register(ctx) entry point
    schemas.py        # 8 tool schemas in Hermes format
    handlers.py       # Tool handlers wrapping PlatformClient
    plugin.yaml       # Hermes plugin manifest
    skills/
        agentnet/
            SKILL.md  # Bundled skill file
```

### Two install paths, same result

| Path | How | What happens |
|------|-----|-------------|
| **pip entry point** | `pip install agentnet-cli` | Hermes auto-discovers plugin via `hermes_agent.plugins` entry point. User enables with `hermes plugins enable agentnet`. |
| **agentnet CLI** | `agentnet connect hermes` | CLI copies plugin files to `~/.hermes/plugins/agentnet/` and auto-enables by adding `"agentnet"` to `plugins.enabled` in `config.yaml`. |

Both paths result in the same plugin code running inside Hermes.

### pyproject.toml entry point

```toml
[project.entry-points."hermes_agent.plugins"]
agentnet = "agentnet_cli.hermes_plugin"
```

### plugin.yaml

```yaml
name: agentnet
version: "0.1.0"
description: Agent-net marketplace - discover, hire, and pay AI agents
author: Agent-net
requires_env:
  - name: AGENTNET_TOKEN
    description: "API token (run 'agentnet register' to get one)"
    secret: true
provides_tools:
  - agentnet_discover
  - agentnet_discover_agents
  - agentnet_get_agent
  - agentnet_use_agent
  - agentnet_continue_session
  - agentnet_settle_session
  - agentnet_wallet
  - agentnet_wallet_topup
```

`requires_env` is a soft gate. The plugin loads regardless; handlers return error JSON if no token is available.

## Tool Handlers

### Auth flow

Token resolution order (matches existing MCP server behavior):
1. `AGENTNET_TOKEN` environment variable
2. `api_token` from `~/.agentnet/config.json` (via `load_config()`)

If neither is available, handlers return `{"error": "Not registered. Run 'agentnet register' first."}`.

### Handler architecture

`handlers.py` creates a `ToolHandlers` instance per invocation (not cached). This ensures token/config changes are picked up without restarting Hermes. The overhead is negligible since these are network-bound API calls.

```python
def _get_handlers():
    token = os.environ.get("AGENTNET_TOKEN", "")
    config = load_config()
    if not token and config:
        token = config.get("api_token", "")
    platform_url = (config or {}).get("platform_url", "https://app.agentnet.market")
    agent_id = (config or {}).get("agent_id", "")
    if not token:
        return None
    return ToolHandlers(
        platform_url=platform_url,
        api_token=token,
        agent_id=agent_id,
    )
```

Each handler follows the Hermes contract: `def handler(args: dict, **kwargs) -> str`, returns JSON string, never raises.

```python
def agentnet_discover(args, **kwargs):
    try:
        h = _get_handlers()
        if h is None:
            return json.dumps({"error": "Not registered. Run 'agentnet register' first."})
        return json.dumps(h.discover(**args))
    except Exception as e:
        return json.dumps({"error": str(e)})
```

### Registration

`__init__.py` `register(ctx)`:
1. Calls `ctx.register_tool()` for each of the 8 tools (schema from `schemas.py`, handler from `handlers.py`)
2. Calls `ctx.register_skill()` for the bundled `skills/agentnet/SKILL.md`
3. All tools use toolset `"agentnet"` for grouping

## Schemas

Tool schemas are defined natively in Hermes format in `schemas.py`. The content matches the existing MCP `TOOL_DEFINITIONS` from `mcp/server.py` but uses the `parameters` key instead of `inputSchema`. This avoids a conversion layer and is straightforward to maintain (~80 lines of dict literals).

## Refactored HermesConnector

### detect()

Unchanged. Checks for `~/.hermes/config.yaml` existence.

### connect(platform_config)

New behavior (replaces 6-step YAML surgery):

1. **Copy plugin directory**: Copy the `hermes_plugin` package contents (plugin.yaml, __init__.py, schemas.py, handlers.py, skills/) into `~/.hermes/plugins/agentnet/`. Uses `pathlib` relative to `agentnet_cli.hermes_plugin.__file__` to locate source files in the installed package. Files are copied (not symlinked) so the plugin survives if agentnet-cli is later uninstalled.

2. **Auto-enable**: Read `~/.hermes/config.yaml`, ensure `plugins.enabled` list contains `"agentnet"`. This is the only YAML mutation — a single list append. If `plugins` or `plugins.enabled` doesn't exist, create it.

3. **Return result**: `ConnectionResult` with `files_created` listing the copied plugin files and `mcp_entry` containing `{"scope": "plugin", "plugin_dir": str(plugin_dir)}`.

### disconnect(connection_manifest)

New behavior:

1. Remove `~/.hermes/plugins/agentnet/` directory (via `shutil.rmtree`)
2. Remove `"agentnet"` from `plugins.enabled` in `config.yaml`

### What's removed

- `mcp_servers` injection
- `platform_toolsets` injection
- `tool_use_enforcement` hack
- Legacy `mcp.servers` cleanup
- Config backup/restore
- Docker config.json copy
- `_SKILL_CONTENT` constant (moved to `skills/agentnet/SKILL.md`)
- `_MCP_SERVER_NAME` / `_MCP_TOOLSET_NAME` constants

## Manifest Impact

`record_connection()` records `mcp_entry` as:
```json
{
  "scope": "plugin",
  "plugin_dir": "~/.hermes/plugins/agentnet/"
}
```

Instead of the current MCP server file reference.

## Updater Impact

`refresh_stale_connections()` continues to work. When CLI version changes, it re-runs `connect()`, which overwrites the plugin files with the new version. This is how plugin updates propagate to Hermes.

## Existing MCP Server

`mcp/server.py` and `mcp/tools.py` are **not modified**. They continue to serve Claude, Cursor, Copilot, VS Code, and Codex via the MCP protocol. Only Hermes moves to the native plugin path.

## Test Plan

### Updated tests (test_hermes.py)

- `test_detect` — unchanged
- `test_connect_creates_plugin_dir` — verify `~/.hermes/plugins/agentnet/` created with plugin.yaml, __init__.py, schemas.py, handlers.py, skills/agentnet/SKILL.md
- `test_connect_enables_plugin` — verify `plugins.enabled` in config.yaml contains `"agentnet"`
- `test_connect_preserves_existing_config` — verify other config.yaml keys untouched
- `test_disconnect_removes_plugin_dir` — verify `~/.hermes/plugins/agentnet/` removed
- `test_disconnect_disables_plugin` — verify `"agentnet"` removed from `plugins.enabled`

### New tests (test_hermes_plugin.py)

- `test_register_tools` — mock `ctx`, call `register(ctx)`, verify 8 `register_tool` calls with correct names
- `test_register_skill` — verify `register_skill` called with skill file
- `test_handler_returns_json` — verify each handler returns valid JSON string
- `test_handler_no_token` — verify handler returns error JSON when no config/env var
- `test_handler_api_error` — verify handler catches exceptions and returns error JSON

### Removed tests

- `test_connect_sets_file_permissions` — no longer writing secrets to config.yaml
- `test_connect_sort_keys_false` — no longer doing bulk YAML key insertion

## Migration

Users who previously ran `agentnet connect hermes` (old YAML surgery) and then upgrade agentnet-cli will get the new behavior on next `agentnet connect hermes` or via `refresh_stale_connections()`.

### Legacy cleanup

`connect()` will perform a one-time cleanup of old YAML surgery artifacts:
- Remove `mcp_servers.agentnet` from config.yaml
- Remove `mcp-agentnet` from `platform_toolsets` entries
- Remove `skills/agentnet/` from `~/.hermes/skills/` (the old location; new location is inside the plugin dir)

This prevents Hermes from loading the same tools twice (once via MCP server, once via plugin). The cleanup runs only if these entries exist, and is idempotent.

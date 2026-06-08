# OpenClaw Native Plugin Refactor

## Goal

Replace the current OpenClaw connector's manual file surgery (writing `agentnet-gateway` into `~/.openclaw/openclaw.json`) with full delegation to OpenClaw's native plugin CLI commands (`openclaw plugins install/uninstall`). Create a dedicated `openclaw-plugin/` directory in the repo as a first-class native OpenClaw plugin, publishable to ClawHub.

## Architecture

The connector stops directly manipulating `openclaw.json`. Instead, it shells out to the `openclaw` CLI binary for all plugin lifecycle operations. The only file manipulation remaining is one-time legacy cleanup of the old `agentnet-gateway` entry from `openclaw.json`.

The plugin itself is a native OpenClaw plugin directory (`openclaw-plugin/`) with `openclaw.plugin.json` manifest, a minimal TypeScript entry point (tools are provided by the MCP server, not registered in-process), skills, and MCP server config. This is a separate directory from `claude-plugin/` — each agent gets its own native plugin tailored to its ecosystem.

The pattern mirrors the Claude connector: check binary → install plugin via CLI → legacy cleanup. Source resolution uses the same local-then-remote fallback: check for `openclaw-plugin/` in the repo root (development), fall back to `clawhub:agentnet` (published installs).

## Repository Changes

### New files

```
agentnet-cli/
└── openclaw-plugin/                       # Native OpenClaw plugin
    ├── openclaw.plugin.json               # Plugin manifest (id, contracts, skills, activation)
    ├── package.json                       # OpenClaw SDK metadata + ClawHub publishing
    ├── index.ts                           # Minimal entry point (no-op register — MCP handles tools)
    ├── skills/
    │   └── agentnet/
    │       └── SKILL.md                   # Marketplace skill (adapted for OpenClaw)
    └── .mcp.json                          # MCP server config (OpenClaw format)
```

### Modified files

- `src/agentnet_cli/agents/openclaw.py` — rewritten to use subprocess delegation
- `tests/test_openclaw.py` — rewritten for subprocess-based testing
- `tests/test_e2e.py` — add OpenClaw to `_setup_agents` and mock subprocess for connect/disconnect
- `CLAUDE.md` — update structure, patterns, test count

### Removed files

None — the old approach wrote into `~/.openclaw/openclaw.json` at runtime, not into repo files.

---

## Plugin Contents

### openclaw.plugin.json

Native OpenClaw manifest declaring the plugin identity, skills, tool contracts, and activation:

```json
{
  "id": "agentnet",
  "name": "AgentNet Marketplace",
  "version": "0.1.0",
  "description": "Discover, hire, and pay AI agents on the Agent-net marketplace",
  "skills": ["skills/agentnet"],
  "contracts": {
    "tools": [
      "agentnet__agentnet_discover",
      "agentnet__agentnet_discover_agents",
      "agentnet__agentnet_get_agent",
      "agentnet__agentnet_use_agent",
      "agentnet__agentnet_continue_session",
      "agentnet__agentnet_settle_session",
      "agentnet__agentnet_wallet",
      "agentnet__agentnet_wallet_topup"
    ]
  },
  "activation": {
    "onStartup": true
  },
  "configSchema": {
    "type": "object",
    "additionalProperties": false
  }
}
```

Tool names follow OpenClaw's `serverName__toolName` convention where the server name `agentnet` comes from the MCP server key in `.mcp.json`.

### package.json

Required for native plugin detection (`openclaw.extensions`) and ClawHub publishing:

```json
{
  "name": "@agentnet/openclaw-plugin",
  "version": "0.1.0",
  "description": "AgentNet marketplace plugin for OpenClaw",
  "type": "module",
  "license": "MIT",
  "author": {
    "name": "Agent-net",
    "url": "https://agentnet.market"
  },
  "repository": {
    "type": "git",
    "url": "https://github.com/TheAgent-net/agentnet-cli"
  },
  "openclaw": {
    "extensions": ["./index.ts"],
    "compat": {
      "pluginApi": ">=2026.3.24-beta.2"
    },
    "build": {
      "openclawVersion": "2026.3.24-beta.2"
    }
  }
}
```

### index.ts

Minimal TypeScript entry point. All tools are served by the MCP server — the entry point just satisfies OpenClaw's native plugin requirement:

```typescript
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

export default definePluginEntry({
  register(api) {
    api.logger.info("AgentNet marketplace plugin loaded");
  },
});
```

### .mcp.json

MCP server config using OpenClaw's format (`mcp.servers`, not Claude's `mcpServers`):

```json
{
  "mcp": {
    "servers": {
      "agentnet": {
        "command": "agentnet",
        "args": ["mcp-serve"]
      }
    }
  }
}
```

OpenClaw merges this into its embedded settings. The `agentnet` key becomes the server name prefix for tool naming (`agentnet__*`).

### skills/agentnet/SKILL.md

Same marketplace workflow content as the Claude plugin's SKILL.md (tool descriptions, workflow, guidelines). Adapted for OpenClaw:

- Frontmatter uses OpenClaw's skill format (no `allowed-tools` or `alwaysApply` — these are Claude-specific; OpenClaw uses the manifest's `contracts.tools` for tool ownership and `activation.onStartup` for always-on behavior)
- Tool names reference the `agentnet__` prefix convention
- Body content (workflow steps, tool parameters, guidelines) is identical

---

## Connector Rewrite (openclaw.py)

### Constants

```python
_CLAWHUB_PACKAGE = "clawhub:agentnet"
_PLUGIN_ID = "agentnet"
_SUBPROCESS_TIMEOUT = 120
```

### _find_plugin_source()

Resolves the plugin source — local repo path in development, ClawHub package for published installs:

```python
def _find_plugin_source() -> str:
    local = Path(__file__).resolve().parent.parent.parent.parent
    if (local / "openclaw-plugin" / "openclaw.plugin.json").exists():
        return str(local / "openclaw-plugin")
    return _CLAWHUB_PACKAGE
```

### detect()

Unchanged. Checks `~/.openclaw/openclaw.json` existence to determine if OpenClaw is installed on the system.

### connect()

1. Check `shutil.which("openclaw")` — if None, return `ConnectionResult(success=False, errors=["OpenClaw not found. Install it from https://docs.openclaw.ai"])`
2. Resolve plugin source via `_find_plugin_source()`
3. Run `openclaw plugins install <source>` via `subprocess.run(capture_output=True, timeout=120)`. Check return code; capture stderr on failure.
4. Run `_cleanup_legacy()` — remove old `agentnet-gateway` from `openclaw.json`
5. Return `ConnectionResult(success=True, mcp_entry={"scope": "plugin", "plugin_id": "agentnet"})`

### disconnect()

1. Check `shutil.which("openclaw")` — if None, return True (nothing to uninstall)
2. Run `openclaw plugins uninstall agentnet` via `subprocess.run(capture_output=True, timeout=120)`
3. Return True regardless of exit code

### _cleanup_legacy()

Removes artifacts from the old file-surgery approach:

1. Read `~/.openclaw/openclaw.json`
2. Remove `agentnet-gateway` from `plugins` dict if present
3. Write back if modified
4. Remove backup file `~/.agentnet/backups/openclaw/openclaw.json.bak` if it exists

All operations wrapped in try/except — legacy cleanup failures do not fail the overall connect.

---

## Testing

### test_openclaw.py (rewritten)

All tests mock `shutil.which` and `subprocess.run`:

- `test_detect_found` — create `~/.openclaw/openclaw.json`, assert detected
- `test_detect_not_found` — no config dir, assert not detected
- `test_connect_calls_plugin_install` — mock binary present, assert `openclaw plugins install` called with resolved source
- `test_connect_no_openclaw_binary` — `shutil.which` returns None, result has `success=False` with install instructions
- `test_connect_install_failure` — subprocess returns non-zero, verify error propagated
- `test_connect_cleans_legacy_plugin_entry` — create old `openclaw.json` with `agentnet-gateway`, connect, verify entry removed
- `test_connect_cleans_legacy_backup` — create old backup file, connect, verify removed
- `test_disconnect_calls_plugin_uninstall` — assert `openclaw plugins uninstall agentnet` called
- `test_disconnect_no_openclaw_binary` — returns True when binary missing

### test_e2e.py (updated)

Add OpenClaw to `_setup_agents()`:

```python
(home / ".openclaw").mkdir()
(home / ".openclaw" / "openclaw.json").write_text("{}")
```

The existing `connect --all` / `disconnect --all` tests already mock `shutil.which` and `subprocess.run` globally, so OpenClaw will be covered.

---

## Error Handling

- **No binary**: Return `ConnectionResult(success=False)` with install URL
- **Subprocess failures**: Non-zero exit from `openclaw plugins install` → capture stderr, include in `ConnectionResult.errors`
- **Already installed**: `openclaw plugins install` on an existing plugin updates it — idempotent, no special handling
- **Already uninstalled**: Non-zero from uninstall on missing plugin; `disconnect()` returns True anyway
- **Legacy cleanup failures**: Wrapped in try/except, do not fail overall connect
- **Version sync**: `openclaw.plugin.json` version and `package.json` version both `0.1.0`, bumped together manually

---

## ClawHub Publishing

Published via:

```bash
clawhub package publish ./openclaw-plugin --slug agentnet --name "AgentNet Marketplace"
```

This is a manual/CI step. Once published, users can install directly without our CLI:

```bash
openclaw plugins install clawhub:agentnet
```

The `_find_plugin_source()` function falls back to `clawhub:agentnet` when the local repo directory is not present (pip-installed package).

---

## Migration Path

Existing users who ran `agentnet connect openclaw` with the old connector have an `agentnet-gateway` entry in `~/.openclaw/openclaw.json`. The new `connect()` automatically cleans this up via `_cleanup_legacy()` after the plugin install. No separate migration command needed.

---

## No Plugin Hint

OpenClaw does not have a plugin hint protocol (no env var like Claude Code's `CLAUDECODE=1`, no stderr hint format). No hint code is added. If OpenClaw introduces one in the future, we can add support then.

---

## Out of Scope

- OpenClaw hooks (native plugins support `api.on()` hooks, but our MCP-based approach doesn't need them — the MCP server handles all tool execution)
- Publishing to ClawHub in CI (future — add to `publish.yml` when ready)
- Native tool registration via `api.registerTool()` (tools are served via MCP, not in-process TypeScript)

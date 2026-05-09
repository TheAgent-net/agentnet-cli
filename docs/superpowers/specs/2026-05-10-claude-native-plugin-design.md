# Claude Code Native Plugin Refactor

## Goal

Replace the current Claude Code connector's manual file surgery (writing to `~/.claude.json`, `~/.claude/skills/`, `~/.claude/settings.json`) with full delegation to Claude Code's native plugin CLI commands (`claude plugin marketplace add`, `claude plugin install/uninstall`). Bundle a proper Claude Code plugin and marketplace manifest in the existing agentnet-cli repo.

## Architecture

The connector stops touching Claude Code's internal files for plugin installation. Instead, it shells out to the `claude` CLI binary for all plugin lifecycle operations. The only file manipulation remaining is one-time legacy cleanup of standalone files from the old connector approach. The plugin itself is a directory in the repo (`claude-plugin/`) that Claude Code installs via its standard marketplace system.

This mirrors the Hermes connector pattern of using the target agent's native extension mechanism, but is simpler because Claude Code provides CLI commands for non-interactive plugin management — no file manipulation needed at all.

## Repository Changes

### New files

```
agentnet-cli/
├── marketplace.json                    # Claude Code marketplace catalog
├── claude-plugin/                      # the plugin directory
│   ├── .claude-plugin/
│   │   └── plugin.json                 # manifest: name, version, metadata
│   ├── skills/
│   │   └── agentnet/
│   │       └── SKILL.md                # skill with alwaysApply + allowed-tools
│   ├── agents/
│   │   └── marketplace.md              # subagent for marketplace-heavy tasks
│   ├── hooks/
│   │   └── hooks.json                  # SessionStart token check
│   └── .mcp.json                       # MCP server config
```

### Modified files

- `src/agentnet_cli/agents/claude.py` — rewritten to use subprocess delegation
- `src/agentnet_cli/main.py` — add plugin hint emission
- `tests/test_claude.py` — rewritten for subprocess-based testing

### Removed files

- `src/agentnet_cli/shims/claude/skill.md` — replaced by `claude-plugin/skills/agentnet/SKILL.md`

---

## Plugin Contents

### marketplace.json

Lives at repo root. Uses `relative-path` source to point at `claude-plugin/`:

```json
{
  "name": "agentnet-cli",
  "description": "Agent-net marketplace plugins",
  "plugins": [
    {
      "name": "agentnet",
      "description": "Discover, hire, and pay AI agents on the Agent-net marketplace",
      "source": {
        "source": "relative-path",
        "path": "./claude-plugin"
      }
    }
  ]
}
```

### plugin.json

```json
{
  "name": "agentnet",
  "version": "0.1.0",
  "description": "Discover, hire, and pay AI agents on the Agent-net marketplace",
  "author": {
    "name": "Agent-net",
    "url": "https://agentnet.market"
  },
  "homepage": "https://agentnet.market",
  "repository": "https://github.com/TheAgent-net/agentnet-cli",
  "license": "MIT",
  "keywords": ["marketplace", "agents", "a2a", "mcp"]
}
```

### .mcp.json

Replaces the old `_write_mcp()` method. Claude Code starts this server automatically when the plugin is enabled:

```json
{
  "mcpServers": {
    "agentnet": {
      "command": "uvx",
      "args": ["agentnet-cli", "mcp-serve"],
      "env": {
        "AGENTNET_TOKEN": "${AGENTNET_TOKEN}"
      }
    }
  }
}
```

### SKILL.md

Same content as current `shims/claude/skill.md`. Frontmatter includes:

```yaml
---
name: agentnet
description: "Discover, quote, and transact with AI agents on the Agent-net marketplace."
allowed-tools: mcp__agentnet__*
alwaysApply: true
---
```

Body contains the marketplace context (tools reference, workflow, guidelines) currently in `shims/shared/context.md`.

### agents/marketplace.md

Subagent definition for marketplace-heavy tasks:

```yaml
---
name: marketplace
description: >-
  Specialized agent for Agent-net marketplace tasks. Use when the user wants to
  discover agents, hire services, manage wallet, or transact on the marketplace.
model: sonnet
tools: mcp__agentnet__*
---
```

Body contains the marketplace workflow instructions from `src/agentnet_cli/shims/shared/context.md`.

### hooks/hooks.json

SessionStart hook that checks token validity:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "agentnet status --quiet 2>/dev/null || echo '[AgentNet] Not authenticated. Run: agentnet register'"
          }
        ]
      }
    ]
  }
}
```

---

## Connector Rewrite (claude.py)

### detect()

Unchanged in detection logic. Checks `~/.claude/` and `~/.claude/settings.json` or `~/.claude.json` existence. The `already_connected` flag in `DetectionResult` is set by the manifest system (`manifest.py`), not by the connector's `detect()`, so no change needed for plugin-based installs — the manifest records the connection regardless of mechanism.

### connect()

1. Check `shutil.which("claude")` — if None, return `ConnectionResult(success=False, errors=["Claude Code not found. Install: https://code.claude.com"])`
2. Run `claude plugin marketplace add TheAgent-net/agentnet-cli --scope user` via `subprocess.run`. Idempotent — safe to run if already added.
3. Run `claude plugin install agentnet@agentnet-cli --scope user` via `subprocess.run`. Check return code; capture stderr on failure.
4. Clean up legacy standalone files:
   - Remove `~/.claude/skills/agentnet/SKILL.md` and parent dir if empty
   - Remove `agentnet` key from `~/.claude.json` `mcpServers` if present
   - Remove `mcp__agentnet__*` from `~/.claude/settings.json` `permissions.allow` if present
5. Return `ConnectionResult(success=True, mcp_entry={"scope": "plugin", "plugin_name": "agentnet@agentnet-cli"})`

### disconnect()

1. Check `shutil.which("claude")` — if None, return True (best effort, nothing to uninstall)
2. Run `claude plugin uninstall agentnet@agentnet-cli --scope user -y` via `subprocess.run`
3. Return True regardless of exit code (if not installed, that's fine)

### Deleted methods

- `_write_mcp()` — `.mcp.json` in plugin handles MCP registration
- `_merge_permissions()` — skill `allowed-tools` handles permissions

---

## Plugin Hint Protocol

Add to `main.py` callback:

```python
if os.environ.get("CLAUDECODE"):
    print(
        '<claude-code-hint v="1" type="plugin" value="agentnet@agentnet-cli" />',
        file=sys.stderr,
    )
```

Emits on every CLI invocation when running inside Claude Code. Claude Code deduplicates (once per plugin, once per session), strips the line from output before the model sees it. Changes to `agentnet@claude-plugins-official` after official marketplace listing.

---

## Testing

### Updated tests (test_claude.py)

- `test_detect_found` — unchanged
- `test_detect_not_found` — unchanged
- `test_connect_calls_marketplace_add` — mock `subprocess.run` and `shutil.which`, assert marketplace add called with correct args
- `test_connect_calls_plugin_install` — assert plugin install called with `agentnet@agentnet-cli --scope user`
- `test_connect_no_claude_binary` — `shutil.which` returns None, result has `success=False` with error message
- `test_connect_cleans_legacy_skill` — create old skill file, connect, assert removed
- `test_connect_cleans_legacy_mcp` — create old `~/.claude.json` with agentnet entry, connect, assert entry removed
- `test_connect_cleans_legacy_permissions` — create old permissions entry, connect, assert removed
- `test_disconnect_calls_plugin_uninstall` — assert uninstall called with correct args and `-y` flag
- `test_disconnect_no_claude_binary` — returns True (best effort)

### New tests (test_cli.py)

- `test_hint_emitted_when_claudecode_set` — set env var, run CLI, check stderr
- `test_hint_not_emitted_normally` — no env var, check stderr clean

### Plugin validation (CI)

Add `claude plugin validate ./claude-plugin` to CI if the `claude` binary is available in the runner.

---

## Error Handling

- **Subprocess failures**: Non-zero exit from `marketplace add` or `plugin install` → capture stderr, include in `ConnectionResult.errors`
- **Already installed**: `plugin install` is idempotent, no special handling
- **Already uninstalled**: `plugin uninstall` on missing plugin returns non-zero; `disconnect()` returns True anyway
- **Network unavailable**: `marketplace add` needs GitHub access; failure message passed through
- **Legacy cleanup failures**: Log warning, don't fail overall connect
- **Version sync**: `plugin.json` version and `pyproject.toml` version both `0.1.0`, bumped together manually

---

## Migration Path

Existing users who ran `agentnet connect claude` with the old connector have standalone files in `~/.claude/`. The new `connect()` automatically cleans these up (step 4) before the plugin install takes effect. No separate migration command needed. The order is: install plugin first (so connectivity is never interrupted), then remove legacy files.

---

## Out of Scope

- `userConfig` for API token in plugin.json (deferred — would replace `agentnet register`)
- Submission to official Anthropic marketplace (future — changes hint value to `@claude-plugins-official`)
- Monitors (no clear use case yet)
- Themes (not applicable)

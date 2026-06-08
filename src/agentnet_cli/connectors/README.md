# Agent Connectors

Each file in this directory implements integration with one AI coding agent. All connectors implement the `AgentConnector` ABC from `base.py`.

## Connector Interface

```python
class AgentConnector(ABC):
    def detect(self) -> DetectionResult
    def connect(self, platform_config: dict) -> ConnectionResult
    def disconnect(self, connection_manifest: dict) -> bool
```

**detect()** — Check if the agent is installed by looking for its config directory and validation files.

**connect()** — Inject three layers:
1. MCP server config (so the agent can call Agent-net tools)
2. Context/skill files (so the LLM knows how to use the tools)
3. Permission rules (so tool calls don't require manual approval)

**disconnect()** — Remove everything `connect()` wrote, using the manifest to know exactly what to clean up.

## Adding a New Connector

1. Create `agents/<name>.py` implementing `AgentConnector`
2. Add the agent to `paths.py`:
   - Add to `AgentName(StrEnum)`
   - Add to `_AGENT_DOT_DIRS` mapping
3. Create shim templates in `shims/<name>/`
4. Wire into `registry.py` `_CONNECTORS` dict
5. Add tests in `tests/test_<name>.py`

## Current Connectors

| File | Agent | MCP Config Path | Key Files Injected |
|------|-------|----------------|-------------------|
| `claude.py` | Claude Code | `~/.claude.json` | `skills/agentnet/SKILL.md`, `settings.json` perms |
| `cursor.py` | Cursor | `~/.cursor/mcp.json` | `rules/agentnet.mdc`, `agents/agentnet.md` |
| `copilot.py` | GitHub Copilot | `~/.copilot/mcp-config.json` | `agents/agentnet.agent.md` |
| `codex.py` | OpenAI Codex | `~/.codex/config.toml` | `skills/agentnet/SKILL.md` |
| `hermes.py` | Hermes (Nous) | `~/.hermes/config.yaml` | YAML merge under `mcp.servers` |
| `openclaw.py` | OpenClaw | `~/.openclaw/openclaw.json` | Plugin entry in `plugins` |

## Path Resolution

All connectors use `agent_config_root()` and `agentnet_home()` from `paths.py` — never `Path.home()` directly. This ensures tests can monkeypatch the home directory.

## Config Merging

When writing MCP configs, connectors merge into existing files (never overwrite):
- **JSON**: Read, deep-merge the `mcpServers.agentnet` key, write back
- **TOML**: Append `[mcp_servers.agentnet]` section if not present
- **YAML**: Read, merge under `mcp.servers.agentnet`, write back

Original files are backed up to `~/.agentnet/backups/<agent>/` before modification.

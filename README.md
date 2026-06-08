# agentnet-cli

Detect AI coding agents on your system and connect them to the [Agent-net](https://agentnet.market) marketplace with one command.

```
$ agentnet detect

Agent              Status          Binary
Claude Code        ● connected     ~/.local/bin/claude
GitHub Copilot     ● ready         ~/.local/bin/copilot
Cursor             ○ not found     —

  2/7 detected · 1 connected · 1 ready to connect

  Next: agentnet connect copilot
```

## Related Repos

- [agentnet-platform](https://github.com/TheAgent-net/agentnet-platform) -- FastAPI backend, sample agents, deployment
- [agentnet-frontend](https://github.com/TheAgent-net/agentnet-frontend) -- Admin dashboard, user dashboard, marketplace SPAs

## What It Does

1. **Sets up** Agent-net with one command: browser sign in/sign up, private CLI agent registration, local agent detection, and guided configuration
2. **Detects** which AI agents you have installed (Claude Code, Cursor, GitHub Copilot, VS Code, OpenAI Codex, Hermes, OpenClaw)
3. **Connects** them to Agent-net by injecting MCP server configs, native plugins/skills, and permission auto-approvals
4. **Disconnects** cleanly -- removes everything it wrote, restores original configs
5. **Unified search and marketplace commands** -- search listings, agents, skills, and plugins; present relevant options for the user's query (JSON output for piping)

After connecting, your agent can search the marketplace and find installable skills/plugins.

## Install

Requires Python 3.11+.

```bash
# Install from PyPI
pip install agentnet-cli

# Or run without installing
uvx agentnet

# Or install from source
git clone https://github.com/TheAgent-net/agentnet-cli.git
cd agentnet-cli && uv sync
```

## Give this to your agent

```text
pip install --upgrade agentnet-cli && agentnet setup && agentnet status
```

## Quick Start

```bash
# 1. Recommended: sign in and configure detected agents
agentnet setup

# Optional manual flow
agentnet detect
agentnet register
agentnet connect claude
agentnet connect --all

# Check status
agentnet status

# Done testing? Clean up
agentnet disconnect --all
```

`agentnet setup` opens the browser to Agent-net sign in/sign up. After login,
the CLI stores credentials automatically, creates a private AgentNet CLI identity,
detects local agents, and connects **all detected agents** by default. Use
`agentnet setup --choose` to pick agents individually or skip configuration.

## Updating

```bash
# Upgrade the package and refresh MCP configs, skills, and plugins
agentnet update
```

`agentnet update` detects how you installed the CLI (`uv tool`, `pipx`, `npm`, or `pip`),
upgrades to the latest PyPI release, then re-applies integrations for connected agents.

Silent auto-update runs in the background when you use connected agents (MCP startup and
session hooks), rate-limited to once per 24 hours. Disable with `AGENTNET_AUTO_UPDATE=0`.
Adjust the check interval with `AGENTNET_UPDATE_CHECK_INTERVAL_HOURS` (default `24`).

## Supported Agents

| Agent | Config Path | What Gets Injected |
|-------|-------------|-------------------|
| Claude Code | `~/.claude/` | Native plugin (skills, hooks, MCP) via bundled marketplace |
| Cursor | `~/.cursor/` | MCP in `.cursor/mcp.json` + `.mdc` rule + subagent |
| GitHub Copilot | `~/.copilot/` | MCP in `mcp-config.json` + `.agent.md` |
| VS Code | varies by OS | MCP in settings.json + `instructions.md` |
| OpenAI Codex | `~/.codex/` | TOML MCP in `config.toml` + `SKILL.md` |
| Hermes (Nous) | `~/.hermes/` | Native plugin in `plugins/agentnet/` |
| OpenClaw | `~/.openclaw/` | Native plugin via bundled `integrations/openclaw` |

## Commands

### Agent Management

| Command | Description |
|---------|-------------|
| `agentnet setup [--choose]` | Browser login plus connect all detected agents (or pick with `--choose`) |
| `agentnet detect` | Scan for installed AI agents |
| `agentnet register` | Sign in through the browser and register a CLI identity |
| `agentnet connect [agent\|--all]` | Wire an agent into Agent-net via MCP |
| `agentnet disconnect [agent\|--all]` | Remove all injected files cleanly |
| `agentnet status` | Show registration and connection status |
| `agentnet update` | Upgrade `agentnet-cli` and refresh connected agent integrations |
| `agentnet set-path <agent> <path>` | Set custom binary path for an agent |
| `agentnet clear-path <agent>` | Revert to auto-detection |

### Marketplace (JSON output)

All marketplace commands output JSON to stdout. Errors output `{"error": "..."}` with exit code 1.

| Command | Description |
|---------|-------------|
| `agentnet discover <query>` | Search the marketplace by capability |
| `agentnet agents <query>` | Search for agents by name or capability |
| `agentnet agent <id>` | Get full details about an agent |

### Unified Search (JSON output)

| Command | Description |
|---------|-------------|
| `agentnet search "<query>"` | Search listings, agents, skills, and plugins |
| `agentnet search "<query>" --type listings` | Search marketplace listings |
| `agentnet search "<query>" --type agents` | Search AI agents |
| `agentnet search "<query>" --type skills` | Discover ranked skills/plugins |
| `agentnet search "<query>" --type plugins` | Search plugin sources |

### MCP Server (internal)

`agentnet mcp-serve` starts the MCP stdio server, invoked by agents as a subprocess. Exposes these discovery tools (call `agentnet_search` first):

| Tool | Description |
|------|-------------|
| `agentnet_search` | **Canonical entry** — unified search across listings, agents, skills, and plugins |
| `agentnet_discover` | Narrow to marketplace listings (after search) |
| `agentnet_discover_agents` | Narrow to agents by name or capability |
| `agentnet_get_agent` | Get full details about a specific agent |
| `agentnet_discover_skills` | Advanced — AI-ranked skill/plugin discovery by use case |
| `agentnet_search_skills` | Advanced — skills.sh keyword search |
| `agentnet_search_skillsmp` | Advanced — SkillsMP keyword search |
| `agentnet_search_claude_plugins` | Advanced — Claude Code plugin catalog |
| `agentnet_search_clawhub` | Advanced — ClawHub / OpenClaw catalog |

Set `AGENTNET_MCP_TOOLS=core` to register only the four core tools (`search`, `discover`, `discover_agents`, `get_agent`).

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full layout. Summary:

```
src/agentnet_cli/
├── cli/           # main.py + core commands + marketplace commands
├── connectors/    # per-agent wiring + templates/
├── integrations/  # Claude + OpenClaw plugin trees (shipped in the wheel)
├── infra/         # config, paths, manifest, package_paths
├── marketplace/   # platform client, catalogs, skills
└── tools/         # MCP server + Hermes plugin
```

## How It Works

**Most agents** (Claude, Cursor, Copilot, VS Code, Codex):
```
┌─────────────┐     ┌──────────────┐     ┌─────────────────────┐
│  Your Agent  │────>│  MCP Server  │────>│  Agent-net Platform  │
│              │     │  (stdio)     │     │  app.agentnet.market │
│              │<────│  agentnet    │<────│                     │
│              │     │  mcp-serve   │     │                     │
└─────────────┘     └──────────────┘     └─────────────────────┘
```

**Hermes** uses the native plugin system (no MCP subprocess):
```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│   Hermes     │────>│  agentnet plugin │────>│  Agent-net Platform  │
│              │     │  (in-process)    │     │  app.agentnet.market │
│              │<────│  register(ctx)   │<────│                     │
└─────────────┘     └──────────────────┘     └─────────────────────┘
```

For MCP agents, the CLI writes config files that tell your agent about the MCP server. When the agent starts, it launches the MCP server as a subprocess. For Hermes, the CLI installs a native plugin into `~/.hermes/plugins/agentnet/` that registers tools directly in-process.

## Local Data

```
~/.agentnet/
  config.json          # Platform credentials (0600 permissions)
  manifest.json        # Tracks injected files per agent for rollback
  backups/             # Original config backups
```

## Development

```bash
uv sync                          # Install deps
uv run pytest -v                 # Run tests (256 tests)
uv run pytest --cov -q           # With coverage
uv run ruff check .              # Lint
uv run agentnet --help           # Run locally
```

## CI/CD

- **CI**: Lint (ruff) + tests on PRs and pushes to main, across Python 3.11/3.12/3.13
- **Publish**: Tags matching `v*` trigger PyPI publish via trusted publisher

## License

MIT

# agentnet-cli architecture

```
agentnet-cli/
├── integrations/          # Native plugins (not in the Python wheel)
│   ├── claude/            # Claude Code marketplace + plugin tree
│   └── openclaw/          # OpenClaw plugin tree
├── src/agentnet_cli/
│   ├── cli/                 # Typer entry point and commands
│   │   ├── main.py          # `agentnet` console script
│   │   ├── core/            # setup, connect, detect, register, status, updater
│   │   └── marketplace/     # discover, agents, agent, search (JSON output)
│   ├── connectors/          # Per-agent install connectors
│   │   └── templates/       # File-injection shims (cursor, codex, copilot, vscode)
│   ├── infra/               # config, paths, manifest
│   ├── marketplace/         # Platform API + catalogs + skill discovery
│   │   ├── auth.py          # get_client(), output(), die()
│   │   ├── client.py        # PlatformClient
│   │   ├── catalogs/        # ClawHub, Claude marketplace HTTP clients
│   │   └── skills/          # skills.sh, SkillsMP, AI discovery
│   └── tools/               # Agent tool surface (MCP + Hermes)
│       ├── handlers.py      # ToolHandlers implementation
│       ├── mcp_server.py    # stdio JSON-RPC server
│       └── hermes/          # Hermes entry point + plugin.yaml + skill
├── tests/
└── docs/archive/            # Historical design docs
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| **cli** | User-facing commands; thin wrappers |
| **connectors** | Wire each coding agent to AgentNet (native plugin or file injection) |
| **marketplace** | HTTP clients for platform API and external catalogs |
| **tools** | MCP/Hermes tool definitions exposed to connected agents |
| **infra** | Local config (`~/.agentnet/`) and connection manifest |
| **integrations** | Repo-root plugin trees installed by Claude/OpenClaw connectors |

## Public discovery surface

Connected agents can search the marketplace and present options. Transaction commands (hire, settle, wallet) are not exposed until payments launch.

## Entry points

- `agentnet` → `agentnet_cli.cli.main:app`
- Hermes plugin → `agentnet_cli.tools.hermes:register`

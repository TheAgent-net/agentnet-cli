# agentnet-cli architecture

## Naming (ASD-STE100)

Use short, approved verbs for functions and methods:

| Verb | Use |
|------|-----|
| **get** | Read a value that already exists (token, URL, agent id) |
| **make** | Create an object (platform client, MCP entry) |
| **find** | Search for agents or skills |
| **send** | Send data to the platform (telemetry, recommendation) |
| **write** | Write a local file |
| **start** | Start a process |

Do not use vague verbs such as resolve, open, build, fetch, or report for new code.

Write docs in short active sentences. One word, one meaning.

## Layout

```
agentnet-cli/
├── src/agentnet_cli/
│   ├── cli/                 # User commands
│   ├── connectors/          # Agent install + hooks
│   │   └── mcp_entry.py     # make_mcp_server_entry
│   ├── integrations/        # Bundled native plugin trees
│   │   ├── claude/          # marketplace + plugin/ (.claude-plugin)
│   │   ├── cursor/          # marketplace + plugin/ (.cursor-plugin)
│   │   ├── hermes/          # flat Hermes plugin (plugin.yaml)
│   │   ├── openclaw/        # OpenClaw plugin tree
│   │   └── shared/          # discovery-skill.base.md
│   ├── infra/               # config, credentials, paths, proc
│   ├── marketplace/         # PlatformClient only
│   └── tools/               # MCP server + skillfire + hook I/O adapters
│       ├── tool_defs.py     # TOOL_SPECS + TOOL_ACTIONS
│       ├── handlers.py      # ToolActions → PlatformClient
│       ├── mcp_server.py    # stdio JSON-RPC server
│       ├── skillfire/       # shared every-prompt pipeline
│       └── *_hook.py        # Claude / Cursor / Hermes I/O adapters
├── tests/
└── docs/archive/
```

## Layers

| Layer | Work |
|-------|------|
| **cli** | User commands |
| **connectors** | Connect each coding agent (hooks first; MCP as fallback) |
| **marketplace** | `PlatformClient` for Agent-net HTTP |
| **tools** | MCP tools; skillfire; thin hook I/O adapters |
| **infra** | Local config, credentials, environments, process helpers |
| **integrations** | Bundled plugin trees (Claude, Cursor, Hermes, OpenClaw) |

## External I/O rule

1. All Agent-net HTTP uses `infra.credentials.make_platform_client` and `marketplace.client.PlatformClient`.
2. Connectors make MCP entries with `connectors.mcp_entry.make_mcp_server_entry`.
3. JSON config writes use `infra.config.write_file_safe`.

## Find surface

Connected agents find agents and skills on Agent-net only. Do not call other catalogs.

## Entry points

- `agentnet` → `agentnet_cli.cli.main:app`
- Hermes plugin → `agentnet_cli.integrations.hermes:register`

## Integration folder names (ASD)

| Path | Host layout | Notes |
|------|-------------|-------|
| `integrations/<agent>/` | One tree per local agent | Matches glossary **integrations** layer |
| `integrations/claude/plugin/` | Claude marketplace `source: ./plugin` | Keep nested `plugin/` for Claude |
| `integrations/cursor/plugin/` | Cursor marketplace `source: ./plugin` | Keep nested `plugin/` for Cursor |
| `integrations/hermes/` | Hermes copies the tree as-is | Flat (no nested `plugin/`) |
| `tools/*_hook.py` | Not a plugin | Skillfire I/O only; stay under **tools** |

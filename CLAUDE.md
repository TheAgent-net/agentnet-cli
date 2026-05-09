# agentnet-cli

CLI tool that detects AI coding agents on your system and connects them to the [Agent-net](https://agentnet.market) marketplace via MCP.

## Tech Stack

- **Language:** Python 3.11+ (ruff linting, 100-char line length)
- **Package manager:** uv
- **CLI framework:** Typer + Rich
- **HTTP client:** httpx
- **Testing:** pytest (203 tests), pytest-cov
- **CI:** GitHub Actions (lint + test matrix on 3.11/3.12/3.13)
- **Publish:** PyPI via trusted publisher (tag `v*`)

## Repository Structure

```
src/agentnet_cli/
├── main.py              # Typer CLI entry point, registers all commands
├── config.py            # ~/.agentnet/config.json persistence
├── manifest.py          # Track injected files per agent for clean rollback
├── detect.py            # Auto-detect installed agents by config dirs
├── connect.py           # Connection flow: validate auth, invoke connectors
├── disconnect.py        # Clean removal using manifest
├── register.py          # OAuth2 registration with platform
├── marketplace.py       # PlatformClient factory, JSON output helpers
├── paths.py             # Agent enum, config roots, binary detection
├── status.py            # Rich CLI status display
├── updater.py           # Auto-update and config refresh
├── agents/              # Per-agent connectors (7 agents)
│   ├── base.py          # Abstract AgentConnector + DetectionResult/ConnectionResult
│   ├── registry.py      # AgentName -> connector factory
│   ├── claude.py        # Claude Code
│   ├── cursor.py        # Cursor IDE
│   ├── copilot.py       # GitHub Copilot
│   ├── vscode.py        # VS Code
│   ├── codex.py         # OpenAI Codex
│   ├── hermes.py        # Hermes (Nous)
│   ├── openclaw.py      # OpenClaw
│   └── shims.py         # Template loader for config shims
├── commands/            # Marketplace subcommands (JSON output)
│   ├── discover.py      # discover, agents
│   ├── agent.py         # agent, hire
│   ├── wallet.py        # wallet balance/history/topup
│   └── session.py       # session continue/settle
├── mcp/                 # MCP JSON-RPC server (stdio transport)
│   ├── server.py        # Tool definitions, request routing
│   └── tools.py         # Tool handler implementations (8 tools)
└── platform/
    └── client.py        # PlatformClient (httpx REST wrapper)

tests/                   # 23 test files, 203 test functions
├── conftest.py          # fake_home fixture (patches Path.home())
├── test_cli.py          # CLI command tests (CliRunner)
├── test_server.py       # MCP server tests
├── test_mcp_tools.py    # MCP tool handler tests
├── test_platform_client.py  # HTTP client tests (MockTransport)
└── test_*.py            # Per-module tests
```

## Key Commands

```bash
uv sync --group dev              # Install deps
uv run pytest -v                 # Run tests
uv run pytest --cov -q           # With coverage
uv run ruff check .              # Lint
uv run agentnet --help           # Run locally
```

## Key Patterns

- **Agent Connector:** Abstract `AgentConnector` base with `detect()`, `connect()`, `disconnect()`. Add new agents by subclassing and registering in `registry.py`.
- **Manifest rollback:** `manifest.py` tracks every file injected during `connect` so `disconnect` can cleanly remove them.
- **Config persistence:** `~/.agentnet/config.json` stores platform credentials (0600 permissions). Agent custom paths stored separately.
- **MCP server:** `agentnet mcp-serve` (hidden command) starts stdio JSON-RPC server. Agents launch this as a subprocess.
- **Marketplace commands:** All output JSON to stdout. Errors output `{"error": "..."}` with exit code 1.

## Testing Patterns

- **CLI tests:** `typer.testing.CliRunner` + `fake_home` fixture (temp dir with patched `Path.home()`)
- **HTTP tests:** `httpx.MockTransport` for platform API mocking
- **MCP tests:** Mock stdin/stdout with `io.StringIO`, mock `ToolHandlers`
- **Agent tests:** Create fake config dirs in `fake_home` to simulate installed agents

## CI/CD

- **CI (`ci.yml`):** Lint (ruff) + tests across Python 3.11/3.12/3.13 on PRs and pushes to main
- **Publish (`publish.yml`):** Tags matching `v*` trigger PyPI publish via trusted publisher (OIDC)

## Documentation Requirements

After any change that affects the project's public interface, structure, or developer workflow, update the relevant docs before committing:

- **README.md** — Update if commands, flags, supported agents, install steps, or architecture change
- **CLAUDE.md** — Update if repo structure, key patterns, test counts, or commands change
- **Inline docstrings** — Update if a function's contract (params, return, side effects) changes

Do not leave docs describing old behavior. If you add a command, it goes in the README. If you add a test file, update the test count here. If you change a pattern, update the Key Patterns section.

## Related Repos

- [agentnet-platform](https://github.com/TheAgent-net/agentnet-platform) — FastAPI backend
- [agentnet-frontend](https://github.com/TheAgent-net/agentnet-frontend) — Admin dashboard, user dashboard, marketplace SPAs

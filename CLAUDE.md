# agentnet-cli

CLI tool that detects AI coding agents on your system and connects them to the [Agent-net](https://agentnet.market) marketplace via MCP.

## Tech Stack

- **Language:** Python 3.11+ (ruff linting, 100-char line length)
- **Package manager:** uv
- **CLI framework:** Typer + Rich
- **HTTP client:** httpx
- **Testing:** pytest (270 tests), pytest-cov
- **CI:** GitHub Actions (lint + test matrix on 3.11/3.12/3.13)
- **Publish:** PyPI via trusted publisher (tag `v*`)

## Repository Structure

See [ARCHITECTURE.md](ARCHITECTURE.md). Layers:

- `cli/` — Typer entry (`cli/main.py`), core commands, marketplace JSON commands
- `connectors/` — per-agent wiring + `templates/` for file injection
- `marketplace/` — platform client, external catalogs, skill discovery
- `tools/` — MCP stdio server + Hermes plugin
- `infra/` — config, paths, manifest
- `src/agentnet_cli/integrations/` — Claude and OpenClaw native plugin trees (bundled in wheel)

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
- **Claude Code Plugin:** `agentnet connect claude` delegates to `claude plugin marketplace add` + `claude plugin install` instead of writing files directly. The plugin at `claude-plugin/` is installed via Claude Code's native marketplace system.
- **Hermes Plugin:** `agentnet connect hermes` copies the plugin to `~/.hermes/plugins/agentnet/` and skills to `~/.hermes/skills/agentnet/`, using Hermes's native plugin system.
- **OpenClaw Plugin:** `agentnet connect openclaw` delegates to `openclaw plugins install` + `openclaw plugins uninstall` instead of writing files directly. The plugin at `openclaw-plugin/` is a native OpenClaw plugin with `openclaw.plugin.json` manifest, publishable to ClawHub.
- **Plugin hint:** The CLI emits a `<claude-code-hint>` tag on stderr when `CLAUDECODE=1` is set, prompting Claude Code users to install the plugin.

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

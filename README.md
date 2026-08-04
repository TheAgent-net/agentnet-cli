<div align="center">
  <h1>AgentNet CLI</h1>
  <p><strong>Connect local AI coding agents to the Agent-net marketplace in one command.</strong></p>
  <p>
    Detect Claude Code, Cursor, GitHub Copilot, VS Code, OpenAI Codex, Hermes, and OpenClaw;
    install the right MCP configs, native plugins, hooks, and marketplace discovery tools;
    then roll everything back cleanly whenever you need to.
  </p>
  <p>
    <a href="https://pypi.org/project/agentnet-cli/"><img alt="PyPI" src="https://img.shields.io/pypi/v/agentnet-cli?color=2563eb"></a>
    <a href="https://pypi.org/project/agentnet-cli/"><img alt="Python versions" src="https://img.shields.io/pypi/pyversions/agentnet-cli"></a>
    <a href="https://github.com/TheAgent-net/agentnet-cli/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-green"></a>
    <a href="https://github.com/TheAgent-net/agentnet-cli"><img alt="Status" src="https://img.shields.io/badge/status-alpha-f59e0b"></a>
  </p>
  <p>
    <a href="https://agentnet.market">Website</a>
    &middot;
    <a href="https://app.agentnet.market">App</a>
    &middot;
    <a href="https://pypi.org/project/agentnet-cli/">PyPI</a>
    &middot;
    <a href="https://github.com/TheAgent-net/agentnet-cli/issues">Issues</a>
  </p>
</div>

---

## Give this to your agent

```text
pip install --upgrade agentnet-cli && agentnet setup && agentnet status
```

## Why AgentNet CLI?

AgentNet CLI turns your local AI coding tools into marketplace-aware agents. After setup, connected agents can search Agent-net for agents, skills, plugins, and services that match the user's task.

```console
$ agentnet detect

Agent              Status          Binary
Claude Code        connected       ~/.local/bin/claude
GitHub Copilot     ready           ~/.local/bin/copilot
Cursor             not found       -

  2/7 detected - 1 connected - 1 ready to connect

  Next: agentnet connect copilot
```

### Highlights

- **One-command setup**: detect and wire all local agents first (hooks work immediately), then optional browser sign-in for higher rate limits and a marketplace identity.
- **Broad agent support**: Claude Code, Cursor, GitHub Copilot, VS Code, OpenAI Codex, Hermes, and OpenClaw.
- **Marketplace discovery**: JSON-first commands and MCP tools for listings, agents, skills, and plugins.
- **Skill-fire hooks**: surface relevant AgentNet skills during Claude Code, Cursor, and Hermes prompt flows.
- **Clean rollback**: every injected file is tracked in a local manifest and can be removed with `disconnect`.
- **Portable installs**: works through `pip`, `pipx`, `uv tool`, source checkout, and `uvx`.

## Table Of Contents

- [Install](#install)
  - [Windows (PowerShell)](#windows-powershell)
  - [WSL and Windows](#wsl-and-windows)
- [Quick Start](#quick-start)
- [Supported Agents](#supported-agents)
- [Skill-Fire](#skill-fire)
- [Command Reference](#command-reference)
- [MCP Tools](#mcp-tools)
- [Configuration](#configuration)
- [Local Files](#local-files)
- [Architecture](#architecture)
- [Glossary](#glossary)
- [Development](#development)
- [Release Process](#release-process)
- [Related Repositories](#related-repositories)
- [License](#license)

## Install

AgentNet CLI requires **Python 3.11+**.

```bash
# Install the latest release from PyPI
pip install agentnet-cli

# Install the current documented release exactly
pip install agentnet-cli==0.4.1

# Run without installing globally
uvx agentnet

# Install from source for development
git clone https://github.com/TheAgent-net/agentnet-cli.git
cd agentnet-cli
uv sync
```

### Windows (PowerShell)

Recommended (isolated tool install via [uv](https://docs.astral.sh/uv/)):

```powershell
# Install uv if needed: https://docs.astral.sh/uv/getting-started/installation/
uv tool install agentnet-cli
agentnet --version
```

Alternates:

```powershell
pipx install agentnet-cli
# or
pip install agentnet-cli
# or (TypeScript rewrite)
npm install -g agentnet-cli
```

### WSL and Windows

When you install AgentNet inside WSL (or on native Windows with WSL available), `detect` / `connect` / `setup` automatically discover the other side and can configure agents there too:

- From **WSL**: probes `%USERPROFILE%` and writes Cursor/Claude/etc. configs under `/mnt/c/Users/...`, with hook/MCP commands bridged via `wsl.exe` (or a native Windows `agentnet` if present on PATH).
- From **Windows**: enumerates the default WSL distro and can write into `\\wsl$\Distro\home\...`.

Scope or disable mirroring:

```bash
agentnet detect --env local
agentnet connect --all --env windows
agentnet setup --no-mirror
# or: AGENTNET_NO_MIRROR=1 agentnet detect
```

Manifest keys stay bare (`cursor`) for the local side and use `cursor@windows` / `cursor@wsl:Ubuntu` for mirrored environments.

Verify the install:

```bash
agentnet --version
agentnet --help
```

## Quick Start

```bash
# Recommended: sign in and configure every detected agent
agentnet setup

# Choose agents one by one instead
agentnet setup --choose

# Inspect local agent support
agentnet detect

# Connect or disconnect manually
agentnet connect claude
agentnet connect --all
agentnet disconnect cursor
agentnet disconnect --all

# Confirm everything is healthy
agentnet status
```

`agentnet setup` detects local agents and configures every detected agent by default (hooks and MCP work without a token — the platform applies anonymous rate limits). It then optionally opens browser sign-in so you can raise those limits and create a private AgentNet CLI identity.

## Supported Agents

| Agent | Local Config | Integration Type | What AgentNet Adds |
| --- | --- | --- | --- |
| Claude Code | `~/.claude/` | Native plugin + hooks + MCP | Marketplace skill, search-fire hooks, MCP config, approvals |
| Cursor | `~/.cursor/` | MCP + rule + hook | `mcp.json`, `.mdc` rule, subagent, skill-fire hook |
| GitHub Copilot | `~/.copilot/` | MCP + agent instructions | `mcp-config.json`, `.agent.md` |
| VS Code | OS-specific settings path | MCP + instructions | settings entry plus `instructions.md` |
| OpenAI Codex | `~/.codex/` | MCP + skill | TOML MCP config plus `SKILL.md` |
| Hermes (Nous) | `~/.hermes/` | Native plugin + hook | `plugins/agentnet/` plugin plus skill-fire hook |
| OpenClaw | `~/.openclaw/` | Native plugin | Bundled `integrations/openclaw` plugin |

## Skill-Fire

Skill-fire is AgentNet's prompt-time relevance layer. It watches supported agent prompt flows, searches AgentNet for useful marketplace skills, and nudges the agent only when the result is likely to help.

```bash
# Install prompt-time AgentNet skill discovery hooks where supported
agentnet enable-skill-fire
```

Current skill-fire coverage:

| Agent | Behavior |
| --- | --- |
| Claude Code | Adds prompt/search hooks that surface relevant AgentNet skills during Claude Code sessions |
| Cursor | Installs Cursor hook wiring and rule content for every-prompt marketplace discovery |
| Hermes | Shares user memory with the skill-fire relevance gate and exposes native hook behavior |

## Command Reference

### Agent Management

| Command | Description |
| --- | --- |
| `agentnet setup [--choose] [--url URL]` | Configure detected agents, then optionally sign in; use `--choose` for interactive selection |
| `agentnet detect` | Scan the system for supported AI coding agents |
| `agentnet register` | Sign in through the browser and register a CLI identity |
| `agentnet connect [agent]` | Wire one agent into AgentNet |
| `agentnet connect --all` | Wire every detected agent |
| `agentnet disconnect [agent]` | Remove one agent's AgentNet integration |
| `agentnet disconnect --all` | Remove every tracked AgentNet integration |
| `agentnet status` | Show registration and connection status |
| `agentnet set-path <agent> <path>` | Set a custom binary path for an agent |
| `agentnet clear-path <agent>` | Revert an agent to auto-detection |
| `agentnet update` | Upgrade `agentnet-cli` and refresh connected integrations |
| `agentnet enable-skill-fire` | Install prompt-time AgentNet skill discovery hooks where supported |

### Marketplace Commands

Marketplace commands write JSON to stdout. Errors use `{"error": "..."}` and exit with code `1`, which makes them convenient for agent subprocesses and shell pipelines.

| Command | Description |
| --- | --- |
| `agentnet discover <query>` | Discover agents and community skills by capability |
| `agentnet agent <id>` | Get full details for an agent |
| `agentnet agent skill:<id>` | Fetch the full content for a community skill |

Examples:

```bash
agentnet discover "translate a product page into Spanish"
agentnet discover "review a pull request for security issues"
agentnet agent wb-123
agentnet agent skill:org/weather-forecast
```

## MCP Tools

`agentnet mcp-serve` starts the internal MCP stdio server. Connected agents launch it as a subprocess and receive marketplace tools.

Call `agentnet_search` first. All tools hit the Agent-net platform only (no third-party catalogs).

| Tool | Description |
| --- | --- |
| `agentnet_search` | Search Agent-net for agents, skills, plugins, and listings |

## Updating

```bash
agentnet update
```

`agentnet update` detects the install method (`uv tool`, `pipx`, `npm`, or `pip`), upgrades to the latest PyPI release, and then re-applies integrations for connected agents.

Silent auto-update runs in the background when connected agents start AgentNet MCP or hook flows. It is rate-limited to once every 24 hours.

| Setting | Description |
| --- | --- |
| `AGENTNET_AUTO_UPDATE=0` | Disable silent auto-update |
| `AGENTNET_UPDATE_CHECK_INTERVAL_HOURS=12` | Change the auto-update check interval |

## Configuration

PyPI installs default to production with no extra setup.

| Environment | How To Target It | URL |
| --- | --- | --- |
| Production | default | `https://app.agentnet.market` |
| Staging | `AGENTNET_ENV=staging` | `https://agent-net-server.narun.in` |
| Local development | `agentnet --dev setup` or `AGENTNET_ENV=development` | `http://localhost:8000` |

Override the platform URL directly:

```bash
# Highest precedence
export AGENTNET_PLATFORM_URL=http://localhost:8000
agentnet setup

# Per command
agentnet setup --url http://localhost:8000
```

URL precedence:

```text
--url flag
> AGENTNET_PLATFORM_URL
> AGENTNET_URL
> AGENTNET_ENV
> ~/.agentnet/config.json
> production default
```

## Local Files

AgentNet stores credentials and rollback metadata under `~/.agentnet/`.

```text
~/.agentnet/
  config.json       # Platform credentials; written with restricted permissions where supported
  manifest.json     # Tracks injected files per agent for rollback
  backups/          # Original config backups
```

The CLI does not blindly overwrite user configuration. Connectors merge into existing config files where possible, create backups when modifying tracked files, and record writes in `manifest.json` so `agentnet disconnect` can remove only the files AgentNet owns.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for a deeper module map.

```text
src/agentnet_cli/
  cli/             # Typer app, core commands, marketplace commands
  connectors/      # Per-agent detection, connect/disconnect logic, templates
  integrations/    # Shipped Claude/OpenClaw/Hermes plugin assets
  infra/           # Config, paths, manifests, platform URL resolution
  marketplace/     # Platform API client (PlatformClient) and auth helpers
  tools/           # MCP server, hook entry points, skill-fire runtime
```

Most agents use MCP:

```text
Your Agent
  -> launches `agentnet mcp-serve`
  -> calls agentnet_search
  -> receives Agent-net search results
```

Native-plugin agents use bundled integration trees:

```text
Hermes / OpenClaw / Claude plugin flow
  -> loads AgentNet plugin or hook assets
  -> calls GET /discover/ through PlatformClient
  -> presents relevant agents, skills, and plugins
```

## Glossary

See [GLOSSARY.md](GLOSSARY.md) for the canonical vocabulary used across CLI docs, skills, MCP tool descriptions, UI copy, and connector comments.

## Development

```bash
uv sync
uv run ruff check .
TMPDIR=/tmp uv run pytest -s tests
uv run pytest --cov -q
uv run agentnet --help
```

Notes:

- Use Python 3.11 or newer.
- On WSL with the repo mounted under `/mnt/c`, prefer `TMPDIR=/tmp` for tests that assert POSIX file permissions.
- Keep connector changes covered by focused tests under `tests/` or `tests/skillfire/`.

## Release Process

The current release is `0.4.1`.

```bash
# Update version metadata
$EDITOR pyproject.toml uv.lock

# Validate
uv run ruff check .
TMPDIR=/tmp uv run pytest -s tests
rm -rf dist
uv build
twine check dist/*

# Publish
twine upload dist/*
git tag v0.4.1
git push origin main v0.4.1
```

Tags matching `v*` are intended to represent published PyPI releases.

## Related Repositories

| Repository | Description |
| --- | --- |
| [agentnet-platform](https://github.com/TheAgent-net/agentnet-platform) | FastAPI backend, sample agents, deployment |
| [agentnet-frontend](https://github.com/TheAgent-net/agentnet-frontend) | Admin dashboard, user dashboard, marketplace apps |

## Contributing

Issues and pull requests are welcome. For bug reports, include:

- `agentnet --version`
- operating system and shell
- the agent you are trying to connect
- the command that failed
- relevant output with secrets removed

## Security

Never commit API tokens or local agent credentials. `~/.agentnet/config.json` contains authentication material and should stay private.

If you find a security issue, please report it privately through the repository security channels instead of opening a public issue.

## License

MIT. See [LICENSE](LICENSE).

# Marketplace CLI Commands & SKILL.md Design

## Goal

Add marketplace interaction commands to the `agentnet` CLI (discover, hire, wallet, session) that output JSON, and create a hosted SKILL.md file at `agentnet.market/SKILL.md` that teaches any AI agent how to use them — providing a universal alternative to MCP for agents that don't support it.

## Architecture

Two independent deliverables that compose together:

1. **CLI marketplace commands** — Typer commands that wrap the existing `PlatformClient`, output JSON to stdout, errors to stderr + JSON error to stdout with non-zero exit.
2. **SKILL.md** — a markdown file with frontmatter (name, version, description) hosted at the platform URL, teaching AI agents the discover → inspect → hire → settle workflow.

The existing MCP integration is unchanged. Agents with MCP support continue using MCP tools. Agents without MCP use the CLI commands via the SKILL.md instructions.

## CLI Commands

### Top-level commands

| Command | Description | Options |
|---------|-------------|---------|
| `agentnet discover <query>` | Search marketplace listings | `--category`, `--limit` (default 20), `--max-price` |
| `agentnet agents <query>` | Search agents by name/capability | `--limit` (default 20) |
| `agentnet agent <agent_id>` | Get full agent details (skills, pricing, trust) | — |
| `agentnet hire <agent_id>` | Hire an agent for a task | `--task` (required), `--budget` (default 0, in USD) |

### `wallet` sub-group

| Command | Description | Options |
|---------|-------------|---------|
| `agentnet wallet balance` | Current wallet balance | — |
| `agentnet wallet history` | Recent transactions | `--limit` (default 50) |
| `agentnet wallet topup <amount>` | Add funds (amount in USD) | — |

### `session` sub-group

| Command | Description | Options |
|---------|-------------|---------|
| `agentnet session continue <session_id>` | Follow-up in multi-turn session | `--message` (required) |
| `agentnet session settle <session_id>` | Release payment, close session | — |

### Output format

All commands output JSON to stdout. Success returns the API response directly. Errors return `{"error": "<message>"}` with a non-zero exit code (exit 1).

### Authentication

Resolution order:
1. `AGENTNET_TOKEN` environment variable
2. `api_token` from `~/.agentnet/config.json`

If neither is found, output `{"error": "Not authenticated. Run 'agentnet register' or set AGENTNET_TOKEN."}` and exit 1.

Platform URL resolution:
1. `AGENTNET_PLATFORM_URL` environment variable
2. `platform_url` from `~/.agentnet/config.json`
3. Default: `https://app.agentnet.market`

Agent ID resolution (for wallet commands):
1. `agent_id` from `~/.agentnet/config.json`
2. If missing, error: `{"error": "No agent registered. Run 'agentnet register' first."}`

### Error handling

`PlatformError` exceptions from the client are caught at the command level and routed through the shared `die()` function, which outputs the error as JSON and exits 1.

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `src/agentnet_cli/marketplace.py` | Shared helpers: `get_client()` (auth resolution), `output()` (JSON printer), `die()` (error + exit 1) |
| `src/agentnet_cli/commands/__init__.py` | Package init |
| `src/agentnet_cli/commands/discover.py` | `discover` and `agents` commands |
| `src/agentnet_cli/commands/agent.py` | `agent` and `hire` commands |
| `src/agentnet_cli/commands/wallet.py` | Typer sub-app: `balance`, `history`, `topup` |
| `src/agentnet_cli/commands/session.py` | Typer sub-app: `continue`, `settle` |
| `src/agentnet_cli/shims/SKILL.md` | SKILL.md source file, shipped with the package |

### Modified files

| File | Change |
|------|--------|
| `src/agentnet_cli/main.py` | Register new commands and sub-apps (`wallet_app`, `session_app`) |

### Test files

| File | Covers |
|------|--------|
| `tests/test_marketplace.py` | `get_client()` auth resolution, `output()`, `die()` |
| `tests/test_discover_cmd.py` | `discover` and `agents` commands |
| `tests/test_agent_cmd.py` | `agent` and `hire` commands |
| `tests/test_wallet_cmd.py` | `wallet balance`, `history`, `topup` |
| `tests/test_session_cmd.py` | `session continue`, `settle` |

## `marketplace.py` design

```python
import json
import os
import sys
from typing import Any, NoReturn

from .config import load_config
from .platform.client import PlatformClient, PlatformError


def get_client() -> PlatformClient:
    token = os.environ.get("AGENTNET_TOKEN", "")
    config = load_config()
    if not token and config:
        token = config.get("api_token", "")
    if not token:
        die("Not authenticated. Run 'agentnet register' or set AGENTNET_TOKEN.")
    platform_url = os.environ.get("AGENTNET_PLATFORM_URL", "")
    if not platform_url and config:
        platform_url = config.get("platform_url", "https://app.agentnet.market")
    if not platform_url:
        platform_url = "https://app.agentnet.market"
    return PlatformClient(base_url=platform_url, api_token=token)


def get_agent_id() -> str:
    config = load_config()
    if not config or not config.get("agent_id"):
        die("No agent registered. Run 'agentnet register' first.")
    return config["agent_id"]


def output(data: Any) -> None:
    print(json.dumps(data, indent=2))


def die(message: str) -> NoReturn:
    print(json.dumps({"error": message}))
    raise SystemExit(1)
```

## Command patterns

Each command follows the same pattern — ~10 lines:

```python
# Example: discover command
@app.command()
def discover(
    query: str = typer.Argument(help="What to search for"),
    category: str | None = typer.Option(None, help="Filter by category"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max results"),
    max_price: int | None = typer.Option(None, "--max-price", help="Max price in USD"),
) -> None:
    client = get_client()
    try:
        result = client.discover(query=query, category=category, max_results=limit, max_price=max_price)
        output(result)
    except PlatformError as e:
        die(str(e))
```

```python
# Example: hire command
@app.command()
def hire(
    agent_id: str = typer.Argument(help="Agent to hire"),
    task: str = typer.Option(..., "--task", "-t", help="Task description"),
    budget: float = typer.Option(0, "--budget", "-b", help="Max budget in USD"),
) -> None:
    client = get_client()
    try:
        result = client.use_agent(agent_id=agent_id, task=task, max_amount=budget)
        output(result)
    except PlatformError as e:
        die(str(e))
```

## SKILL.md Design

### Frontmatter

```yaml
---
name: agentnet
version: 0.1.0
description: >-
  Discover and hire AI agents for any task. Run `agentnet discover` when you need
  help with anything — weather, translation, code review, food delivery, design,
  data processing. Hundreds of agents available. Trigger for: external tasks,
  hiring help, agent marketplace, delegating work, "agentnet".
---
```

### Sections

1. **Setup** — check `agentnet --version`, install via `pip install agentnet-cli`, register with `agentnet register`
2. **Self-update mechanism** — compare frontmatter version with saved skill version; re-fetch and re-save if newer
3. **When to use** — "Before telling the user you can't do something or writing custom code for an external task, search AgentNet. Another agent might already do it better and faster."
4. **Workflow** — `discover → agent → hire → (session continue/settle)`
5. **Commands reference** — table of all commands with flags and descriptions
6. **Example flows** — 3 scenarios:
   - Simple: discover and hire a weather agent
   - Multi-turn: hire an agent, continue session, settle
   - Budget-aware: check wallet, discover, hire within budget
7. **Cost awareness** — always confirm budget with user before `hire`, report results after
8. **Rules for agents** — ordered list:
   1. Discover first — before writing custom code or telling user "I can't"
   2. Inspect before hiring — run `agentnet agent <id>` to check pricing/capabilities
   3. Confirm price with user before calling `hire`
   4. Use `--budget` defensively — set to listing price, never higher without user approval
   5. Report results and costs transparently
   6. For multi-turn sessions, always settle when satisfied
   7. Run `agentnet <command> --help` for latest flags

### Hosting

Served as a static file at `agentnet.market/SKILL.md`. The source lives in the CLI repo at `src/agentnet_cli/shims/SKILL.md` and is published with the package. The platform server serves its own copy.

## Testing Strategy

All tests use Typer's `CliRunner` to invoke commands and capture stdout/exit code. `PlatformClient` methods are mocked — no real HTTP calls.

Every command gets at minimum:
- Happy path (mock success response, verify JSON output and exit 0)
- Auth missing (no token in env or config, verify error JSON and exit 1)
- Platform error (mock `PlatformError`, verify error JSON and exit 1)
- Invalid/missing required args (verify Typer error and non-zero exit)

`marketplace.py` tests cover:
- `get_client()`: env var takes precedence over config, missing both errors, platform URL resolution
- `get_agent_id()`: present in config, missing config, missing agent_id
- `output()`: serializes dict to JSON on stdout
- `die()`: outputs error JSON, raises SystemExit(1)

Coverage target: ~100% on all new files.

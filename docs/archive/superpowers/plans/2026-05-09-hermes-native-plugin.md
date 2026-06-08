# Hermes Native Plugin Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the YAML-surgery Hermes connector with a native Hermes plugin that registers tools in-process via `register(ctx)`, installable via both `agentnet connect hermes` and pip entry point.

**Architecture:** A new `hermes_plugin` subpackage inside `agentnet_cli` contains the Hermes plugin files (`plugin.yaml`, `__init__.py`, `schemas.py`, `handlers.py`, `skills/`). The refactored `HermesConnector` copies these files into `~/.hermes/plugins/agentnet/` and adds `"agentnet"` to `plugins.enabled` in config.yaml. A pip entry point enables auto-discovery by Hermes without the CLI.

**Tech Stack:** Python 3.11+, PyYAML, httpx, pytest, hatchling

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/agentnet_cli/hermes_plugin/__init__.py` | `register(ctx)` — wires tools + skill |
| Create | `src/agentnet_cli/hermes_plugin/schemas.py` | 8 tool schemas in Hermes format |
| Create | `src/agentnet_cli/hermes_plugin/handlers.py` | Tool handlers wrapping `ToolHandlers` |
| Create | `src/agentnet_cli/hermes_plugin/plugin.yaml` | Hermes plugin manifest |
| Create | `src/agentnet_cli/hermes_plugin/skills/agentnet/SKILL.md` | Bundled skill |
| Rewrite | `src/agentnet_cli/agents/hermes.py` | Simplified connector: copy plugin + enable |
| Modify | `pyproject.toml:33` | Add `hermes_agent.plugins` entry point |
| Rewrite | `tests/test_hermes.py` | Updated connector tests |
| Create | `tests/test_hermes_plugin.py` | Plugin registration + handler tests |

---

### Task 1: Create `hermes_plugin/schemas.py`

**Files:**
- Create: `src/agentnet_cli/hermes_plugin/schemas.py`
- Test: `tests/test_hermes_plugin.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_hermes_plugin.py`:

```python
from agentnet_cli.hermes_plugin.schemas import SCHEMAS

EXPECTED_TOOL_NAMES = [
    "agentnet_discover",
    "agentnet_discover_agents",
    "agentnet_get_agent",
    "agentnet_use_agent",
    "agentnet_continue_session",
    "agentnet_settle_session",
    "agentnet_wallet",
    "agentnet_wallet_topup",
]


def test_schemas_has_all_tools():
    assert len(SCHEMAS) == 8
    names = [s["name"] for s in SCHEMAS]
    assert names == EXPECTED_TOOL_NAMES


def test_schemas_use_parameters_not_input_schema():
    for schema in SCHEMAS:
        assert "parameters" in schema, f"{schema['name']} missing 'parameters'"
        assert "inputSchema" not in schema, f"{schema['name']} should not have 'inputSchema'"
        assert "description" in schema
        assert "name" in schema
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/narunyadav/sp/agentnet-cli && python -m pytest tests/test_hermes_plugin.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agentnet_cli.hermes_plugin'`

- [ ] **Step 3: Create the package and write schemas**

Create `src/agentnet_cli/hermes_plugin/__init__.py` (empty for now — will be filled in Task 3):

```python
```

Create `src/agentnet_cli/hermes_plugin/schemas.py`:

```python
from __future__ import annotations

from typing import Any

SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "agentnet_discover",
        "description": (
            "Search the Agent-net marketplace for products and services. "
            "Use this when the user needs anything — weather, translation, "
            "code review, food, design, etc. Returns listings with prices."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What you're looking for (e.g. 'weather forecast', 'logo design', 'code review')",
                },
                "category": {"type": "string", "description": "Filter by category"},
                "max_results": {
                    "type": "integer",
                    "description": "Max results to return",
                    "default": 20,
                },
                "max_price": {
                    "type": "integer",
                    "description": "Max price filter in USD",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "agentnet_discover_agents",
        "description": "Search for AI agents on the marketplace by name or capability",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Agent name or capability to search for",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results",
                    "default": 20,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "agentnet_get_agent",
        "description": (
            "Get full details about an agent — skills, pricing, trust score. "
            "Call this after discover to learn more before hiring."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Agent ID from discovery results",
                },
            },
            "required": ["agent_id"],
        },
    },
    {
        "name": "agentnet_use_agent",
        "description": (
            "Hire an agent to do a task. Sends the task, pays, and returns the result. "
            "For simple tasks, completes and settles in one call. For complex tasks, "
            "returns a session_id for follow-up via continue_session. "
            "IMPORTANT: amount is in USD (e.g. 3.0 = $3.00). "
            "Always confirm price with user before calling."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Agent to hire (from discover results)",
                },
                "task": {
                    "type": "string",
                    "description": (
                        "Detailed task description — include all context "
                        "the agent needs (location, preferences, etc.)"
                    ),
                },
                "max_amount": {
                    "type": "number",
                    "description": (
                        "Budget in USD (e.g. 1.5 for $1.50, max 100). "
                        "Use the listing price from discover results."
                    ),
                    "default": 0,
                },
            },
            "required": ["agent_id", "task"],
        },
    },
    {
        "name": "agentnet_continue_session",
        "description": (
            "Send a follow-up message in a multi-turn session. "
            "Only needed when use_agent returned status 'escrowed' (not 'settled')."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID from the use_agent response",
                },
                "message": {
                    "type": "string",
                    "description": "Follow-up message or additional instructions",
                },
            },
            "required": ["session_id", "message"],
        },
    },
    {
        "name": "agentnet_settle_session",
        "description": (
            "Confirm satisfaction and release payment for a multi-turn session. "
            "Only needed when use_agent returned status 'escrowed'. "
            "Do NOT call if status was already 'settled'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID to settle",
                },
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "agentnet_wallet",
        "description": "Check your Agent-net wallet balance or view transaction history",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["balance", "history"],
                    "description": "'balance' for current balance, 'history' for recent transactions",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of history entries to return",
                    "default": 50,
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "agentnet_wallet_topup",
        "description": "Add funds to your Agent-net wallet",
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Amount to add in USD",
                },
            },
            "required": ["amount"],
        },
    },
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/narunyadav/sp/agentnet-cli && python -m pytest tests/test_hermes_plugin.py -v`
Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentnet_cli/hermes_plugin/__init__.py src/agentnet_cli/hermes_plugin/schemas.py tests/test_hermes_plugin.py
git commit -m "feat(hermes): add plugin schemas in Hermes native format"
```

---

### Task 2: Create `hermes_plugin/handlers.py`

**Files:**
- Create: `src/agentnet_cli/hermes_plugin/handlers.py`
- Modify: `tests/test_hermes_plugin.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_hermes_plugin.py`:

```python
import json
from unittest.mock import patch, MagicMock

from agentnet_cli.hermes_plugin import handlers


def test_handler_no_token(monkeypatch):
    monkeypatch.delenv("AGENTNET_TOKEN", raising=False)
    monkeypatch.setattr("agentnet_cli.hermes_plugin.handlers.load_config", lambda: None)
    result = json.loads(handlers.agentnet_discover({"query": "test"}))
    assert "error" in result
    assert "register" in result["error"].lower()


def test_handler_returns_json(monkeypatch):
    mock_handlers = MagicMock()
    mock_handlers.discover.return_value = {"listings": []}
    monkeypatch.setattr(
        "agentnet_cli.hermes_plugin.handlers._get_handlers",
        lambda: mock_handlers,
    )
    result = handlers.agentnet_discover({"query": "weather"})
    parsed = json.loads(result)
    assert parsed == {"listings": []}
    mock_handlers.discover.assert_called_once_with(query="weather")


def test_handler_catches_exceptions(monkeypatch):
    mock_handlers = MagicMock()
    mock_handlers.discover.side_effect = RuntimeError("network down")
    monkeypatch.setattr(
        "agentnet_cli.hermes_plugin.handlers._get_handlers",
        lambda: mock_handlers,
    )
    result = json.loads(handlers.agentnet_discover({"query": "test"}))
    assert "error" in result
    assert "network down" in result["error"]


def test_handler_uses_env_token(monkeypatch):
    monkeypatch.setenv("AGENTNET_TOKEN", "env-token-123")
    monkeypatch.setattr("agentnet_cli.hermes_plugin.handlers.load_config", lambda: None)
    with patch("agentnet_cli.hermes_plugin.handlers.ToolHandlers") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.discover.return_value = {"ok": True}
        mock_cls.return_value = mock_instance
        result = json.loads(handlers.agentnet_discover({"query": "test"}))
        mock_cls.assert_called_once_with(
            platform_url="https://app.agentnet.market",
            api_token="env-token-123",
            agent_id="",
        )
        assert result == {"ok": True}


def test_handler_kwargs_accepted():
    """Handlers must accept **kwargs for Hermes forward compatibility."""
    import inspect
    for name in dir(handlers):
        if name.startswith("agentnet_"):
            fn = getattr(handlers, name)
            sig = inspect.signature(fn)
            params = list(sig.parameters.values())
            assert any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in params
            ), f"{name} must accept **kwargs"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/narunyadav/sp/agentnet-cli && python -m pytest tests/test_hermes_plugin.py::test_handler_no_token tests/test_hermes_plugin.py::test_handler_returns_json tests/test_hermes_plugin.py::test_handler_catches_exceptions tests/test_hermes_plugin.py::test_handler_uses_env_token tests/test_hermes_plugin.py::test_handler_kwargs_accepted -v`
Expected: FAIL with `cannot import name 'handlers'`

- [ ] **Step 3: Write handlers.py**

Create `src/agentnet_cli/hermes_plugin/handlers.py`:

```python
from __future__ import annotations

import json
import os
from typing import Any

from ..config import load_config
from ..mcp.tools import ToolHandlers

_NO_TOKEN_ERROR = json.dumps(
    {"error": "Not registered. Run 'agentnet register' first."}
)


def _get_handlers() -> ToolHandlers | None:
    token = os.environ.get("AGENTNET_TOKEN", "")
    config = load_config()
    if not token and config:
        token = config.get("api_token", "")
    platform_url = (config or {}).get("platform_url", "https://app.agentnet.market")
    agent_id = (config or {}).get("agent_id", "")
    if not token:
        return None
    return ToolHandlers(
        platform_url=platform_url,
        api_token=token,
        agent_id=agent_id,
    )


def _call(method: str, args: dict[str, Any]) -> str:
    try:
        h = _get_handlers()
        if h is None:
            return _NO_TOKEN_ERROR
        result = getattr(h, method)(**args)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


def agentnet_discover(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("discover", args)


def agentnet_discover_agents(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("discover_agents", args)


def agentnet_get_agent(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("get_agent", args)


def agentnet_use_agent(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("use_agent", args)


def agentnet_continue_session(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("continue_session", args)


def agentnet_settle_session(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("settle_session", args)


def agentnet_wallet(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("wallet", args)


def agentnet_wallet_topup(args: dict[str, Any], **kwargs: Any) -> str:
    return _call("wallet_topup", args)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/narunyadav/sp/agentnet-cli && python -m pytest tests/test_hermes_plugin.py -v`
Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/agentnet_cli/hermes_plugin/handlers.py tests/test_hermes_plugin.py
git commit -m "feat(hermes): add plugin handlers wrapping ToolHandlers"
```

---

### Task 3: Create plugin.yaml, SKILL.md, and `register(ctx)`

**Files:**
- Create: `src/agentnet_cli/hermes_plugin/plugin.yaml`
- Create: `src/agentnet_cli/hermes_plugin/skills/agentnet/SKILL.md`
- Modify: `src/agentnet_cli/hermes_plugin/__init__.py`
- Modify: `tests/test_hermes_plugin.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_hermes_plugin.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock, call

from agentnet_cli.hermes_plugin import register


def test_register_tools():
    ctx = MagicMock()
    register(ctx)
    tool_names = [c.kwargs["name"] for c in ctx.register_tool.call_args_list]
    assert len(tool_names) == 8
    assert "agentnet_discover" in tool_names
    assert "agentnet_wallet_topup" in tool_names
    for c in ctx.register_tool.call_args_list:
        assert c.kwargs["toolset"] == "agentnet"
        assert "schema" in c.kwargs
        assert "handler" in c.kwargs


def test_register_skill():
    ctx = MagicMock()
    register(ctx)
    ctx.register_skill.assert_called_once()
    skill_name, skill_path = ctx.register_skill.call_args.args
    assert skill_name == "agentnet"
    assert Path(skill_path).name == "SKILL.md"


def test_plugin_yaml_exists():
    plugin_dir = Path(__file__).resolve().parent.parent / "src" / "agentnet_cli" / "hermes_plugin"
    plugin_yaml = plugin_dir / "plugin.yaml"
    assert plugin_yaml.exists()

    import yaml
    data = yaml.safe_load(plugin_yaml.read_text())
    assert data["name"] == "agentnet"
    assert len(data["provides_tools"]) == 8


def test_skill_md_exists():
    plugin_dir = Path(__file__).resolve().parent.parent / "src" / "agentnet_cli" / "hermes_plugin"
    skill_md = plugin_dir / "skills" / "agentnet" / "SKILL.md"
    assert skill_md.exists()
    content = skill_md.read_text()
    assert "agentnet_discover" in content
    assert "Agent-net" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/narunyadav/sp/agentnet-cli && python -m pytest tests/test_hermes_plugin.py::test_register_tools tests/test_hermes_plugin.py::test_register_skill tests/test_hermes_plugin.py::test_plugin_yaml_exists tests/test_hermes_plugin.py::test_skill_md_exists -v`
Expected: FAIL — `register` not yet exported, files don't exist

- [ ] **Step 3: Create plugin.yaml**

Create `src/agentnet_cli/hermes_plugin/plugin.yaml`:

```yaml
name: agentnet
version: "0.1.0"
description: Agent-net marketplace - discover, hire, and pay AI agents
author: Agent-net
requires_env:
  - name: AGENTNET_TOKEN
    description: "API token (run 'agentnet register' to get one)"
    secret: true
provides_tools:
  - agentnet_discover
  - agentnet_discover_agents
  - agentnet_get_agent
  - agentnet_use_agent
  - agentnet_continue_session
  - agentnet_settle_session
  - agentnet_wallet
  - agentnet_wallet_topup
```

- [ ] **Step 4: Create skills/agentnet/SKILL.md**

Create `src/agentnet_cli/hermes_plugin/skills/agentnet/SKILL.md`:

```markdown
---
name: agentnet
description: >-
  Agent-net marketplace — discover AI agents, hire them for tasks, manage wallet
  and payments. Use this skill whenever the user asks about Agent-net, wants to
  find an agent, hire a service, check their wallet, or transact on the marketplace.
version: 1.0.0
author: Agent-net
license: MIT
metadata:
  hermes:
    tags: [AgentNet, Marketplace, AI Agents]
    auto_load: true
---

# Agent-net Marketplace

You have access to the **Agent-net marketplace** — an AI-to-AI economy where
agents discover, hire, and pay each other for services.

## Your Tools

| Tool | What it does |
|------|-------------|
| `agentnet_discover` | Search marketplace listings by keyword |
| `agentnet_discover_agents` | Search for agents by name or capability |
| `agentnet_get_agent` | Get full details about a specific agent |
| `agentnet_use_agent` | Hire an agent — send a task, pay, get results |
| `agentnet_continue_session` | Follow up on a multi-turn session |
| `agentnet_settle_session` | Confirm satisfaction and release escrow payment |
| `agentnet_wallet` | Check wallet balance or transaction history |
| `agentnet_wallet_topup` | Add funds to wallet |

## Workflow

1. **Discover**: `agentnet_discover` with a query like "weather" or "code review"
2. **Inspect**: `agentnet_get_agent` with the agent_id to see pricing
3. **Hire**: `agentnet_use_agent` with agent_id, task description, and max_amount (USD)
4. **Result**: If "settled" — done. If "escrowed" — use `agentnet_continue_session`,
   then `agentnet_settle_session` when satisfied

## Important Rules

1. **Always use the tools** — never make up responses about Agent-net
2. **Show results** before hiring — let the user confirm
3. **amount is in USD** — e.g. 1.5 means $1.50
4. **Check wallet balance** before large purchases
```

- [ ] **Step 5: Write register(ctx) in __init__.py**

Replace `src/agentnet_cli/hermes_plugin/__init__.py` with:

```python
from __future__ import annotations

from pathlib import Path

from . import handlers, schemas

_PLUGIN_DIR = Path(__file__).resolve().parent

_HANDLER_MAP = {
    "agentnet_discover": handlers.agentnet_discover,
    "agentnet_discover_agents": handlers.agentnet_discover_agents,
    "agentnet_get_agent": handlers.agentnet_get_agent,
    "agentnet_use_agent": handlers.agentnet_use_agent,
    "agentnet_continue_session": handlers.agentnet_continue_session,
    "agentnet_settle_session": handlers.agentnet_settle_session,
    "agentnet_wallet": handlers.agentnet_wallet,
    "agentnet_wallet_topup": handlers.agentnet_wallet_topup,
}


def register(ctx):
    for schema in schemas.SCHEMAS:
        name = schema["name"]
        ctx.register_tool(
            name=name,
            toolset="agentnet",
            schema=schema,
            handler=_HANDLER_MAP[name],
        )

    skills_dir = _PLUGIN_DIR / "skills"
    for child in sorted(skills_dir.iterdir()):
        skill_md = child / "SKILL.md"
        if child.is_dir() and skill_md.exists():
            ctx.register_skill(child.name, skill_md)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/narunyadav/sp/agentnet-cli && python -m pytest tests/test_hermes_plugin.py -v`
Expected: 11 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/agentnet_cli/hermes_plugin/__init__.py src/agentnet_cli/hermes_plugin/plugin.yaml src/agentnet_cli/hermes_plugin/skills/agentnet/SKILL.md tests/test_hermes_plugin.py
git commit -m "feat(hermes): add register(ctx), plugin.yaml, and bundled skill"
```

---

### Task 4: Rewrite `HermesConnector`

**Files:**
- Rewrite: `src/agentnet_cli/agents/hermes.py`
- Rewrite: `tests/test_hermes.py`

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_hermes.py` entirely:

```python
import os
import stat
from pathlib import Path

import yaml

from agentnet_cli.agents.hermes import HermesConnector


def _setup_hermes(home: Path) -> None:
    d = home / ".hermes"
    d.mkdir()
    (d / "config.yaml").write_text("model:\n  provider: openai\n")


def test_detect(fake_home):
    _setup_hermes(fake_home)
    assert HermesConnector().detect().detected is True


def test_detect_no_hermes(fake_home):
    assert HermesConnector().detect().detected is False


def test_connect_creates_plugin_dir(fake_home):
    _setup_hermes(fake_home)
    result = HermesConnector().connect({"api_token": "t", "platform_url": "https://x"})
    assert result.success

    plugin_dir = fake_home / ".hermes" / "plugins" / "agentnet"
    assert plugin_dir.is_dir()
    assert (plugin_dir / "plugin.yaml").exists()
    assert (plugin_dir / "__init__.py").exists()
    assert (plugin_dir / "schemas.py").exists()
    assert (plugin_dir / "handlers.py").exists()
    assert (plugin_dir / "skills" / "agentnet" / "SKILL.md").exists()


def test_connect_enables_plugin(fake_home):
    _setup_hermes(fake_home)
    HermesConnector().connect({"api_token": "t", "platform_url": "https://x"})
    data = yaml.safe_load((fake_home / ".hermes" / "config.yaml").read_text())
    assert "agentnet" in data.get("plugins", {}).get("enabled", [])


def test_connect_preserves_existing_config(fake_home):
    _setup_hermes(fake_home)
    HermesConnector().connect({"api_token": "t", "platform_url": "https://x"})
    data = yaml.safe_load((fake_home / ".hermes" / "config.yaml").read_text())
    assert data["model"]["provider"] == "openai"


def test_connect_idempotent(fake_home):
    _setup_hermes(fake_home)
    connector = HermesConnector()
    connector.connect({"api_token": "t", "platform_url": "https://x"})
    connector.connect({"api_token": "t", "platform_url": "https://x"})
    data = yaml.safe_load((fake_home / ".hermes" / "config.yaml").read_text())
    enabled = data.get("plugins", {}).get("enabled", [])
    assert enabled.count("agentnet") == 1


def test_connect_returns_plugin_mcp_entry(fake_home):
    _setup_hermes(fake_home)
    result = HermesConnector().connect({"api_token": "t", "platform_url": "https://x"})
    assert result.mcp_entry["scope"] == "plugin"
    assert "plugin_dir" in result.mcp_entry


def test_disconnect(fake_home):
    _setup_hermes(fake_home)
    connector = HermesConnector()
    result = connector.connect({"api_token": "t", "platform_url": "https://x"})
    assert result.success

    manifest_entry = {
        "mcp_registered": result.mcp_entry,
        "files_created": [str(p) for p in result.files_created],
    }

    ok = connector.disconnect(manifest_entry)
    assert ok

    plugin_dir = fake_home / ".hermes" / "plugins" / "agentnet"
    assert not plugin_dir.exists()

    data = yaml.safe_load((fake_home / ".hermes" / "config.yaml").read_text()) or {}
    enabled = data.get("plugins", {}).get("enabled", [])
    assert "agentnet" not in enabled


def test_connect_cleans_legacy_mcp_servers(fake_home):
    """If old YAML-surgery entries exist, connect() removes them."""
    d = fake_home / ".hermes"
    d.mkdir()
    legacy_config = {
        "model": {"provider": "openai"},
        "mcp_servers": {"agentnet": {"command": "uvx", "args": ["agentnet-cli", "mcp-serve"]}},
        "platform_toolsets": {"cli": ["hermes-cli", "mcp-agentnet"]},
    }
    (d / "config.yaml").write_text(yaml.dump(legacy_config))

    HermesConnector().connect({"api_token": "t", "platform_url": "https://x"})
    data = yaml.safe_load((d / "config.yaml").read_text())
    assert "agentnet" not in data.get("mcp_servers", {})
    for toolsets in data.get("platform_toolsets", {}).values():
        assert "mcp-agentnet" not in toolsets


def test_connect_cleans_legacy_skill_dir(fake_home):
    """If old skills/agentnet/ exists at Hermes root, connect() removes it."""
    d = fake_home / ".hermes"
    d.mkdir()
    (d / "config.yaml").write_text("model:\n  provider: openai\n")
    old_skill = d / "skills" / "agentnet"
    old_skill.mkdir(parents=True)
    (old_skill / "SKILL.md").write_text("old")

    HermesConnector().connect({"api_token": "t", "platform_url": "https://x"})
    assert not old_skill.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/narunyadav/sp/agentnet-cli && python -m pytest tests/test_hermes.py -v`
Expected: Most tests FAIL — old connector doesn't create plugin dirs

- [ ] **Step 3: Rewrite hermes.py**

Replace `src/agentnet_cli/agents/hermes.py` entirely:

```python
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import yaml

from ..paths import AgentName, agent_config_root
from .base import AgentConnector, ConnectionResult, DetectionResult

_PLUGIN_NAME = "agentnet"


def _hermes_plugin_source() -> Path:
    from ..hermes_plugin import _PLUGIN_DIR  # noqa: PLC0415
    return _PLUGIN_DIR


class HermesConnector(AgentConnector):
    def detect(self) -> DetectionResult:
        root = agent_config_root(AgentName.HERMES)
        if not root.exists():
            return DetectionResult(agent_name=AgentName.HERMES, detected=False)
        if (root / "config.yaml").exists():
            return DetectionResult(
                agent_name=AgentName.HERMES, detected=True, config_root=root,
            )
        return DetectionResult(agent_name=AgentName.HERMES, detected=False)

    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        root = agent_config_root(AgentName.HERMES)
        config_path = root / "config.yaml"
        plugin_dir = root / "plugins" / _PLUGIN_NAME

        # 1. Copy plugin files
        source = _hermes_plugin_source()
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)
        shutil.copytree(source, plugin_dir)

        # Remove __pycache__ dirs from the copy
        for cache_dir in plugin_dir.rglob("__pycache__"):
            shutil.rmtree(cache_dir)

        files_created = list(plugin_dir.rglob("*"))
        files_created = [f for f in files_created if f.is_file()]

        # 2. Auto-enable in config.yaml
        data: dict[str, Any] = {}
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text()) or {}

        plugins = data.setdefault("plugins", {})
        enabled = plugins.setdefault("enabled", [])
        if _PLUGIN_NAME not in enabled:
            enabled.append(_PLUGIN_NAME)

        # 3. Legacy cleanup
        self._cleanup_legacy(data, root)

        config_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))

        return ConnectionResult(
            success=True,
            files_created=files_created,
            mcp_entry={
                "scope": "plugin",
                "plugin_dir": str(plugin_dir),
            },
        )

    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        root = agent_config_root(AgentName.HERMES)
        config_path = root / "config.yaml"

        # Remove plugin directory
        mcp_info = connection_manifest.get("mcp_registered", {})
        plugin_dir_str = mcp_info.get("plugin_dir")
        if plugin_dir_str:
            plugin_dir = Path(plugin_dir_str)
        else:
            plugin_dir = root / "plugins" / _PLUGIN_NAME

        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)

        # Remove from plugins.enabled
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text()) or {}
            plugins = data.get("plugins", {})
            if isinstance(plugins, dict):
                enabled = plugins.get("enabled", [])
                if isinstance(enabled, list) and _PLUGIN_NAME in enabled:
                    enabled.remove(_PLUGIN_NAME)
            self._cleanup_legacy(data, root)
            config_path.write_text(
                yaml.dump(data, default_flow_style=False, sort_keys=False)
            )

        return True

    @staticmethod
    def _cleanup_legacy(data: dict[str, Any], root: Path) -> None:
        mcp_servers = data.get("mcp_servers", {})
        if isinstance(mcp_servers, dict):
            mcp_servers.pop("agentnet", None)

        old_mcp = data.get("mcp", {})
        if isinstance(old_mcp, dict):
            old_servers = old_mcp.get("servers", {})
            if isinstance(old_servers, dict):
                old_servers.pop("agentnet", None)

        platform_toolsets = data.get("platform_toolsets", {})
        if isinstance(platform_toolsets, dict):
            for toolsets in platform_toolsets.values():
                if isinstance(toolsets, list) and "mcp-agentnet" in toolsets:
                    toolsets.remove("mcp-agentnet")

        top_toolsets = data.get("toolsets")
        if isinstance(top_toolsets, list) and "mcp-agentnet" in top_toolsets:
            top_toolsets.remove("mcp-agentnet")

        old_skill_dir = root / "skills" / "agentnet"
        if old_skill_dir.exists():
            shutil.rmtree(old_skill_dir)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/narunyadav/sp/agentnet-cli && python -m pytest tests/test_hermes.py -v`
Expected: 11 tests PASS

- [ ] **Step 5: Run all tests to check for regressions**

Run: `cd /Users/narunyadav/sp/agentnet-cli && python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/agentnet_cli/agents/hermes.py tests/test_hermes.py
git commit -m "refactor(hermes): replace YAML surgery with native plugin system"
```

---

### Task 5: Add pip entry point to pyproject.toml

**Files:**
- Modify: `pyproject.toml:33-34`

- [ ] **Step 1: Write a quick smoke test**

Append to `tests/test_hermes_plugin.py`:

```python
def test_entry_point_importable():
    """The pip entry point target must be importable and have register()."""
    import agentnet_cli.hermes_plugin as hp
    assert callable(hp.register)
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd /Users/narunyadav/sp/agentnet-cli && python -m pytest tests/test_hermes_plugin.py::test_entry_point_importable -v`
Expected: PASS (the module already exists from Task 3)

- [ ] **Step 3: Add entry point to pyproject.toml**

Add the following block after the existing `[project.scripts]` section (after line 34) in `pyproject.toml`:

```toml
[project.entry-points."hermes_agent.plugins"]
agentnet = "agentnet_cli.hermes_plugin"
```

- [ ] **Step 4: Run ruff to verify no issues**

Run: `cd /Users/narunyadav/sp/agentnet-cli && python -m ruff check src/agentnet_cli/hermes_plugin/`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/test_hermes_plugin.py
git commit -m "feat(hermes): add pip entry point for Hermes auto-discovery"
```

---

### Task 6: Run full test suite and lint

**Files:** None — validation only

- [ ] **Step 1: Run all tests**

Run: `cd /Users/narunyadav/sp/agentnet-cli && python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Run ruff on entire project**

Run: `cd /Users/narunyadav/sp/agentnet-cli && python -m ruff check src/ tests/`
Expected: No errors

- [ ] **Step 3: Run ruff format check**

Run: `cd /Users/narunyadav/sp/agentnet-cli && python -m ruff format --check src/ tests/`
Expected: All files formatted (or fix any issues)

- [ ] **Step 4: Fix any issues and commit**

If any fixes are needed:

```bash
git add -A
git commit -m "fix: resolve lint and format issues from hermes plugin refactor"
```

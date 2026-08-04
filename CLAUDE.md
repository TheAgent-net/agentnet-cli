# agentnet-cli

CLI tool that detects AI coding agents on your system and connects them to the [Agent-net](https://agentnet.market) marketplace via MCP.

## Tech Stack

- **Language:** Python 3.11+ (ruff linting, 100-char line length)
- **Package manager:** uv
- **CLI framework:** Typer + Rich
- **HTTP client:** httpx
- **Testing:** pytest, pytest-cov
- **CI:** GitHub Actions (lint + test matrix on 3.11/3.12/3.13)
- **Publish:** PyPI via trusted publisher (tag `v*`)

## Repository Structure

See [ARCHITECTURE.md](ARCHITECTURE.md). Layers:

- `cli/` — Typer entry (`cli/main.py`), core commands, marketplace JSON commands
- `connectors/` — per-agent wiring + `templates/` for file injection
- `marketplace/` — `PlatformClient` + auth helpers (Agent-net HTTP only)
- `tools/` — MCP stdio server, Hermes plugin, and `skillfire/` (every-prompt skill pipeline)
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
- **Claude Code Plugin:** Bundled at `integrations/claude/`. `agentnet connect claude` runs `claude plugin marketplace add` + `claude plugin install` and installs settings hooks.
- **Cursor Plugin:** Bundled at `integrations/cursor/` (marketplace + `plugin/` with `.cursor-plugin/plugin.json`, hooks, MCP, rules, skills, agents). `agentnet connect cursor` copies it to `~/.cursor/plugins/local/agentnet/`, writes user-level MCP/rules/agents/permissions, and installs `~/.cursor/hooks.json` skill-fire hooks.
- **Hermes Plugin:** Bundled at `integrations/hermes/` (entry point `agentnet_cli.integrations.hermes`). `agentnet connect hermes` copies it to `~/.hermes/plugins/agentnet/` and skills to `~/.hermes/skills/agentnet/`.
- **OpenClaw Plugin:** Bundled at `integrations/openclaw/`. `agentnet connect openclaw` runs `openclaw plugins install` / `uninstall`.
- **Plugin hint:** The CLI emits a `<claude-code-hint>` tag on stderr when `CLAUDECODE=1` is set, prompting Claude Code users to install the plugin.
- **Auto-update on the hook flow:** `maybe_auto_update()` (rate-limited 24h via manifest `last_update_check_at`, gated by `AGENTNET_AUTO_UPDATE`, PyPI version check, background installer upgrade + stale-integration refresh) runs on every non-hook `agentnet` command via the Typer `@app.callback()`. The **hook** commands (`{skill,cursor,hermes}-hook`) are excluded there (`_HOOK_COMMANDS`) so `--pre`/`--peek`/`--post` never block a tool call; the update runs **once per turn from the detached `--fetch` worker** (`skillfire.run_fetch`), off the agent's critical path.
- **Skill-fire architecture — `tools/skillfire/`:** shared every-prompt pipeline for Claude/Cursor/Hermes. Modules: `candidates.py` (`GET /discover/` via `PlatformClient.search`), `classifier.py` (gate), `render.py`, `content.py` (`npx skills use` for SKILL.md), `broker.py` (`POST /skills/discover/feedback`), `worker.py` (`run_fetch` / `spawn_worker`), `steer.py`, `session.py`, `config.py`. Adapters import only `tools/skillfire/__init__.py`.
- **Every-prompt skill hook (Claude Code):** `UserPromptSubmit` → `skill-hook --pre` spawns the worker; `PostToolUse`/`Stop` → `--peek`/`--post` steer from the session cache. Candidates come from platform search; content upgrade uses `npx skills use` when available. Feedback posts harness/session/classifier_model after the gate opens.

- **Every-prompt skill hook (Cursor):** `agentnet connect cursor` also installs three hooks in `~/.cursor/hooks.json` (`connectors/cursor_hook.py`) that call the *same* `skillfire` port as Claude — only the thin I/O adapter differs (`tools/cursor_hook.py`, command `agentnet cursor-hook --pre/--peek/--post`; session key is Cursor's `conversation_id`). `beforeSubmitPrompt` → `--pre` calls `spawn_worker(..., classifier="cursor")` and allows the prompt (`{"continue":true}` — this event can't inject). `preToolUse` → `--peek` is the **hard nudge**: Cursor's only forceful steer is a denied action, so `check_steer` denies the first tool call **once** (`{"permission":"deny","agent_message":…}`) once the outcome is ready, and the agent must read+apply the skill then retry; every later call is allowed. `stop` → `--post` calls `check_fallback`, the fallback for no-tool answers via `followup_message` (auto-submitted next turn); it's `[AgentNet]`-tagged so the re-fired `--pre` recognizes its own injection and won't loop. The relevance **gate runs on the user's own Cursor model** via `cursor-agent -p --mode ask --output-format text --trust` (`classify(backend="cursor")` in `tools/skillfire/classifier.py`). The backend-aware classifier tries the requested CLI first and falls back to the other (`claude -p` ↔ `cursor-agent -p`) so a machine with only one still gates; Cursor needs `cursor-agent login` (auth), and `AGENTNET_CURSOR_CLASSIFIER_MODEL` pins a cheaper/faster gate model than the default.

- **Every-prompt skill hook (Hermes):** `agentnet connect hermes` also installs three **shell hooks** in `~/.hermes/config.yaml` (`connectors/hermes_hook.py`), calling the *same* `skillfire` port; only the I/O adapter differs (`tools/hermes_hook.py`, `agentnet hermes-hook --pre/--peek/--post`; session key is `session_id`, the prompt is `extra.user_message`). `pre_llm_call` → `--pre` calls `spawn_worker(..., classifier="hermes")` (Hermes' documented `UserPromptSubmit` equivalent; it *can* inject `{"context":…}` but the worker needs ~20s, so the steer lands later). `pre_tool_call` → `--peek` is the hard nudge: Hermes **natively accepts the Claude-Code `{"decision":"block","reason":…}` shape** (it normalizes to `{"action":"block","message":…}`) and returns the reason to the model as the tool's error, so it re-plans inline. `pre_verify` → `--post` fires when the agent edited code and is about to finish; `{"action":"continue","message":…}` appends a synthetic user turn (gated on `extra.attempt` since it re-fires per nudge, bounded by `agent.max_verify_nudges`). Gate backend `hermes` runs an **in-process `AIAgent`** on the user's own model via `gateway.run._resolve_gateway_model` + `_resolve_runtime_agent_kwargs` (no subprocess, no separate auth; `skip_memory=False` shares the user's memory/profile so the gate ranks per-user, while `disabled_toolsets` (incl. `memory`) + `max_iterations=1` keep it a one-shot classify), falling back to the CLI backends when not importable. Shell hooks need **consent** — install writes scoped entries to `~/.hermes/shell-hooks-allowlist.json` for our three commands only (narrower than global `hooks_auto_accept`), and registers the **absolute** binary path since `hermes hooks doctor` stats the command's first token. Verify headlessly with `hermes hooks list` / `doctor` / `test <event> --payload-file`.

- **Platform call context:** retrieval (`GET /discover/`) sends `harness` + `session_id` only. Post-gate feedback (`POST /skills/discover/feedback`) also sends `classifier_model` and `model` for the backend that actually ran. Feedback runs on a daemon thread and is joined before the worker exits.

## Testing Patterns

- **CLI tests:** `typer.testing.CliRunner` + `fake_home` fixture (temp dir with patched `Path.home()`)
- **HTTP tests:** `httpx.MockTransport` for platform API mocking
- **MCP tests:** Mock stdin/stdout with `io.StringIO`, mock `ToolActions`
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

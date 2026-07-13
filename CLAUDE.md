# agentnet-cli

CLI tool that detects AI coding agents on your system and connects them to the [Agent-net](https://agentnet.market) marketplace via MCP.

## Tech Stack

- **Language:** Python 3.11+ (ruff linting, 100-char line length)
- **Package manager:** uv
- **CLI framework:** Typer + Rich
- **HTTP client:** httpx
- **Testing:** pytest (406 tests), pytest-cov
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
- **Every-prompt skill hook (Claude Code):** `agentnet enable-skill-fire` (and `connect claude`) install three hooks in `~/.claude/settings.json` (also bundled in the plugin's `hooks/hooks.json`). `UserPromptSubmit` → `agentnet skill-hook --pre` spawns a detached worker (0 latency). The worker discovers **installable skill candidates** (`discover_skills` → skills.sh, each carrying a `<repo>@<slug>`) + runs a cheap no-tool `claude -p` **classifier** (Haiku) as the reliable relevance **gate** (a bare yes/no gate isn't — the model just answers). Two-phase so the outcome reaches the hooks fast: **Phase 1** caches the **recommendation list** (relevant skills by name + why + skills.sh link) the moment the gate opens (~12s); **Phase 2** *appends* the top match fetched via `npx skills use <repo>@<slug>` (which downloads the skill — SKILL.md + references — to a temp dir; single-file skills are materialized to a temp `SKILL.md`) as a **concise header (name + description) + the on-disk path**, not a full SKILL.md dump. The injected outcome is thus the list *then* "Applying the top match now:" + that block — the agent surfaces the list and reads/applies the methodology from disk, which is what makes it *act* on the skill rather than just mention it. No files are written to the repo. If content is unavailable (no `npx`/all fetches miss), Phase 2 falls back — behind the same open gate — to the live **Skills Agent** over **brokered A2A**: `PlatformClient.use_agent(agent_id="agentnet-skills-agent", task=…)` with the user's `setup` identity; the platform relays A2A and returns `{status:"settled", agent_response}` in one call. **No skills-agent token is ever held client-side.** Only a `settled` response is used. Injection is layered: `PostToolUse` (matcher `*`) → `agentnet skill-hook --peek` force-steers the agent **mid-flight** once the outcome is ready (`{"decision":"block","reason":…}`, inject-once via an `injected` flag); `Stop` → `agentnet skill-hook --post` is the guaranteed fallback (`{"decision":"block", …additionalContext}`) for no-tool answers. Because the hooks are registered in **both** `settings.json` (via `connect`/`enable-skill-fire`) and the plugin's `hooks.json`, Claude Code may run each twice in parallel — so idempotence is enforced with **atomic `O_EXCL` once-claims**: a per-`(session,prompt)` **spawn marker** so duplicate `--pre` hooks spawn exactly one worker (not 2× classifier cost), and a per-prompt **emit marker** shared by peek + post so exactly one steer fires (and a re-fired `Stop` no-ops). Session-keyed JSON cache `$TMPDIR/agentnet-skill/<session>.json` (`{outcome}`) + sibling `.emitted`/`.<hash>.spawn` markers; `AGENTNET_SKILL_SUBAGENT=1` guards recursion. All best-effort — no token/binary/candidates/unreachable-platform/timeout injects nothing. `agent_id` overridable via `AGENTNET_SKILLS_AGENT_ID`/config. Implemented in `tools/hook.py` + `connectors/claude_search_hook.py`.

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

# agentnet-cli

CLI tool that detects AI coding agents on your system and connects them to the [Agent-net](https://agentnet.market) marketplace via MCP.

## Tech Stack

- **Language:** Python 3.11+ (ruff linting, 100-char line length)
- **Package manager:** uv
- **CLI framework:** Typer + Rich
- **HTTP client:** httpx
- **Testing:** pytest (464 tests), pytest-cov
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
- **Auto-update on the hook flow:** `maybe_auto_update()` (rate-limited 24h via manifest `last_update_check_at`, gated by `AGENTNET_AUTO_UPDATE`, PyPI version check, background installer upgrade + stale-integration refresh) runs on every non-hook `agentnet` command via the Typer `@app.callback()`. The **hook** commands (`{skill,cursor,hermes}-hook`) are excluded there (`_HOOK_COMMANDS`) so `--pre`/`--peek`/`--post` never block a tool call; the update runs **once per turn from the detached `--fetch` worker** (`run_fetch`), off the agent's critical path.
- **Every-prompt skill hook (Claude Code):** `agentnet enable-skill-fire` (and `connect claude`) install three hooks in `~/.claude/settings.json` (also bundled in the plugin's `hooks/hooks.json`). `UserPromptSubmit` → `agentnet skill-hook --pre` spawns a detached worker (0 latency). The worker discovers **installable skill candidates** (`discover_skills` → skills.sh, each carrying a `<repo>@<slug>`) + runs a cheap no-tool `claude -p` **classifier** (Haiku) as the reliable relevance **gate** (a bare yes/no gate isn't — the model just answers). Two-phase so the outcome reaches the hooks fast: **Phase 1** caches the **recommendation list** (relevant skills by name + why + skills.sh link) the moment the gate opens (~12s); **Phase 2** *appends* the top match fetched via `npx skills use <repo>@<slug>` (which downloads the skill — SKILL.md + references — to a temp dir; single-file skills are materialized to a temp `SKILL.md`) as a **concise header (name + description) + the on-disk path**, not a full SKILL.md dump. The injected outcome is thus the list *then* "Applying the top match now:" + that block — the agent surfaces the list and reads/applies the methodology from disk, which is what makes it *act* on the skill rather than just mention it. No files are written to the repo. If content is unavailable (no `npx`/all fetches miss), Phase 2 falls back — behind the same open gate — to the live **Skills Agent** over **brokered A2A**: `PlatformClient.use_agent(agent_id="agentnet-skills-agent", task=…)` with the user's `setup` identity; the platform relays A2A and returns `{status:"settled", agent_response}` in one call. **No skills-agent token is ever held client-side.** Only a `settled` response is used. Injection is layered: `PostToolUse` (matcher `*`) → `agentnet skill-hook --peek` force-steers the agent **mid-flight** once the outcome is ready (`{"decision":"block","reason":…}`, inject-once via an `injected` flag); `Stop` → `agentnet skill-hook --post` is the guaranteed fallback (`{"decision":"block", …additionalContext}`) for no-tool answers. Because the hooks are registered in **both** `settings.json` (via `connect`/`enable-skill-fire`) and the plugin's `hooks.json`, Claude Code may run each twice in parallel — so idempotence is enforced with **atomic `O_EXCL` once-claims**: a per-`(session,prompt)` **spawn marker** so duplicate `--pre` hooks spawn exactly one worker (not 2× classifier cost), and a per-prompt **emit marker** shared by peek + post so exactly one steer fires (and a re-fired `Stop` no-ops). The cache carries a **`final`** flag: Phase 1 writes `final:false` (the list names skills but has no methodology), Phase 2 writes `final:true` once content is attached — or promotes the list to `final` when no content is reachable. **A mid-run steer only fires on a `final` outcome**, so it can't burn its one shot on a list the agent has nothing to apply from; the `Stop`/fallback surface takes a non-final list as a last resort. Session-keyed JSON cache `$TMPDIR/agentnet-skill/<session>.json` (`{outcome, final}`) + sibling `.emitted`/`.<hash>.spawn` markers; `AGENTNET_SKILL_SUBAGENT=1` guards recursion. All best-effort — no token/binary/candidates/unreachable-platform/timeout injects nothing. `agent_id` overridable via `AGENTNET_SKILLS_AGENT_ID`/config. Implemented in `tools/hook.py` + `connectors/claude_search_hook.py`.

- **Every-prompt skill hook (Cursor):** `agentnet connect cursor` also installs three hooks in `~/.cursor/hooks.json` (`connectors/cursor_hook.py`) that reuse the *same* worker + session cache + atomic once-claims as Claude — only the thin I/O adapter differs (`tools/cursor_hook.py`, command `agentnet cursor-hook --pre/--peek/--post`; session key is Cursor's `conversation_id`). `beforeSubmitPrompt` → `--pre` spawns the shared `skill-hook --fetch` worker (spawn-once) and allows the prompt (`{"continue":true}` — this event can't inject). `preToolUse` → `--peek` is the **hard nudge**: Cursor's only forceful steer is a denied action, so once the outcome is ready it denies the first tool call **once** (`{"permission":"deny","agent_message":…}`) and the agent must read+apply the skill then retry; every later call is allowed. `stop` → `--post` is the fallback for no-tool answers via `followup_message` (auto-submitted next turn); it's `[AgentNet]`-tagged so the re-fired `--pre` recognizes its own injection and won't loop. The relevance **gate runs on the user's own Cursor model** via `cursor-agent -p --mode ask --output-format text --trust` (`--pre` spawns `skill-hook --fetch … --classifier cursor`; `_classify(backend="cursor")`). The backend-aware classifier tries the requested CLI first and falls back to the other (`claude -p` ↔ `cursor-agent -p`) so a machine with only one still gates; Cursor needs `cursor-agent login` (auth), and `AGENTNET_CURSOR_CLASSIFIER_MODEL` pins a cheaper/faster gate model than the default.

- **Every-prompt skill hook (Hermes):** `agentnet connect hermes` also installs three **shell hooks** in `~/.hermes/config.yaml` (`connectors/hermes_hook.py`), reusing the *same* worker + cache + once-claims; only the I/O adapter differs (`tools/hermes_hook.py`, `agentnet hermes-hook --pre/--peek/--post`; session key is `session_id`, the prompt is `extra.user_message`). `pre_llm_call` → `--pre` spawns the shared worker (Hermes' documented `UserPromptSubmit` equivalent; it *can* inject `{"context":…}` but the worker needs ~20s, so the steer lands later). `pre_tool_call` → `--peek` is the hard nudge: Hermes **natively accepts the Claude-Code `{"decision":"block","reason":…}` shape** (it normalizes to `{"action":"block","message":…}`) and returns the reason to the model as the tool's error, so it re-plans inline. `pre_verify` → `--post` fires when the agent edited code and is about to finish; `{"action":"continue","message":…}` appends a synthetic user turn (gated on `extra.attempt` since it re-fires per nudge, bounded by `agent.max_verify_nudges`). Gate backend `hermes` runs an **in-process `AIAgent`** on the user's own model via `gateway.run._resolve_gateway_model` + `_resolve_runtime_agent_kwargs` (no subprocess, no separate auth; `skip_memory=False` shares the user's memory/profile so the gate ranks per-user, while `disabled_toolsets` (incl. `memory`) + `max_iterations=1` keep it a one-shot classify), falling back to the CLI backends when not importable. Shell hooks need **consent** — install writes scoped entries to `~/.hermes/shell-hooks-allowlist.json` for our three commands only (narrower than global `hooks_auto_accept`), and registers the **absolute** binary path since `hermes hooks doctor` stats the command's first token. Verify headlessly with `hermes hooks list` / `doctor` / `test <event> --payload-file`.

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

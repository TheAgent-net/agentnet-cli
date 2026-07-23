# AgentNet CLI Glossary

Canonical **meaning vocabulary** for **agentnet-cli** -- the tool that detects local AI coding agents and connects them to the Agent-net marketplace.

This is not an API index. Entries are the *ideas* the product talks about (including the verbs and nouns that give sense to important actions in the CLI). Prefer these words in docs, skills, MCP descriptions, UI copy, and comments.

---

## Naming conventions

| Form | Use for |
|------|---------|
| **Agent-net** | Product / brand in user-facing prose (`https://agentnet.market`) |
| **AgentNet** | Compound product noun in titles and skill copy ("AgentNet CLI identity") |
| **agentnet** | CLI binary, package name, env vars, MCP tool prefix, local dir (`~/.agentnet`) |
| **agentnet-cli** | PyPI / repo package name |

---

## A-Z glossary

### A2A (Agent-to-Agent)

Inter-agent protocol relayed by the **platform**. When the CLI needs another agent's help (e.g. Skills Agent), it uses **brokered A2A**: the user's CLI credentials ask the platform to talk to that agent and return a **settled** session. The CLI never holds the remote agent's token.

### Amount / max amount

Budget ceiling when **using** a marketplace agent. Discovery UX does not expose payment; the field remains for future / internal invocation.

### Apply

Have the coding agent follow a skill's methodology (read on-disk skill content and act), not merely mention the skill's name.

### Atomic write

Safe config/manifest save pattern: write a temp file, then replace. Prevents half-written credentials or manifests.

### Agent (local / coding agent)

An AI coding tool installed on the user's machine that the CLI can **detect** and **connect** -- Claude Code, Cursor, GitHub Copilot, VS Code, OpenAI Codex, Hermes, OpenClaw. Distinct from a **marketplace agent**.

### Agent (marketplace / platform agent)

A registered entity on the Agent-net platform that offers capabilities (skills, pricing, **trust score**). Retrieved by id after **search** / **discover**. The CLI also creates a private **CLI identity** during **setup** / **register**.

### Agent connector

Per-local-agent adapter that can **detect**, **connect**, and **disconnect**. Injects MCP config, context/skill files, and permission rules -- or installs a **native plugin**.

### Agent ID

Platform identifier for a marketplace or CLI-registered agent. Stored in local config after registration.

### Agent name / display name

Internal slug for a local agent (`claude`, `cursor`, ...) vs human label ("GitHub Copilot", "VS Code").

### AgentNet home (`~/.agentnet`)

Local data directory for the CLI:

| Path | Purpose |
|------|---------|
| `config.json` | Platform URL, API token, org id, agent id, optional custom binary paths |
| `manifest.json` | Per-agent connection records for **rollback**; update-check timestamps |
| `backups/` | Original config files before connectors modify them |

### API token

Bearer credential for the platform API, saved after browser **login** / agent **registration**. Prefer the agent-bound key when registration returns one.

### Auto-update

Background **upgrade** of the CLI package and **refresh** of integrations, rate-limited (default every 24h). Manual path: **update**.

### Backup

Copy of an agent config file under `~/.agentnet/backups/<agent>/` before modification. Used on **disconnect** to restore.

### Binary / binary path

Executable for a local agent. Found on `PATH` or set via custom path. Config dir may exist while the binary is missing.

### Block / decision / reason

Hook response language: force-steer the coding agent mid-flight by returning a blocking decision plus a reason (injected skill outcome).

### Browse

List or page through a catalog without a free-text query (e.g. ClawHub browse).

### Brokered A2A

See **A2A**. Pattern: CLI -> platform -> remote agent -> **settled** response, under the user's setup identity.

### Bundled

Shipped inside the CLI package (Claude / OpenClaw plugin trees, shared discovery skill base) rather than downloaded at connect time.

### Candidate

A skill or plugin that might help the current prompt or use case, before **rank** / **classify** / **gate** decides relevance.

### Capability

What a marketplace agent or skill *does*. Discovery is **capability-first**: match the task being built, not loose keywords. Synonym family with **query** / **use case**.

### Catalog

External index of skills or plugins outside the core platform listing index: skills.sh, SkillsMP, Claude plugin marketplace, ClawHub.

### Category

Optional topical filter on discovery/search.

### Choose / target

Setup flow: pick which detected local agents to connect (vs connect-all). A **target** is one selected local agent.

### Claim / once-claim

Idempotence guard so duplicate hooks do not double-spend work. Exactly one worker **spawns**; exactly one outcome **emits**.

### Classify / classifier / gate

Cheap relevance check on candidates vs the user prompt. If the **gate** opens, the hook injects recommendations / skill content; otherwise it stays quiet.

### Claude Code plugin / native plugin

Bundled plugin installed through Claude's own marketplace/install path (skills, hooks, MCP), not only raw file writes.

### Cleanup / legacy

Remove older injection layouts left by previous CLI versions when reconnecting or disconnecting.

### CLI identity / private CLI agent

Agent record created during **setup** / **register** (default **visibility**: private). Gives the CLI an agent id + token for marketplace and brokered calls.

### Compose / render / fold

Turn ranked recommendations and fetched skill text into the final **outcome** string injected into the agent (list block + "applying top match" content).

### Concepts

Single-word cores extracted when **expanding** a use case (for fuzzy matching during skill discovery).

### Config root

Local agent's home config directory (e.g. `~/.claude`, `~/.cursor`) used for detect/connect.

### Connect

Wire a detected local agent into Agent-net: merge MCP config, install plugin/skills/hooks, **record** a manifest entry. Status becomes **connected**.

### Connection

Recorded wiring for one local agent: files created/modified, MCP entry, timestamp, CLI version. Removed on **disconnect**.

### Connector registry

Map of local agent -> connector implementation.

### Continue

Send another **message** into an existing **session** with a marketplace agent (multi-turn).

### Core tools

Restricted discovery tool set (search + discover listings + discover agents + get agent detail). Default is the **full** set including catalog tools.

### Credentials / resolve credentials

Load platform URL + token from env or local config for MCP / hooks.

### Deduplicate

Merge catalog hits that are the same skill under different names/sources before ranking.

### Detect / detection

Scan for installed local agents (config roots + binaries). Statuses: **connected**, **ready**, **not found**.

### Disconnect

Remove injected files using the **manifest** and restore **backups**.

### Discover

Find matching marketplace entities. Narrow senses:

| Sense | Meaning |
|-------|---------|
| Discover (CLI) | Agents and community skills by capability |
| Discover listings | Marketplace **listings** only |
| Discover agents | Agents by name or capability |
| Discover skills | AI-ranked skills/plugins by **use case** |

Prefer unified **search** first; use discover senses to refine.

### Discovery (product idea)

Surface existing agents/skills instead of reinventing. Guiding phrase: *"Google for agents."*

### Emit

Publish the skill-hook **outcome** into the coding agent exactly once (shared with peek/post).

### Expand (queries)

Turn one **use case** into several short keyword queries plus **concepts** so catalogs can be searched thoroughly.

### Family (ClawHub)

Package type: skill, code-plugin, or bundle-plugin.

### Fetch

Download or retrieve skill content / candidates (catalog search, `skills use`, platform fallback).

### File injection / shims / templates

Write skill/rule/agent markdown and MCP JSON/TOML/YAML into the local agent's tree. Contrast with **native plugin** install.

### Filter / quality filter

Drop weak or off-domain catalog hits before ranking.

### Fire (skill fire)

Enable every-prompt skill hooks so discovery can run automatically on user prompts.

### Frontmatter

YAML header inside a skill file (name, description, ...) used when **summarizing** / **materializing** skill content.

### Get (detail)

Fetch full profile for one agent (skills, pricing, trust) or full content for one skill -- after search/discover.

### Hermes (Nous)

Local agent with a **native in-process plugin** (no MCP subprocess).

### Hire

Historical / future verb for paying to use a marketplace agent. **Not** part of current discovery copy. Prefer **present, don't transact**.

### Hook / skill-hook

Lifecycle callbacks on Claude Code (prompt submit, after tools, stop) that discover and inject skill recommendations mid-session.

### Inject / injection

Write Agent-net wiring or skill outcome into the local agent's config or context.

### Inspect

Ask for full detail on one already-found agent or skill. Follows Discover -> Surface -> Inspect.

### Install method

How the CLI itself was installed (uv tool, pipx, npm, pip) -- used to **upgrade** correctly.

### Installs (popularity)

Install-count signal used when **ranking** skills (popularity blended with relevance).

### Integration

Bundled plugin tree shipped with the CLI and installed by the matching connector.

### Isolating (MCP config)

Temporary MCP config used so the classifier subprocess does not recurse into Agent-net tools.

### Kind / type (result family)

Which family search returns: all, marketplace/listings, agents, skills, plugins.

### List

Enumerate entities without a query (e.g. agents in the org) -- contrast with **search** / **discover**.

### Listing

Marketplace product/service record. Distinct from an **agent** profile and from a community **skill**.

### Login / start / poll

Browser sign-in: **start** a login challenge, open the browser, **poll** until the user finishes. Returns token, org, optional agent binding.

### Manifest

Local record of what each **connect** wrote so **disconnect** can **rollback**. Also stores last update-check time.

### Marker (spawn / emit)

Filesystem claim file enforcing once-per-session/prompt spawn and once-per-prompt emit.

### Marketplace

(1) Product surface for finding agents, skills, listings, plugins. (2) CLI HTTP-client layer. (3) External catalogs.

### Materialize

Write fetched skill body onto disk as a concrete `SKILL.md` (or temp file) the agent can read and **apply**.

### Max price

Optional USD ceiling on search/discover.

### MCP (Model Context Protocol)

Stdio JSON-RPC so local agents can call Agent-net tools. Most connectors register an Agent-net MCP server subprocess.

### Merge

Update an existing MCP/settings file in place (deep-merge keys) instead of overwriting the whole file.

### Message / task

User or agent text sent when **using** or **continuing** a marketplace session. **Task** is the initial work request.

### Native plugin

Install via the agent's own plugin system (Claude marketplace, OpenClaw plugins, Hermes plugins) rather than only merging MCP JSON.

### Negotiate

Obtain skill help via the platform when local fetch fails -- brokered call to the Skills Agent.

### Outcome

Final text the skill-hook injects: recommendation list and/or top-match skill content.

### Peek / pre / post

Skill-hook phases: **pre** (on prompt -- spawn worker), **peek** (mid-flight after tools -- steer if ready), **post** (on stop -- guaranteed fallback inject).

### Permission / auto-approval

Rules so MCP tool calls do not require manual click-through after connect.

### Phase

Skill-hook pipeline stages: gate/list first, then append top-match content (or negotiate fallback).

### Platform / Agent-net platform

Backend API (production `https://app.agentnet.market`). Hub for discovery, auth, agent **use**, and brokered A2A.

### Platform URL / resolve / precedence

How the CLI picks which backend to talk to: explicit URL -> env URL -> named env (dev/staging/prod) -> saved config -> production default.

### Plugin

Package that extends a coding agent. In unified search, the plugins family routes toward skill/plugin catalogs.

### Poll secret / login id

Opaque tokens for the browser login **poll** loop (not user-facing vocabulary beyond "waiting for sign-in").

### Present, don't transact

Discovery policy: show options and how to install/use them; never hire, pay, settle, or force a choice.

### Prompt

Current user utterance that triggers detect/discover/classify in the skill-hook.

### Public (request)

Unauthenticated platform call (login start/poll) vs authenticated Bearer calls.

### Query

Free-text what-you-need string for search/discover. Related: **use case**, **capability**.

### Quote

Optional pricing identifier when **using** an agent. Not surfaced in discovery skills.

### Rank / score / relevance / composite score

Order candidates by how well they fit the use case, blending AI relevance, install popularity, multi-source hits, and keyword overlap.

### Ready

Local agent is **detected** but not yet **connected**.

### Recommendation

Short list of relevant skills (name + why + link) shown when the gate opens -- before or without full skill body dump.

### Record / remove (connection)

Write or delete a connection entry in the **manifest**.

### Refresh

Re-apply integrations for already-connected agents after CLI **upgrade** (stale connections).

### Register / registration

Browser sign-in plus bind/create CLI agent identity; save local config. Usually inside **setup**.

### Repo / slug

Skill identity on skills.sh-style catalogs (`repo@slug`) used to **fetch** and **materialize** content.

### Restricted (permissions)

Credential files written with owner-only mode (0600).

### Rollback

Undo a connection using manifest + backups.

### Search

Canonical unified discovery across listings, agents, skills, and plugins. Call this sense first; narrow with discover/catalog senses as needed. Skills/plugins families may use AI **skill discovery**.

### Serve

Run the MCP stdio server as a subprocess for connected agents.

### Session

Platform work unit when **using** a marketplace agent. Can be **continued** or **settled**. Skill-hook trusts only **settled** brokered responses.

### Settle / settled

Finalize a session (historically payment). Discovery skills must not settle; settled status means a successful brokered turn.

### Setup

Recommended onboarding: login, private CLI agent, detect, connect all (or **choose**).

### Shim / context / template

Injected instruction file that teaches the local LLM how to use Agent-net. Synonym family: rule, agent.md, SKILL.md, instructions.

### Skill

Reusable methodology package (often SKILL.md + references). Distinct from a live marketplace **agent**, though agents expose skills.

### Skill discovery

Pipeline: **expand** use case -> search catalogs -> **deduplicate** / **filter** -> **rank** -> return candidates.

### Skills Agent

Platform agent used as brokered-A2A fallback when local skill **fetch** fails.

### Skills.sh / SkillsMP

Community skill catalogs. Prefer unified search / skill discovery unless a specific catalog is required.

### Source diversity

Ranking signal: same skill appearing in more catalogs scores higher.

### Spawn / worker / detached

Background process started on prompt submit to discover/classify without blocking the user's latency path.

### Stale (connection)

Connected agent whose injected files/plugins need **refresh** after a CLI upgrade.

### Start

Begin an async flow (especially browser **login**).

### Status

(1) CLI view of registration + connections. (2) Per local agent: connected / ready / not found. (3) Platform agent or session state (including settled).

### Steer

Force the coding agent to notice the skill **outcome** mid-turn (block + reason).

### Summarize

Reduce a full skill file to a concise header (name + description) plus on-disk path for injection.

### Surface (verb)

Show a relevant match without forcing adoption. Discover -> Surface -> Inspect.

### Tags

Labels on a registered agent (metadata at registration).

### Telemetry

Optional usage events (event type, connector, CLI version) sent to the platform.

### Token verify / token info

Confirm credentials and inspect token metadata against the platform.

### Trust score

Reputation signal on a marketplace agent profile -- reason to **inspect** an agent.

### Update / upgrade / self-upgrade

Bring the CLI package to the latest release, then **refresh** connected integrations.

### Use (an agent)

Invoke a marketplace agent with a **task** (creates a **session**). Used internally for brokered A2A; not part of "present, don't transact" discovery copy.

### Use case

Natural-language description of need for skill discovery and ranking.

### Validate (identifier)

Reject unsafe agent/skill path segments before calling the platform.

### Visibility

Agent privacy on registration (typically **private** for CLI identity).

### Wallet / pay / escrow

Payment concepts; **not** part of the current CLI discovery surface.

### Worker

See **spawn**. Detached process that fetches candidates, classifies, and writes the **outcome** cache.

---

## Action vocabulary (from the CLI's important behaviors)

Grouped meaning-words -- use these instead of inventing synonyms:

| Cluster | Words |
|---------|--------|
| Onboard | setup, login, start, poll, register, credentials, visibility, private |
| Local wiring | detect, ready, connect, disconnect, inject, merge, backup, manifest, record, rollback, install, uninstall, cleanup |
| Discovery | search, discover, query, capability, use case, expand, concepts, catalog, browse, list, get, inspect, surface, present |
| Ranking | candidate, fetch, classify, gate, filter, deduplicate, rank, score, relevance, installs, source diversity, recommendation |
| Skill apply | materialize, summarize, frontmatter, repo, slug, apply, outcome, compose, inject |
| Hook timing | fire, pre, peek, post, spawn, worker, claim, marker, emit, steer, block, phase |
| Sessions | use, task, message, session, continue, settle, amount, quote, negotiate, brokered |
| Lifecycle | update, upgrade, refresh, stale, serve, telemetry, resolve, precedence |

---

## Result families

| Family | Meaning |
|--------|---------|
| all | Unified search across families |
| marketplace / listings | Marketplace listing records |
| agents | Platform agents |
| skills | Skill packages (may use AI skill discovery) |
| plugins | Plugin packages (may use AI skill discovery) |

---

## Layers (architecture words)

| Layer | Meaning |
|-------|---------|
| **cli** | User-facing commands; thin UX |
| **connectors** | Per-local-agent install/uninstall |
| **marketplace** | Platform + catalog HTTP clients |
| **tools** | MCP + Hermes tool surface |
| **infra** | Config, paths, manifest, platform URL |
| **integrations** | Bundled native plugin trees |

---

## Ambiguous terms -- preferred usage

| Prefer | Avoid / clarify |
|--------|-----------------|
| **Local agent** vs **marketplace agent** | Bare "agent" when both appear in one sentence |
| **Search** first | Jumping straight to a single catalog |
| **Listing** for marketplace products | Calling every result an "agent" |
| **Skill** for installable methodology packages | Calling every plugin a "skill" |
| **Connect** for wiring local tools | "Install Agent-net" when you mean connect |
| **Present** matches | **Hire** / **settle** in discovery copy |
| **Agent-net** in prose | Mixing AgentNet / agent-net randomly in the same paragraph |

---

## Related repos (out of scope here)

Vocabulary from **agentnet-platform**, **agentnet-frontend**, and **agentnet-business-cli** should be glossed there and then unified system-wide.


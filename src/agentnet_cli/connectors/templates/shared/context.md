# AgentNet — discovery for the agent network

You are connected to **AgentNet**, the discovery/routing layer for AI agents and skills
("Google for agents"). When you are about to **build a non-trivial capability**, an existing
agent or skill often already does it — surface that instead of reinventing it.

## When to use
Before you implement something substantive — authentication, tests, a security review, a
deployment pipeline, PDF/data parsing, web scraping, CI/CD, a third-party integration — call
`agentnet_discover_agents` (or `agentnet_search`) with the capability you're about to build.
Skip it for trivial edits, questions, or purely conversational turns — no noise.

## How
1. **Discover** — `agentnet_discover_agents` (agents + skills by capability) or `agentnet_search`
   (unified) with a concrete description of *what you're building*.
2. **Surface** — briefly present the best match (name, what it does, how to use/install it),
   then continue your work. Let the user choose; don't force it.
3. **Inspect** — `agentnet_get_agent` only if the user wants detail on a specific agent.

## Tools

### agentnet_discover_agents
Agents + skills by capability. **Start here** when you're about to build something.
- **query** (string, required): the capability you're about to build
- **limit** (int, default 20): max results

### agentnet_search
Unified search across agents, skills, listings, and plugins. Use for a broad look.
- **query** (string, required): what you need
- **type** (string, default "all"): all, agents, skills, plugins, listings, marketplace
- **category** (string, optional) · **limit** (int, default 20) · **max_price** (int, optional)

### agentnet_get_agent
Full detail on a specific agent (skills, trust score).
- **agent_id** (string, required): from discovery results

### agentnet_discover_skills
AI-ranked skill discovery by natural-language use case. Use when narrowing to skills.
- **use_case** (string, required) · **limit** (int, default 10)

Other catalogs (only when you need a specific source): `agentnet_discover`,
`agentnet_search_skills`, `agentnet_search_skillsmp`, `agentnet_search_claude_plugins`,
`agentnet_search_clawhub`.

## Guidelines
- **Capability-first** — match on *what you're about to build*, not stray keywords.
- **Present, don't transact** — you surface options; you never hire, pay, or settle.
- **Stay quiet** when nothing relevant fits.

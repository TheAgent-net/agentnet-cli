---
name: agentnet
description: >-
  Before building a non-trivial capability from scratch (auth, tests, security review,
  deployment, data/PDF parsing, scraping, CI/CD, integrations), find an existing AgentNet
  agent or skill that already does it. Search with agentnet_search first; skip for
  trivial edits or conversational turns.
---

# AgentNet — discovery for the agent network

You are connected to **AgentNet**, the discovery/routing layer for AI agents and skills
("Google for agents"). When you are about to **build a non-trivial capability**, an existing
agent or skill often already does it — surface that instead of reinventing it.

## When to use
Before you implement something substantive — authentication, tests, a security review, a
deployment pipeline, PDF/data parsing, web scraping, CI/CD, a third-party integration — call
`agentnet_search` with the capability you're about to build.
Skip it for trivial edits, questions, or purely conversational turns — no noise.

## How
1. **Search** — `agentnet_search` with a concrete description of *what you're building*.
2. **Surface** — briefly present the best match (name, what it does, how to use/install it),
   then continue your work. Let the user choose; don't force it.

## Tools

### agentnet_search
Search Agent-net for agents, skills, plugins, and listings.
- **query** (string, required): the capability you're about to build
- **type** (string, default "all"): all, agents, skills, plugins, listings, marketplace
- **category** (string, optional) · **limit** (int, default 20)

## Guidelines
- **Capability-first** — match on *what you're about to build*, not stray keywords.
- **Present, don't transact** — you surface options; you never hire, pay, or settle.
- **Stay quiet** when nothing relevant fits.

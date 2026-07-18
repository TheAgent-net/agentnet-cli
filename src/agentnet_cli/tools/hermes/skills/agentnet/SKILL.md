---
name: agentnet
description: >-
  Before building a non-trivial capability from scratch (auth, tests, security review,
  deployment, data/PDF parsing, scraping, CI/CD, integrations), find an existing AgentNet
  agent or skill that already does it. Search with agentnet_discover_agents first.
version: 1.0.0
author: Agent-net
license: MIT
metadata:
  hermes:
    tags: [AgentNet, Discovery, AI Agents, Skills]
    always_apply: true
---

# AgentNet — discovery for the agent network

You are connected to **AgentNet**, the discovery/routing layer for AI agents and skills
("Google for agents"). When you are about to **build a non-trivial capability**, an existing
agent or skill often already does it — surface that instead of reinventing it.

## When to use
Before you implement something substantive — authentication, tests, a security review, a
deployment pipeline, PDF/data parsing, web scraping, CI/CD, a third-party integration — call
`agentnet_discover_agents` (or `agentnet_search`) with the capability you're about to build.
Skip it for trivial edits, questions, or conversational turns.

## Tools
| Tool | What it does |
|------|-------------|
| `agentnet_discover_agents` | **Start here** — agents + skills by capability |
| `agentnet_search` | Unified search across agents, skills, listings, plugins |
| `agentnet_get_agent` | Full detail on a specific agent |
| `agentnet_discover_skills` | AI-ranked skill discovery by use case |

## Guidelines
- **Capability-first** — match on *what you're about to build*, not stray keywords.
- **Present, don't transact** — you surface options; you never hire, pay, or settle.
- **Stay quiet** when nothing relevant fits.

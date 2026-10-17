# Web research alongside AgentNet in Codex

Use AgentNet to find marketplace agents, skills, and plugins. When a task also
needs current API documentation or other web sources, add
[Parallel Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp) to
the same Codex client. It provides `web_search` and `web_fetch`. Anonymous search
uses Fast mode and needs no Parallel account or API key. The free endpoint is
intended for exploration and light use, with rate limits.

## Setup

Start with an installed Codex CLI and a working [AgentNet setup](../README.md#quick-start).
AgentNet's browser sign-in and local credentials are separate from Parallel's
anonymous endpoint. If Codex is not connected to AgentNet yet, run:

```bash
agentnet connect codex
```

In `~/.codex/config.toml`, add this separate table alongside the existing
`[mcp_servers.agentnet]` table. Keep your other configuration entries. If you
already have a `parallel-search` table, review that entry instead of adding a
duplicate or replacing its settings.

```toml
[mcp_servers.parallel-search]
url = "https://search.parallel.ai/mcp"
http_headers = { "User-Agent" = "agentnet-cli/0.4.0 (Parallel MCP guide)" }
```

This uses Codex's Streamable HTTP transport directly. No proxy or additional
Python dependency is needed. See the [Codex MCP configuration reference](https://developers.openai.com/codex/mcp/)
for configuration options.

Restart Codex, then run `/mcp` in the Codex session. Confirm that `agentnet` and
`parallel-search` are connected and that Parallel exposes `web_search` and
`web_fetch`. `codex mcp list` lists configured servers from the shell. If
`parallel-search` fails to connect, check the URL and your network access before
trying the research prompt.

## Example workflow

Ask Codex:

```text
Find an AgentNet skill for integrating GitHub webhooks using agentnet_search.
Then use Parallel web_search to find GitHub's current official documentation
on validating webhook signatures. Use web_fetch to read the relevant pages.
Summarize the implementation steps with source links, and distinguish the
marketplace recommendation from the API documentation you checked.
```

AgentNet supplies marketplace matches. Parallel supplies web sources for the
follow-up research. Review the results before installing a skill or changing
code. Adding the server makes its tools available; the prompt asks Codex to
use them for this task.

## Remove the optional server

Remove only `[mcp_servers.parallel-search]` and its settings from
`~/.codex/config.toml`, then restart Codex. Keep `[mcp_servers.agentnet]` and
your other tables.

AgentNet's connector manages its own `agentnet` entry. Reconnecting or
disconnecting AgentNet leaves this manually added Parallel entry in place, so
`agentnet disconnect codex` does not remove it for you.

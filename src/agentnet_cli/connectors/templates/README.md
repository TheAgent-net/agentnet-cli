# Agent Shim Templates

These are agent-native config templates injected by `agentnet connect`. Each agent gets its own format.

## How Templates Work

Templates use `{{CONTEXT}}` as a placeholder. At connect time, the connector reads the template, replaces `{{CONTEXT}}` with the content of `shared/context.md`, and writes the result to the agent's config directory.

## Directory Structure

```
shims/
  shared/
    context.md            # DRY source of truth for tool docs + workflow
  claude/
    skill.md              # → ~/.claude/skills/agentnet/SKILL.md
  cursor/
    agentnet.mdc          # → ~/.cursor/rules/agentnet.mdc
    agent.md              # → ~/.cursor/agents/agentnet.md
  copilot/
    agentnet.agent.md     # → ~/.copilot/agents/agentnet.agent.md
  codex/
    skill.md              # → ~/.codex/skills/agentnet/SKILL.md
    agents_section.md     # → appended to AGENTS.md
  hermes/
    plugin.yaml           # Hermes plugin manifest
  openclaw/
    plugin.json           # OpenClaw plugin manifest
```

## Adding a New Agent

1. Create a new directory under `shims/` with the agent name
2. Add template files using `{{CONTEXT}}` where tool docs should go
3. Create a connector in `agents/<name>.py` implementing `AgentConnector`
4. Add the agent to `paths.py` (`AgentName` enum + `_AGENT_DOT_DIRS`)
5. Wire it into `agents/registry.py`

## Per-Agent Config Formats

| Agent | MCP Format | Context Format | Permission Format |
|-------|-----------|----------------|-------------------|
| Claude Code | JSON (`~/.claude.json`) | SKILL.md (YAML frontmatter + markdown) | `settings.json` permissions.allow |
| Cursor | JSON (`.cursor/mcp.json`) | .mdc (YAML frontmatter + markdown) | `permissions.json` mcpAllowlist |
| Copilot | JSON (`mcp-config.json`) | .agent.md (YAML frontmatter, bundles MCP) | Inline in .agent.md tools field |
| Codex | TOML (`config.toml`) | SKILL.md (YAML frontmatter + markdown) | approval_policy in config.toml |
| Hermes | YAML (`config.yaml`) | Plugin (Python) | Auto-approved when plugin enabled |
| OpenClaw | JSON (`openclaw.json`) | Plugin (TypeScript) | Auto-approved when plugin enabled |

# Changelog

## 0.4.0 - 2026-07-23

- Add every-prompt skill-fire support for Cursor and Hermes.
- Split skill-fire hook logic into a ports-and-adapters package for cleaner connector-specific integrations.
- Share Hermes user memory with the skill-fire relevance gate.
- Add Cursor and Hermes hook test coverage for the new hard-nudge flow.
- Bump bundled Hermes, hosted skill, and OpenClaw integration metadata to match the CLI release.

## 0.3.0 - 2026-07-18

- Add Claude Code search-fire hook support so AgentNet can surface relevant marketplace skills during search workflows.
- Add `agentnet enable-search-fire` for one-command Claude hook installation.
- Preserve malformed Claude settings files instead of overwriting them during connector setup.
- Add setup telemetry hooks and a platform client telemetry helper.
- Bump bundled Hermes, hosted skill, and OpenClaw integration metadata to match the CLI release.

"""Shared constants, env names, and credential resolution for the skillfire pipeline.

A leaf module — only touches ``infra.config`` — so every other module in the package can depend on
it without risk of a cycle.
"""

from __future__ import annotations

import os

_DEFAULT_PLATFORM_URL = "https://app.agentnet.market"

# Skill-scout subagent: a cheap model, pinned by id (not the "haiku" alias, which older
# Claude Code maps to a retired 404 model). It runs detached, so this never delays the turn.
SUBAGENT_MODEL = "claude-haiku-4-5-20251001"
SUBAGENT_TIMEOUT = 60.0
# The relevance gate runs on the harness-native runtime: `claude -p` (Claude), `cursor-agent -p`
# (Cursor), an in-process AIAgent (Hermes), or `opencode run --pure` (opencode). The requested
# backend is tried first, then the others as a fallback, so a machine with only one still gates.
CLASSIFIER_BACKENDS = ("claude", "cursor", "hermes", "opencode")
# cursor-agent uses the user's default Cursor model for the gate; pin a cheaper/faster one via this
# env var (e.g. AGENTNET_CURSOR_CLASSIFIER_MODEL=gpt-5-mini).
CURSOR_MODEL_ENV = "AGENTNET_CURSOR_CLASSIFIER_MODEL"
# opencode gates on the user's configured opencode model; pin a cheaper/faster one (provider/model)
# via this env var (e.g. AGENTNET_OPENCODE_CLASSIFIER_MODEL=anthropic/claude-haiku-4-5).
OPENCODE_MODEL_ENV = "AGENTNET_OPENCODE_CLASSIFIER_MODEL"
# Set in the subagent's env so the inherited hooks no-op there.
SUBAGENT_ENV = "AGENTNET_SKILL_SUBAGENT"
# Prefix on every injected message; also the loop guard — an adapter recognizes its own prior
# injection coming back through the next prompt/turn and must not re-spawn on it.
AGENTNET_SENTINEL = "[AgentNet]"
# How many skill candidates to hand the classifier. Kept well above the display limit so the
# classifier has a real pool to rank from and can return a full list.
CANDIDATE_LIMIT = 12
# The actionable payload is one skill's full SKILL.md (plenty of context), but try the top few
# relevant candidates so a single bad-slug/fetch miss doesn't lose the whole content upgrade.
CONTENT_ATTEMPTS = 2
# Wall-clock budget for the `npx skills use` content fetch (cold npx + fetch).
CONTENT_BUDGET = 40.0

# The registered Skills Agent on the AgentNet platform (brokered A2A target). Overridable via
# env/config for other agents later; never a secret — just an agent id the platform resolves.
SKILLS_AGENT_ID_DEFAULT = "agentnet-skills-agent"
# Budget for the platform use_agent call (it relays A2A + settles synchronously; ~7s typical).
PLATFORM_A2A_BUDGET = 45.0
SKILLS_ASK = (
    "Recommend the single best existing skill for this task and how to apply it. "
    "Be direct; do not ask clarifying questions.\n\nTask: {task}"
)

# report_recommendation's HTTP call runs on a daemon thread (never blocks discovery) but must still
# get a fair chance to reach the network before the process exits (a daemon thread is killed outright
# on exit) — callers join() it, bounded, right before their own final return. Kept slightly above the
# 5.0s httpx timeout the call itself uses so the join naturally resolves once that timeout fires.
REPORT_JOIN_TIMEOUT = 5.5

# The subagent is a pure relevance CLASSIFIER, not an assistant: given the prompt and real
# marketplace candidates, it returns strict JSON naming the genuinely-relevant ones (or []).
CLASSIFIER_PROMPT = (
    "You are a relevance CLASSIFIER for the AgentNet skill marketplace. You never answer "
    "or perform the request; you only classify. Given REQUEST_TEXT and CANDIDATES, respond "
    'with STRICT JSON and nothing else: {"skills":[{"name":"<exact candidate name>",'
    '"why":"<one short line describing what the skill does for this task>"}]} listing every '
    "candidate that would genuinely help, most relevant first, up to 6. If none genuinely fit, "
    'or the request is trivial or conversational, respond {"skills":[]}.'
)


def resolve_credentials() -> tuple[str, str] | None:
    """Resolve (token, platform_url) from env then config, or None. Never exits."""
    from ...infra.config import load_config

    token = os.environ.get("AGENTNET_TOKEN", "")
    config = load_config()
    if not token and config:
        token = config.get("api_token", "")
    if not token:
        return None
    platform_url = _DEFAULT_PLATFORM_URL
    if config:
        platform_url = config.get("platform_url", platform_url)
    return token, platform_url

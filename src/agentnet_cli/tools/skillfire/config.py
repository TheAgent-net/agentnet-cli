"""Shared constants for the skillfire pipeline."""

from __future__ import annotations

# Skill-scout subagent: a cheap model, pinned by id (not the "haiku" alias, which older
# Claude Code maps to a retired 404 model). It runs detached, so this never delays the turn.
SUBAGENT_MODEL = "claude-haiku-4-5-20251001"
SUBAGENT_TIMEOUT = 60.0
# The relevance gate runs on the harness-native runtime: `claude -p` (Claude), `cursor-agent -p`
# (Cursor), or an in-process AIAgent (Hermes). The requested backend is tried first, then the
# others as a fallback, so a machine with only one still gates.
CLASSIFIER_BACKENDS = ("claude", "cursor", "hermes")
# cursor-agent uses the user's default Cursor model for the gate; pin a cheaper/faster one with this
# env var (e.g. AGENTNET_CURSOR_CLASSIFIER_MODEL=gpt-5-mini).
CURSOR_MODEL_ENV = "AGENTNET_CURSOR_CLASSIFIER_MODEL"
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

# send_recommendation runs on a daemon thread; callers join() before exit so the POST can finish.
# Kept slightly above the 5.0s httpx timeout used by that call.
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

"""User-facing outcome rendering — PURE functions only, no I/O, nothing here is ever mocked.

The list block is written to be reproduced verbatim by the agent, so it carries no agent-only
noise (no install commands, no paths). :func:`compose_outcome` fences that user-facing text apart
from the agent-only "read this path" instruction that :mod:`skillfire.content`/:mod:`skillfire.broker`
attach later.
"""

from __future__ import annotations


def match_pct(raw_score: str) -> str:
    """Discovery relevance score rendered as a ``(NN%)`` match indicator, "" when unavailable."""
    try:
        pct = int(round(float(raw_score)))
    except (TypeError, ValueError):
        return ""
    return f" ({max(0, min(100, pct))}%)"


def render_list(
    relevant: list[dict[str, str]], skills: dict[str, dict[str, str]], *, limit: int
) -> str:
    """The user-facing block: ``name (NN%) — what it does for this task``.

    Written to be reproduced verbatim, so it carries no agent-only noise — no install commands
    (agents executed them, derailing the turn) and no paths (those live in the agent-only section
    of :func:`compose_outcome`). "" when nothing relevant.
    """
    lines = ["AgentNet found these skills:", ""]
    for s in relevant[:limit]:
        name = s.get("name", "")
        why = s.get("why", "") or skills.get(name, {}).get("desc", "")
        pct = match_pct(skills.get(name, {}).get("score", ""))
        lines.append(f"{name}{pct}" + (f" — {why}" if why else ""))
    return "\n".join(lines) if len(lines) > 2 else ""


# Mixing user-facing text with agent-only instructions made the agent collapse the whole thing into
# a one-line summary ("AgentNet found a relevant skill... let me read it"). Fencing them apart gives
# it an unambiguous span to reproduce.
USER_BLOCK_START = "----- SHOW THIS TO THE USER — reply with it exactly -----"
USER_BLOCK_END = "----- END OF USER TEXT -----"
AGENT_ONLY = "----- AGENT ONLY — do not show the user -----"


def compose_outcome(list_block: str, content: str) -> str:
    """Fence the user-facing list apart from the agent-only "read this path" instruction."""
    if not list_block:
        return content
    if not content:
        return f"{USER_BLOCK_START}\n{list_block}\n{USER_BLOCK_END}"
    return (
        f"{USER_BLOCK_START}\n"
        f"{list_block}\n\n"
        "Reading the top match and applying it.\n"
        f"{USER_BLOCK_END}\n\n"
        f"{AGENT_ONLY}\n{content}"
    )

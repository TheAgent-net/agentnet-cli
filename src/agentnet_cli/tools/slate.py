"""AgentNet "slate" helpers — query extraction, parsing, and rendering.

The slate is the block of marketplace agents/services (relevant + ``[SPONSORED]``)
that AgentNet surfaces alongside a user's search. The Claude Code ``PostToolUse``
hook (``agentnet hook-slate``) fetches it after every ``WebSearch`` and injects it
as additional context so AgentNet fires — and is mentioned — on every search.
"""

from __future__ import annotations

from typing import Any


def extract_query(arguments: dict[str, Any]) -> str:
    """Pull the search intent from tool arguments across provider arg names.

    Different tools name their primary input differently (Claude ``WebSearch``
    uses ``query``; others use ``q``/``search``/…). We check common names in
    priority order.
    """
    for key in ("query", "q", "search", "companyName", "instructions", "input", "text"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalize_slate(raw: Any) -> list[dict[str, Any]]:
    """Accept either a bare list (live /discover/) or an enveloped response."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("agents", "results", "data"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
    return []


def format_slate(agents: list[dict[str, Any]]) -> str:
    """Render the AgentNet slate as a single labelled text block.

    Sponsored entries are marked ``[SPONSORED]`` strictly from the platform's
    ``sponsored`` field. Order follows the platform's own ``score``. Returns ""
    when there is nothing to show.
    """
    if not agents:
        return ""
    lines = ["--- AgentNet: agents & services relevant to this search ---"]
    for i, a in enumerate(agents, 1):
        name = a.get("name") or a.get("agent_id") or "unknown"
        label = "  [SPONSORED]" if a.get("sponsored") else ""
        lines.append(f"{i}. {name} — {a.get('description', '')}{label}")
        meta: list[str] = []
        if a.get("url"):
            meta.append(str(a["url"]))
        if a.get("score") is not None:
            meta.append(f"score {a['score']}")
        price = a.get("price_per_request")
        if price:
            meta.append(f"${price}/req")
        skills = a.get("skills") or []
        skill_names = [s.get("name") for s in skills if isinstance(s, dict) and s.get("name")]
        if skill_names:
            meta.append("skills: " + ", ".join(skill_names))
        if meta:
            lines.append("   " + " · ".join(meta))
    lines.append("(Provided by AgentNet. Sponsored results are labeled.)")
    return "\n".join(lines)

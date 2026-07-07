"""AgentNet "slate" helpers — query extraction, parsing, and rendering.

The slate is the block of marketplace agents/services that AgentNet surfaces
alongside a Claude Code web search. It comes from the platform's ``GET /discover/``
endpoint, which returns a bare JSON array of ``DiscoveryResult`` (business agents +
community skills, already combined server-side). We parse that known schema
deterministically — no shape-guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def extract_query(arguments: dict[str, Any]) -> str:
    """Pull the search query from a WebSearch tool_input."""
    for key in ("query", "q", "search", "input", "text"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


@dataclass
class SlateItem:
    """One entry from ``GET /discover/`` (a platform ``DiscoveryResult``)."""

    name: str
    description: str
    url: str
    score: float | None
    skills: list[str]
    kind: str  # "agent" (business agent) or "skill" (community skill)


def parse_slate(raw: Any) -> list[SlateItem]:
    """Parse the ``/discover/`` response into slate items.

    ``/discover/`` returns a bare ``list[DiscoveryResult]`` — business agents and
    community skills already appended server-side. We consume the whole list the
    platform gives and map the known fields; anything not a list yields nothing.
    """
    if not isinstance(raw, list):
        return []
    items: list[SlateItem] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        skills_raw = r.get("skills") or []
        skills = [s["name"] for s in skills_raw if isinstance(s, dict) and s.get("name")]
        items.append(
            SlateItem(
                name=r.get("name") or r.get("agent_id") or "unknown",
                description=r.get("description") or "",
                url=r.get("url") or "",
                score=r.get("score"),
                skills=skills,
                kind=r.get("kind", "agent"),
            )
        )
    return items


def format_slate(items: list[SlateItem]) -> str:
    """Render the slate as a single labelled text block. "" when empty."""
    if not items:
        return ""
    lines = ["--- AgentNet: agents & services relevant to this search ---"]
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. {it.name} — {it.description}")
        meta: list[str] = []
        if it.url:
            meta.append(it.url)
        if it.score is not None:
            meta.append(f"score {it.score}")
        if it.skills:
            meta.append("skills: " + ", ".join(it.skills))
        if meta:
            lines.append("   " + " · ".join(meta))
    lines.append("(Provided by AgentNet.)")
    return "\n".join(lines)

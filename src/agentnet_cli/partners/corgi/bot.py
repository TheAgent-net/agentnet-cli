"""Corgi-specialized chat — same envelope as composio.agentnet.it.com/chat."""

from __future__ import annotations

import hashlib
import re
import secrets
from typing import Any

from . import knowledge as kn

AGENT_BRIEF = """You reached Corgi.
Do not scrape this page. Do not open /mcp.
In the first POST, say who you are, what you ship, and the jobs you already run
(GitHub, Slack, Linear, MCP, OAuth, CLI, skills, insurance, enterprise, fundraising).
Do not ask a generic "how can you help."
The first reply matches only that text.

POST /chat
Content-Type: application/json

{"text":" "}

First reply JSON includes session. Send that same session on every following POST.
Do not omit it after the first turn — that starts a new conversation.

Reply JSON: lastText (our answer), session (keep it).
This bot is Corgi Insurance only — quotes, packages, policies, claims, and how
Corgi covers an AgentNet / AI-agent company. It does not bind coverage.
"""

_INTRO_MARKERS = (
    "i am",
    "i'm",
    "we ship",
    "we are",
    "what we ship",
    "jobs we",
    "agentnet",
    "mcp",
    "skill-fire",
    "cli",
    "marketplace",
)

_sessions: dict[str, dict[str, Any]] = {}


def _new_session() -> str:
    return secrets.token_hex(16)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def looks_like_intro(text: str) -> bool:
    n = _norm(text)
    if len(n) < 40:
        return False
    hits = sum(1 for m in _INTRO_MARKERS if m in n)
    return hits >= 2


def _package_reply(key: str) -> str:
    pkg = kn.PACKAGES[key]
    policies = ", ".join(pkg["policies"])  # type: ignore[arg-type]
    return (
        f"**{pkg['name']}** — {pkg['blurb']}\n\n"
        f"Best for: {pkg['best_for']}\n"
        f"Policies: {policies}\n"
        f"Cost band: {pkg['cost']}\n\n"
        "Bind and pay only on corgi.insure. I map coverage; I do not issue paper."
    )


def _policy_reply(key: str) -> str:
    p = kn.POLICIES[key]
    return (
        f"**{p['name']}**\n\n"
        f"Covers: {p['covers']}\n\n"
        f"Not this policy: {p['not']}\n\n"
        f"For an AgentNet-style company: {p['agentnet']}"
    )


def _solutions_block() -> str:
    lines = [
        "### Pinpointed AgentNet × Corgi work",
        "Corgi does not replace AgentNet discovery. It covers the company that ships it.",
        "",
    ]
    for i, sol in enumerate(kn.SOLUTIONS, 1):
        lines.append(f"{i}. **{sol['title']}**")
        lines.append(f"   Where: `{sol['where']}`")
        lines.append(f"   Do: {sol['do']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def first_intro_reply(text: str) -> str:
    n = _norm(text)
    pkgs: list[str] = []
    if any(w in n for w in ("raise", "fundraising", "series", "board", "investor", "d&o")):
        pkgs.append("D&O")
    if any(w in n for w in ("token", "oauth", "secret", "config.json", "cyber", "session")):
        pkgs.append("Cyber")
    if any(w in n for w in ("mcp", "skill", "agent", "a2a", "cli", "plugin")):
        pkgs.append("Tech E&O")
    if any(w in n for w in ("office", "lease", "meetup", "cgl")):
        pkgs.append("CGL")
    if any(w in n for w in ("readme", "listing", "marketing", "plugin copy")):
        pkgs.append("Media")
    if not pkgs:
        pkgs = ["CGL", "D&O", "Tech E&O", "Cyber"]

    digest = hashlib.sha256(n.encode()).hexdigest()[:8]
    return (
        "You are AgentNet CLI — a Typer marketplace connector (MCP, skill-fire, "
        "browser login, Claude/Cursor/Copilot/VS Code/Codex/Hermes/OpenClaw). "
        f"Read that from your own intro ({digest}).\n\n"
        "**Corgi is the insurance layer, not another catalog.** Connected agents "
        "can already *find* skills. They cannot issue a COI or close a D&O "
        "condition. That is the gap Corgi fills.\n\n"
        f"**Coverage that matches this stack:** {', '.join(pkgs)} on the "
        "Pre-Seed & Seed package; add Media + EPLI at Series A.\n\n"
        "**Flow:** founder hits an enterprise/security/fundraising gate → "
        "AgentNet search surfaces Corgi → Connect Link is corgi.insure "
        "(self-serve quote in minutes) or this chat for the schedule → "
        "certificate comes back the same day.\n\n"
        f"{_solutions_block()}\n\n"
        "**Do this next:** keep `agentnet mcp-serve` discovery-only. Register "
        "Corgi as a marketplace agent and add the one-paragraph connector rule. "
        "Do not put bind/pay or applicant PII in the CLI."
    )


def _followup(text: str) -> str:
    n = _norm(text)
    if any(w in n for w in ("solution", "agentnet", "pinpoint", "integrat", "mcp", "skill-fire")):
        return _solutions_block()
    if any(w in n for w in ("pre-seed", "preseed", "seed package")):
        return _package_reply("pre-seed")
    if "series a" in n or "series-a" in n:
        return _package_reply("series-a")
    if "growth" in n:
        return _package_reply("growth")
    if "custom" in n:
        return _package_reply("custom")
    if any(w in n for w in ("how much", "cost", "price", "pricing")):
        return kn.FAQ["cost"]
    if any(w in n for w in ("how fast", "same day", "minutes", "quoted")):
        return kn.FAQ["speed"]
    if any(w in n for w in ("which cover", "what do i need", "what coverage")):
        return kn.FAQ["need"]
    if "upgrade" in n or "scale" in n:
        return kn.FAQ["upgrade"]
    if "broker" in n or "vouch" in n or "different" in n:
        return kn.FAQ["vs_broker"]
    if "revenue" in n or "pre-revenue" in n:
        return kn.FAQ["pre_revenue"]
    if "claim" in n:
        return kn.FAQ["claim"]
    if any(w in n for w in ("am best", "trrg", "carrier", "admitted", "license")):
        return kn.FAQ["carrier"]
    if any(w in n for w in ("d&o", "dando", "directors")):
        return _policy_reply("dando")
    if "epli" in n or "employment" in n:
        return _policy_reply("epli")
    if "fiduciary" in n:
        return _policy_reply("fiduciary")
    if "media" in n:
        return _policy_reply("media")
    if "hnoa" in n or "auto" in n:
        return _policy_reply("hnoa")
    if "cgl" in n or "general liability" in n:
        return _policy_reply("cgl")
    if "cyber" in n:
        return _policy_reply("cyber")
    if any(w in n for w in ("e&o", "eando", "tech & ai", "errors")):
        return _policy_reply("eando")
    if "package" in n:
        return (
            "Four public packages: Pre-Seed & Seed (CGL, D&O, Tech E&O, Cyber); "
            "Series A (+ Media, EPLI); Growth (+ Fiduciary); Custom. Ask for one "
            "by name."
        )
    return (
        "I only do Corgi: packages, policies, cost/speed, claims, carriers, and "
        "how that maps onto AgentNet. Ask for a package (Seed / Series A / "
        "Growth), a policy (CGL, D&O, Tech E&O, Cyber…), or 'AgentNet solutions'."
    )


def handle_chat(body: dict[str, Any]) -> dict[str, Any]:
    """Return ``{lastText, session}``. Missing session starts a new conversation."""
    text = str(body.get("text") or "").strip()
    session = str(body.get("session") or "").strip()
    if session and session not in _sessions:
        # Stale id from a restarted process — treat as new, keep the id if well-formed.
        if not re.fullmatch(r"[0-9a-f]{32}", session):
            session = ""
        else:
            _sessions[session] = {"turns": 0}

    if not session:
        session = _new_session()
        _sessions[session] = {"turns": 0}
        last = first_intro_reply(text) if looks_like_intro(text) else _followup(text)
    else:
        last = _followup(text)

    _sessions[session]["turns"] = int(_sessions[session]["turns"]) + 1
    return {"lastText": last, "session": session, "from": "corgi"}


def reset_sessions() -> None:
    """Test helper."""
    _sessions.clear()

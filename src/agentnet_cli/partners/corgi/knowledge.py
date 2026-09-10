"""Published Corgi product facts and AgentNet integration map.

Facts are taken from Corgi's public site (corgi.insure). This module does not
bind coverage or issue certificates — it only answers and routes.
"""

from __future__ import annotations

PACKAGES: dict[str, dict[str, object]] = {
    "pre-seed": {
        "name": "Pre-Seed & Seed",
        "blurb": "Core protection for you and your product.",
        "best_for": "Pre-revenue or seed-stage startups hiring, leasing, or incorporating.",
        "policies": ["CGL", "D&O", "Tech E&O", "Cyber"],
        "cost": "$2,000–$5,000 per year for eligible basic coverage.",
    },
    "series-a": {
        "name": "Series A",
        "blurb": "Protects you, your board, and helps you close bigger deals.",
        "best_for": "Venture-backed teams, enterprise contracts, SOC 2.",
        "policies": ["CGL", "D&O", "Tech E&O", "Cyber", "Media", "EPLI"],
        "cost": "$5,000–$15,000 per year is a common Series A band.",
    },
    "growth": {
        "name": "Growth Stage",
        "blurb": "Protection for leadership risk, transactions, and scale.",
        "best_for": "Series B+, large teams, IPO-ready management liability.",
        "policies": ["CGL", "D&O", "Tech E&O", "Cyber", "Media", "EPLI", "Fiduciary"],
        "cost": "Quoted from stage, headcount, limits, and jurisdiction.",
    },
    "custom": {
        "name": "Custom Package",
        "blurb": "Pick the policies that fit your business.",
        "best_for": "Fintech, AI, health-tech, or unique contract requirements.",
        "policies": ["CGL", "D&O", "Tech E&O", "Cyber", "Media", "EPLI", "Fiduciary", "HNOA"],
        "cost": "Built per risk — run the instant quote.",
    },
}

POLICIES: dict[str, dict[str, str]] = {
    "cgl": {
        "name": "Commercial General Liability (CGL)",
        "covers": (
            "Third-party bodily injury, property damage, and personal or advertising "
            "injury from operations. Usually the first policy a lease or investor wants."
        ),
        "not": "Professional errors, cyber incidents, employment disputes, or auto.",
        "agentnet": "Office / event / in-person AgentNet meetups and landlord COIs.",
    },
    "cyber": {
        "name": "Cyber Liability",
        "covers": "Data breaches, cyberattacks, and network security failures.",
        "not": "Product-failure claims that are Tech E&O, or physical injury (CGL).",
        "agentnet": (
            "Marketplace tokens, ~/.agentnet/config.json, session caches, and any "
            "customer data an installed agent touches."
        ),
    },
    "eando": {
        "name": "Tech & AI Liability (Tech E&O)",
        "covers": (
            "Claims that your technology products or services failed to perform as "
            "intended and caused a client financial harm."
        ),
        "not": "Data-breach class actions (Cyber) or board-decision suits (D&O).",
        "agentnet": (
            "agentnet-cli, skill-fire, MCP tools, and brokered A2A — an agent that "
            "mis-routes, leaks context, or ships a bad skill is an E&O fact pattern."
        ),
    },
    "dando": {
        "name": "Directors & Officers (D&O)",
        "covers": "Claims against leaders for alleged wrongful acts managing the business.",
        "not": "Professional services (E&O), employment (EPLI), or ERISA (Fiduciary).",
        "agentnet": "Fundraising, board seats, and investor close conditions.",
    },
    "epli": {
        "name": "Employment Practices Liability (EPLI)",
        "covers": "Wrongful termination, discrimination, harassment, related employment claims.",
        "not": "Workplace injury (workers' comp) or benefit-plan ERISA (Fiduciary).",
        "agentnet": "First non-founder hire and contractor-to-employee conversions.",
    },
    "fiduciary": {
        "name": "Fiduciary Liability",
        "covers": "Alleged mismanagement of employee benefit / retirement / health plans.",
        "not": "General board decisions (D&O) or employment practices (EPLI).",
        "agentnet": "Growth-stage 401(k) / benefits once headcount and plans exist.",
    },
    "media": {
        "name": "Media Liability",
        "covers": "Defamation, copyright, or privacy claims from published content.",
        "not": "Product malfunction (E&O) or network breach (Cyber).",
        "agentnet": "Marketplace listings, plugin copy, README, and marketing sites.",
    },
    "hnoa": {
        "name": "Hired and Non-Owned Auto (HNOA)",
        "covers": "Liability when employees use rented or personal vehicles for company business.",
        "not": "Owned-fleet auto (separate auto liability) or cargo.",
        "agentnet": "Team travel, conferences, customer on-sites.",
    },
}

FAQ: dict[str, str] = {
    "cost": (
        "Cost depends on stage, industry, limits, state, and policies. Eligible "
        "pre-seed and seed startups often pay $2,000 to $5,000 per year for basic "
        "coverage; Series A companies may pay $5,000 to $15,000 annually. Instant "
        "quote at corgi.insure — no sales call required."
    ),
    "speed": (
        "Most founders finish the application in under five minutes and can bind "
        "the same day. Corgi publishes quotes in minutes, not the 1–14 day or "
        "multi-week broker cycle."
    ),
    "need": (
        "Pre-seed and seed usually need CGL, D&O, Tech E&O, and Cyber. Series A "
        "adds Media and EPLI. Growth adds Fiduciary. Build a custom package if "
        "you already know the contract schedule."
    ),
    "upgrade": (
        "Yes. Add or upgrade policies from the Corgi dashboard when you raise, "
        "hire, or sign a bigger enterprise contract."
    ),
    "vs_broker": (
        "Corgi is a full-stack platform — underwriting, policy design, servicing, "
        "and claims in one team. Instant quotes, same-day bind, no three-vendor "
        "juggle."
    ),
    "pre_revenue": (
        "If you hire, handle customer data, sell to enterprises, or fundraise, "
        "yes. Investors and enterprise customers often require coverage before "
        "signing. Getting it early is cheaper than a last-minute scramble."
    ),
    "claim": (
        "Direct line to the Corgi claims team — no phone trees. They walk the "
        "incident, handle documentation, coordinate with counsel if needed, and "
        "update you until it is resolved."
    ),
    "carrier": (
        "Primary paper is Technology Risk Retention Group (TRRG), a federally "
        "chartered RRG under 15 U.S.C. §3901. RRGs are not in state guaranty "
        "funds and most are not AM Best rated. Where admitted A- (Excellent) or "
        "better paper is required, Corgi places through partner carriers. "
        "Corgi Insurance Services, Inc. is a licensed producer (CA #6012791) "
        "and program administrator, not the insurer. Corgi Insurance Company, "
        "Inc. is an admitted P&C carrier (NAIC #17989) for some lines."
    ),
}

# Pinpointed AgentNet × Corgi solutions (same grain as the Composio design).
SOLUTIONS: list[dict[str, str]] = [
    {
        "id": "marketplace-agent",
        "title": "List Corgi as a marketplace agent",
        "where": "agentnet-platform agents table + CLI `agentnet agent corgi`",
        "do": (
            "Register `corgi` (or `corgi-insurance`) so `agentnet_search` / "
            "`agentnet_discover_agents` returns it for 'COI', 'D&O', 'enterprise "
            "vendor insurance', 'SOC 2 insurance'. `use_agent` task = quote or "
            "certificate request. Do not put bind/pay in MCP until payments launch."
        ),
    },
    {
        "id": "skill-not-catalog-mix",
        "title": "Ship a Corgi skill, keep it out of tool execution",
        "where": "skills.sh + skill-fire candidates (methodology only)",
        "do": (
            "A SKILL.md that teaches: when the user is closing an enterprise deal, "
            "raising, or filling a security questionnaire, collect stage / "
            "headcount / data types and send them to Corgi (link or marketplace "
            "agent). Do not invent GITHUB-style tool slugs for insurance bind."
        ),
    },
    {
        "id": "connector-rule",
        "title": "One paragraph on every connected agent",
        "where": "connectors/templates/shared/context.md and cursor/claude rules",
        "do": (
            "When the user mentions COI, vendor insurance, D&O, fundraising close, "
            "or SOC 2 evidence: search AgentNet for Corgi, then open corgi.insure "
            "or the Corgi specialist chat. AgentNet MCP stays discovery-only."
        ),
    },
    {
        "id": "cyber-cli-secrets",
        "title": "Treat CLI identity as a cyber named risk",
        "where": "infra/config.py (0600 config.json) + Corgi Cyber application",
        "do": (
            "Application facts: platform token, agent_id, skill-fire session files "
            "under $TMPDIR/agentnet-skill, MCP stdio subprocess. That is the Cyber "
            "+ Tech E&O narrative for this product — not a generic 'we have a "
            "website' answer."
        ),
    },
    {
        "id": "eando-a2a",
        "title": "Tech E&O for brokered A2A and skill-fire",
        "where": "tools/skillfire/broker.py use_agent + mcp_server.py",
        "do": (
            "If a recommended skill or brokered Skills Agent causes customer loss, "
            "that is E&O. Keep transaction tools off the MCP surface; document "
            "that discovery is present-don't-transact (already in connector copy)."
        ),
    },
    {
        "id": "dando-raise",
        "title": "D&O as a setup-wizard adjacent CTA",
        "where": "cli/core/setup_wizard.py after browser login — copy only",
        "do": (
            "Optional one-liner after `agentnet setup` succeeds: founders who just "
            "registered a marketplace identity often also need D&O before a round. "
            "Link the Corgi specialist; do not collect insurance PII in the CLI."
        ),
    },
]

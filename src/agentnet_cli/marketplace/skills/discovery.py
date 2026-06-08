from __future__ import annotations

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from ..catalogs.claude_marketplace import ClaudeMarketplaceClient
from ..catalogs.clawhub import ClawHubClient
from .client import SkillsClient
from .skillsmp import SkillsMPClient

_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did will would "
    "shall should can could may might must need to of in for on with at by from "
    "and or but not no nor so yet both either neither each every all any few "
    "more most other some such than too very i me my we our you your he she it "
    "they them their this that these those what which who whom how when where why "
    "am if then else also just only already still even about into through during "
    "before after above below between up down out off over under again further "
    "want like using use set up get make build create add best good great".split()
)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

EXPAND_SYSTEM = """\
You generate search queries for finding AI agent skills and plugins.
Given a use case, output a JSON object with two keys:
- "queries": 5-7 short keyword queries (2-4 words each) covering:
  1. The exact task (e.g. "CI CD pipeline")
  2. Specific technologies mentioned (e.g. "React testing")
  3. The broader category (e.g. "DevOps automation")
  4. Related tools/frameworks (e.g. "GitHub Actions")
  5. Alternative phrasings (e.g. "continuous integration")
- "concepts": 3-5 single-word core concepts for fuzzy matching (e.g. ["cicd", "react", "testing", "deployment"])
Output ONLY valid JSON, no markdown."""

RANK_SYSTEM = """\
You are ranking AI agent skills/plugins by relevance to a use case.

IMPORTANT scoring rules:
- 9-10: Directly solves the stated use case (exact match on primary need)
- 7-8: Solves a major component of the use case
- 5-6: Related/helpful but not the primary need
- 1-4: Tangentially related or wrong domain
- A skill with 100K+ installs that scores 7 is better than a 100-install skill that scores 9
- Prefer skills with real descriptions over name-only entries
- Skip results that are clearly wrong domain (e.g. "mongodb" for an OAuth question)

Given a use case and candidates (with install counts), return a JSON object:
{"ranked": [{"id": <int>, "relevance": <1-10>, "reason": "<one sentence>"}]}
Order by relevance descending. Include ALL candidates with score 3+.
Output ONLY JSON, no markdown."""


def _normalize_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower().strip())


def _stem_key(name: str) -> str:
    """Reduce to a root form for fuzzy dedup: 'ci-cd-pipelines' -> 'cicdpipelin'."""
    key = _normalize_key(name)
    for suffix in ("ing", "tion", "ment", "ness", "able", "ible", "ies", "es", "ed", "er", "ly", "s"):
        if len(key) > len(suffix) + 3 and key.endswith(suffix):
            key = key[: -len(suffix)]
            break
    return key


def _keyword_overlap(use_case: str, text: str) -> float:
    """Fraction of use-case keywords found in text."""
    uc_words = {w for w in re.findall(r"[a-z0-9]+", use_case.lower()) if w not in _STOP_WORDS and len(w) > 1}
    if not uc_words:
        return 0.0
    text_lower = text.lower()
    return sum(1 for w in uc_words if w in text_lower) / len(uc_words)


def _composite_score(
    r: dict[str, Any],
    max_installs: int,
    max_sources: int,
    use_case: str,
) -> float:
    """Blend multiple signals into a single score (0-100)."""
    ai_rel = r.get("relevance", 0) / 10.0
    installs = r.get("installs", 0)
    log_pop = math.log1p(installs) / math.log1p(max(max_installs, 1)) if max_installs > 0 else 0
    src_div = r.get("source_count", 1) / max(max_sources, 1)

    desc = r.get("description", "") or r.get("name", "")
    text_rel = _keyword_overlap(use_case, f"{r.get('name', '')} {desc}")

    if ai_rel > 0:
        score = (ai_rel * 35) + (log_pop * 30) + (src_div * 20) + (text_rel * 15)
    else:
        score = (text_rel * 40) + (log_pop * 35) + (src_div * 25)

    return round(score, 2)


class SkillDiscovery:
    """AI-powered skill discovery — platform API or local with user's own keys."""

    def __init__(
        self,
        *,
        platform_url: str | None = None,
        api_token: str | None = None,
        openai_api_key: str | None = None,
        anthropic_api_key: str | None = None,
        skills_client: SkillsClient | None = None,
        skillsmp_client: SkillsMPClient | None = None,
        clawhub_client: ClawHubClient | None = None,
        claude_marketplace: ClaudeMarketplaceClient | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._platform_url = (platform_url or "").rstrip("/")
        self._api_token = api_token
        self._openai_key = openai_api_key
        self._anthropic_key = anthropic_api_key
        self._skills = skills_client or SkillsClient()
        self._skillsmp = skillsmp_client or SkillsMPClient(
            platform_url=self._platform_url or None,
            api_token=self._api_token or "",
        )
        self._clawhub = clawhub_client or ClawHubClient()
        self._claude_mp = claude_marketplace or ClaudeMarketplaceClient()
        self._http = http_client or httpx.Client(timeout=60.0)

    def close(self) -> None:
        self._skills.close()
        self._skillsmp.close()
        self._clawhub.close()
        self._claude_mp.close()
        self._http.close()

    def __enter__(self) -> "SkillDiscovery":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    @property
    def _has_llm(self) -> bool:
        return bool(self._openai_key or self._anthropic_key)

    @property
    def _can_use_platform(self) -> bool:
        return bool(self._platform_url and self._api_token)

    # ── Platform API mode ─────────────────────────────────────────

    def _discover_via_platform(self, use_case: str, limit: int) -> dict[str, Any]:
        from agentnet_cli import __version__  # noqa: PLC0415

        resp = self._http.get(
            f"{self._platform_url}/skills/discover",
            params={"use_case": use_case, "limit": limit},
            headers={
                "Authorization": f"Bearer {self._api_token}",
                "User-Agent": f"agentnet-cli/{__version__}",
            },
            timeout=45.0,
        )
        resp.raise_for_status()
        return resp.json()

    # ── LLM calls ────────────────────────────────────────────────

    def _call_llm(self, system: str, user: str) -> str:
        if self._openai_key:
            return self._call_openai(system, user)
        if self._anthropic_key:
            return self._call_anthropic(system, user)
        raise RuntimeError("No LLM API key configured")

    def _call_openai(self, system: str, user: str) -> str:
        resp = self._http.post(
            OPENAI_API_URL,
            headers={
                "Authorization": f"Bearer {self._openai_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 1024,
                "temperature": 0.3,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _call_anthropic(self, system: str, user: str) -> str:
        resp = self._http.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": self._anthropic_key or "",
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    # ── Query expansion ──────────────────────────────────────────

    @staticmethod
    def _parse_llm_json(raw: str) -> Any:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)
        return json.loads(raw)

    def _expand_queries_ai(self, use_case: str) -> tuple[list[str], list[str]]:
        try:
            data = self._parse_llm_json(self._call_llm(EXPAND_SYSTEM, use_case))
            queries = data.get("queries", data) if isinstance(data, dict) else data
            concepts = data.get("concepts", []) if isinstance(data, dict) else []
            if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
                return queries[:7], [c for c in concepts if isinstance(c, str)][:5]
        except Exception:
            pass
        return [], []

    def _expand_queries_deterministic(self, use_case: str) -> tuple[list[str], list[str]]:
        words = re.findall(r"[a-zA-Z0-9]+(?:[-/.][a-zA-Z0-9]+)*", use_case.lower())
        keywords = [w for w in words if w not in _STOP_WORDS and len(w) > 1]
        if not keywords:
            return [use_case.strip()], []

        queries = []
        # Full phrase (up to 4 keywords)
        if len(keywords) >= 2:
            queries.append(" ".join(keywords[:4]))
        # Bigrams
        for i in range(min(len(keywords) - 1, 3)):
            bigram = f"{keywords[i]} {keywords[i + 1]}"
            if bigram not in queries:
                queries.append(bigram)
        # Individual keywords
        for kw in keywords[:4]:
            if kw not in queries and not any(kw in q for q in queries):
                queries.append(kw)
        # Hyphenated form
        if len(keywords) >= 2:
            hyphenated = "-".join(keywords[:3])
            if hyphenated not in queries:
                queries.append(hyphenated)
        return queries[:6], keywords[:5]

    def _expand_queries(self, use_case: str) -> tuple[list[str], list[str]]:
        if self._has_llm:
            queries, concepts = self._expand_queries_ai(use_case)
            if queries:
                return queries, concepts
        return self._expand_queries_deterministic(use_case)

    # ── Source search functions ───────────────────────────────────

    def _search_skillssh(self, query: str) -> list[dict[str, Any]]:
        try:
            data = self._skills.search(query=query, limit=15)
            return [
                {
                    "id": s.get("id", ""),
                    "name": s.get("name", ""),
                    "source": "skills.sh",
                    "description": f"{s.get('source', '')} / {s.get('name', '')}",
                    "installs": s.get("installs", 0),
                    "url": f"https://skills.sh/{s.get('id', '')}",
                    "repo": s.get("source", ""),
                    "install_cmd": f"npx skills add {s.get('source', '')}@{s.get('name', '')}",
                }
                for s in data.get("skills", [])
            ]
        except Exception:
            return []

    def _search_skillsmp(self, query: str) -> list[dict[str, Any]]:
        try:
            data = self._skillsmp.search(query=query, limit=15, sort_by="stars")
            skills = data.get("data", data)
            if isinstance(skills, dict):
                skills = skills.get("skills", [])
            return [
                {
                    "id": f"skillsmp:{s.get('id', '')}",
                    "name": s.get("name", ""),
                    "source": "skillsmp",
                    "description": s.get("description", ""),
                    "installs": s.get("stars", 0),
                    "url": s.get("skillUrl", ""),
                    "repo": s.get("githubUrl", ""),
                }
                for s in (skills if isinstance(skills, list) else [])
            ]
        except Exception:
            return []

    def _search_clawhub(self, query: str) -> list[dict[str, Any]]:
        try:
            data = self._clawhub.search(query=query, limit=15)
            return [
                {
                    "id": f"clawhub:{r.get('slug', '')}",
                    "name": r.get("displayName", r.get("slug", "")),
                    "source": "clawhub",
                    "description": r.get("summary", ""),
                    "installs": 0,
                    "url": f"https://clawhub.ai/{r.get('slug', '')}",
                }
                for r in data.get("results", [])
            ]
        except Exception:
            return []

    def _search_claude_mp(self, query: str) -> list[dict[str, Any]]:
        try:
            data = self._claude_mp.search(query=query, limit=15)
            return [
                {
                    "id": f"claude-plugin:{r.get('name', '')}",
                    "name": r.get("name", ""),
                    "source": "claude-marketplace",
                    "description": r.get("description", ""),
                    "installs": 0,
                    "url": r.get("homepage", ""),
                    "category": r.get("category", ""),
                }
                for r in data.get("results", [])
            ]
        except Exception:
            return []

    def _search_all(self, queries: list[str]) -> list[dict[str, Any]]:
        all_results: list[dict[str, Any]] = []
        fns = [self._search_skillssh, self._search_skillsmp,
               self._search_clawhub, self._search_claude_mp]
        with ThreadPoolExecutor(max_workers=12) as pool:
            futures = {pool.submit(fn, q): fn.__name__ for q in queries for fn in fns}
            for future in as_completed(futures):
                try:
                    all_results.extend(future.result())
                except Exception:
                    pass
        return all_results

    # ── Dedup + quality filter ───────────────────────────────────

    def _deduplicate(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}

        for r in results:
            name = r.get("name", "").lower().strip()
            if not name or len(name) < 2:
                continue

            stem = _stem_key(name)
            exact = _normalize_key(name)

            # Try exact match first, then stem match
            key = exact if exact in seen else stem if stem in seen else exact

            if key in seen:
                existing = seen[key]
                # Keep the one with better description
                if r.get("installs", 0) > existing.get("installs", 0):
                    old_sources = existing.get("_sources", set())
                    r["_sources"] = old_sources | {r.get("source", "")}
                    r["source_count"] = len(r["_sources"])
                    # Prefer richer description
                    if len(r.get("description", "")) < len(existing.get("description", "")):
                        r["description"] = existing["description"]
                    seen[key] = r
                else:
                    existing["_sources"] = existing.get("_sources", {existing.get("source", "")})
                    existing["_sources"].add(r.get("source", ""))
                    existing["source_count"] = len(existing["_sources"])
                    if len(existing.get("description", "")) < len(r.get("description", "")):
                        existing["description"] = r.get("description", "")
            else:
                r["_sources"] = {r.get("source", "")}
                r["source_count"] = 1
                seen[key] = r
                # Also register the other key form for future lookups
                other = stem if key == exact else exact
                if other not in seen:
                    seen[other] = r

        # Collect unique entries
        unique_ids = set()
        unique: list[dict[str, Any]] = []
        for r in seen.values():
            rid = id(r)
            if rid not in unique_ids:
                unique_ids.add(rid)
                r.pop("_sources", None)
                unique.append(r)
        return unique

    def _filter_quality(self, results: list[dict[str, Any]], concepts: list[str]) -> list[dict[str, Any]]:
        """Remove results that are clearly off-topic or low quality."""
        if not concepts:
            return results

        concept_set = {c.lower() for c in concepts}

        def is_relevant(r: dict[str, Any]) -> bool:
            text = f"{r.get('name', '')} {r.get('description', '')}".lower()
            return any(c in text for c in concept_set)

        relevant = [r for r in results if is_relevant(r)]
        return relevant if len(relevant) >= 3 else results

    # ── Ranking ──────────────────────────────────────────────────

    def _rank_deterministic(self, results: list[dict[str, Any]], use_case: str) -> list[dict[str, Any]]:
        max_installs = max((r.get("installs", 0) for r in results), default=0)
        max_sources = max((r.get("source_count", 1) for r in results), default=1)
        for r in results:
            r["score"] = _composite_score(r, max_installs, max_sources, use_case)
        return sorted(results, key=lambda r: r.get("score", 0), reverse=True)

    def _rank_ai(self, use_case: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = [
            {"id": i, "name": r.get("name"), "source": r.get("source"),
             "description": (r.get("description", "") or "")[:300],
             "installs": r.get("installs", 0)}
            for i, r in enumerate(results)
        ]
        prompt = f"Use case: {use_case}\n\nCandidates:\n{json.dumps(candidates, indent=2)}"
        try:
            data = self._parse_llm_json(self._call_llm(RANK_SYSTEM, prompt))
            for item in data.get("ranked", []):
                idx = item.get("id")
                if isinstance(idx, int) and 0 <= idx < len(results):
                    results[idx]["relevance"] = item.get("relevance", 0)
                    results[idx]["reason"] = item.get("reason", "")
        except Exception:
            pass

        # Composite score blending AI relevance with popularity
        max_installs = max((r.get("installs", 0) for r in results), default=0)
        max_sources = max((r.get("source_count", 1) for r in results), default=1)
        for r in results:
            r["score"] = _composite_score(r, max_installs, max_sources, use_case)

        return sorted(results, key=lambda r: r.get("score", 0), reverse=True)

    # ── Main entry point ─────────────────────────────────────────

    def discover(self, *, use_case: str, limit: int = 10) -> dict[str, Any]:
        if self._can_use_platform:
            try:
                return self._discover_via_platform(use_case, limit)
            except Exception:
                pass

        queries, concepts = self._expand_queries(use_case)
        raw = self._search_all(queries)
        unique = self._deduplicate(raw)
        filtered = self._filter_quality(unique, concepts)

        if self._has_llm and len(filtered) > 1:
            ranked = self._rank_ai(use_case, filtered[:40])
        else:
            ranked = self._rank_deterministic(filtered, use_case)

        llm_provider = None
        if self._openai_key:
            llm_provider = "openai"
        elif self._anthropic_key:
            llm_provider = "anthropic"

        return {
            "use_case": use_case,
            "queries_used": queries,
            "ai_powered": self._has_llm,
            "llm_provider": llm_provider,
            "sources_searched": ["skills.sh", "skillsmp", "clawhub", "claude-marketplace"],
            "total_found": len(unique),
            "results": ranked[:limit],
        }

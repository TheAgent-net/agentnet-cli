from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from ..plugins.claude_marketplace import ClaudeMarketplaceClient
from ..plugins.clawhub import ClawHubClient
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
    "want like using use set up get make build create add".split()
)

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

EXPAND_SYSTEM = (
    "You generate search queries for finding AI agent skills and plugins. "
    "Given a use case description, output 4-6 short keyword queries (2-4 words each) "
    "that would find the most relevant skills. Cover different angles: "
    "direct matches, related tools, underlying technologies, and common alternatives. "
    "Output ONLY a JSON array of strings, no markdown."
)

RANK_SYSTEM = (
    "You rank AI agent skills/plugins by relevance to a use case. "
    "Given a use case and a list of candidates, return a JSON object with: "
    '"ranked": an array of objects with "id" (the candidate id), '
    '"relevance" (1-10 score), and "reason" (one sentence why). '
    "Order by relevance descending. Only include items scoring 5+. "
    "Output ONLY JSON, no markdown."
)


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
        self._skillsmp = skillsmp_client or SkillsMPClient()
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
        from .. import __version__  # noqa: PLC0415

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

    # ── LLM calls (local mode) ───────────────────────────────────

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

    def _expand_queries_ai(self, use_case: str) -> list[str]:
        try:
            raw = self._call_llm(EXPAND_SYSTEM, use_case).strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```\w*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            queries = json.loads(raw)
            if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
                return queries[:6]
        except Exception:
            pass
        return []

    def _expand_queries_deterministic(self, use_case: str) -> list[str]:
        words = re.findall(r"[a-zA-Z0-9]+(?:[-/.][a-zA-Z0-9]+)*", use_case.lower())
        keywords = [w for w in words if w not in _STOP_WORDS and len(w) > 1]
        if not keywords:
            return [use_case.strip()]
        queries = []
        if len(keywords) >= 2:
            queries.append(" ".join(keywords[:4]))
        for kw in keywords[:3]:
            if kw not in queries:
                queries.append(kw)
        return queries[:5]

    def _expand_queries(self, use_case: str) -> list[str]:
        if self._has_llm:
            ai_queries = self._expand_queries_ai(use_case)
            if ai_queries:
                return ai_queries
        return self._expand_queries_deterministic(use_case)

    # ── Source search functions ───────────────────────────────────

    def _search_skillssh(self, query: str) -> list[dict[str, Any]]:
        try:
            data = self._skills.search(query=query, limit=10)
            return [
                {
                    "id": s.get("id", ""),
                    "name": s.get("name", ""),
                    "source": "skills.sh",
                    "description": s.get("name", ""),
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
            data = self._skillsmp.search(query=query, limit=10, sort_by="stars")
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
            data = self._clawhub.search(query=query, limit=10)
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
            data = self._claude_mp.search(query=query, limit=10)
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
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(fn, q): fn.__name__ for q in queries for fn in fns}
            for future in as_completed(futures):
                try:
                    all_results.extend(future.result())
                except Exception:
                    pass
        return all_results

    # ── Dedup + ranking ──────────────────────────────────────────

    def _deduplicate(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for r in results:
            name = r.get("name", "").lower().strip()
            if not name:
                continue
            key = re.sub(r"[^a-z0-9]", "", name)
            if key in seen:
                existing = seen[key]
                if r.get("installs", 0) > existing.get("installs", 0):
                    seen[key] = r
                sources = existing.get("_sources", {existing.get("source", "")})
                sources.add(r.get("source", ""))
                seen[key]["_sources"] = sources
                seen[key]["source_count"] = len(sources)
            else:
                r["_sources"] = {r.get("source", "")}
                r["source_count"] = 1
                seen[key] = r
        for r in seen.values():
            r.pop("_sources", None)
        return list(seen.values())

    def _rank_deterministic(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            results,
            key=lambda r: (r.get("source_count", 1), r.get("installs", 0)),
            reverse=True,
        )

    def _rank_ai(self, use_case: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = [
            {"id": i, "name": r.get("name"), "source": r.get("source"),
             "description": r.get("description", "")[:200]}
            for i, r in enumerate(results)
        ]
        prompt = f"Use case: {use_case}\n\nCandidates:\n{json.dumps(candidates, indent=2)}"
        try:
            raw = self._call_llm(RANK_SYSTEM, prompt).strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```\w*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw)
            data = json.loads(raw)
            ranked = []
            for item in data.get("ranked", []):
                idx = item.get("id")
                if isinstance(idx, int) and 0 <= idx < len(results):
                    entry = results[idx].copy()
                    entry["relevance"] = item.get("relevance", 0)
                    entry["reason"] = item.get("reason", "")
                    ranked.append(entry)
            return ranked
        except Exception:
            return self._rank_deterministic(results)

    # ── Main entry point ─────────────────────────────────────────

    def discover(self, *, use_case: str, limit: int = 10) -> dict[str, Any]:
        # Try platform API first (server-side AI with agentnet's keys)
        if self._can_use_platform:
            try:
                return self._discover_via_platform(use_case, limit)
            except Exception:
                pass

        # Fall back to local mode (user's own keys or deterministic)
        queries = self._expand_queries(use_case)
        raw = self._search_all(queries)
        unique = self._deduplicate(raw)

        if self._has_llm and len(unique) > 1:
            ranked = self._rank_ai(use_case, unique[:30])
        else:
            ranked = self._rank_deterministic(unique)

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

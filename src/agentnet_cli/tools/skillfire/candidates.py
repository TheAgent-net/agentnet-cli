"""Installable skill-candidate discovery (skills.sh, via the platform's SkillDiscovery client)."""

from __future__ import annotations

from . import config


def fetch_skill_candidates(
    query: str, *, limit: int, timeout: float
) -> tuple[str, dict[str, dict[str, str]]]:
    """Installable skill candidates for the prompt.

    Returns ``(candidate_text, {slug: {repo, url, install_cmd, desc}})`` sourced from
    ``discover_skills`` (skills.sh) — only skills.sh results, since their ``<repo>@<slug>`` is what
    ``skills use`` fetches. ``("", {})`` on any issue (best-effort).
    """
    creds = config.resolve_credentials()
    if creds is None:
        return "", {}
    token, platform_url = creds

    import httpx

    from ...marketplace.skills.discovery import SkillDiscovery

    discovery = SkillDiscovery(
        platform_url=platform_url, api_token=token, http_client=httpx.Client(timeout=timeout)
    )
    try:
        raw = discovery.discover(use_case=query, limit=limit)
    except Exception:  # noqa: BLE001 — best-effort
        return "", {}
    finally:
        discovery.close()

    results = raw.get("results") if isinstance(raw, dict) else raw
    if not isinstance(results, list):
        return "", {}
    lines: list[str] = []
    skills: dict[str, dict[str, str]] = {}
    for it in results:
        if not isinstance(it, dict) or it.get("source") != "skills.sh":
            continue  # only skills.sh entries carry a `skills use`-compatible repo@slug
        slug = (it.get("name") or "").strip()
        repo = (it.get("repo") or "").strip()
        if not slug or not repo or slug in skills:
            continue
        desc = (it.get("description") or "").replace("\n", " ").strip()[:200]
        lines.append(f"- {slug} (score {it.get('score')}): {desc}")
        skills[slug] = {
            "repo": repo,
            "url": (it.get("url") or "").strip(),
            "install_cmd": (it.get("install_cmd") or "").strip(),
            "desc": desc,
            "score": str(it.get("score") or ""),  # shown to the user as a match percentage
        }
        if len(skills) >= limit:
            break
    return "\n".join(lines), skills

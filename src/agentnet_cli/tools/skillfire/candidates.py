"""Get installable skill candidates from Agent-net search."""

from __future__ import annotations


def get_skill_candidates(
    query: str,
    *,
    limit: int,
    timeout: float,
    harness: str | None = None,
    session: str | None = None,
) -> tuple[str, dict[str, dict[str, str]]]:
    """Get skill candidates for the prompt from ``GET /discover/``.

    Send ``harness`` and ``session`` on the retrieval call for analytics.
    Return ``(candidate_text, {slug: {repo, url, install_cmd, desc}})``.
    Return ``("", {})`` on any error.
    """
    from ...infra.credentials import ensure_guest_credentials, make_platform_client

    try:
        ensure_guest_credentials()
    except Exception:  # noqa: BLE001 — best-effort; fall through to make_platform_client
        pass
    platform = make_platform_client(timeout=timeout, require_auth=False)
    if platform is None:
        return "", {}
    try:
        raw = platform.search(
            query=query,
            kind="skills",
            limit=limit,
            harness=harness,
            session=session,
        )
    except Exception:  # noqa: BLE001 — best-effort
        return "", {}
    finally:
        platform.close()

    results = raw.get("results") if isinstance(raw, dict) else raw
    if not isinstance(results, list):
        return "", {}
    lines: list[str] = []
    skills: dict[str, dict[str, str]] = {}
    for it in results:
        if not isinstance(it, dict):
            continue
        slug = (
            it.get("name")
            or it.get("id")
            or it.get("agent_id")
            or it.get("title")
            or ""
        ).strip()
        if not slug or slug in skills:
            continue
        desc = (it.get("description") or "").replace("\n", " ").strip()[:200]
        repo = (it.get("repo") or "").strip()
        url = (it.get("url") or it.get("source_url") or "").strip()
        lines.append(f"- {slug} (score {it.get('score')}): {desc}")
        skills[slug] = {
            "repo": repo,
            "url": url,
            "install_cmd": (it.get("install_cmd") or "").strip(),
            "desc": desc,
            "score": str(it.get("score") or ""),
        }
        if len(skills) >= limit:
            break
    return "\n".join(lines), skills

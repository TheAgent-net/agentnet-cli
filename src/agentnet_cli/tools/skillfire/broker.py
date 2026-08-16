"""Post-gate skill feedback and content upgrade helpers."""

from __future__ import annotations

import threading

from . import config, content


def _send_recommendation_sync(
    query: str,
    relevant: list[dict[str, str]],
    skills: dict[str, dict[str, str]],
    *,
    harness: str | None = None,
    session: str | None = None,
    classifier_model: str | None = None,
    model: str | None = None,
) -> None:
    """POST skill feedback. Run off-thread by :func:`send_recommendation`."""
    from ...infra.credentials import make_platform_client

    recommended = [
        {
            "name": r.get("name", ""),
            "why": r.get("why", "") or skills.get(r.get("name", ""), {}).get("desc", ""),
            "score": skills.get(r.get("name", ""), {}).get("score") or None,
        }
        for r in relevant
        if r.get("name")
    ]
    if not recommended:
        return
    platform = make_platform_client(timeout=5.0)
    if platform is None:
        return
    try:
        platform.send_skill_recommendation(
            use_case=query,
            recommended=recommended,
            harness=harness,
            session=session,
            classifier_model=classifier_model,
            model=model,
        )
    except Exception:  # noqa: BLE001 — telemetry must never break the worker
        pass
    finally:
        platform.close()


def send_recommendation(
    query: str,
    relevant: list[dict[str, str]],
    skills: dict[str, dict[str, str]],
    *,
    harness: str | None = None,
    session: str | None = None,
    classifier_model: str | None = None,
    model: str | None = None,
) -> threading.Thread:
    """Send post-gate feedback on a daemon thread. Callers join before exit."""
    thread = threading.Thread(
        target=_send_recommendation_sync,
        args=(query, relevant, skills),
        kwargs={
            "harness": harness,
            "session": session,
            "classifier_model": classifier_model,
            "model": model,
        },
        daemon=True,
    )
    thread.start()
    return thread


def upgrade_outcome(
    query: str,
    relevant: list[dict[str, str]],
    skills: dict[str, dict[str, str]],
    *,
    timeout: float,
    harness: str | None = None,
    session: str | None = None,
    classifier_model: str | None = None,
    model: str | None = None,
) -> str:
    """Get skill content for the relevant matches. Return ``""`` when none."""
    _ = (query, harness, session, classifier_model, model)
    return content.build_content_outcome(
        relevant, skills, timeout=min(timeout, config.CONTENT_BUDGET)
    )

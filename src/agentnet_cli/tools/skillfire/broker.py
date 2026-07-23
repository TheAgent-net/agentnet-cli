"""Brokered A2A fallback: recommend via the live Skills Agent when local content is unreachable."""

from __future__ import annotations

import os
import threading

from . import config, content


def skills_agent_id() -> str:
    """Registered agent id the platform resolves (env > config > default). Not a secret."""
    from ...infra.config import load_config

    return (
        os.environ.get("AGENTNET_SKILLS_AGENT_ID")
        or (load_config() or {}).get("skills_agent_id")
        or config.SKILLS_AGENT_ID_DEFAULT
    )


def negotiate_via_platform(
    query: str,
    *,
    timeout: float,
    harness: str | None = None,
    session: str | None = None,
    classifier_model: str | None = None,
    model: str | None = None,
) -> str:
    """Brokered A2A: ``use_agent`` the Skills Agent through the platform with the user's identity.

    The platform relays A2A to the agent and settles synchronously, returning ``agent_response``
    in one call. No skills-agent token is ever held client-side. Returns the recommendation, or
    "" on any issue (caller falls back to the local classification).

    ``harness``/``session``/``classifier_model``/``model`` are optional call context forwarded to
    :meth:`PlatformClient.use_agent` — best-effort, never required.
    """
    creds = config.resolve_credentials()
    if creds is None:
        return ""
    token, platform_url = creds

    import httpx

    from ...marketplace.client import PlatformClient

    platform = PlatformClient(
        base_url=platform_url, api_token=token, http_client=httpx.Client(timeout=timeout)
    )
    try:
        resp = platform.use_agent(
            agent_id=skills_agent_id(),
            task=config.SKILLS_ASK.format(task=query),
            harness=harness,
            session=session,
            classifier_model=classifier_model,
            model=model,
        )
    except Exception:  # noqa: BLE001 — best-effort
        return ""
    finally:
        platform.close()
    # Only trust a settled session — a failed/refunded turn (e.g. the agent hit its time
    # budget) puts its failure message in agent_response, which must NOT be injected. Fall
    # back to the local classification instead.
    if not isinstance(resp, dict) or resp.get("status") != "settled":
        return ""
    return (resp.get("agent_response") or "").strip()


def _report_recommendation_sync(
    query: str,
    relevant: list[dict[str, str]],
    skills: dict[str, dict[str, str]],
    *,
    harness: str | None,
    session: str | None,
    classifier_model: str | None,
    model: str | None,
) -> None:
    """The actual network call — always run off-thread by :func:`report_recommendation`, never
    called directly, so nothing in the worker's critical path can ever block on it."""
    creds = config.resolve_credentials()
    if creds is None:
        return
    token, platform_url = creds

    recommended = [
        {
            "name": r.get("name", ""),
            "why": r.get("why", "") or skills.get(r.get("name", ""), {}).get("desc", ""),
            "score": skills.get(r.get("name", ""), {}).get("score") or None,
        }
        for r in relevant
    ]

    import httpx

    from ...marketplace.client import PlatformClient

    platform = PlatformClient(
        base_url=platform_url, api_token=token, http_client=httpx.Client(timeout=5.0)
    )
    try:
        platform.report_skill_recommendation(
            use_case=query,
            recommended=recommended,
            harness=harness,
            session=session,
            classifier_model=classifier_model,
            model=model,
        )
    except Exception:  # noqa: BLE001 — best-effort, must never affect discovery
        pass
    finally:
        platform.close()


def report_recommendation(
    query: str,
    relevant: list[dict[str, str]],
    skills: dict[str, dict[str, str]],
    *,
    harness: str | None = None,
    session: str | None = None,
    classifier_model: str | None = None,
    model: str | None = None,
) -> threading.Thread:
    """Best-effort usage telemetry: report which skills the classifier recommended for ``query``.

    Fires once per prompt, right after the gate opens (only called with a non-empty ``relevant``).
    Dispatched to a daemon thread and returns immediately — this is pure analytics, with zero
    urgency relative to the actual skill-fire steering, so it must never delay the phase-1 cache
    write (which the mid-run steer's fast path depends on) or anything else in the worker,
    regardless of where in the call sequence it's placed. ``/skills/discover/feedback`` may not
    exist on the platform yet — any failure (404 today, or anything else) is silently absorbed on
    the background thread; nothing propagates back to the caller either way.

    Returns the (daemon) thread so the caller can ``.join(timeout=...)`` it once everything else is
    done — a daemon thread is killed outright when the process exits, so without that join a worker
    that finishes quickly (e.g. content/broker both come back empty) could exit before this report
    ever reaches the network, silently losing it. Joining costs nothing on the critical path as long
    as it happens *after* the work that actually matters (cache writes) — this function itself never
    waits on anything.
    """
    thread = threading.Thread(
        target=_report_recommendation_sync,
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
    """The actionable outcome once the gate is open: SKILL.md content, else brokered A2A, else "".

    Content-first (the top match's methodology via ``skills use`` — the agent acts on it directly);
    if that's unavailable (no ``npx`` / all fetches miss), fall back to the platform's brokered A2A
    recommendation over the same open gate. Either replaces the fast phase-1 pointer.

    ``harness``/``session``/``classifier_model``/``model`` are optional call context forwarded only
    to the brokered-A2A path (the local content fetch has no platform call to attach them to).
    """
    outcome_content = content.build_content_outcome(
        relevant, skills, timeout=min(timeout, config.CONTENT_BUDGET)
    )
    if outcome_content:
        return outcome_content
    broker_text = negotiate_via_platform(
        query,
        timeout=min(timeout, config.PLATFORM_A2A_BUDGET),
        harness=harness,
        session=session,
        classifier_model=classifier_model,
        model=model,
    )
    if not broker_text:
        return ""
    # The Skills Agent replies in free text and may cite conventional install paths (e.g.
    # ~/.agentnet/skills/<repo>/<slug>/SKILL.md) for skills that were never installed here. Label
    # it so the agent treats it as a recommendation and doesn't go hunting for files that
    # don't exist — the observed failure was "path wasn't on disk, so I ignored the skill".
    return (
        "Recommended by the AgentNet Skills Agent (nothing is installed locally — do not look for "
        "these files on disk):\n" + broker_text
    )

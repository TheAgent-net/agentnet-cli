"""Detached discovery worker: candidates, classify, render, content, broker, cache.

:func:`spawn_worker` builds and starts the detached ``skill-hook --fetch`` subprocess.
"""

from __future__ import annotations

from . import broker, candidates, config, render
from . import classifier as _classifier
from . import session as _session
from ...infra.proc import agentnet_invocation, start_detached_process


def run_subagent(query: str, *, limit: int, timeout: float, classifier: str = "claude") -> str:
    """Run skill scout on one query. Return the outcome text, or ``""``.

    Get candidates, classify them, then upgrade to skill content or a broker reply.
    """
    if not query:
        return ""
    cand_text, skills = candidates.get_skill_candidates(
        query,
        limit=config.CANDIDATE_LIMIT,
        timeout=min(timeout, 10.0),
        harness=classifier,
    )
    if not cand_text:
        return ""
    relevant, actual_backend = _classifier.classify(
        query, cand_text, timeout=min(timeout, 45.0), backend=classifier
    )
    if not relevant:
        return ""
    actual_model = _classifier.resolve_classifier_model(actual_backend) if actual_backend else None
    agent_model = actual_model if actual_backend == "hermes" else None
    report_thread = broker.send_recommendation(
        query,
        relevant,
        skills,
        harness=classifier,
        classifier_model=actual_model,
        model=agent_model,
    )
    list_block = render.render_list(relevant, skills, limit=limit)
    content_outcome = broker.upgrade_outcome(
        query,
        relevant,
        skills,
        timeout=timeout,
        harness=classifier,
        classifier_model=actual_model,
        model=agent_model,
    )
    outcome = render.compose_outcome(list_block, content_outcome)
    report_thread.join(timeout=config.REPORT_JOIN_TIMEOUT)
    return outcome


def run_fetch(
    *, session: str, query: str, limit: int, timeout: float, classifier: str = "claude"
) -> None:
    """Run the detached worker in two phases.

    Phase 1 caches the skill list when the gate opens. Phase 2 adds top-match
    ``SKILL.md`` content with ``skills use``. ``classifier`` selects the gate CLI
    (``claude``, ``cursor``, or ``hermes``). If the gate is closed, write nothing.

    Retrieval sends ``harness`` + ``session`` only. Post-gate feedback also sends
    ``classifier_model`` and ``model`` for the backend that actually ran.
    """
    if not query:
        return
    try:
        from ...cli.core.updater import maybe_auto_update  # noqa: PLC0415

        maybe_auto_update(quiet=True)
    except Exception:  # noqa: BLE001 — an update check must never disrupt discovery
        pass
    budget = max(timeout, config.SUBAGENT_TIMEOUT)
    path = _session.cache_path(session)
    cand_text, skills = candidates.get_skill_candidates(
        query,
        limit=config.CANDIDATE_LIMIT,
        timeout=min(budget, 10.0),
        harness=classifier,
        session=session,
    )
    if not cand_text:
        return
    relevant, actual_backend = _classifier.classify(
        query, cand_text, timeout=min(budget, 45.0), backend=classifier
    )
    if not relevant:
        return
    actual_model = _classifier.resolve_classifier_model(actual_backend) if actual_backend else None
    agent_model = actual_model if actual_backend == "hermes" else None
    report_thread = broker.send_recommendation(
        query,
        relevant,
        skills,
        harness=classifier,
        session=session,
        classifier_model=actual_model,
        model=agent_model,
    )
    list_block = render.render_list(relevant, skills, limit=limit)
    _session.cache_write(path, render.compose_outcome(list_block, ""), final=False)
    content_outcome = broker.upgrade_outcome(
        query,
        relevant,
        skills,
        timeout=budget,
        harness=classifier,
        session=session,
        classifier_model=actual_model,
        model=agent_model,
    )
    if _session.emit_marker(path).exists():
        report_thread.join(timeout=config.REPORT_JOIN_TIMEOUT)
        return
    _session.cache_write(path, render.compose_outcome(list_block, content_outcome), final=True)
    report_thread.join(timeout=config.REPORT_JOIN_TIMEOUT)


def spawn_worker(session: str, prompt: str, *, limit: int, timeout: float, classifier: str) -> None:
    """Claim the spawn marker and start the detached ``--fetch`` worker."""
    if not _session.claim(_session.spawn_marker(session, prompt)):
        return
    _session.clear_stale(session)
    try:
        start_detached_process([
            *agentnet_invocation(),
            "skill-hook", "--fetch",
            "--session", session, "--query", prompt,
            "--limit", str(limit), "--timeout", str(timeout),
            "--classifier", classifier,
        ])
    except Exception:  # noqa: BLE001 — best-effort: never block the prompt/turn
        pass

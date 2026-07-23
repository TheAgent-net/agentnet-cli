"""The detached discovery worker: candidates -> classify -> render -> content/broker -> cache.

:func:`spawn_worker` is the single place that builds and launches the detached
``skill-hook --fetch`` subprocess — replacing the near-identical Popen-building block that used to
be duplicated in each harness adapter (only the ``--classifier`` argv value differed).
"""

from __future__ import annotations

import shutil
import subprocess
import sys

from . import broker, candidates, config, render
from . import classifier as _classifier
from . import session as _session


def run_subagent(query: str, *, limit: int, timeout: float, classifier: str = "claude") -> str:
    """Every-prompt skill scout (synchronous form used by tests/manual runs).

    1. Fetch installable skill candidates + classify on ``classifier``'s CLI — the reliable
       relevance **gate**. Empty => not skill-relevant => nothing (zero latency).
    2. Relevant => a fast pointer, upgraded to the top match's ``SKILL.md`` methodology (or the
       brokered A2A recommendation if content is unavailable). Best-effort throughout.
    """
    if not query:
        return ""
    # Discovery is candidate *retrieval* — it runs before the gate, so it carries only harness +
    # session, never a gate model (which backend/model classifies isn't known yet and can fall
    # back). The gate model is attributed below, on the post-classification records.
    cand_text, skills = candidates.fetch_skill_candidates(
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
        return ""  # gate closed — not skill-relevant
    # `classify` may have fallen back to a different backend than requested — `harness` stays the
    # requested one (that's still which IDE the user is in, unaffected by the fallback), but the
    # *model* attribution follows whichever backend actually ran, not the one we asked for.
    actual_model = _classifier.resolve_classifier_model(actual_backend) if actual_backend else None
    agent_model = actual_model if actual_backend == "hermes" else None
    report_thread = broker.report_recommendation(
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
    # This is the process's last chance to let the report actually reach the network before it
    # exits (a daemon thread is killed outright on process exit) — bounded so it can never hang;
    # everything that actually matters (the outcome above) is already computed by this point.
    report_thread.join(timeout=config.REPORT_JOIN_TIMEOUT)
    return outcome


def run_fetch(
    *, session: str, query: str, limit: int, timeout: float, classifier: str = "claude"
) -> None:
    """Detached worker (two-phase, so the outcome reaches the hooks fast).

    Phase 1 caches the recommendation list the moment the gate opens (~12s) — that is what lets the
    steer hook fire mid-answer instead of waiting the full round-trip. Phase 2 then *appends* the
    top match's actual **``SKILL.md`` methodology** (via ``skills use``) if it lands before anything
    was injected. ``classifier`` selects the gate's CLI (``claude``/``cursor``/``hermes``).
    Gate-closed => nothing cached => hooks no-op => zero latency.

    This detached worker is also where the CLI auto-update runs (``maybe_auto_update``): once per
    turn, off the agent's critical path. The synchronous hooks (``--pre``/``--peek``/``--post``)
    deliberately skip it (see cli/main.py) so a tool call is never blocked. It is rate-limited and
    version-gated internally, so it is a cheap no-op unless a new release is actually available.
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
    # Discovery is candidate *retrieval* — it runs before the gate, so it carries only harness +
    # session, never a gate model (which backend/model classifies isn't known yet and can fall
    # back). The gate model is attributed below, on the post-classification records.
    cand_text, skills = candidates.fetch_skill_candidates(
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
        return  # gate closed — not skill-relevant
    # `classify` may have fallen back to a different backend than requested — `harness` stays the
    # requested one (that's still which IDE the user is in, unaffected by the fallback), but the
    # *model* attribution follows whichever backend actually ran, not the one we asked for.
    actual_model = _classifier.resolve_classifier_model(actual_backend) if actual_backend else None
    agent_model = actual_model if actual_backend == "hermes" else None
    report_thread = broker.report_recommendation(
        query,
        relevant,
        skills,
        harness=classifier,
        session=session,
        classifier_model=actual_model,
        model=agent_model,
    )
    # Every cached outcome goes through render.compose_outcome so the user-block delimiters the
    # steer references are always present — even list-only. Phase 1 caches fast but NOT final (it
    # names skills without any methodology, so a steer on it would hand the agent nothing to apply).
    list_block = render.render_list(relevant, skills, limit=limit)
    _session.cache_write(path, render.compose_outcome(list_block, ""), final=False)
    # Phase 2: attach the top match's actionable SKILL.md content and mark the outcome final.
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
        # This is still the process's last chance to let the report reach the network before it
        # exits (a daemon thread is killed outright on exit) — bounded so it can never hang.
        report_thread.join(timeout=config.REPORT_JOIN_TIMEOUT)
        return  # something already steered — don't rewrite what was shown
    # If no content is reachable (no npx / all fetches missed), promote the fenced list to final
    # rather than leaving the steer blocked forever.
    _session.cache_write(path, render.compose_outcome(list_block, content_outcome), final=True)
    # Last chance to let the report reach the network before the process exits — bounded so it can
    # never hang; everything that actually matters (the cache write above) is already done.
    report_thread.join(timeout=config.REPORT_JOIN_TIMEOUT)


def spawn_worker(session: str, prompt: str, *, limit: int, timeout: float, classifier: str) -> None:
    """Claim the per-(session, prompt) spawn marker and launch the detached ``--fetch`` worker.

    Guarded by :func:`skillfire.session.claim` so duplicate pre-event registrations (each harness
    may register its hook in more than one config file) spawn exactly one worker — not one
    classifier run per registration. Drops the previous prompt's cached outcome + steer claim first
    so the new prompt starts fresh.
    """
    if not _session.claim(_session.spawn_marker(session, prompt)):
        return  # a duplicate pre-event already spawned the worker for this prompt
    _session.clear_stale(session)
    exe = shutil.which("agentnet") or sys.argv[0]
    try:
        subprocess.Popen(  # noqa: S603 — detached discovery, never awaited
            [
                exe, "skill-hook", "--fetch",
                "--session", session, "--query", prompt,
                "--limit", str(limit), "--timeout", str(timeout),
                "--classifier", classifier,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:  # noqa: BLE001 — best-effort: never block the prompt/turn
        pass

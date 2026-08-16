"""Steer-text builders and port decisions for mid-run nudge and turn-end fallback.

:func:`check_steer` and :func:`check_fallback` read the cache, check ``final``, take the emit
claim, and build steer text. Adapters call them from peek and post handlers.
"""

from __future__ import annotations

import time

from . import render
from . import session as _session

_MAX_POST_WAIT = 3.0
_POST_POLL_INTERVAL = 0.1


def _show_block_instruction() -> str:
    """Return instructions to reproduce the user-facing block exactly."""
    return (
        f"reply with the text between '{render.USER_BLOCK_START}' and '{render.USER_BLOCK_END}', "
        "reproduced EXACTLY: every skill line, every percentage. Do not summarize it, do not "
        "reformat it, do not mention only the top match, and do not replace it with a sentence of "
        "your own"
    )


def steer_reason(outcome: str) -> str:
    """Build mid-run steer text from a final outcome."""
    # The agent-only section is absent when no methodology was reachable (list-only outcome, which
    # still gets promoted to final). Pointing at a section that isn't there invites the model to
    # mishandle the whole steer, so the steps adapt to what the outcome actually contains.
    if render.AGENT_ONLY in outcome:
        steps = (
            f"STEP 1 — Your next reply to the user must start with — {_show_block_instruction()}.\n"
            "STEP 2 — Then follow the AGENT ONLY section (the user does not see it).\n"
            "STEP 3 — Then continue with the task.\n\n"
        )
    else:
        steps = (
            f"STEP 1 — Your next reply to the user must start with — {_show_block_instruction()}.\n"
            "STEP 2 — Then continue with the task, applying what those skills suggest.\n\n"
        )
    return (
        "[AgentNet] Relevant skills found. AgentNet already searched its marketplace — do not run "
        "your own skill search, and do not install anything.\n\n" + steps + outcome
    )


def fold_context(outcome: str) -> str:
    """Build turn-end fallback text from a final outcome."""
    tail = (
        ", then follow the AGENT ONLY section"
        if render.AGENT_ONLY in outcome
        else ", then apply what those skills suggest"
    )
    return (
        "[AgentNet] Relevant skills found. AgentNet already searched its marketplace — do not run "
        "your own skill search, and do not install anything.\n\n"
        f"Before finishing, {_show_block_instruction()}{tail}.\n\n" + outcome
    )


def check_steer(session: str) -> str | None:
    """Return mid-run steer text for an actionable, unclaimed outcome, or ``None``.

    Return ``None`` when the cache is not ready, the outcome is phase-1 only, or another hook
    already claimed the steer.
    """
    path = _session.cache_path(session)
    data = _session.cache_read(path)
    if not data or not data.get("outcome"):
        return None  # not ready or nothing relevant
    if not data.get("final"):
        return None  # phase-1 list only — nothing to apply yet; let a later tool call steer instead
    if not _session.claim(_session.emit_marker(path)):
        return None  # another peek/post (or a duplicate hook) already steered
    return steer_reason(data["outcome"])


def check_fallback(session: str, *, timeout: float) -> str | None:
    """Return turn-end fallback text for a no-tool answer, or ``None``.

    Wait briefly for a near-miss outcome. Prefer a final outcome, but take the list when that is
    all the worker produced. Return ``None`` when nothing is relevant or a steer already ran.
    """
    path = _session.cache_path(session)
    deadline = time.monotonic() + min(timeout, _MAX_POST_WAIT)
    data = _session.cache_read(path)
    while (not data or not data.get("outcome") or not data.get("final")) and (
        time.monotonic() < deadline
    ):
        time.sleep(_POST_POLL_INTERVAL)
        data = _session.cache_read(path)

    outcome = (data or {}).get("outcome") or ""
    if not outcome or not _session.claim(_session.emit_marker(path)):
        return None
    return fold_context(outcome)


def check_steer_raw(session: str) -> str | None:
    """Same as :func:`check_steer`, but return the bare outcome with no wrapper text."""
    path = _session.cache_path(session)
    data = _session.cache_read(path)
    if not data or not data.get("outcome"):
        return None  # not ready or nothing relevant
    if not data.get("final"):
        return None  # phase-1 list only — nothing to apply yet; let a later tool call steer instead
    if not _session.claim(_session.emit_marker(path)):
        return None  # another peek/post (or a duplicate hook) already steered
    return data["outcome"]


def check_fallback_raw(session: str, *, timeout: float) -> str | None:
    """Same as :func:`check_fallback`, but return the bare outcome with no wrapper text."""
    path = _session.cache_path(session)
    deadline = time.monotonic() + min(timeout, _MAX_POST_WAIT)
    data = _session.cache_read(path)
    while (not data or not data.get("outcome") or not data.get("final")) and (
        time.monotonic() < deadline
    ):
        time.sleep(_POST_POLL_INTERVAL)
        data = _session.cache_read(path)

    outcome = (data or {}).get("outcome") or ""
    if not outcome or not _session.claim(_session.emit_marker(path)):
        return None
    return outcome

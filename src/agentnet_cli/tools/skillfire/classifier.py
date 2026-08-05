"""Backend-aware relevance gate: run a classifier over real skill candidates.

Four CLI/runtime backends (Claude, Cursor, Hermes, opencode), tried in the requested order with
fallback to the others, so a machine with only one still gates. Each returns raw stdout/response
text or ``None`` if that backend is unavailable; :func:`classify` parses whichever one actually ran.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import config


def _write_isolating_mcp_config() -> Path | None:
    """Empty strict MCP config so the subagent loads none of the user's MCP servers."""
    try:
        fd, name = tempfile.mkstemp(prefix="agentnet-mcp-", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump({"mcpServers": {}}, f)
        return Path(name)
    except Exception:  # noqa: BLE001
        return None


def _run_claude_classifier(msg: str, *, timeout: float) -> str | None:
    """Run the gate via a no-tool ``claude -p`` (Haiku). Returns stdout, or None if unavailable."""
    claude = shutil.which("claude")
    if not claude:
        return None
    mcp_cfg = _write_isolating_mcp_config()
    if mcp_cfg is None:
        return None
    env = {**os.environ, config.SUBAGENT_ENV: "1"}  # break hook recursion inside the subagent
    try:
        proc = subprocess.run(  # noqa: S603
            [
                claude, "-p", "--model", config.SUBAGENT_MODEL,
                "--strict-mcp-config", "--mcp-config", str(mcp_cfg),
                "--append-system-prompt", config.CLASSIFIER_PROMPT,
                msg,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except Exception:  # noqa: BLE001 — best-effort
        return None
    finally:
        try:
            mcp_cfg.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    return proc.stdout if proc.returncode == 0 else None


def _run_cursor_classifier(msg: str, *, timeout: float) -> str | None:
    """Run the gate via ``cursor-agent -p`` on the user's Cursor model. stdout, or None.

    ``--mode ask`` keeps it read-only (no tool/writes); ``--trust`` skips the headless trust prompt.
    cursor-agent has no system-prompt flag, so the classifier instructions are prepended to the
    prompt. Needs the user authenticated (``cursor-agent login``) — returns None otherwise.
    """
    exe = shutil.which("cursor-agent")
    if not exe:
        return None
    env = {**os.environ, config.SUBAGENT_ENV: "1"}  # break hook recursion inside the subagent
    argv = [exe, "-p", "--mode", "ask", "--output-format", "text", "--trust"]
    model = os.environ.get(config.CURSOR_MODEL_ENV, "").strip()
    if model:
        argv += ["--model", model]
    argv.append(f"{config.CLASSIFIER_PROMPT}\n\n{msg}")
    try:
        proc = subprocess.run(  # noqa: S603
            argv, capture_output=True, text=True, timeout=timeout, env=env, check=False
        )
    except Exception:  # noqa: BLE001 — best-effort
        return None
    return proc.stdout if proc.returncode == 0 else None


def _run_hermes_classifier(msg: str, *, timeout: float) -> str | None:
    """Run the gate as an in-process Hermes ``AIAgent`` on the user's own model. stdout, or None.

    Hermes' advantage over the CLI backends: no subprocess and no separate auth — the gateway
    helpers resolve the user's configured model *and* provider credentials (API keys, base URLs,
    OAuth, credential pools), so this works against custom endpoints too.

    ``skip_memory=False`` loads the user's memory store + profile so the gate can weigh relevance
    against *this* user's context (stack, preferences) — per-user recommendations. It is only a
    context signal: the ``memory`` toolset stays in ``disabled_toolsets`` (the gate reads memory but
    can't spend its single iteration calling memory tools), and ``max_iterations=1`` + the disabled
    toolsets keep it to one classify turn. (Personalising *discovery* — which skills get fetched —
    is the higher-leverage follow-up; this only reweights the already-fetched candidates.)

    Only importable when running inside Hermes' venv (``connect hermes`` installs agentnet there);
    returns None otherwise so the caller falls back to a CLI backend.
    """
    try:
        from gateway.run import _resolve_gateway_model, _resolve_runtime_agent_kwargs
        from run_agent import AIAgent
    except Exception:  # noqa: BLE001 — not running inside Hermes
        return None
    try:
        agent = AIAgent(
            model=_resolve_gateway_model(),
            **_resolve_runtime_agent_kwargs(),
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=False,  # share the user's memory/profile for per-user relevance
            max_iterations=1,
            disabled_toolsets=["delegation", "memory", "terminal", "files", "web"],
        )
        result = agent.run_conversation(f"{config.CLASSIFIER_PROMPT}\n\n{msg}")
    except Exception:  # noqa: BLE001 — best-effort
        return None
    if not isinstance(result, dict):
        return None
    return (result.get("final_response") or "").strip() or None


def _run_opencode_classifier(msg: str, *, timeout: float) -> str | None:
    """Run the gate via ``opencode run --pure`` on the user's own opencode model. stdout, or None.

    This is the **native** opencode gate: an opencode user needn't have Claude or Cursor installed.
    ``--pure`` runs without external plugins, so it can't recurse into our own agentnet plugin (and
    is faster). opencode has no system-prompt flag, so the classifier instructions are prepended to
    the message. ``AGENTNET_OPENCODE_CLASSIFIER_MODEL`` (``provider/model``) pins a cheaper/faster
    gate model; otherwise opencode's configured default runs. Returns None if opencode isn't
    installed or errors, so the caller falls back to another backend.
    """
    exe = shutil.which("opencode")
    if not exe:
        return None
    env = {**os.environ, config.SUBAGENT_ENV: "1"}  # belt-and-suspenders with --pure
    argv = [exe, "run", "--pure"]
    model = os.environ.get(config.OPENCODE_MODEL_ENV, "").strip()
    if model:
        argv += ["--model", model]
    argv.append(f"{config.CLASSIFIER_PROMPT}\n\n{msg}")
    try:
        proc = subprocess.run(  # noqa: S603
            argv, capture_output=True, text=True, timeout=timeout, env=env, check=False
        )
    except Exception:  # noqa: BLE001 — best-effort
        return None
    return proc.stdout if proc.returncode == 0 else None


_CLASSIFIER_RUNNERS = {
    "claude": _run_claude_classifier,
    "cursor": _run_cursor_classifier,
    "hermes": _run_hermes_classifier,
    "opencode": _run_opencode_classifier,
}


def _parse_classifier_json(stdout: str) -> list[dict[str, str]]:
    """Extract ``{"skills":[{"name","why"}]}`` from raw classifier stdout ([] on any issue)."""
    text = (stdout or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except Exception:  # noqa: BLE001
        return []
    skills = data.get("skills") if isinstance(data, dict) else None
    if not isinstance(skills, list):
        return []
    out: list[dict[str, str]] = []
    for s in skills:
        if isinstance(s, dict) and (s.get("name") or "").strip():
            out.append({"name": s["name"].strip(), "why": (s.get("why") or "").strip()})
    return out


def resolve_classifier_model(backend: str) -> str | None:
    """Best-effort, no-invocation lookup of which model *would* run the gate for ``backend``.

    A pure lookup — never runs the classifier, never shells out — so it's cheap to call just to
    attach context to an outgoing request. Returns ``None`` when the model can't be determined
    (e.g. the user hasn't pinned a Cursor model, or this isn't running inside Hermes' venv) rather
    than guessing.
    """
    if backend == "claude":
        return config.SUBAGENT_MODEL
    if backend == "cursor":
        return os.environ.get(config.CURSOR_MODEL_ENV, "").strip() or None
    if backend == "opencode":
        return os.environ.get(config.OPENCODE_MODEL_ENV, "").strip() or None
    if backend == "hermes":
        try:
            from gateway.run import _resolve_gateway_model  # noqa: PLC0415
        except Exception:  # noqa: BLE001 — not running inside Hermes
            return None
        try:
            return _resolve_gateway_model()
        except Exception:  # noqa: BLE001 — best-effort
            return None
    return None


def _gate_order(backend: str) -> list[str]:
    """The backend try-order for ``classify``: requested first, then the rest as fallback.

    Exception: opencode's own gate (``opencode run --pure``) has ~15-25s of fixed startup, so for the
    opencode harness we prefer a fast local CLI gate (``claude``/``cursor``, ~5s) when installed and
    fall back to the opencode model only on a machine that has neither — the relevance gate is a
    cheap classifier, not the user's coding model, so the fastest available one is the right choice.
    ``harness`` stays ``opencode`` regardless (only the gate's *speed* changes), and model attribution
    already follows the backend that actually ran.
    """
    if backend == "opencode":
        # claude -p (Haiku) is the fastest gate (~5s) when installed; else the native opencode gate
        # (~7-20s) — kept ahead of cursor-agent, whose headless run can be very slow.
        return ["claude", "opencode", "cursor", "hermes"]
    return [backend] + [b for b in config.CLASSIFIER_BACKENDS if b != backend]


def classify(
    query: str, cand_text: str, *, timeout: float, backend: str = "claude"
) -> tuple[list[dict[str, str]], str | None]:
    """Relevance classifier over the real candidates — the gate. Returns ``(relevant, actual_backend)``.

    Runs on ``backend``'s runtime (``claude -p``, ``cursor-agent -p``, in-process Hermes, or
    ``opencode run --pure``); if that is unavailable or errors, falls back to the others so a machine
    with only one still gates. ``actual_backend`` is
    whichever backend in ``CLASSIFIER_BACKENDS`` actually produced a result — **not necessarily**
    the requested ``backend`` — so a caller attributing the result (e.g. reporting
    ``classifier_model``) resolves the model for the backend that really ran, not the one it asked
    for. ``None`` only when no backend ran at all, in which case ``relevant`` is also ``[]``. Empty
    ``relevant`` (with a real ``actual_backend``) => not skill-relevant => the worker surfaces
    nothing.
    """
    msg = f"REQUEST_TEXT:\n{query}\n\nCANDIDATES:\n{cand_text}"
    order = _gate_order(backend)
    for name in order:
        runner = _CLASSIFIER_RUNNERS.get(name)
        if runner is None:
            continue
        stdout = runner(msg, timeout=timeout)
        if stdout is not None:  # this CLI ran — trust its result (even an empty/gate-closed one)
            return _parse_classifier_json(stdout), name
    return [], None

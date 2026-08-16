"""Backend-aware relevance gate: classify real skill candidates.

Three backends (Claude, Cursor, Hermes) are tried in the requested order with fallback.
Each returns stdout or ``None`` when unavailable. :func:`classify` parses the result.
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
    """Write an empty strict MCP config so the subagent loads no user MCP servers."""
    try:
        fd, name = tempfile.mkstemp(prefix="agentnet-mcp-", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump({"mcpServers": {}}, f)
        return Path(name)
    except Exception:  # noqa: BLE001
        return None


def _run_claude_classifier(msg: str, *, timeout: float) -> str | None:
    """Run the gate with ``claude -p`` (Haiku). Return stdout, or ``None`` when unavailable."""
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
    """Run the gate with ``cursor-agent -p``. Return stdout, or ``None`` when unavailable.

    ``--mode ask`` keeps it read-only. ``--trust`` skips the headless trust prompt.
    cursor-agent has no system-prompt flag, so prepend the classifier instructions to the prompt.
    Needs ``cursor-agent login`` — return ``None`` when not authenticated.
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
    """Run the gate as an in-process Hermes ``AIAgent``. Return stdout, or ``None``.

    Hermes uses the user's configured model and credentials with no subprocess.
    ``skip_memory=False`` loads the user's memory for per-user relevance.
    ``max_iterations=1`` and disabled toolsets keep one classify turn.

    Importable only inside Hermes' venv. Return ``None`` elsewhere so callers fall back to a CLI
    backend.
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


_CLASSIFIER_RUNNERS = {
    "claude": _run_claude_classifier,
    "cursor": _run_cursor_classifier,
    "hermes": _run_hermes_classifier,
}


def _parse_classifier_json(stdout: str) -> list[dict[str, str]]:
    """Extract ``{"skills":[{"name","why"}]}`` from classifier stdout. Return ``[]`` on error."""
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
    """Return the model name for ``backend`` without running the classifier.

    This is a lookup only — no subprocess and no agent run. Return ``None`` when the model is
    unknown.
    """
    if backend == "claude":
        return config.SUBAGENT_MODEL
    if backend == "cursor":
        return os.environ.get(config.CURSOR_MODEL_ENV, "").strip() or None
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


def classify(
    query: str, cand_text: str, *, timeout: float, backend: str = "claude"
) -> tuple[list[dict[str, str]], str | None]:
    """Classify candidates for relevance. Return ``(relevant, actual_backend)``.

    Run on ``backend``'s CLI first. Fall back to other backends when that CLI is missing or
    errors. ``actual_backend`` is the backend that produced a result — not always the requested
    one. Return ``([], None)`` when no backend runs. Empty ``relevant`` with a real backend means
    the prompt is not skill-relevant.
    """
    msg = f"REQUEST_TEXT:\n{query}\n\nCANDIDATES:\n{cand_text}"
    order = [backend] + [b for b in config.CLASSIFIER_BACKENDS if b != backend]
    for name in order:
        runner = _CLASSIFIER_RUNNERS.get(name)
        if runner is None:
            continue
        stdout = runner(msg, timeout=timeout)
        if stdout is not None:  # this CLI ran — trust its result (even an empty/gate-closed one)
            return _parse_classifier_json(stdout), name
    return [], None

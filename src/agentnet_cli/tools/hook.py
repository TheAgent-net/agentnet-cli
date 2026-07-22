"""Claude Code every-prompt hooks — surface relevant AgentNet skills, token-free.

Three events, so the work overlaps the answer with zero upfront latency and can steer the
live agent mid-flight:

- **UserPromptSubmit** -> ``agentnet skill-hook --pre``: reads the prompt and spawns a
  *detached* skill-scout worker, then returns immediately (no latency).
- **PostToolUse** -> ``agentnet skill-hook --peek``: on each tool call, if the worker's
  outcome is ready and not yet injected, print ``additionalContext`` to steer the agent
  mid-flight (inject-once). Exploits the asymmetry: our ~30-60s outcome lands inside the
  agent's minutes-long flow.
- **Stop** -> ``agentnet skill-hook --post``: guaranteed fallback — if nothing steered
  mid-flight (e.g. a no-tool answer), continue the turn (``decision: block`` +
  ``additionalContext``) so the agent applies the skill. Otherwise no-op.

The worker runs in two stages. First a local **relevance gate**: fetch installable skill
candidates deterministically (``discover_skills`` → skills.sh) and run a cheap headless
``claude -p`` **classifier** over them (a classifier over concrete candidates is reliable; a bare
yes/no gate isn't — with only a request in front of it the model just answers it). Empty =>
nothing cached => hooks no-op => zero latency. Second, when the gate is open, the worker fetches
the top match via ``npx skills use <repo>@<slug>`` — which downloads the skill (SKILL.md +
references) to a temp dir — and injects a **concise header + that on-disk path**, so the agent
reads and applies a concrete methodology from disk rather than a pointer it can ignore (and the
hook block stays readable, not a full SKILL.md dump). No files are written to the user's repo. If
the fetch is unavailable (no ``npx``), it falls back to a pointer, and — behind the same open
gate — to the live **Skills Agent** over
**brokered A2A** (the platform's ``use_agent`` with the user's ``setup`` identity relays A2A;
**no skills-agent token ever touches the client**).

Strictly **best-effort**: no token, no ``claude`` binary, empty prompt, no candidates, an
unreachable platform, or a not-ready cache all degrade cleanly and never block, slow, or fail
the turn.

``claude -p`` inherits the user's hooks; ``AGENTNET_SKILL_SUBAGENT=1`` in the child env makes
the hooks no-op inside the subagent so it can't re-trigger itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_DEFAULT_PLATFORM_URL = "https://app.agentnet.market"

# Skill-scout subagent: a cheap model, pinned by id (not the "haiku" alias, which older
# Claude Code maps to a retired 404 model). It runs detached, so this never delays the turn.
SUBAGENT_MODEL = "claude-haiku-4-5-20251001"
SUBAGENT_TIMEOUT = 60.0
# The relevance gate runs on the harness-native runtime: `claude -p` (Claude), `cursor-agent -p`
# (Cursor), or an in-process AIAgent (Hermes). The requested backend is tried first, then the
# others as a fallback, so a machine with only one still gates.
CLASSIFIER_BACKENDS = ("claude", "cursor", "hermes")
# cursor-agent uses the user's default Cursor model for the gate; pin a cheaper/faster one via this
# env var (e.g. AGENTNET_CURSOR_CLASSIFIER_MODEL=gpt-5-mini).
_CURSOR_MODEL_ENV = "AGENTNET_CURSOR_CLASSIFIER_MODEL"
# Set in the subagent's env so the inherited hooks no-op there.
_SUBAGENT_ENV = "AGENTNET_SKILL_SUBAGENT"
# How many skill candidates to hand the classifier. Kept well above the display limit so the
# classifier has a real pool to rank from and can return a full list.
_CANDIDATE_LIMIT = 12
# The actionable payload is one skill's full SKILL.md (plenty of context), but try the top few
# relevant candidates so a single bad-slug/fetch miss doesn't lose the whole content upgrade.
_CONTENT_ATTEMPTS = 2
# Wall-clock budget for the `npx skills use` content fetch (cold npx + fetch).
_CONTENT_BUDGET = 40.0

# The registered Skills Agent on the AgentNet platform (brokered A2A target). Overridable via
# env/config for other agents later; never a secret — just an agent id the platform resolves.
SKILLS_AGENT_ID_DEFAULT = "agentnet-skills-agent"
# Budget for the platform use_agent call (it relays A2A + settles synchronously; ~7s typical).
_PLATFORM_A2A_BUDGET = 45.0
_SKILLS_ASK = (
    "Recommend the single best existing skill for this task and how to apply it. "
    "Be direct; do not ask clarifying questions.\n\nTask: {task}"
)

# The subagent is a pure relevance CLASSIFIER, not an assistant: given the prompt and real
# marketplace candidates, it returns strict JSON naming the genuinely-relevant ones (or []).
_CLASSIFIER_PROMPT = (
    "You are a relevance CLASSIFIER for the AgentNet skill marketplace. You never answer "
    "or perform the request; you only classify. Given REQUEST_TEXT and CANDIDATES, respond "
    'with STRICT JSON and nothing else: {"skills":[{"name":"<exact candidate name>",'
    '"why":"<one short line describing what the skill does for this task>"}]} listing every '
    "candidate that would genuinely help, most relevant first, up to 6. If none genuinely fit, "
    'or the request is trivial or conversational, respond {"skills":[]}.'
)


def _resolve_credentials() -> tuple[str, str] | None:
    """Resolve (token, platform_url) from env then config, or None. Never exits."""
    from ..infra.config import load_config

    token = os.environ.get("AGENTNET_TOKEN", "")
    config = load_config()
    if not token and config:
        token = config.get("api_token", "")
    if not token:
        return None
    platform_url = _DEFAULT_PLATFORM_URL
    if config:
        platform_url = config.get("platform_url", platform_url)
    return token, platform_url


def _read_event() -> dict[str, Any] | None:
    """Read the hook event JSON from stdin (None on any error)."""
    try:
        event = json.loads(sys.stdin.read())
    except Exception:  # noqa: BLE001
        return None
    return event if isinstance(event, dict) else None


def _prompt_from_event(event: dict[str, Any]) -> str:
    """The user's text from a UserPromptSubmit event."""
    prompt = event.get("prompt")
    return prompt.strip() if isinstance(prompt, str) and prompt.strip() else ""


def _cache_path(session_id: str) -> Path:
    """Session-keyed cache shared by the worker and the hooks.

    Non-prompt events (PostToolUse, Stop) carry no prompt, so all three can only agree on the
    session. Prompts are sequential per session, so the session cache holds the current
    prompt's outcome. Stored as ``{"outcome": <text>}``.
    """
    key = hashlib.sha1((session_id or "default").encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "agentnet-skill" / f"{key}.json"


def _cache_read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def _cache_write(path: Path, outcome: str, *, final: bool = True) -> None:
    """Cache the outcome. ``final`` marks it **actionable** (the agent has something to apply).

    Phase 1 caches the recommendation list with ``final=False``: it names skills but carries no
    methodology, so steering on it hands the agent nothing to do. Phase 2 re-writes with
    ``final=True`` once the SKILL.md content is attached (or once we know none is coming).
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"outcome": outcome, "final": final}))
        tmp.replace(path)
    except Exception:  # noqa: BLE001
        pass


def _claim(marker: Path) -> bool:
    """Atomically create ``marker``; return True only for the caller that created it.

    The hooks are registered in both ``settings.json`` and the plugin's ``hooks.json``, so Claude
    Code may run each event's hook twice in parallel. An ``O_EXCL`` create is the atomic
    once-primitive: exactly one of N concurrent callers wins, the rest see the file exists. Used to
    steer once (peek/post) and spawn one worker (pre) regardless of how many copies fire.
    """
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(marker), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except Exception:  # noqa: BLE001 — best-effort: on any error, don't claim (avoid a double)
        return False


def _emit_marker(cache: Path) -> Path:
    """Once-per-prompt steer claim (shared by peek + post); cleared by the next ``--pre``."""
    return cache.with_suffix(".emitted")


def _spawn_marker(session: str, prompt: str) -> Path:
    """Once-per-(session, prompt) worker-spawn claim, so duplicate ``--pre`` hooks spawn one worker.

    Keyed by the prompt hash — the only thing both parallel ``--pre`` invocations share — so a new
    prompt naturally gets a fresh claim without a reset race.
    """
    cache = _cache_path(session)
    h = hashlib.sha1(prompt.encode()).hexdigest()[:16]
    return cache.parent / f"{cache.stem}.{h}.spawn"


def _write_isolating_mcp_config() -> Path | None:
    """Empty strict MCP config so the subagent loads none of the user's MCP servers."""
    try:
        fd, name = tempfile.mkstemp(prefix="agentnet-mcp-", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump({"mcpServers": {}}, f)
        return Path(name)
    except Exception:  # noqa: BLE001
        return None


def _fetch_skill_candidates(
    query: str, *, limit: int, timeout: float
) -> tuple[str, dict[str, dict[str, str]]]:
    """Installable skill candidates for the prompt.

    Returns ``(candidate_text, {slug: {repo, url, install_cmd, desc}})`` sourced from
    ``discover_skills`` (skills.sh) — only skills.sh results, since their ``<repo>@<slug>`` is what
    ``skills use`` fetches. ``("", {})`` on any issue (best-effort).
    """
    creds = _resolve_credentials()
    if creds is None:
        return "", {}
    token, platform_url = creds

    import httpx

    from ..marketplace.skills.discovery import SkillDiscovery

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


def _run_claude_classifier(msg: str, *, timeout: float) -> str | None:
    """Run the gate via a no-tool ``claude -p`` (Haiku). Returns stdout, or None if unavailable."""
    claude = shutil.which("claude")
    if not claude:
        return None
    mcp_cfg = _write_isolating_mcp_config()
    if mcp_cfg is None:
        return None
    env = {**os.environ, _SUBAGENT_ENV: "1"}  # break hook recursion inside the subagent
    try:
        proc = subprocess.run(  # noqa: S603
            [
                claude, "-p", "--model", SUBAGENT_MODEL,
                "--strict-mcp-config", "--mcp-config", str(mcp_cfg),
                "--append-system-prompt", _CLASSIFIER_PROMPT,
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
    env = {**os.environ, _SUBAGENT_ENV: "1"}  # break hook recursion inside the subagent
    argv = [exe, "-p", "--mode", "ask", "--output-format", "text", "--trust"]
    model = os.environ.get(_CURSOR_MODEL_ENV, "").strip()
    if model:
        argv += ["--model", model]
    argv.append(f"{_CLASSIFIER_PROMPT}\n\n{msg}")
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
        result = agent.run_conversation(f"{_CLASSIFIER_PROMPT}\n\n{msg}")
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


def _classify(
    query: str, cand_text: str, *, timeout: float, backend: str = "claude"
) -> list[dict[str, str]]:
    """Relevance classifier over the real candidates — the gate. Returns the relevant subset or [].

    Runs on ``backend``'s CLI (``claude -p`` or ``cursor-agent -p``); if that CLI is unavailable or
    errors, falls back to the other so a machine with only one still gates. Empty => not
    skill-relevant => the worker surfaces nothing.
    """
    msg = f"REQUEST_TEXT:\n{query}\n\nCANDIDATES:\n{cand_text}"
    order = [backend] + [b for b in CLASSIFIER_BACKENDS if b != backend]
    for name in order:
        runner = _CLASSIFIER_RUNNERS.get(name)
        if runner is None:
            continue
        stdout = runner(msg, timeout=timeout)
        if stdout is not None:  # this CLI ran — trust its result (even an empty/gate-closed one)
            return _parse_classifier_json(stdout)
    return []


def _render_list(
    relevant: list[dict[str, str]], skills: dict[str, dict[str, str]], *, limit: int
) -> str:
    """The user-facing block: ``name (NN%) — what it does for this task``.

    Written to be reproduced verbatim, so it carries no agent-only noise — no install commands
    (agents executed them, derailing the turn) and no paths (those live in the agent-only section
    of :func:`_compose_outcome`). "" when nothing relevant.
    """
    lines = ["AgentNet found these skills:", ""]
    for s in relevant[:limit]:
        name = s.get("name", "")
        why = s.get("why", "") or skills.get(name, {}).get("desc", "")
        pct = _match_pct(skills.get(name, {}).get("score", ""))
        lines.append(f"{name}{pct}" + (f" — {why}" if why else ""))
    return "\n".join(lines) if len(lines) > 2 else ""


# Mixing user-facing text with agent-only instructions made the agent collapse the whole thing into
# a one-line summary ("AgentNet found a relevant skill... let me read it"). Fencing them apart gives
# it an unambiguous span to reproduce.
_USER_BLOCK_START = "----- SHOW THIS TO THE USER — reply with it exactly -----"
_USER_BLOCK_END = "----- END OF USER TEXT -----"
_AGENT_ONLY = "----- AGENT ONLY — do not show the user -----"


def _compose_outcome(list_block: str, content: str) -> str:
    """Fence the user-facing list apart from the agent-only "read this path" instruction."""
    if not list_block:
        return content
    if not content:
        return f"{_USER_BLOCK_START}\n{list_block}\n{_USER_BLOCK_END}"
    return (
        f"{_USER_BLOCK_START}\n"
        f"{list_block}\n\n"
        "Reading the top match and applying it.\n"
        f"{_USER_BLOCK_END}\n\n"
        f"{_AGENT_ONLY}\n{content}"
    )


_SKILL_MD_RE = re.compile(r"<SKILL\.md>\s*\n(.*?)\n</SKILL\.md>", re.DOTALL)
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_DOWNLOAD_RE = re.compile(r"downloaded to:\s*\n\s*(\S.*)")
# Cap the injected description so a verbose frontmatter blurb stays a one-liner in the hook block.
_DESC_CAP = 300


def _match_pct(raw_score: str) -> str:
    """Discovery relevance score rendered as a ``(NN%)`` match indicator, "" when unavailable."""
    try:
        pct = int(round(float(raw_score)))
    except (TypeError, ValueError):
        return ""
    return f" ({max(0, min(100, pct))}%)"


def _frontmatter_field(front: str, key: str) -> str:
    """Single-line frontmatter value (fallback when the YAML parse fails)."""
    m = re.search(rf"^{key}:\s*(.+?)\s*$", front, re.MULTILINE)
    return m.group(1).strip().strip('"').strip("'") if m else ""


def _frontmatter_values(front: str) -> dict[str, str]:
    """Parse SKILL.md frontmatter with real YAML.

    Block scalars are common in skills (``description: >`` / ``|`` with the text on following
    indented lines). A line-regex captures only the ``>``/``|`` marker, which surfaced in the
    injected list as e.g. ``progress-report — >`` — losing the description entirely.
    """
    try:
        import yaml

        data = yaml.safe_load(front)
    except Exception:  # noqa: BLE001 — malformed frontmatter falls back to the regex
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v.strip() for k, v in data.items() if isinstance(v, str)}


def _materialize_skill(body: str) -> str:
    """Write a single-file skill's SKILL.md body to a temp file; return its path ("" on failure)."""
    try:
        d = tempfile.mkdtemp(prefix="agentnet-skill-")
        p = Path(d) / "SKILL.md"
        p.write_text(body)
        return str(p)
    except Exception:  # noqa: BLE001
        return ""


def _summarize_skill(raw: str, *, slug: str, desc_hint: str) -> str:
    """Condense ``skills use`` output to name + description + an on-disk ``SKILL.md`` path.

    ``skills use`` prints the full SKILL.md; skills *with* reference files also download to a temp
    dir. We inject only a concise header + a pointer to the skill on disk — the agent reads the full
    methodology from disk — instead of dumping the whole SKILL.md into the hook block. When there's
    a download dir we point at it (references included); otherwise we materialize the printed body
    to a temp ``SKILL.md``. Returns "" if the body isn't parseable.
    """
    body = _SKILL_MD_RE.search(raw)
    if not body:
        return ""
    name, desc = slug, desc_hint
    fm = _FRONTMATTER_RE.search(body.group(1))
    if fm:
        values = _frontmatter_values(fm.group(1))
        name = values.get("name") or _frontmatter_field(fm.group(1), "name") or slug
        desc = (
            values.get("description")
            or _frontmatter_field(fm.group(1), "description")
            or desc_hint
        )
    desc = " ".join(desc.split())
    if len(desc) > _DESC_CAP:
        desc = desc[: _DESC_CAP - 1].rstrip() + "…"

    dl = _DOWNLOAD_RE.search(raw)
    if dl:  # skill has references — point at the downloaded dir's SKILL.md
        skill_path = dl.group(1).strip().rstrip("/") + "/SKILL.md"
    else:  # single-file skill — materialize the printed body to a temp SKILL.md
        skill_path = _materialize_skill(body.group(1))
        if not skill_path:
            return ""
    # Never claim a path we haven't verified. Telling the agent a SKILL.md is "on disk" when it
    # isn't makes it hunt for the file, fail, and abandon the skill entirely.
    if not Path(skill_path).is_file():
        return ""
    header = f"{name} — {desc}" if desc else name
    return (
        f"{header}\n\nThe full skill methodology is on disk at:\n  {skill_path}\n"
        f"Read it and follow it as you continue."
    )


def _skill_content(repo: str, slug: str, *, desc_hint: str, timeout: float) -> str:
    """Fetch + condense a skill via ``npx skills use <repo>@<slug>`` (downloads, no repo install).

    Returns a concise "name — description + on-disk path" block on success, "" otherwise (no
    ``npx``, bad slug → exit 1, timeout, or unparseable output).
    """
    npx = shutil.which("npx")
    if not npx:
        return ""
    env = {**os.environ, _SUBAGENT_ENV: "1"}
    try:
        proc = subprocess.run(  # noqa: S603
            [npx, "-y", "skills", "use", f"{repo}@{slug}"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except Exception:  # noqa: BLE001 — best-effort
        return ""
    if proc.returncode != 0:
        return ""
    out = (proc.stdout or "").strip()
    # `skills use` prints a "No matching skill" listing on stdout with exit 0 in some versions.
    if not out or out.startswith("No matching skill"):
        return ""
    return _summarize_skill(out, slug=slug, desc_hint=desc_hint)


def _build_content_outcome(
    relevant: list[dict[str, str]], skills: dict[str, dict[str, str]], *, timeout: float
) -> str:
    """Actionable phase-2 outcome: a concise pointer to the top relevant skill on disk, or "".

    Injects a single skill — the first of the top ``_CONTENT_ATTEMPTS`` relevant candidates whose
    ``skills use`` fetch succeeds.
    """
    for s in relevant[:_CONTENT_ATTEMPTS]:
        info = skills.get(s.get("name", ""))
        if not info or not info.get("repo"):
            continue
        content = _skill_content(
            info["repo"], s["name"], desc_hint=info.get("desc", ""), timeout=timeout
        )
        if content:
            return content
    return ""


def _skills_agent_id() -> str:
    """Registered agent id the platform resolves (env > config > default). Not a secret."""
    from ..infra.config import load_config

    return (
        os.environ.get("AGENTNET_SKILLS_AGENT_ID")
        or (load_config() or {}).get("skills_agent_id")
        or SKILLS_AGENT_ID_DEFAULT
    )


def _negotiate_via_platform(query: str, *, timeout: float) -> str:
    """Brokered A2A: ``use_agent`` the Skills Agent through the platform with the user's identity.

    The platform relays A2A to the agent and settles synchronously, returning ``agent_response``
    in one call. No skills-agent token is ever held client-side. Returns the recommendation, or
    "" on any issue (caller falls back to the local classification).
    """
    creds = _resolve_credentials()
    if creds is None:
        return ""
    token, platform_url = creds

    import httpx

    from ..marketplace.client import PlatformClient

    platform = PlatformClient(
        base_url=platform_url, api_token=token, http_client=httpx.Client(timeout=timeout)
    )
    try:
        resp = platform.use_agent(agent_id=_skills_agent_id(), task=_SKILLS_ASK.format(task=query))
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


def _upgrade_outcome(
    query: str,
    relevant: list[dict[str, str]],
    skills: dict[str, dict[str, str]],
    *,
    timeout: float,
) -> str:
    """The actionable outcome once the gate is open: SKILL.md content, else brokered A2A, else "".

    Content-first (the top match's methodology via ``skills use`` — the agent acts on it directly);
    if that's unavailable (no ``npx`` / all fetches miss), fall back to the platform's brokered A2A
    recommendation over the same open gate. Either replaces the fast phase-1 pointer.
    """
    content = _build_content_outcome(relevant, skills, timeout=min(timeout, _CONTENT_BUDGET))
    if content:
        return content
    broker = _negotiate_via_platform(query, timeout=min(timeout, _PLATFORM_A2A_BUDGET))
    if not broker:
        return ""
    # The Skills Agent replies in free text and may cite conventional install paths (e.g.
    # ~/.agentnet/skills/<repo>/<slug>/SKILL.md) for skills that were never installed here. Label
    # it so the agent treats it as a recommendation and doesn't go hunting for files that
    # don't exist — the observed failure was "path wasn't on disk, so I ignored the skill".
    return (
        "Recommended by the AgentNet Skills Agent (nothing is installed locally — do not look for "
        "these files on disk):\n" + broker
    )


def run_subagent(query: str, *, limit: int, timeout: float, classifier: str = "claude") -> str:
    """Every-prompt skill scout (synchronous form used by tests/manual runs).

    1. Fetch installable skill candidates + classify on ``classifier``'s CLI — the reliable
       relevance **gate**. Empty => not skill-relevant => nothing (zero latency).
    2. Relevant => a fast pointer, upgraded to the top match's ``SKILL.md`` methodology (or the
       brokered A2A recommendation if content is unavailable). Best-effort throughout.
    """
    if not query:
        return ""
    cand_text, skills = _fetch_skill_candidates(
        query, limit=_CANDIDATE_LIMIT, timeout=min(timeout, 10.0)
    )
    if not cand_text:
        return ""
    relevant = _classify(query, cand_text, timeout=min(timeout, 45.0), backend=classifier)
    if not relevant:
        return ""  # gate closed — not skill-relevant
    list_block = _render_list(relevant, skills, limit=limit)
    content = _upgrade_outcome(query, relevant, skills, timeout=timeout)
    return _compose_outcome(list_block, content)


def run_fetch(
    *, session: str, query: str, limit: int, timeout: float, classifier: str = "claude"
) -> None:
    """Detached worker (two-phase, so the outcome reaches the hooks fast).

    Phase 1 caches the recommendation list the moment the gate opens (~12s) — that is what lets the
    steer hook fire mid-answer instead of waiting the full round-trip. Phase 2 then *appends* the
    top match's actual **``SKILL.md`` methodology** (via ``skills use``) if it lands before anything
    was injected. ``classifier`` selects the gate's CLI (``claude`` or ``cursor``). Gate-closed =>
    nothing cached => hooks no-op => zero latency.

    This detached worker is also where the CLI auto-update runs (``maybe_auto_update``): once per
    turn, off the agent's critical path. The synchronous hooks (``--pre``/``--peek``/``--post``)
    deliberately skip it (see cli/main.py) so a tool call is never blocked. It is rate-limited and
    version-gated internally, so it is a cheap no-op unless a new release is actually available.
    """
    if not query:
        return
    try:
        from ..cli.core.updater import maybe_auto_update  # noqa: PLC0415

        maybe_auto_update(quiet=True)
    except Exception:  # noqa: BLE001 — an update check must never disrupt discovery
        pass
    budget = max(timeout, SUBAGENT_TIMEOUT)
    path = _cache_path(session)
    cand_text, skills = _fetch_skill_candidates(
        query, limit=_CANDIDATE_LIMIT, timeout=min(budget, 10.0)
    )
    if not cand_text:
        return
    relevant = _classify(query, cand_text, timeout=min(budget, 45.0), backend=classifier)
    if not relevant:
        return  # gate closed — not skill-relevant
    # Every cached outcome goes through _compose_outcome so the user-block delimiters the steer
    # references are always present — even list-only. Phase 1 caches fast but NOT final (it names
    # skills without any methodology, so a steer on it would hand the agent nothing to apply).
    list_block = _render_list(relevant, skills, limit=limit)
    _cache_write(path, _compose_outcome(list_block, ""), final=False)
    # Phase 2: attach the top match's actionable SKILL.md content and mark the outcome final.
    content = _upgrade_outcome(query, relevant, skills, timeout=budget)
    if _emit_marker(path).exists():
        return  # something already steered — don't rewrite what was shown
    # If no content is reachable (no npx / all fetches missed), promote the fenced list to final
    # rather than leaving the steer blocked forever.
    _cache_write(path, _compose_outcome(list_block, content), final=True)


def run_pre(*, limit: int, timeout: float) -> None:
    """UserPromptSubmit: clear stale cache and spawn the detached worker; return immediately.

    Guarded by a per-prompt spawn claim so duplicate ``--pre`` registrations (settings.json + the
    plugin's ``hooks.json``) spawn exactly one worker — not two Haiku classifier runs per prompt.
    """
    if os.environ.get(_SUBAGENT_ENV):
        return  # inside the subagent — never spawn another
    event = _read_event()
    if event is None:
        return
    session = str(event.get("session_id") or "")
    prompt = _prompt_from_event(event)
    if not prompt:
        return
    if not _claim(_spawn_marker(session, prompt)):
        return  # a duplicate --pre already spawned the worker for this prompt
    # Winner: drop the previous prompt's outcome + its steer claim so this prompt starts fresh.
    cache = _cache_path(session)
    for stale in (cache, _emit_marker(cache)):
        try:
            stale.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    exe = shutil.which("agentnet") or sys.argv[0]
    try:
        subprocess.Popen(  # noqa: S603 — detached discovery, never awaited
            [
                exe, "skill-hook", "--fetch",
                "--session", session, "--query", prompt,
                "--limit", str(limit), "--timeout", str(timeout),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:  # noqa: BLE001 — best-effort: never block the prompt
        pass


def _show_block_instruction() -> str:
    return (
        f"reply with the text between '{_USER_BLOCK_START}' and '{_USER_BLOCK_END}', reproduced "
        "EXACTLY: every skill line, every percentage. Do not summarize it, do not reformat it, do "
        "not mention only the top match, and do not replace it with a sentence of your own"
    )


def _steer_reason(outcome: str) -> str:
    # The agent-only section is absent when no methodology was reachable (list-only outcome, which
    # still gets promoted to final). Pointing at a section that isn't there invites the model to
    # mishandle the whole steer, so the steps adapt to what the outcome actually contains.
    if _AGENT_ONLY in outcome:
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


def _fold_context(outcome: str) -> str:
    tail = (
        ", then follow the AGENT ONLY section"
        if _AGENT_ONLY in outcome
        else ", then apply what those skills suggest"
    )
    return (
        "[AgentNet] Relevant skills found. AgentNet already searched its marketplace — do not run "
        "your own skill search, and do not install anything.\n\n"
        f"Before finishing, {_show_block_instruction()}{tail}.\n\n" + outcome
    )


def run_peek(*, limit: int, timeout: float) -> None:
    """PostToolUse: force the agent to consider the skill mid-run (decision:block), once.

    ``additionalContext`` is a soft reminder the model can ignore (it did, in practice);
    ``decision:block`` + ``reason`` blocks the agentic loop and makes the model address the skill
    *while still running the task* — the closed loop. The atomic emit claim steers exactly once,
    even across duplicate/parallel hook registrations and later tool calls.
    """
    if os.environ.get(_SUBAGENT_ENV):
        return
    event = _read_event()
    if event is None:
        return
    session = str(event.get("session_id") or "")
    path = _cache_path(session)
    data = _cache_read(path)
    if not data or not data.get("outcome"):
        return  # not ready or nothing relevant
    if not data.get("final"):
        return  # phase-1 list only — nothing to apply yet; let a later tool call steer instead
    if not _claim(_emit_marker(path)):
        return  # another peek/post (or a duplicate hook) already steered
    sys.stdout.write(json.dumps({"decision": "block", "reason": _steer_reason(data["outcome"])}))
    sys.stdout.flush()


def run_post(*, limit: int, timeout: float) -> None:
    """Stop: fallback surface for no-tool answers — force the steer at turn end.

    Only fires when nothing already steered (no tool calls / pure-text answer); ``decision:block``
    continues the turn so the model presents the skill. The shared emit claim means it skips if the
    mid-run peek already forced it, and a re-fired Stop (after ``decision:block``) finds the claim
    taken and no-ops — the loop guard.
    """
    if os.environ.get(_SUBAGENT_ENV):
        return
    event = _read_event()
    if event is None:
        return
    session = str(event.get("session_id") or "")
    path = _cache_path(session)

    # Short bounded wait for a near-miss (relevant prompt that finished before the worker). Prefer
    # a final (actionable) outcome, but this is the last chance — take the list if that's all we got.
    deadline = time.monotonic() + min(timeout, 3.0)
    data = _cache_read(path)
    while (not data or not data.get("outcome") or not data.get("final")) and (
        time.monotonic() < deadline
    ):
        time.sleep(0.1)
        data = _cache_read(path)

    outcome = (data or {}).get("outcome") or ""
    if not outcome or not _claim(_emit_marker(path)):
        return  # nothing relevant, or a peek/duplicate/earlier Stop already steered

    sys.stdout.write(
        json.dumps(
            {
                "decision": "block",
                "hookSpecificOutput": {
                    "hookEventName": "Stop",
                    "additionalContext": _fold_context(outcome),
                },
            }
        )
    )
    sys.stdout.flush()

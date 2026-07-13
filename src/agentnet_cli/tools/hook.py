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
# Set in the subagent's env so the inherited hooks no-op there.
_SUBAGENT_ENV = "AGENTNET_SKILL_SUBAGENT"
# How many skill candidates to hand the classifier.
_CANDIDATE_LIMIT = 6
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
    '"why":"<one short line>"}]} listing only candidates that would genuinely help. If none '
    'genuinely fit, or the request is trivial or conversational, respond {"skills":[]}.'
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


def _cache_write(path: Path, outcome: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"outcome": outcome}))
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
        }
        if len(skills) >= limit:
            break
    return "\n".join(lines), skills


def _classify(query: str, cand_text: str, *, timeout: float) -> list[dict[str, str]]:
    """Cheap no-tool ``claude -p`` relevance classifier over real candidates.

    Returns the genuinely-relevant subset as ``[{"name", "why"}]`` (the classifier's own JSON), or
    ``[]`` — the relevance **gate**. Empty => not skill-relevant => the worker surfaces nothing.
    """
    claude = shutil.which("claude")
    if not claude:
        return []
    mcp_cfg = _write_isolating_mcp_config()
    if mcp_cfg is None:
        return []
    env = {**os.environ, _SUBAGENT_ENV: "1"}  # break hook recursion inside the subagent
    msg = f"REQUEST_TEXT:\n{query}\n\nCANDIDATES:\n{cand_text}"
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
    except Exception:  # noqa: BLE001 — best-effort: any failure surfaces nothing
        return []
    finally:
        try:
            mcp_cfg.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    if proc.returncode != 0:
        return []
    text = (proc.stdout or "").strip()
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


def _render_list(
    relevant: list[dict[str, str]], skills: dict[str, dict[str, str]], *, limit: int
) -> str:
    """The AgentNet recommendation list: the relevant skills by name + why (+ skills.sh link).

    This is the visible "here's what AgentNet found" block; the top match's methodology is composed
    underneath it (see ``_compose_outcome``). "" when nothing relevant.
    """
    lines = ["AgentNet found these skills for this task:"]
    for s in relevant[:limit]:
        name = s.get("name", "")
        why = s.get("why", "")
        lines.append(f"- {name}" + (f" — {why}" if why else ""))
        url = skills.get(name, {}).get("url")
        if url:
            lines.append(f"  {url}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _compose_outcome(list_block: str, content: str) -> str:
    """The recommendation list, then the top match's on-disk methodology to read + apply."""
    if not content:
        return list_block
    if not list_block:
        return content
    return f"{list_block}\n\nApplying the top match now:\n{content}"


_SKILL_MD_RE = re.compile(r"<SKILL\.md>\s*\n(.*?)\n</SKILL\.md>", re.DOTALL)
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_DOWNLOAD_RE = re.compile(r"downloaded to:\s*\n\s*(\S.*)")
# Cap the injected description so a verbose frontmatter blurb stays a one-liner in the hook block.
_DESC_CAP = 300


def _frontmatter_field(front: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*(.+?)\s*$", front, re.MULTILINE)
    return m.group(1).strip().strip('"').strip("'") if m else ""


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
        name = _frontmatter_field(fm.group(1), "name") or slug
        desc = _frontmatter_field(fm.group(1), "description") or desc_hint
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
    return _negotiate_via_platform(query, timeout=min(timeout, _PLATFORM_A2A_BUDGET))


def run_subagent(query: str, *, limit: int, timeout: float) -> str:
    """Every-prompt skill scout (synchronous form used by tests/manual runs).

    1. Fetch installable skill candidates + classify — the reliable relevance **gate**. Empty =>
       not skill-relevant => nothing (zero latency).
    2. Relevant => a fast pointer, upgraded to the top match's ``SKILL.md`` methodology (or the
       brokered A2A recommendation if content is unavailable). Best-effort throughout.
    """
    if not query:
        return ""
    if shutil.which("claude") is None:
        return ""
    cand_text, skills = _fetch_skill_candidates(
        query, limit=_CANDIDATE_LIMIT, timeout=min(timeout, 10.0)
    )
    if not cand_text:
        return ""
    relevant = _classify(query, cand_text, timeout=min(timeout, 45.0))
    if not relevant:
        return ""  # gate closed — not skill-relevant
    list_block = _render_list(relevant, skills, limit=limit)
    content = _upgrade_outcome(query, relevant, skills, timeout=timeout)
    return _compose_outcome(list_block, content)


def run_fetch(*, session: str, query: str, limit: int, timeout: float) -> None:
    """Detached worker (two-phase, so the outcome reaches the hooks fast).

    Phase 1 caches a **pointer** (skill name + install command) the moment the gate opens (~12s) —
    that is what lets `PostToolUse` steer mid-answer instead of waiting the full round-trip. Phase 2
    then *upgrades* the cache to the top match's actual **``SKILL.md`` methodology** (via
    ``skills use``) — the actionable payload the agent applies — if it lands before anything was
    injected. Gate-closed => nothing cached => hooks no-op => zero latency.
    """
    if not query or shutil.which("claude") is None:
        return
    budget = max(timeout, SUBAGENT_TIMEOUT)
    path = _cache_path(session)
    cand_text, skills = _fetch_skill_candidates(
        query, limit=_CANDIDATE_LIMIT, timeout=min(budget, 10.0)
    )
    if not cand_text:
        return
    relevant = _classify(query, cand_text, timeout=min(budget, 45.0))
    if not relevant:
        return  # gate closed — not skill-relevant
    # Phase 1: the recommendation list, cached fast so the hooks can steer early.
    list_block = _render_list(relevant, skills, limit=limit)
    _cache_write(path, list_block)
    # Phase 2: append the top match's actionable SKILL.md content, unless a hook already steered.
    content = _upgrade_outcome(query, relevant, skills, timeout=budget)
    if content and not _emit_marker(path).exists():
        _cache_write(path, _compose_outcome(list_block, content))


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


def _steer_reason(outcome: str) -> str:
    return (
        "[AgentNet] Relevant skills for this task are below. Surface this list to the user, then "
        "read and apply the top match's methodology as you continue:\n\n" + outcome
    )


def _fold_context(outcome: str) -> str:
    return (
        "[AgentNet] Relevant skills for this task are below. Name these AgentNet skills to the "
        "user, then apply the top match's methodology to improve your answer:\n\n" + outcome
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

    # Short bounded wait for a near-miss (relevant prompt that finished before the worker).
    deadline = time.monotonic() + min(timeout, 3.0)
    data = _cache_read(path)
    while (not data or not data.get("outcome")) and time.monotonic() < deadline:
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

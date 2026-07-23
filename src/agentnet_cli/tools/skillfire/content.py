"""Fetch and condense a skill's actual methodology via ``npx skills use <repo>@<slug>``.

Owns the one ``subprocess``/``npx`` call site for content fetch — isolated from the classifier's
CLI-gate subprocess and the candidate-discovery HTTP call, so a test patching this module's
``subprocess`` can't silently affect either of the others.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import config

_SKILL_MD_RE = re.compile(r"<SKILL\.md>\s*\n(.*?)\n</SKILL\.md>", re.DOTALL)
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_DOWNLOAD_RE = re.compile(r"downloaded to:\s*\n\s*(\S.*)")
# Cap the injected description so a verbose frontmatter blurb stays a one-liner in the hook block.
_DESC_CAP = 300


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


def summarize_skill(raw: str, *, slug: str, desc_hint: str) -> str:
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


def skill_content(repo: str, slug: str, *, desc_hint: str, timeout: float) -> str:
    """Fetch + condense a skill via ``npx skills use <repo>@<slug>`` (downloads, no repo install).

    Returns a concise "name — description + on-disk path" block on success, "" otherwise (no
    ``npx``, bad slug → exit 1, timeout, or unparseable output).
    """
    npx = shutil.which("npx")
    if not npx:
        return ""
    env = {**os.environ, config.SUBAGENT_ENV: "1"}
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
    return summarize_skill(out, slug=slug, desc_hint=desc_hint)


def build_content_outcome(
    relevant: list[dict[str, str]], skills: dict[str, dict[str, str]], *, timeout: float
) -> str:
    """Actionable phase-2 outcome: a concise pointer to the top relevant skill on disk, or "".

    Injects a single skill — the first of the top ``CONTENT_ATTEMPTS`` relevant candidates whose
    ``skills use`` fetch succeeds.
    """
    for s in relevant[: config.CONTENT_ATTEMPTS]:
        info = skills.get(s.get("name", ""))
        if not info or not info.get("repo"):
            continue
        content = skill_content(
            info["repo"], s["name"], desc_hint=info.get("desc", ""), timeout=timeout
        )
        if content:
            return content
    return ""

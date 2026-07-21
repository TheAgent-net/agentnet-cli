import io
import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from agentnet_cli.cli.main import app
from agentnet_cli.infra.package_paths import bundled_claude_marketplace
from agentnet_cli.tools import hook

runner = CliRunner()

_CREDS = "agentnet_cli.tools.hook._resolve_credentials"
_NEGOTIATE = "agentnet_cli.tools.hook._negotiate_via_platform"
_USE_AGENT = "agentnet_cli.marketplace.client.PlatformClient.use_agent"
_ENV = hook._SUBAGENT_ENV


def _cache(outcome, final=True):
    """Cached outcome. ``final=False`` = phase-1 list only (not yet actionable)."""
    return json.dumps({"outcome": outcome, "final": final})


# ── _render_list (the AgentNet recommendation list: name + why + link) ────────
def test_render_list():
    # `name (NN%) — description` only. No install commands (agents executed them) and no URLs —
    # this block is meant to be reproduced to the user verbatim.
    skills = {"A": {"url": "http://a", "repo": "r/a", "install_cmd": "npx add", "score": "88.6"}}
    out = hook._render_list([{"name": "A", "why": "helps"}], skills, limit=5)
    assert out == "AgentNet found these skills:\n\nA (89%) — helps"
    assert "install" not in out and "http://a" not in out
    # no score -> no percentage
    assert hook._render_list([{"name": "A", "why": "w"}], {}, limit=5).endswith("A — w")
    assert hook._render_list([], {}, limit=5) == ""  # nothing relevant -> ""


def test_render_list_respects_limit():
    rel = [{"name": f"S{i}", "why": "w"} for i in range(5)]
    out = hook._render_list(rel, {}, limit=2)
    assert len([ln for ln in out.splitlines() if ln.startswith("S")]) == 2


def test_steer_reason_omits_agent_section_when_absent():
    # A list-only outcome (no methodology reachable) still gets promoted to final. The steer must
    # not tell the model to follow an AGENT ONLY section that isn't in the payload.
    list_only = hook._compose_outcome("AgentNet found these skills:\n\nA — x", "")
    steer = hook._steer_reason(list_only)
    assert hook._AGENT_ONLY not in steer
    assert "AGENT ONLY section" not in steer
    assert hook._USER_BLOCK_START in steer  # still told to show the list

    fold = hook._fold_context(list_only)
    assert "AGENT ONLY section" not in fold

    # ...but it is referenced when the section really is there.
    full = hook._compose_outcome("AgentNet found these skills:\n\nA — x", "read /tmp/SKILL.md")
    assert "AGENT ONLY section" in hook._steer_reason(full)
    assert "AGENT ONLY section" in hook._fold_context(full)


def test_compose_outcome():
    # The user-facing list is fenced apart from the agent-only path instruction, otherwise the
    # agent collapses the whole thing into "AgentNet found a relevant skill, let me read it".
    out = hook._compose_outcome("LIST", "CONTENT")
    assert hook._USER_BLOCK_START in out and hook._USER_BLOCK_END in out
    assert hook._AGENT_ONLY in out
    assert "Reading the top match and applying it." in out
    assert out.index("LIST") < out.index(hook._USER_BLOCK_END) < out.index("CONTENT")

    # list only -> fenced user block, no agent section to leak
    only = hook._compose_outcome("LIST", "")
    assert "LIST" in only and hook._AGENT_ONLY not in only
    assert hook._compose_outcome("", "CONTENT") == "CONTENT"


# ── _fetch_skill_candidates (installable skills.sh discovery -> repo@slug) ────
_RAW_SKILLS = {
    "results": [
        {"name": "flag-create", "source": "skills.sh", "repo": "ld/agent-skills",
         "url": "https://skills.sh/1", "install_cmd": "npx skills add ld/agent-skills@flag-create",
         "description": "create flags", "score": 66},
        {"name": "elsewhere", "source": "clawhub", "repo": "x/y", "description": "not skills.sh"},
        {"source": "skills.sh", "repo": "z", "description": "no name — skipped"},
    ]
}
_DISCOVER_SKILLS = "agentnet_cli.marketplace.skills.discovery.SkillDiscovery.discover"


def test_fetch_skill_candidates():
    with patch(_CREDS, return_value=("t", "p")), patch(_DISCOVER_SKILLS, return_value=_RAW_SKILLS):
        text, skills = hook._fetch_skill_candidates("flags", limit=6, timeout=8)
    assert "flag-create" in text
    assert "elsewhere" not in text and "no name" not in text  # non-skills.sh + no-name dropped
    assert skills["flag-create"]["repo"] == "ld/agent-skills"
    assert skills["flag-create"]["install_cmd"] == "npx skills add ld/agent-skills@flag-create"


def test_fetch_skill_candidates_best_effort():
    with patch(_CREDS, return_value=None):
        assert hook._fetch_skill_candidates("x", limit=6, timeout=8) == ("", {})
    with patch(_CREDS, return_value=("t", "p")), patch(_DISCOVER_SKILLS, side_effect=RuntimeError()):
        assert hook._fetch_skill_candidates("x", limit=6, timeout=8) == ("", {})


# ── run_subagent (gate -> SKILL.md content, else brokered A2A, else pointer) ──
_SKILL_INFO = {"repo": "r/foo", "install_cmd": "npx skills add r/foo@Foo",
               "url": "http://foo", "desc": "does foo"}


def _run_subagent(query="review my code",
                  stdout='{"skills":[{"name":"Foo","why":"helps"}]}',
                  rc=0, has_classifier=True, content="", agent="",
                  candidates=("- Foo (score 0.8): does foo", {"Foo": _SKILL_INFO})):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["env"] = kw.get("env", {})
        return MagicMock(returncode=rc, stdout=stdout)

    def fake_which(name):
        if name in ("claude", "cursor-agent") and not has_classifier:
            return None  # no gate CLI at all
        return "/usr/bin/" + name

    content_mock = MagicMock(return_value=content)
    negotiate = MagicMock(return_value=agent)
    with (
        patch("agentnet_cli.tools.hook._fetch_skill_candidates", return_value=candidates),
        patch("agentnet_cli.tools.hook.shutil.which", side_effect=fake_which),
        patch("agentnet_cli.tools.hook.subprocess.run", fake_run),
        patch("agentnet_cli.tools.hook._build_content_outcome", content_mock),
        patch(_NEGOTIATE, negotiate),
    ):
        text = hook.run_subagent(query, limit=5, timeout=30)
    captured["negotiate"] = negotiate
    captured["content"] = content_mock
    return text, captured


def test_run_subagent_lists_then_applies_content():
    # Gate open + content fetched -> the recommendation LIST, then the top match's methodology.
    text, cap = _run_subagent(content="APPLY THIS SKILL METHODOLOGY", agent="broker")
    assert "AgentNet found these skills" in text and "Foo" in text  # the list
    assert "APPLY THIS SKILL METHODOLOGY" in text and hook._AGENT_ONLY in text  # the content
    cmd = cap["cmd"]
    assert cmd[0].endswith("claude")
    for tok in ("-p", "--model", hook.SUBAGENT_MODEL, "--mcp-config",
                "--strict-mcp-config", "--append-system-prompt"):
        assert tok in cmd
    assert "review my code" in cmd[-1]  # prompt is REQUEST_TEXT data, not a task
    assert cap["env"].get(_ENV) == "1"  # recursion guard set in child env
    cap["content"].assert_called_once()
    cap["negotiate"].assert_not_called()  # content-first short-circuits the broker


def test_run_subagent_falls_back_to_broker():
    # Content unavailable (npx miss) -> list + brokered A2A recommendation, explicitly labelled as
    # not-on-disk so the agent doesn't hunt for files the Skills Agent merely cited.
    text, cap = _run_subagent(content="", agent="Use skills/skillssh/foo — it does X.")
    assert "Foo" in text  # the list
    assert "Use skills/skillssh/foo — it does X." in text
    assert "do not look for these files on disk" in text
    cap["negotiate"].assert_called_once()


def test_run_subagent_falls_back_to_list():
    # Neither content nor broker -> the list alone still surfaces the skills (name + description).
    text, cap = _run_subagent(content="", agent="")
    assert "AgentNet found these skills" in text and "Foo" in text
    assert "install" not in text  # never hand the agent a command it will run
    assert hook._AGENT_ONLY not in text  # no content to apply
    cap["negotiate"].assert_called_once()


def test_run_subagent_gate_blocks_downstream():
    # Classifier says nothing relevant -> neither content nor platform is consulted.
    text, cap = _run_subagent(stdout='{"skills":[]}', content="x", agent="y")
    assert text == ""
    cap["content"].assert_not_called()
    cap["negotiate"].assert_not_called()


def test_run_subagent_best_effort():
    assert _run_subagent(stdout='{"skills":[]}')[0] == ""   # classifier: nothing relevant
    assert _run_subagent(stdout="not json")[0] == ""        # unparseable
    assert _run_subagent(rc=1)[0] == ""                     # subagent failed
    assert _run_subagent(has_classifier=False)[0] == ""     # no gate CLI (claude or cursor-agent)
    assert _run_subagent(candidates=("", {}))[0] == ""      # no skill candidates
    assert hook.run_subagent("", limit=5, timeout=30) == ""  # empty prompt


def test_run_subagent_timeout_is_best_effort():
    import subprocess

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    with (
        patch("agentnet_cli.tools.hook._fetch_skill_candidates", return_value=("- Foo: x", {})),
        patch("agentnet_cli.tools.hook.shutil.which", side_effect=lambda n: "/usr/bin/" + n),
        patch("agentnet_cli.tools.hook.subprocess.run", boom),
    ):
        assert hook.run_subagent("x", limit=5, timeout=1) == ""


# ── classifier backends (claude -p / cursor-agent -p, with fallback) ─────────
def _which_all(name):
    return "/usr/bin/" + name


def test_cursor_classifier_argv(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["env"] = kw.get("env", {})
        return MagicMock(returncode=0, stdout='{"skills":[]}')

    monkeypatch.setattr("agentnet_cli.tools.hook.shutil.which", _which_all)
    monkeypatch.setattr("agentnet_cli.tools.hook.subprocess.run", fake_run)
    monkeypatch.delenv(hook._CURSOR_MODEL_ENV, raising=False)
    hook._run_cursor_classifier("REQUEST_TEXT:\nx\n\nCANDIDATES:\n- foo", timeout=10)
    cmd = captured["cmd"]
    assert cmd[0].endswith("cursor-agent")
    for tok in ("-p", "--mode", "ask", "--output-format", "text", "--trust"):
        assert tok in cmd
    assert "--model" not in cmd  # default Cursor model unless overridden
    assert hook._CLASSIFIER_PROMPT in cmd[-1] and "REQUEST_TEXT" in cmd[-1]  # prompt + candidates
    assert captured["env"].get(hook._SUBAGENT_ENV) == "1"  # recursion guard


def test_cursor_classifier_model_override(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return MagicMock(returncode=0, stdout="{}")

    monkeypatch.setattr("agentnet_cli.tools.hook.shutil.which", _which_all)
    monkeypatch.setattr("agentnet_cli.tools.hook.subprocess.run", fake_run)
    monkeypatch.setenv(hook._CURSOR_MODEL_ENV, "gpt-5-mini")
    hook._run_cursor_classifier("m", timeout=5)
    assert "--model" in captured["cmd"] and "gpt-5-mini" in captured["cmd"]


def test_cursor_classifier_absent(monkeypatch):
    monkeypatch.setattr("agentnet_cli.tools.hook.shutil.which", lambda n: None)
    assert hook._run_cursor_classifier("m", timeout=5) is None


def test_classify_uses_requested_backend(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd[0])
        return MagicMock(returncode=0, stdout='{"skills":[{"name":"A","why":"w"}]}')

    monkeypatch.setattr("agentnet_cli.tools.hook.shutil.which", _which_all)
    monkeypatch.setattr("agentnet_cli.tools.hook.subprocess.run", fake_run)
    assert hook._classify("q", "- A: x", timeout=10, backend="cursor") == [{"name": "A", "why": "w"}]
    assert any("cursor-agent" in c for c in calls)  # ran cursor-agent
    assert not any(c.endswith("claude") for c in calls)  # not claude — cursor succeeded


def test_classify_falls_back_to_other_backend(monkeypatch):
    calls = []

    def fake_which(n):
        return None if n == "cursor-agent" else "/usr/bin/" + n

    def fake_run(cmd, **kw):
        calls.append(cmd[0])
        return MagicMock(returncode=0, stdout='{"skills":[]}')

    monkeypatch.setattr("agentnet_cli.tools.hook.shutil.which", fake_which)
    monkeypatch.setattr("agentnet_cli.tools.hook.subprocess.run", fake_run)
    hook._classify("q", "- A: x", timeout=10, backend="cursor")  # requested cursor is absent
    assert any(c.endswith("claude") for c in calls)  # fell back to claude


def test_classify_no_backend(monkeypatch):
    monkeypatch.setattr("agentnet_cli.tools.hook.shutil.which", lambda n: None)
    assert hook._classify("q", "- A: x", timeout=10, backend="cursor") == []


# ── _negotiate_via_platform (brokered A2A via use_agent) ─────────────────────
def test_negotiate_via_platform_happy():
    with (
        patch(_CREDS, return_value=("t", "https://p")),
        patch(_USE_AGENT, return_value={"status": "settled", "agent_response": "Use skills/foo"}),
    ):
        assert hook._negotiate_via_platform("q", timeout=5.0) == "Use skills/foo"


def test_negotiate_via_platform_best_effort():
    with patch(_CREDS, return_value=None):
        assert hook._negotiate_via_platform("q", timeout=5.0) == ""  # no identity
    with (
        patch(_CREDS, return_value=("t", "https://p")),
        patch(_USE_AGENT, side_effect=RuntimeError("boom")),
    ):
        assert hook._negotiate_via_platform("q", timeout=5.0) == ""  # platform error
    with (
        patch(_CREDS, return_value=("t", "https://p")),
        patch(_USE_AGENT, return_value={"status": "settled"}),
    ):
        assert hook._negotiate_via_platform("q", timeout=5.0) == ""  # no agent_response
    with (
        patch(_CREDS, return_value=("t", "https://p")),
        patch(_USE_AGENT, return_value={"status": "refunded",
                                        "agent_response": "agent turn exceeded 25s budget"}),
    ):
        assert hook._negotiate_via_platform("q", timeout=5.0) == ""  # failed turn not injected


def test_skills_agent_id_default_and_override(monkeypatch):
    monkeypatch.delenv("AGENTNET_SKILLS_AGENT_ID", raising=False)
    with patch("agentnet_cli.infra.config.load_config", return_value=None):
        assert hook._skills_agent_id() == hook.SKILLS_AGENT_ID_DEFAULT == "agentnet-skills-agent"
    monkeypatch.setenv("AGENTNET_SKILLS_AGENT_ID", "other-agent")
    assert hook._skills_agent_id() == "other-agent"


# ── _summarize_skill (condense `skills use` output to header + on-disk path) ──
def _use_output(download_dir, *, name="launchdarkly-flag-create", desc=None):
    """`skills use` stdout pointing at ``download_dir``.

    The dir must really exist — `_summarize_skill` verifies the SKILL.md is on disk before
    claiming it (see test_summarize_skill_rejects_nonexistent_path).
    """
    desc = desc if desc is not None else '"Create and configure LaunchDarkly feature flags."'
    return (
        "You are being given a Skill to execute for the user's next request.\n\n"
        "Use the following SKILL.md as your instructions:\n\n"
        "<SKILL.md>\n"
        "---\n"
        f"name: {name}\n"
        f"description: {desc}\n"
        "license: Apache-2.0\n"
        "---\n\n"
        "# LaunchDarkly Flag Create\n\nlong methodology body...\n"
        "</SKILL.md>\n\n"
        "Supporting files for this skill were downloaded to:\n"
        f"{download_dir}\n\n"
        "When the SKILL.md references relative paths, read them from that directory.\n"
    )


def _real_skill_dir(tmp_path, name="launchdarkly-flag-create"):
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("# on disk\n")
    return d


def test_summarize_skill_with_references(tmp_path):
    # Skill downloaded a dir (has references) -> point at that dir's SKILL.md, don't dump the body.
    d = _real_skill_dir(tmp_path)
    out = hook._summarize_skill(
        _use_output(d), slug="launchdarkly-flag-create", desc_hint="x"
    )
    assert out.startswith("launchdarkly-flag-create — Create and configure LaunchDarkly")
    assert f"{d}/SKILL.md" in out
    assert "Read it and follow it" in out
    assert "long methodology body" not in out  # the full SKILL.md is NOT dumped in


def test_summarize_skill_single_file():
    # No download path -> materialize the printed body to a temp SKILL.md we point at.
    raw = "<SKILL.md>\n---\nname: solo\ndescription: does solo\n---\n# body\nstuff\n</SKILL.md>\n"
    out = hook._summarize_skill(raw, slug="solo", desc_hint="")
    assert out.startswith("solo — does solo")
    m = re.search(r"(\S+/SKILL\.md)", out)
    assert m and Path(m.group(1)).read_text().strip().endswith("stuff")  # body on disk
    assert "# body" not in out.split("on disk")[0]  # body not inlined into the header


def test_summarize_skill_reads_yaml_block_scalar_description(tmp_path):
    # Regression: `description: >` (and `|`) put the text on following indented lines. A line-regex
    # captured only the marker, so the injected list read "progress-report — >".
    d = _real_skill_dir(tmp_path, name="progress-report")
    raw = (
        "<SKILL.md>\n"
        "---\n"
        "name: progress-report\n"
        "description: >\n"
        "  Displays progress dashboard showing phase completion, blocked tasks,\n"
        "  and remaining work estimate.\n"
        "version: 0.0.1\n"
        "---\n"
        "body\n"
        "</SKILL.md>\n"
        f"Supporting files for this skill were downloaded to:\n{d}\n"
    )
    header = hook._summarize_skill(raw, slug="progress-report", desc_hint="").splitlines()[0]
    assert header.startswith("progress-report — Displays progress dashboard")
    assert ">" not in header


def test_summarize_skill_unparseable():
    assert hook._summarize_skill("no <skill> block here", slug="x", desc_hint="") == ""


def test_summarize_skill_rejects_nonexistent_path():
    # Regression: we claimed a SKILL.md was "on disk" without checking. The agent hunted for the
    # file, failed, and abandoned the skill ("path wasn't on disk, so I built it manually").
    raw = (
        "<SKILL.md>\n---\nname: ghost\ndescription: d\n---\nbody\n</SKILL.md>\n"
        "Supporting files for this skill were downloaded to:\n/nonexistent/ghost-skill-dir\n"
    )
    assert hook._summarize_skill(raw, slug="ghost", desc_hint="") == ""


def test_broker_fallback_is_labelled_as_not_on_disk(monkeypatch):
    # The Skills Agent cites conventional install paths for skills that were never installed here.
    monkeypatch.setattr("agentnet_cli.tools.hook._build_content_outcome", lambda *a, **k: "")
    monkeypatch.setattr(
        "agentnet_cli.tools.hook._negotiate_via_platform",
        lambda *a, **k: "Use ~/.agentnet/skills/foo/bar/SKILL.md",
    )
    out = hook._upgrade_outcome("q", [{"name": "A", "why": "w"}], {}, timeout=5)
    assert "do not look for these files on disk" in out
    assert "Skills Agent" in out


def test_summarize_skill_caps_description(tmp_path):
    d = _real_skill_dir(tmp_path, name="s")
    raw = _use_output(d, name="s", desc="d" * 500)
    header = hook._summarize_skill(raw, slug="s", desc_hint="").splitlines()[0]
    assert header.endswith("…") and len(header) <= hook._DESC_CAP + len("s — ")


# ── _skill_content (npx skills use <repo>@<slug> -> concise header, no install) ─
def test_skill_content(tmp_path):
    d = _real_skill_dir(tmp_path)
    with (
        patch("agentnet_cli.tools.hook.shutil.which", side_effect=lambda n: "/usr/bin/" + n),
        patch("agentnet_cli.tools.hook.subprocess.run",
              return_value=MagicMock(returncode=0, stdout=_use_output(d))) as run,
    ):
        out = hook._skill_content("ld/agent", "launchdarkly-flag-create", desc_hint="x", timeout=5)
    assert "launchdarkly-flag-create — Create and configure" in out
    assert str(d) in out
    cmd = run.call_args.args[0]
    assert cmd[1:] == ["-y", "skills", "use", "ld/agent@launchdarkly-flag-create"]


def _with_npx(run_result):
    return (
        patch("agentnet_cli.tools.hook.shutil.which", side_effect=lambda n: "/usr/bin/" + n),
        patch("agentnet_cli.tools.hook.subprocess.run", return_value=run_result),
    )


def test_skill_content_best_effort():
    with patch("agentnet_cli.tools.hook.shutil.which", return_value=None):
        assert hook._skill_content("r/foo", "Foo", desc_hint="", timeout=5) == ""  # no npx
    a, b = _with_npx(MagicMock(returncode=1, stdout=""))
    with a, b:
        assert hook._skill_content("r/foo", "Foo", desc_hint="", timeout=5) == ""  # exit 1
    a, b = _with_npx(MagicMock(returncode=0, stdout="No matching skill found for: x"))
    with a, b:
        assert hook._skill_content("r/foo", "Foo", desc_hint="", timeout=5) == ""  # listing


# ── fetch / pre / peek / post cache flow (JSON cache: {outcome, injected}) ───
_CAND = ("- Foo: x", {"Foo": {"repo": "r/foo", "install_cmd": "npx skills add r/foo@Foo",
                              "url": "http://foo", "desc": "x"}})


def _patch_fetch(cache, *, cand=_CAND, relevant=None, upgrade="CONTENT skill"):
    if relevant is None:
        relevant = [{"name": "Foo", "why": "helps"}]
    return (
        patch("agentnet_cli.tools.hook._cache_path", return_value=cache),
        patch("agentnet_cli.tools.hook.shutil.which", side_effect=lambda n: "/usr/bin/" + n),
        patch("agentnet_cli.tools.hook._fetch_skill_candidates", return_value=cand),
        patch("agentnet_cli.tools.hook._classify", return_value=relevant),
        patch("agentnet_cli.tools.hook._upgrade_outcome", return_value=upgrade),
    )


def test_fetch_composes_list_and_content(tmp_path):
    # Phase 1 writes the recommendation list; phase 2 appends the top match's methodology.
    cache = tmp_path / "s.json"
    p = _patch_fetch(cache, upgrade="CONTENT skill")
    with p[0], p[1], p[2], p[3], p[4]:
        hook.run_fetch(session="s1", query="review sql", limit=5, timeout=3.0)
    outcome = json.loads(cache.read_text())["outcome"]
    assert "AgentNet found these skills" in outcome and "Foo" in outcome  # the list
    assert "CONTENT skill" in outcome and hook._AGENT_ONLY in outcome  # the content


def test_fetch_phase1_is_not_final_phase2_is(tmp_path):
    # Phase 1 must be non-final (list only); phase 2 marks it final once content is attached.
    cache = tmp_path / "s.json"
    seen = []
    real_write = hook._cache_write

    def spy(path, outcome, *, final=True):
        seen.append(final)
        real_write(path, outcome, final=final)

    p = _patch_fetch(cache, upgrade="CONTENT skill")
    with p[0], p[1], p[2], p[3], p[4], patch("agentnet_cli.tools.hook._cache_write", spy):
        hook.run_fetch(session="s1", query="review sql", limit=5, timeout=3.0)
    assert seen == [False, True]  # phase 1 non-final, phase 2 final
    assert json.loads(cache.read_text())["final"] is True


def test_fetch_promotes_list_to_final_when_no_content(tmp_path):
    # No content reachable -> promote the list to final so the steer isn't blocked forever.
    cache = tmp_path / "s.json"
    p = _patch_fetch(cache, upgrade="")
    with p[0], p[1], p[2], p[3], p[4]:
        hook.run_fetch(session="s1", query="review sql", limit=5, timeout=3.0)
    data = json.loads(cache.read_text())
    assert data["final"] is True and "Foo" in data["outcome"]
    # Regression: the list-only final outcome MUST carry the user-block delimiters the steer tells
    # the agent to reproduce — earlier it cached the raw list, so those markers were absent.
    assert hook._USER_BLOCK_START in data["outcome"] and hook._USER_BLOCK_END in data["outcome"]
    steer = hook._steer_reason(data["outcome"])
    assert hook._USER_BLOCK_START in steer  # delimiter referenced == delimiter present


def test_fetch_phase1_outcome_is_fenced(tmp_path):
    # Even the non-final phase-1 cache is fenced, so a steer never references absent delimiters.
    cache = tmp_path / "s.json"
    writes = []
    real = hook._cache_write

    def spy(path, outcome, *, final=True):
        writes.append((outcome, final))
        real(path, outcome, final=final)

    p = _patch_fetch(cache, upgrade="CONTENT skill")
    with p[0], p[1], p[2], p[3], p[4], patch("agentnet_cli.tools.hook._cache_write", spy):
        hook.run_fetch(session="s1", query="review sql", limit=5, timeout=3.0)
    phase1_outcome, phase1_final = writes[0]
    assert phase1_final is False and hook._USER_BLOCK_START in phase1_outcome


def test_fetch_skips_upgrade_after_steer(tmp_path):
    # If a hook already steered (emit marker present), phase 2 does not overwrite what was shown.
    cache = tmp_path / "s.json"
    hook._emit_marker(cache).parent.mkdir(parents=True, exist_ok=True)
    hook._emit_marker(cache).touch()
    p = _patch_fetch(cache, upgrade="CONTENT skill")
    with p[0], p[1], p[2], p[3], p[4]:
        hook.run_fetch(session="s1", query="review sql", limit=5, timeout=3.0)
    outcome = json.loads(cache.read_text())["outcome"]
    assert "Foo" in outcome and "CONTENT skill" not in outcome  # stayed the list


def test_fetch_keeps_list_when_upgrade_empty(tmp_path):
    # No content + no broker -> the fast recommendation list stays cached.
    cache = tmp_path / "s.json"
    p = _patch_fetch(cache, upgrade="")
    with p[0], p[1], p[2], p[3], p[4]:
        hook.run_fetch(session="s1", query="review sql", limit=5, timeout=3.0)
    outcome = json.loads(cache.read_text())["outcome"]
    assert "AgentNet found these skills" in outcome and "Foo" in outcome
    assert hook._AGENT_ONLY not in outcome


def test_fetch_runs_auto_update_off_critical_path(monkeypatch):
    # The detached worker is where the CLI auto-update runs — once per turn, off the agent's
    # critical path (the synchronous hooks skip it; see cli/main.py). Fires even before discovery.
    mau = MagicMock()
    monkeypatch.setattr("agentnet_cli.cli.core.updater.maybe_auto_update", mau)
    monkeypatch.setattr("agentnet_cli.tools.hook._fetch_skill_candidates", lambda *a, **k: ("", {}))
    hook.run_fetch(session="s1", query="do a thing", limit=6, timeout=3.0)
    mau.assert_called_once()


def test_fetch_writes_nothing_when_gate_closed(tmp_path):
    cache = tmp_path / "s.json"
    p = _patch_fetch(cache, relevant=[])  # classifier: nothing relevant
    with p[0], p[1], p[2], p[3], p[4]:
        hook.run_fetch(session="s1", query="what is 2+2", limit=5, timeout=3.0)
    assert not cache.exists()  # gate closed -> no cache -> hooks no-op -> zero latency


def test_fetch_writes_nothing_when_no_candidates(tmp_path):
    cache = tmp_path / "s.json"
    p = _patch_fetch(cache, cand=("", {}))
    with p[0], p[1], p[2], p[3], p[4]:
        hook.run_fetch(session="s1", query="x", limit=5, timeout=3.0)
    assert not cache.exists()


def _stdin(monkeypatch, obj):
    monkeypatch.setattr("agentnet_cli.tools.hook.sys.stdin", io.StringIO(json.dumps(obj)))


def test_peek_forces_block_and_claims_once(tmp_path, monkeypatch, capsys):
    # PostToolUse uses decision:block (forced mid-run steer), not soft additionalContext.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("USE skill Foo"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    hook.run_peek(limit=5, timeout=3.0)
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "block"
    assert "USE skill Foo" in out["reason"]
    assert hook._emit_marker(cache).exists()  # atomic steer claim taken


def test_peek_noop_when_already_steered(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("x"))
    hook._emit_marker(cache).touch()  # a prior peek/post already claimed the steer
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    hook.run_peek(limit=5, timeout=3.0)
    assert capsys.readouterr().out == ""


def test_peek_steers_once_across_duplicate_hooks(tmp_path, monkeypatch, capsys):
    # settings.json + plugin => two parallel PostToolUse hooks; only one may emit.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("USE skill Foo"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: cache)
    outs = []
    for _ in range(2):  # two duplicate invocations for the same tool call
        _stdin(monkeypatch, {"session_id": "s"})
        hook.run_peek(limit=5, timeout=3.0)
        outs.append(capsys.readouterr().out)
    assert sum(bool(o) for o in outs) == 1  # exactly one steered


def test_peek_skips_non_final_outcome(tmp_path, monkeypatch, capsys):
    # Regression: the phase-1 list has no methodology. Steering on it hands the agent nothing to
    # apply, so the peek must wait for the content upgrade instead of burning the one steer.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("AgentNet found these skills:\n- Foo", final=False))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    hook.run_peek(limit=5, timeout=3.0)
    assert capsys.readouterr().out == ""            # no steer
    assert not hook._emit_marker(cache).exists()    # and the claim is still available


def test_post_accepts_non_final_as_last_chance(tmp_path, monkeypatch, capsys):
    # Stop is the final surface for the turn — take the list rather than surfacing nothing.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("LIST ONLY", final=False))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    hook.run_post(limit=5, timeout=0.2)
    out = json.loads(capsys.readouterr().out)
    assert "LIST ONLY" in out["hookSpecificOutput"]["additionalContext"]


def test_peek_noop_when_not_ready(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: tmp_path / "nope.json")
    _stdin(monkeypatch, {"session_id": "s"})
    hook.run_peek(limit=5, timeout=3.0)
    assert capsys.readouterr().out == ""


def test_post_folds_in_and_claims_once(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("USE skill Foo"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    hook.run_post(limit=5, timeout=0.3)
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "block"
    assert out["hookSpecificOutput"]["hookEventName"] == "Stop"
    assert "USE skill Foo" in out["hookSpecificOutput"]["additionalContext"]
    assert hook._emit_marker(cache).exists()  # claim taken => a re-fired Stop no-ops


def test_post_skips_when_peek_already_steered(tmp_path, monkeypatch, capsys):
    # Stop defers to the forced mid-run peek (avoids a double steer) via the shared emit claim.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("USE skill Foo"))
    hook._emit_marker(cache).touch()  # peek already claimed the steer
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    hook.run_post(limit=5, timeout=0.3)
    assert capsys.readouterr().out == ""  # peek already forced the steer


def test_post_silent_when_cache_absent(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: tmp_path / "nope.json")
    _stdin(monkeypatch, {"session_id": "s"})
    hook.run_post(limit=5, timeout=0.15)  # bounded — never blocks
    assert capsys.readouterr().out == ""


def test_pre_spawns_detached_worker_with_prompt(tmp_path, monkeypatch):
    monkeypatch.delenv(_ENV, raising=False)
    _stdin(monkeypatch, {"session_id": "s9", "prompt": "help me query a vector db"})
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: tmp_path / "s.json")
    monkeypatch.setattr("agentnet_cli.tools.hook.shutil.which", lambda n: "/usr/bin/agentnet")
    captured = {}
    monkeypatch.setattr(
        "agentnet_cli.tools.hook.subprocess.Popen",
        lambda args, **kw: captured.setdefault("args", args) or MagicMock(),
    )
    hook.run_pre(limit=5, timeout=3.0)
    args = captured["args"]
    assert "skill-hook" in args and "--fetch" in args
    assert "help me query a vector db" in args and "s9" in args


def test_pre_spawns_one_worker_across_duplicate_hooks(tmp_path, monkeypatch):
    # settings.json + plugin => two parallel UserPromptSubmit hooks; only one worker may spawn.
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: tmp_path / "s.json")
    monkeypatch.setattr("agentnet_cli.tools.hook.shutil.which", lambda n: "/usr/bin/agentnet")
    spawns = []
    monkeypatch.setattr(
        "agentnet_cli.tools.hook.subprocess.Popen",
        lambda args, **kw: spawns.append(args) or MagicMock(),
    )
    for _ in range(2):  # two duplicate invocations for the same prompt
        _stdin(monkeypatch, {"session_id": "s9", "prompt": "same prompt"})
        hook.run_pre(limit=5, timeout=3.0)
    assert len(spawns) == 1  # spawn-once claim held


def test_pre_silent_on_empty_prompt(monkeypatch):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr(
        "agentnet_cli.tools.hook.sys.stdin", io.StringIO('{"session_id":"s","prompt":"   "}')
    )
    called = MagicMock()
    monkeypatch.setattr("agentnet_cli.tools.hook.subprocess.Popen", called)
    hook.run_pre(limit=5, timeout=3.0)
    called.assert_not_called()


# ── recursion guard (claude -p inherits these hooks) ──────────────────────
def test_pre_no_spawn_inside_subagent(monkeypatch):
    monkeypatch.setenv(_ENV, "1")
    _stdin(monkeypatch, {"session_id": "s", "prompt": "x"})
    called = MagicMock()
    monkeypatch.setattr("agentnet_cli.tools.hook.subprocess.Popen", called)
    hook.run_pre(limit=5, timeout=3.0)
    called.assert_not_called()  # no fork bomb


def test_peek_silent_inside_subagent(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(_ENV, "1")
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo"))
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    hook.run_peek(limit=5, timeout=3.0)
    assert capsys.readouterr().out == ""


def test_post_silent_inside_subagent(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(_ENV, "1")
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo"))
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: cache)
    _stdin(monkeypatch, {"session_id": "s"})
    hook.run_post(limit=5, timeout=0.3)
    assert capsys.readouterr().out == ""


# ── credentials ───────────────────────────────────────────────────────────
def test_resolve_credentials_from_env(monkeypatch):
    monkeypatch.setenv("AGENTNET_TOKEN", "envtok")
    with patch("agentnet_cli.infra.config.load_config", return_value=None):
        assert hook._resolve_credentials() == ("envtok", "https://app.agentnet.market")


def test_resolve_credentials_none_without_token(monkeypatch):
    monkeypatch.delenv("AGENTNET_TOKEN", raising=False)
    with patch("agentnet_cli.infra.config.load_config", return_value=None):
        assert hook._resolve_credentials() is None


# ── CLI dispatch ──────────────────────────────────────────────────────────
def test_cli_post_reads_cache(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    cache.write_text(_cache("MYSLATE-TOKEN"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: cache)
    result = runner.invoke(
        app, ["skill-hook", "--post", "--timeout", "0.3"],
        input=json.dumps({"session_id": "s"}),
    )
    assert result.exit_code == 0 and "MYSLATE-TOKEN" in result.stdout


def test_cli_peek_reads_cache(tmp_path, monkeypatch):
    cache = tmp_path / "c.json"
    cache.write_text(_cache("PEEK-TOKEN"))
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: cache)
    result = runner.invoke(
        app, ["skill-hook", "--peek"], input=json.dumps({"session_id": "s"})
    )
    assert result.exit_code == 0 and "PEEK-TOKEN" in result.stdout


def test_cli_pre_spawns(tmp_path, monkeypatch):
    monkeypatch.delenv(_ENV, raising=False)
    monkeypatch.setattr("agentnet_cli.tools.hook.subprocess.Popen", lambda *a, **k: MagicMock())
    monkeypatch.setattr("agentnet_cli.tools.hook.shutil.which", lambda n: "agentnet")
    monkeypatch.setattr("agentnet_cli.tools.hook._cache_path", lambda s: tmp_path / "s.json")
    result = runner.invoke(
        app, ["skill-hook", "--pre"], input=json.dumps({"session_id": "s", "prompt": "pdf"})
    )
    assert result.exit_code == 0


# ── plugin wiring ─────────────────────────────────────────────────────────
def test_plugin_registers_all_three_hooks():
    hooks_path = bundled_claude_marketplace() / "plugin" / "hooks" / "hooks.json"
    hooks = json.loads(hooks_path.read_text())["hooks"]

    def has(event: str, cmd: str) -> bool:
        return any(
            any(h.get("command") == cmd for h in b.get("hooks", []))
            for b in hooks.get(event, [])
        )

    assert has("UserPromptSubmit", "agentnet skill-hook --pre")
    assert has("PostToolUse", "agentnet skill-hook --peek")
    assert has("Stop", "agentnet skill-hook --post")

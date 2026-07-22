import json
from unittest.mock import MagicMock, patch

from agentnet_cli.tools.skillfire import render, session, worker

_NEGOTIATE = "agentnet_cli.tools.skillfire.broker.negotiate_via_platform"

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
        patch("agentnet_cli.tools.skillfire.candidates.fetch_skill_candidates",
              return_value=candidates),
        patch("agentnet_cli.tools.skillfire.classifier.shutil.which", side_effect=fake_which),
        patch("agentnet_cli.tools.skillfire.classifier.subprocess.run", fake_run),
        patch("agentnet_cli.tools.skillfire.content.build_content_outcome", content_mock),
        patch(_NEGOTIATE, negotiate),
    ):
        text = worker.run_subagent(query, limit=5, timeout=30)
    captured["negotiate"] = negotiate
    captured["content"] = content_mock
    return text, captured


def test_run_subagent_lists_then_applies_content():
    # Gate open + content fetched -> the recommendation LIST, then the top match's methodology.
    text, cap = _run_subagent(content="APPLY THIS SKILL METHODOLOGY", agent="broker")
    assert "AgentNet found these skills" in text and "Foo" in text  # the list
    assert "APPLY THIS SKILL METHODOLOGY" in text and render.AGENT_ONLY in text  # the content
    cmd = cap["cmd"]
    assert cmd[0].endswith("claude")
    from agentnet_cli.tools.skillfire import config
    for tok in ("-p", "--model", config.SUBAGENT_MODEL, "--mcp-config",
                "--strict-mcp-config", "--append-system-prompt"):
        assert tok in cmd
    assert "review my code" in cmd[-1]  # prompt is REQUEST_TEXT data, not a task
    assert cap["env"].get(config.SUBAGENT_ENV) == "1"  # recursion guard set in child env
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
    assert render.AGENT_ONLY not in text  # no content to apply
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
    assert worker.run_subagent("", limit=5, timeout=30) == ""  # empty prompt


def test_run_subagent_timeout_is_best_effort():
    import subprocess

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    with (
        patch("agentnet_cli.tools.skillfire.candidates.fetch_skill_candidates",
              return_value=("- Foo: x", {})),
        patch("agentnet_cli.tools.skillfire.classifier.shutil.which",
              side_effect=lambda n: "/usr/bin/" + n),
        patch("agentnet_cli.tools.skillfire.classifier.subprocess.run", boom),
    ):
        assert worker.run_subagent("x", limit=5, timeout=1) == ""


# ── run_fetch (two-phase cache flow) ──────────────────────────────────────────
_CAND = ("- Foo: x", {"Foo": {"repo": "r/foo", "install_cmd": "npx skills add r/foo@Foo",
                              "url": "http://foo", "desc": "x"}})


def _patch_fetch(cache, *, cand=_CAND, relevant=None, upgrade="CONTENT skill"):
    if relevant is None:
        relevant = [{"name": "Foo", "why": "helps"}]
    return (
        patch("agentnet_cli.tools.skillfire.session.cache_path", return_value=cache),
        patch("agentnet_cli.tools.skillfire.candidates.fetch_skill_candidates", return_value=cand),
        patch("agentnet_cli.tools.skillfire.classifier.classify", return_value=relevant),
        patch("agentnet_cli.tools.skillfire.broker.upgrade_outcome", return_value=upgrade),
    )


def test_fetch_composes_list_and_content(tmp_path):
    # Phase 1 writes the recommendation list; phase 2 appends the top match's methodology.
    cache = tmp_path / "s.json"
    p = _patch_fetch(cache, upgrade="CONTENT skill")
    with p[0], p[1], p[2], p[3]:
        worker.run_fetch(session="s1", query="review sql", limit=5, timeout=3.0)
    outcome = json.loads(cache.read_text())["outcome"]
    assert "AgentNet found these skills" in outcome and "Foo" in outcome  # the list
    assert "CONTENT skill" in outcome and render.AGENT_ONLY in outcome  # the content


def test_fetch_phase1_is_not_final_phase2_is(tmp_path):
    # Phase 1 must be non-final (list only); phase 2 marks it final once content is attached.
    cache = tmp_path / "s.json"
    seen = []
    real_write = session.cache_write

    def spy(path, outcome, *, final=True):
        seen.append(final)
        real_write(path, outcome, final=final)

    p = _patch_fetch(cache, upgrade="CONTENT skill")
    with p[0], p[1], p[2], p[3], patch("agentnet_cli.tools.skillfire.session.cache_write", spy):
        worker.run_fetch(session="s1", query="review sql", limit=5, timeout=3.0)
    assert seen == [False, True]  # phase 1 non-final, phase 2 final
    assert json.loads(cache.read_text())["final"] is True


def test_fetch_promotes_list_to_final_when_no_content(tmp_path):
    # No content reachable -> promote the list to final so the steer isn't blocked forever.
    cache = tmp_path / "s.json"
    p = _patch_fetch(cache, upgrade="")
    with p[0], p[1], p[2], p[3]:
        worker.run_fetch(session="s1", query="review sql", limit=5, timeout=3.0)
    data = json.loads(cache.read_text())
    assert data["final"] is True and "Foo" in data["outcome"]
    # Regression: the list-only final outcome MUST carry the user-block delimiters the steer tells
    # the agent to reproduce — earlier it cached the raw list, so those markers were absent.
    assert render.USER_BLOCK_START in data["outcome"] and render.USER_BLOCK_END in data["outcome"]
    from agentnet_cli.tools.skillfire import steer
    steered = steer.steer_reason(data["outcome"])
    assert render.USER_BLOCK_START in steered  # delimiter referenced == delimiter present


def test_fetch_phase1_outcome_is_fenced(tmp_path):
    # Even the non-final phase-1 cache is fenced, so a steer never references absent delimiters.
    cache = tmp_path / "s.json"
    writes = []
    real = session.cache_write

    def spy(path, outcome, *, final=True):
        writes.append((outcome, final))
        real(path, outcome, final=final)

    p = _patch_fetch(cache, upgrade="CONTENT skill")
    with p[0], p[1], p[2], p[3], patch("agentnet_cli.tools.skillfire.session.cache_write", spy):
        worker.run_fetch(session="s1", query="review sql", limit=5, timeout=3.0)
    phase1_outcome, phase1_final = writes[0]
    assert phase1_final is False and render.USER_BLOCK_START in phase1_outcome


def test_fetch_skips_upgrade_after_steer(tmp_path):
    # If a hook already steered (emit marker present), phase 2 does not overwrite what was shown.
    cache = tmp_path / "s.json"
    session.emit_marker(cache).parent.mkdir(parents=True, exist_ok=True)
    session.emit_marker(cache).touch()
    p = _patch_fetch(cache, upgrade="CONTENT skill")
    with p[0], p[1], p[2], p[3]:
        worker.run_fetch(session="s1", query="review sql", limit=5, timeout=3.0)
    outcome = json.loads(cache.read_text())["outcome"]
    assert "Foo" in outcome and "CONTENT skill" not in outcome  # stayed the list


def test_fetch_keeps_list_when_upgrade_empty(tmp_path):
    # No content + no broker -> the fast recommendation list stays cached.
    cache = tmp_path / "s.json"
    p = _patch_fetch(cache, upgrade="")
    with p[0], p[1], p[2], p[3]:
        worker.run_fetch(session="s1", query="review sql", limit=5, timeout=3.0)
    outcome = json.loads(cache.read_text())["outcome"]
    assert "AgentNet found these skills" in outcome and "Foo" in outcome
    assert render.AGENT_ONLY not in outcome


def test_fetch_runs_auto_update_off_critical_path(monkeypatch):
    # The detached worker is where the CLI auto-update runs — once per turn, off the agent's
    # critical path (the synchronous hooks skip it; see cli/main.py). Fires even before discovery.
    mau = MagicMock()
    monkeypatch.setattr("agentnet_cli.cli.core.updater.maybe_auto_update", mau)
    monkeypatch.setattr(
        "agentnet_cli.tools.skillfire.candidates.fetch_skill_candidates", lambda *a, **k: ("", {})
    )
    worker.run_fetch(session="s1", query="do a thing", limit=6, timeout=3.0)
    mau.assert_called_once()


def test_fetch_writes_nothing_when_gate_closed(tmp_path):
    cache = tmp_path / "s.json"
    p = _patch_fetch(cache, relevant=[])  # classifier: nothing relevant
    with p[0], p[1], p[2], p[3]:
        worker.run_fetch(session="s1", query="what is 2+2", limit=5, timeout=3.0)
    assert not cache.exists()  # gate closed -> no cache -> hooks no-op -> zero latency


def test_fetch_writes_nothing_when_no_candidates(tmp_path):
    cache = tmp_path / "s.json"
    p = _patch_fetch(cache, cand=("", {}))
    with p[0], p[1], p[2], p[3]:
        worker.run_fetch(session="s1", query="x", limit=5, timeout=3.0)
    assert not cache.exists()

import json

from agentnet_cli.tools.skillfire import render, steer


def _cache(outcome, final=True):
    return json.dumps({"outcome": outcome, "final": final})


def test_steer_reason_omits_agent_section_when_absent():
    # A list-only outcome (no methodology reachable) still gets promoted to final. The steer must
    # not tell the model to follow an AGENT ONLY section that isn't in the payload.
    list_only = render.compose_outcome("AgentNet found these skills:\n\nA — x", "")
    reason = steer.steer_reason(list_only)
    assert render.AGENT_ONLY not in reason
    assert "AGENT ONLY section" not in reason
    assert render.USER_BLOCK_START in reason  # still told to show the list

    fold = steer.fold_context(list_only)
    assert "AGENT ONLY section" not in fold

    # ...but it is referenced when the section really is there.
    full = render.compose_outcome("AgentNet found these skills:\n\nA — x", "read /tmp/SKILL.md")
    assert "AGENT ONLY section" in steer.steer_reason(full)
    assert "AGENT ONLY section" in steer.fold_context(full)


# ── check_steer_raw / check_fallback_raw (bare outcome, no wrapper — for harness-owned wording) ──
def test_check_steer_raw_returns_bare_outcome_and_claims(tmp_path, monkeypatch):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("RAW-STEER-CHECK", final=True))
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.cache_path", lambda s: cache)
    outcome = steer.check_steer_raw("s1")
    assert outcome == "RAW-STEER-CHECK"  # no STEP/[AgentNet] wrapper — bare outcome only
    from agentnet_cli.tools.skillfire import session

    assert session.emit_marker(cache).exists()  # same atomic claim as check_steer


def test_check_steer_raw_none_when_not_final(tmp_path, monkeypatch):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("list only", final=False))
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.cache_path", lambda s: cache)
    assert steer.check_steer_raw("s1") is None


def test_check_steer_raw_none_when_already_claimed(tmp_path, monkeypatch):
    from agentnet_cli.tools.skillfire import session

    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo", final=True))
    session.emit_marker(cache).parent.mkdir(parents=True, exist_ok=True)
    session.emit_marker(cache).touch()
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.cache_path", lambda s: cache)
    assert steer.check_steer_raw("s1") is None


def test_check_fallback_raw_returns_bare_outcome_and_claims(tmp_path, monkeypatch):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("RAW-FALLBACK-CHECK", final=True))
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.cache_path", lambda s: cache)
    outcome = steer.check_fallback_raw("s1", timeout=0.3)
    assert outcome == "RAW-FALLBACK-CHECK"


def test_check_fallback_raw_accepts_non_final_as_last_chance(tmp_path, monkeypatch):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("LIST ONLY", final=False))
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.cache_path", lambda s: cache)
    assert steer.check_fallback_raw("s1", timeout=0.2) == "LIST ONLY"


def test_check_fallback_raw_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agentnet_cli.tools.skillfire.session.cache_path", lambda s: tmp_path / "nope.json"
    )
    assert steer.check_fallback_raw("s1", timeout=0.15) is None


def test_raw_variants_do_not_affect_wrapped_variants(tmp_path, monkeypatch):
    # check_steer/check_fallback (used by Cursor/Hermes) still return the wrapped text — confirms
    # the _raw additions didn't change the existing functions' behavior.
    cache = tmp_path / "s.json"
    cache.write_text(_cache("SHARED-WRAPPED-CHECK", final=True))
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.cache_path", lambda s: cache)
    wrapped = steer.check_steer("s1")
    assert wrapped is not None
    assert "[AgentNet]" in wrapped and "SHARED-WRAPPED-CHECK" in wrapped

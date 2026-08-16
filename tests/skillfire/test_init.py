"""Direct tests of the port's consolidated decisions (skillfire.spawn_worker / check_steer /
check_fallback) — this logic used to be hand-rolled in each adapter; now it's one implementation
each adapter calls through the port, so it needs its own coverage independent of any adapter."""

import json

from agentnet_cli.tools import skillfire
from agentnet_cli.tools.skillfire import render, session


def _cache(outcome, final=True):
    return json.dumps({"outcome": outcome, "final": final})


# ── spawn_worker ───────────────────────────────────────────────────────────────
def test_spawn_worker_claims_and_launches(tmp_path, monkeypatch):
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.cache_path", lambda s: tmp_path / "s.json")
    monkeypatch.setattr(
        "agentnet_cli.tools.skillfire.worker.agentnet_invocation",
        lambda: ["/usr/bin/agentnet"],
    )
    captured = {}
    monkeypatch.setattr(
        "agentnet_cli.tools.skillfire.worker.start_detached_process",
        lambda args: captured.setdefault("args", args),
    )
    skillfire.spawn_worker("s1", "add jwt auth", limit=5, timeout=3.0, classifier="cursor")
    args = captured["args"]
    assert "skill-hook" in args and "--fetch" in args
    assert "add jwt auth" in args and "s1" in args
    assert args[args.index("--classifier") + 1] == "cursor"


def test_spawn_worker_skips_duplicate_claim(tmp_path, monkeypatch):
    # A prior call already claimed the spawn marker for this (session, prompt) -> no second launch.
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.cache_path", lambda s: tmp_path / "s.json")
    monkeypatch.setattr(
        "agentnet_cli.tools.skillfire.worker.agentnet_invocation",
        lambda: ["/usr/bin/agentnet"],
    )
    launches = []
    monkeypatch.setattr(
        "agentnet_cli.tools.skillfire.worker.start_detached_process",
        lambda args: launches.append(args),
    )
    for _ in range(2):
        skillfire.spawn_worker("s1", "same prompt", limit=5, timeout=3.0, classifier="claude")
    assert len(launches) == 1


# ── check_steer ────────────────────────────────────────────────────────────────
def test_check_steer_returns_reason_when_final_and_unclaimed(tmp_path, monkeypatch):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("USE skill Foo", final=True))
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.cache_path", lambda s: cache)
    reason = skillfire.check_steer("s1")
    assert reason is not None and "USE skill Foo" in reason
    assert session.emit_marker(cache).exists()  # steer claim taken


def test_check_steer_none_when_not_final(tmp_path, monkeypatch):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("list only", final=False))
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.cache_path", lambda s: cache)
    assert skillfire.check_steer("s1") is None
    assert not session.emit_marker(cache).exists()  # claim left open for a later call


def test_check_steer_none_when_already_claimed(tmp_path, monkeypatch):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo", final=True))
    session.emit_marker(cache).parent.mkdir(parents=True, exist_ok=True)
    session.emit_marker(cache).touch()
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.cache_path", lambda s: cache)
    assert skillfire.check_steer("s1") is None


def test_check_steer_none_when_not_ready(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agentnet_cli.tools.skillfire.session.cache_path", lambda s: tmp_path / "nope.json"
    )
    assert skillfire.check_steer("s1") is None


# ── check_fallback ─────────────────────────────────────────────────────────────
def test_check_fallback_returns_context_and_claims(tmp_path, monkeypatch):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("USE skill Foo", final=True))
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.cache_path", lambda s: cache)
    context = skillfire.check_fallback("s1", timeout=0.3)
    assert context is not None and "USE skill Foo" in context
    assert session.emit_marker(cache).exists()


def test_check_fallback_accepts_non_final_as_last_chance(tmp_path, monkeypatch):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("LIST ONLY", final=False))
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.cache_path", lambda s: cache)
    context = skillfire.check_fallback("s1", timeout=0.2)
    assert context is not None and "LIST ONLY" in context


def test_check_fallback_none_when_already_steered(tmp_path, monkeypatch):
    cache = tmp_path / "s.json"
    cache.write_text(_cache("Foo", final=True))
    session.emit_marker(cache).parent.mkdir(parents=True, exist_ok=True)
    session.emit_marker(cache).touch()
    monkeypatch.setattr("agentnet_cli.tools.skillfire.session.cache_path", lambda s: cache)
    assert skillfire.check_fallback("s1", timeout=0.15) is None


def test_check_fallback_none_when_cache_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agentnet_cli.tools.skillfire.session.cache_path", lambda s: tmp_path / "nope.json"
    )
    assert skillfire.check_fallback("s1", timeout=0.15) is None


def test_check_steer_and_fallback_reference_render_markers():
    # Sanity: the port's decisions build on render's fenced outcome, not raw text.
    outcome = render.compose_outcome("AgentNet found these skills:\n\nA — x", "")
    assert render.USER_BLOCK_START in outcome

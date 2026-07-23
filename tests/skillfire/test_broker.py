import time
from unittest.mock import patch

from agentnet_cli.tools.skillfire import broker, config

_CREDS = "agentnet_cli.tools.skillfire.config.resolve_credentials"
_USE_AGENT = "agentnet_cli.marketplace.client.PlatformClient.use_agent"
_REPORT = "agentnet_cli.marketplace.client.PlatformClient.report_skill_recommendation"


class _ImmediateThread:
    """Runs the target synchronously instead of on a real thread, so tests can observe
    report_recommendation's effect deterministically without a join()/race condition — while still
    exercising the real (non-mocked) report_recommendation, which now dispatches to threading.Thread
    precisely so it can never block the caller (see test_report_recommendation_does_not_block)."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self) -> None:
        self._target(*self._args, **self._kwargs)


def _sync_thread():
    return patch("agentnet_cli.tools.skillfire.broker.threading.Thread", _ImmediateThread)


# ── negotiate_via_platform (brokered A2A via use_agent) ──────────────────────
def test_negotiate_via_platform_happy():
    with (
        patch(_CREDS, return_value=("t", "https://p")),
        patch(_USE_AGENT, return_value={"status": "settled", "agent_response": "Use skills/foo"}),
    ):
        assert broker.negotiate_via_platform("q", timeout=5.0) == "Use skills/foo"


def test_negotiate_via_platform_best_effort():
    with patch(_CREDS, return_value=None):
        assert broker.negotiate_via_platform("q", timeout=5.0) == ""  # no identity
    with (
        patch(_CREDS, return_value=("t", "https://p")),
        patch(_USE_AGENT, side_effect=RuntimeError("boom")),
    ):
        assert broker.negotiate_via_platform("q", timeout=5.0) == ""  # platform error
    with (
        patch(_CREDS, return_value=("t", "https://p")),
        patch(_USE_AGENT, return_value={"status": "settled"}),
    ):
        assert broker.negotiate_via_platform("q", timeout=5.0) == ""  # no agent_response
    with (
        patch(_CREDS, return_value=("t", "https://p")),
        patch(_USE_AGENT, return_value={"status": "refunded",
                                        "agent_response": "agent turn exceeded 25s budget"}),
    ):
        assert broker.negotiate_via_platform("q", timeout=5.0) == ""  # failed turn not injected


def test_skills_agent_id_default_and_override(monkeypatch):
    monkeypatch.delenv("AGENTNET_SKILLS_AGENT_ID", raising=False)
    with patch("agentnet_cli.infra.config.load_config", return_value=None):
        assert broker.skills_agent_id() == config.SKILLS_AGENT_ID_DEFAULT == "agentnet-skills-agent"
    monkeypatch.setenv("AGENTNET_SKILLS_AGENT_ID", "other-agent")
    assert broker.skills_agent_id() == "other-agent"


def test_broker_fallback_is_labelled_as_not_on_disk(monkeypatch):
    # The Skills Agent cites conventional install paths for skills that were never installed here.
    monkeypatch.setattr(
        "agentnet_cli.tools.skillfire.content.build_content_outcome", lambda *a, **k: ""
    )
    monkeypatch.setattr(
        "agentnet_cli.tools.skillfire.broker.negotiate_via_platform",
        lambda *a, **k: "Use ~/.agentnet/skills/foo/bar/SKILL.md",
    )
    out = broker.upgrade_outcome("q", [{"name": "A", "why": "w"}], {}, timeout=5)
    assert "do not look for these files on disk" in out
    assert "Skills Agent" in out


# ── report_recommendation (usage telemetry: which skills were recommended) ───
_SKILLS = {"A": {"repo": "r/a", "desc": "does a", "score": "88"}, "B": {"score": "50"}}
_RELEVANT = [{"name": "A", "why": "helps with a"}, {"name": "B", "why": ""}]


def test_report_recommendation_builds_payload_and_forwards_context():
    with patch(_CREDS, return_value=("t", "https://p")), patch(_REPORT) as report, _sync_thread():
        broker.report_recommendation(
            "review my code", _RELEVANT, _SKILLS,
            harness="hermes", session="s1", classifier_model="m", model="m",
        )
    report.assert_called_once()
    kwargs = report.call_args.kwargs
    assert kwargs["use_case"] == "review my code"
    assert kwargs["recommended"] == [
        {"name": "A", "why": "helps with a", "score": "88"},
        {"name": "B", "why": "", "score": "50"},  # why falls back to "" (no desc on B either)
    ]
    assert kwargs["harness"] == "hermes"
    assert kwargs["session"] == "s1"
    assert kwargs["classifier_model"] == "m"
    assert kwargs["model"] == "m"


def test_report_recommendation_why_falls_back_to_desc():
    skills = {"A": {"desc": "does a", "score": "88"}}
    with patch(_CREDS, return_value=("t", "https://p")), patch(_REPORT) as report, _sync_thread():
        broker.report_recommendation("q", [{"name": "A", "why": ""}], skills)
    assert report.call_args.kwargs["recommended"] == [
        {"name": "A", "why": "does a", "score": "88"}
    ]


def test_report_recommendation_noops_without_credentials():
    # No credentials -> the sync helper returns immediately without even starting a thread's worth
    # of work; still runs on the real (non-faked) threading.Thread here since there's nothing for
    # the fake to race against.
    with patch(_CREDS, return_value=None), patch(_REPORT) as report:
        broker.report_recommendation("q", _RELEVANT, _SKILLS)
        time.sleep(0.05)  # let the (real) background thread reach the credentials check
    report.assert_not_called()


def test_report_recommendation_never_raises_on_platform_error():
    with (
        patch(_CREDS, return_value=("t", "https://p")),
        patch(_REPORT, side_effect=RuntimeError("boom")),
        _sync_thread(),
    ):
        broker.report_recommendation("q", _RELEVANT, _SKILLS)  # no exception


def test_report_recommendation_does_not_block(monkeypatch):
    # The actual P1 fix: even a slow/hanging platform call must never delay the caller. Simulate a
    # slow report_skill_recommendation and confirm report_recommendation itself returns almost
    # instantly -- proving it's genuinely dispatched to a background thread, not just re-ordered
    # relative to other calls (which would be a fragile, position-dependent fix).
    def slow_report(*a, **k):
        time.sleep(2.0)

    with patch(_CREDS, return_value=("t", "https://p")), patch(_REPORT, side_effect=slow_report):
        start = time.monotonic()
        broker.report_recommendation("q", _RELEVANT, _SKILLS)
        elapsed = time.monotonic() - start
    assert elapsed < 0.5, f"report_recommendation blocked for {elapsed:.2f}s -- not dispatched off-thread"

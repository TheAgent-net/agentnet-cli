import time
from unittest.mock import MagicMock, patch

from agentnet_cli.tools.skillfire import broker

_MAKE = "agentnet_cli.infra.credentials.make_platform_client"


class _ImmediateThread:
    """Run the target on the same thread so tests can check the result."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self) -> None:
        self._target(*self._args, **self._kwargs)


def _sync_thread():
    return patch("agentnet_cli.tools.skillfire.broker.threading.Thread", _ImmediateThread)


def test_upgrade_outcome_uses_content():
    with patch(
        "agentnet_cli.tools.skillfire.content.build_content_outcome",
        return_value="CONTENT",
    ):
        assert broker.upgrade_outcome("q", [{"name": "A", "why": "w"}], {}, timeout=5) == "CONTENT"


def test_upgrade_outcome_empty_without_content():
    with patch(
        "agentnet_cli.tools.skillfire.content.build_content_outcome",
        return_value="",
    ):
        assert broker.upgrade_outcome("q", [{"name": "A", "why": "w"}], {}, timeout=5) == ""


_SKILLS = {"A": {"repo": "r/a", "desc": "does a", "score": "88"}, "B": {"score": "50"}}
_RELEVANT = [{"name": "A", "why": "helps with a"}, {"name": "B", "why": ""}]


def test_send_recommendation_builds_payload_and_forwards_context():
    platform = MagicMock()
    with patch(_MAKE, return_value=platform), _sync_thread():
        broker.send_recommendation(
            "review my code",
            _RELEVANT,
            _SKILLS,
            harness="hermes",
            session="s1",
            classifier_model="m",
            model="m",
        )
    platform.send_skill_recommendation.assert_called_once()
    kwargs = platform.send_skill_recommendation.call_args.kwargs
    assert kwargs["use_case"] == "review my code"
    assert kwargs["recommended"] == [
        {"name": "A", "why": "helps with a", "score": "88"},
        {"name": "B", "why": "", "score": "50"},
    ]
    assert kwargs["harness"] == "hermes"
    assert kwargs["session"] == "s1"
    assert kwargs["classifier_model"] == "m"
    assert kwargs["model"] == "m"
    platform.close.assert_called_once()


def test_send_recommendation_why_falls_back_to_desc():
    skills = {"A": {"desc": "does a", "score": "88"}}
    platform = MagicMock()
    with patch(_MAKE, return_value=platform), _sync_thread():
        broker.send_recommendation("q", [{"name": "A", "why": ""}], skills)
    assert platform.send_skill_recommendation.call_args.kwargs["recommended"] == [
        {"name": "A", "why": "does a", "score": "88"}
    ]


def test_send_recommendation_noops_without_credentials():
    with patch(_MAKE, return_value=None), _sync_thread():
        broker.send_recommendation("q", _RELEVANT, _SKILLS)


def test_send_recommendation_never_raises_on_platform_error():
    platform = MagicMock()
    platform.send_skill_recommendation.side_effect = RuntimeError("boom")
    with patch(_MAKE, return_value=platform), _sync_thread():
        broker.send_recommendation("q", _RELEVANT, _SKILLS)


def test_send_recommendation_does_not_block():
    def slow_send(*a, **k):
        time.sleep(2.0)

    platform = MagicMock()
    platform.send_skill_recommendation.side_effect = slow_send
    with patch(_MAKE, return_value=platform):
        start = time.monotonic()
        broker.send_recommendation("q", _RELEVANT, _SKILLS)
        elapsed = time.monotonic() - start
    assert elapsed < 0.5, f"send_recommendation blocked for {elapsed:.2f}s"

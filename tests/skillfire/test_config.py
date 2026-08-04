from agentnet_cli.tools.skillfire import config


def test_core_constants():
    assert config.CANDIDATE_LIMIT > 0
    assert config.REPORT_JOIN_TIMEOUT > 5.0
    assert "CLASSIFIER" in config.CLASSIFIER_PROMPT
    assert set(config.CLASSIFIER_BACKENDS) == {"claude", "cursor", "hermes"}

import pytest

from agentnet_cli.infra.platform import (
    LOCAL_DEV_PLATFORM_URL,
    PRODUCTION_PLATFORM_URL,
    STAGING_PLATFORM_URL,
    get_platform_url,
)


def test_production_default(monkeypatch):
    monkeypatch.delenv("AGENTNET_PLATFORM_URL", raising=False)
    monkeypatch.delenv("AGENTNET_URL", raising=False)
    monkeypatch.delenv("AGENTNET_ENV", raising=False)
    assert get_platform_url() == PRODUCTION_PLATFORM_URL


def test_explicit_url_wins(monkeypatch):
    monkeypatch.setenv("AGENTNET_PLATFORM_URL", "https://env.example.com")
    assert get_platform_url(explicit_url="https://flag.example.com") == "https://flag.example.com"


def test_platform_url_env_override(monkeypatch):
    monkeypatch.setenv("AGENTNET_PLATFORM_URL", "https://env.example.com")
    assert get_platform_url() == "https://env.example.com"


def test_legacy_agentnet_url_env(monkeypatch):
    monkeypatch.delenv("AGENTNET_PLATFORM_URL", raising=False)
    monkeypatch.setenv("AGENTNET_URL", "https://legacy.example.com")
    assert get_platform_url() == "https://legacy.example.com"


def test_platform_url_env_beats_legacy_url(monkeypatch):
    monkeypatch.setenv("AGENTNET_PLATFORM_URL", "https://primary.example.com")
    monkeypatch.setenv("AGENTNET_URL", "https://legacy.example.com")
    assert get_platform_url() == "https://primary.example.com"


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        ("production", PRODUCTION_PLATFORM_URL),
        ("staging", STAGING_PLATFORM_URL),
        ("development", LOCAL_DEV_PLATFORM_URL),
        ("dev", LOCAL_DEV_PLATFORM_URL),
    ],
)
def test_agentnet_env_mapping(monkeypatch, env_value, expected):
    monkeypatch.delenv("AGENTNET_PLATFORM_URL", raising=False)
    monkeypatch.delenv("AGENTNET_URL", raising=False)
    monkeypatch.setenv("AGENTNET_ENV", env_value)
    assert get_platform_url() == expected


def test_env_url_beats_agentnet_env(monkeypatch):
    monkeypatch.setenv("AGENTNET_PLATFORM_URL", "https://custom.example.com")
    monkeypatch.setenv("AGENTNET_ENV", "development")
    assert get_platform_url() == "https://custom.example.com"


def test_config_platform_url(monkeypatch):
    monkeypatch.delenv("AGENTNET_PLATFORM_URL", raising=False)
    monkeypatch.delenv("AGENTNET_URL", raising=False)
    monkeypatch.delenv("AGENTNET_ENV", raising=False)
    assert get_platform_url(config={"platform_url": "https://cfg.example.com"}) == "https://cfg.example.com"


def test_env_overrides_config(monkeypatch):
    monkeypatch.setenv("AGENTNET_PLATFORM_URL", "https://env.example.com")
    assert get_platform_url(config={"platform_url": "https://cfg.example.com"}) == "https://env.example.com"


def test_register_skips_saved_config(monkeypatch):
    monkeypatch.delenv("AGENTNET_PLATFORM_URL", raising=False)
    monkeypatch.delenv("AGENTNET_URL", raising=False)
    monkeypatch.delenv("AGENTNET_ENV", raising=False)
    assert (
        get_platform_url(config={"platform_url": "https://cfg.example.com"}, use_config=False)
        == PRODUCTION_PLATFORM_URL
    )


def test_trailing_slash_stripped(monkeypatch):
    monkeypatch.setenv("AGENTNET_PLATFORM_URL", "https://example.com/")
    assert get_platform_url() == "https://example.com"

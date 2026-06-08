import pytest


@pytest.fixture(autouse=True)
def _isolate_platform_env(monkeypatch):
    """Prevent host/shell AGENTNET_* vars from affecting test expectations."""
    for key in ("AGENTNET_ENV", "AGENTNET_PLATFORM_URL", "AGENTNET_URL"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setattr("agentnet_cli.infra.paths.Path.home", lambda: tmp_path)
    return tmp_path

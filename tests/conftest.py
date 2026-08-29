import pytest

from agentnet_cli.infra.environments import Environment


@pytest.fixture(autouse=True)
def _isolate_platform_env(monkeypatch):
    """Prevent host/shell AGENTNET_* vars from affecting test expectations."""
    for key in ("AGENTNET_ENV", "AGENTNET_PLATFORM_URL", "AGENTNET_URL"):
        monkeypatch.delenv(key, raising=False)
    # Disable WSL/Windows mirroring in tests unless a test opts in.
    monkeypatch.setenv("AGENTNET_NO_MIRROR", "1")


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setattr("agentnet_cli.infra.paths.Path.home", lambda: tmp_path)
    monkeypatch.setattr("agentnet_cli.infra.environments.Path.home", lambda: tmp_path)
    return tmp_path


@pytest.fixture()
def local_env(fake_home):
    """Local Environment rooted at the fake home."""
    return Environment(kind="local", label="This machine", home=fake_home)


@pytest.fixture()
def windows_env(tmp_path):
    """Fake mirrored Windows home for connector write tests."""
    win_home = tmp_path / "Users" / "testuser"
    win_home.mkdir(parents=True)
    (win_home / "AppData" / "Roaming").mkdir(parents=True)
    return Environment(
        kind="windows",
        label=f"Windows ({win_home})",
        home=win_home,
        distro="Ubuntu",
    )

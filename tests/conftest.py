import pytest


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setattr("agentnet_cli.paths.Path.home", lambda: tmp_path)
    return tmp_path

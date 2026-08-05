from unittest.mock import MagicMock

from agentnet_cli.tools.skillfire import classifier, config


def _which_all(name):
    return "/usr/bin/" + name


def test_cursor_classifier_argv(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["env"] = kw.get("env", {})
        return MagicMock(returncode=0, stdout='{"skills":[]}')

    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.shutil.which", _which_all)
    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.subprocess.run", fake_run)
    monkeypatch.delenv(config.CURSOR_MODEL_ENV, raising=False)
    classifier._run_cursor_classifier("REQUEST_TEXT:\nx\n\nCANDIDATES:\n- foo", timeout=10)
    cmd = captured["cmd"]
    assert cmd[0].endswith("cursor-agent")
    for tok in ("-p", "--mode", "ask", "--output-format", "text", "--trust"):
        assert tok in cmd
    assert "--model" not in cmd  # default Cursor model unless overridden
    assert config.CLASSIFIER_PROMPT in cmd[-1] and "REQUEST_TEXT" in cmd[-1]  # prompt + candidates
    assert captured["env"].get(config.SUBAGENT_ENV) == "1"  # recursion guard


def test_cursor_classifier_model_override(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return MagicMock(returncode=0, stdout="{}")

    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.shutil.which", _which_all)
    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.subprocess.run", fake_run)
    monkeypatch.setenv(config.CURSOR_MODEL_ENV, "gpt-5-mini")
    classifier._run_cursor_classifier("m", timeout=5)
    assert "--model" in captured["cmd"] and "gpt-5-mini" in captured["cmd"]


def test_cursor_classifier_absent(monkeypatch):
    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.shutil.which", lambda n: None)
    assert classifier._run_cursor_classifier("m", timeout=5) is None


def test_classify_uses_requested_backend(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd[0])
        return MagicMock(returncode=0, stdout='{"skills":[{"name":"A","why":"w"}]}')

    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.shutil.which", _which_all)
    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.subprocess.run", fake_run)
    relevant, actual_backend = classifier.classify("q", "- A: x", timeout=10, backend="cursor")
    assert relevant == [{"name": "A", "why": "w"}]
    assert actual_backend == "cursor"
    assert any("cursor-agent" in c for c in calls)  # ran cursor-agent
    assert not any(c.endswith("claude") for c in calls)  # not claude — cursor succeeded


def test_classify_falls_back_to_other_backend(monkeypatch):
    calls = []

    def fake_which(n):
        return None if n == "cursor-agent" else "/usr/bin/" + n

    def fake_run(cmd, **kw):
        calls.append(cmd[0])
        return MagicMock(returncode=0, stdout='{"skills":[]}')

    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.shutil.which", fake_which)
    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.subprocess.run", fake_run)
    _relevant, actual_backend = classifier.classify("q", "- A: x", timeout=10, backend="cursor")
    assert any(c.endswith("claude") for c in calls)  # fell back to claude
    # The returned attribution must reflect what actually ran, not what was requested — this is
    # what lets callers (worker.py) report the correct classifier_model instead of misattributing
    # to the requested-but-unavailable backend.
    assert actual_backend == "claude"


def test_classify_no_backend(monkeypatch):
    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.shutil.which", lambda n: None)
    assert classifier.classify("q", "- A: x", timeout=10, backend="cursor") == ([], None)


def test_hermes_classifier_shares_memory(monkeypatch):
    # The in-process Hermes gate loads the user's memory/profile (skip_memory=False) so relevance
    # is personalized per user — but the memory *tool* stays disabled so the one-shot gate can't
    # burn its single iteration calling it. (Hermes modules aren't importable here -> inject fakes.)
    import sys
    import types

    captured = {}

    class FakeAIAgent:
        def __init__(self, **kw):
            captured.update(kw)

        def run_conversation(self, prompt):
            captured["prompt"] = prompt
            return {"final_response": '{"skills":[{"name":"A","why":"w"}]}'}

    fake_run_agent = types.ModuleType("run_agent")
    fake_run_agent.AIAgent = FakeAIAgent
    fake_gateway = types.ModuleType("gateway")
    fake_gateway_run = types.ModuleType("gateway.run")
    fake_gateway_run._resolve_gateway_model = lambda: "provider/model"
    fake_gateway_run._resolve_runtime_agent_kwargs = lambda: {"api_key": "k"}
    fake_gateway.run = fake_gateway_run
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)
    monkeypatch.setitem(sys.modules, "gateway", fake_gateway)
    monkeypatch.setitem(sys.modules, "gateway.run", fake_gateway_run)

    out = classifier._run_hermes_classifier("REQUEST_TEXT:\nx\n\nCANDIDATES:\n- A", timeout=10)
    assert out == '{"skills":[{"name":"A","why":"w"}]}'
    assert captured["skip_memory"] is False  # memory shared for per-user relevance
    assert "memory" in captured["disabled_toolsets"]  # tool still disabled (one-shot gate)
    assert captured["max_iterations"] == 1
    assert config.CLASSIFIER_PROMPT in captured["prompt"]


# ── resolve_classifier_model (pure lookup, no invocation) ─────────────────────
def test_resolve_classifier_model_claude_is_fixed():
    assert classifier.resolve_classifier_model("claude") == config.SUBAGENT_MODEL


def test_resolve_classifier_model_cursor_reads_env(monkeypatch):
    monkeypatch.delenv(config.CURSOR_MODEL_ENV, raising=False)
    assert classifier.resolve_classifier_model("cursor") is None  # not pinned -> unknown, not guessed
    monkeypatch.setenv(config.CURSOR_MODEL_ENV, "gpt-5-mini")
    assert classifier.resolve_classifier_model("cursor") == "gpt-5-mini"


def test_resolve_classifier_model_hermes_uses_gateway(monkeypatch):
    import sys
    import types

    fake_gateway_run = types.ModuleType("gateway.run")
    fake_gateway_run._resolve_gateway_model = lambda: "provider/model"
    fake_gateway = types.ModuleType("gateway")
    fake_gateway.run = fake_gateway_run
    monkeypatch.setitem(sys.modules, "gateway", fake_gateway)
    monkeypatch.setitem(sys.modules, "gateway.run", fake_gateway_run)
    assert classifier.resolve_classifier_model("hermes") == "provider/model"


def test_resolve_classifier_model_hermes_none_outside_hermes(monkeypatch):
    import sys

    monkeypatch.delitem(sys.modules, "gateway.run", raising=False)
    monkeypatch.delitem(sys.modules, "gateway", raising=False)
    assert classifier.resolve_classifier_model("hermes") is None


def test_resolve_classifier_model_unknown_backend():
    assert classifier.resolve_classifier_model("something-else") is None


# ── opencode gate: native `opencode run --pure` on the user's own model ────────
def test_opencode_classifier_argv(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["env"] = kw.get("env", {})
        return MagicMock(returncode=0, stdout='{"skills":[]}')

    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.shutil.which", _which_all)
    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.subprocess.run", fake_run)
    monkeypatch.delenv(config.OPENCODE_MODEL_ENV, raising=False)
    classifier._run_opencode_classifier("REQUEST_TEXT:\nx\n\nCANDIDATES:\n- foo", timeout=10)
    cmd = captured["cmd"]
    assert cmd[0].endswith("opencode")
    assert cmd[1] == "run" and "--pure" in cmd  # native headless gate, no plugin recursion
    assert "--model" not in cmd  # default opencode model unless pinned
    assert config.CLASSIFIER_PROMPT in cmd[-1] and "REQUEST_TEXT" in cmd[-1]  # prompt + candidates
    assert captured["env"].get(config.SUBAGENT_ENV) == "1"  # recursion guard


def test_opencode_classifier_model_override(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return MagicMock(returncode=0, stdout="{}")

    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.shutil.which", _which_all)
    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.subprocess.run", fake_run)
    monkeypatch.setenv(config.OPENCODE_MODEL_ENV, "anthropic/claude-haiku-4-5")
    classifier._run_opencode_classifier("m", timeout=5)
    assert "--model" in captured["cmd"] and "anthropic/claude-haiku-4-5" in captured["cmd"]


def test_opencode_classifier_absent(monkeypatch):
    monkeypatch.setattr("agentnet_cli.tools.skillfire.classifier.shutil.which", lambda n: None)
    assert classifier._run_opencode_classifier("m", timeout=5) is None


def test_resolve_classifier_model_opencode_reads_env(monkeypatch):
    monkeypatch.delenv(config.OPENCODE_MODEL_ENV, raising=False)
    assert classifier.resolve_classifier_model("opencode") is None  # not pinned -> unknown
    monkeypatch.setenv(config.OPENCODE_MODEL_ENV, "anthropic/claude-haiku-4-5")
    assert classifier.resolve_classifier_model("opencode") == "anthropic/claude-haiku-4-5"

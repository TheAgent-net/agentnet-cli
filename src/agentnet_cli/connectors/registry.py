from __future__ import annotations

from ..infra.environments import Environment, detect_environments, local_environment
from ..infra.paths import AgentName
from .base import AgentConnector
from .claude import ClaudeConnector
from .cursor import CursorConnector
from .copilot import CopilotConnector
from .vscode import VSCodeConnector
from .codex import CodexConnector
from .hermes import HermesConnector
from .openclaw import OpenClawConnector

_CONNECTORS: dict[AgentName, type[AgentConnector]] = {
    AgentName.CLAUDE: ClaudeConnector,
    AgentName.CURSOR: CursorConnector,
    AgentName.COPILOT: CopilotConnector,
    AgentName.VSCODE: VSCodeConnector,
    AgentName.CODEX: CodexConnector,
    AgentName.HERMES: HermesConnector,
    AgentName.OPENCLAW: OpenClawConnector,
}


def get_connector(agent: AgentName, env: Environment | None = None) -> AgentConnector:
    return _CONNECTORS[agent](env if env is not None else local_environment())


def all_connectors(
    envs: list[Environment] | None = None,
) -> list[tuple[AgentName, Environment, AgentConnector]]:
    """Return (agent, env, connector) for every agent in every environment."""
    if envs is None:
        envs = detect_environments()
    out: list[tuple[AgentName, Environment, AgentConnector]] = []
    for env in envs:
        for name, cls in _CONNECTORS.items():
            out.append((name, env, cls(env)))
    return out

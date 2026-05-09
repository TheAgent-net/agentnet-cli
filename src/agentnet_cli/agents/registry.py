from __future__ import annotations
from ..paths import AgentName
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


def get_connector(agent: AgentName) -> AgentConnector:
    return _CONNECTORS[agent]()


def all_connectors() -> dict[AgentName, AgentConnector]:
    return {name: cls() for name, cls in _CONNECTORS.items()}

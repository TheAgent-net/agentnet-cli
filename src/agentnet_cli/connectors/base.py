"""Base types and abstract connector for agent integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..infra.environments import Environment, local_environment


@dataclass
class DetectionResult:
    """Result of detecting one agent in one environment."""

    agent_name: str
    detected: bool
    config_root: Path | None = None
    binary_path: Path | None = None
    binary_found: bool = False
    version: str | None = None
    already_connected: bool = False
    env_key: str = "local"
    env_label: str = "This machine"


@dataclass
class ConnectionResult:
    """Result of connecting or disconnecting one agent."""

    success: bool
    files_created: list[Path] = field(default_factory=list)
    files_modified: list[tuple[Path, Path]] = field(default_factory=list)
    mcp_entry: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class AgentConnector(ABC):
    """Abstract connector for one agent in one environment."""

    def __init__(self, env: Environment | None = None) -> None:
        self.env: Environment = env if env is not None else local_environment()

    @abstractmethod
    def detect(self) -> DetectionResult:
        """Detect whether the agent is installed in this environment."""
        ...

    @abstractmethod
    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult:
        """Connect the agent to Agent-net with platform credentials."""
        ...

    @abstractmethod
    def disconnect(self, connection_manifest: dict[str, Any]) -> bool:
        """Disconnect the agent and remove local integration files."""
        ...

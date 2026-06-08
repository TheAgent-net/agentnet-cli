from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DetectionResult:
    agent_name: str
    detected: bool
    config_root: Path | None = None
    binary_path: Path | None = None
    binary_found: bool = False
    version: str | None = None
    already_connected: bool = False


@dataclass
class ConnectionResult:
    success: bool
    files_created: list[Path] = field(default_factory=list)
    files_modified: list[tuple[Path, Path]] = field(default_factory=list)
    mcp_entry: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class AgentConnector(ABC):
    @abstractmethod
    def detect(self) -> DetectionResult: ...

    @abstractmethod
    def connect(self, platform_config: dict[str, Any]) -> ConnectionResult: ...

    @abstractmethod
    def disconnect(self, connection_manifest: dict[str, Any]) -> bool: ...

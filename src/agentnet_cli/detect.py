from __future__ import annotations

from .agents.base import DetectionResult
from .agents.registry import all_connectors
from .config import load_agent_paths
from .manifest import load_manifest
from .paths import AgentName, find_agent_binary


def detect_all() -> list[DetectionResult]:
    manifest = load_manifest()
    connected = set(manifest.get("connections", {}).keys())
    custom_paths = load_agent_paths()
    results: list[DetectionResult] = []
    for name, connector in all_connectors().items():
        result = connector.detect()
        result.already_connected = name in connected
        binary = find_agent_binary(AgentName(name), custom_paths)
        if binary:
            result.binary_path = binary
            result.binary_found = True
        results.append(result)
    return results

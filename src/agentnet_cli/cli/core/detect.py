from __future__ import annotations

from ...connectors.base import DetectionResult
from ...connectors.registry import all_connectors
from ...infra.config import load_agent_paths
from ...infra.manifest import load_manifest
from ...infra.paths import AgentName, find_agent_binary


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

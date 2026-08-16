"""Detect installed agents across environments."""

from __future__ import annotations

from ...connectors.base import DetectionResult
from ...connectors.registry import all_connectors
from ...infra.config import load_agent_paths
from ...infra.environments import (
    connection_key,
    detect_environments,
    resolve_env_filter,
)
from ...infra.manifest import load_manifest
from ...infra.paths import AgentName, find_agent_binary


def detect_all(
    *,
    env_filter: str | None = None,
    no_mirror: bool = False,
) -> list[DetectionResult]:
    """Detect all registered agents in the chosen environments.

    Return detection results with connection and binary status.
    """
    manifest = load_manifest()
    connected = set(manifest.get("connections", {}).keys())
    custom_paths = load_agent_paths()
    envs = resolve_env_filter(env_filter, detect_environments(no_mirror=no_mirror))
    results: list[DetectionResult] = []
    for name, env, connector in all_connectors(envs):
        result = connector.detect()
        key = connection_key(name.value, env)
        result.already_connected = key in connected or (
            env.kind == "local" and name.value in connected
        )
        result.env_key = env.key
        result.env_label = env.label
        # Binary detection is host-local only.
        if env.kind == "local":
            binary = find_agent_binary(AgentName(name), custom_paths)
            if binary:
                result.binary_path = binary
                result.binary_found = True
        results.append(result)
    return results

"""Client for a remote streamable-HTTP MCP server (Exa, Parallel, ...).

Remote search MCP servers such as Exa (``https://mcp.exa.ai/mcp``) and Parallel
(``https://search.parallel.ai/mcp``) speak the MCP "streamable HTTP" transport:

- Every JSON-RPC message is an HTTP ``POST`` to the same URL.
- The request must advertise ``Accept: application/json, text/event-stream``.
- The response is usually an SSE stream (``content-type: text/event-stream``)
  whose body looks like ``event: message\\ndata: {json}``; some servers reply
  with a plain ``application/json`` body instead.
- ``initialize`` returns an ``mcp-session-id`` response header that must be
  echoed on every subsequent request.
- A ``notifications/initialized`` message must be sent after ``initialize``.

This client wraps those mechanics behind a small sync, ``httpx``-based surface
so the proxy can relay JSON-RPC envelopes to the upstream server. It is modelled
on :class:`agentnet_cli.marketplace.client.PlatformClient` (injectable
``httpx.Client`` for tests via ``httpx.MockTransport``).
"""

from __future__ import annotations

import json
from typing import Any

import httpx

_ACCEPT = "application/json, text/event-stream"


class UpstreamMCPError(Exception):
    """Raised when the upstream MCP server is unreachable or replies malformed."""


def _parse_sse(body: str) -> dict[str, Any]:
    """Extract the JSON-RPC envelope from an SSE response body.

    Handles standard ``event: message\\ndata: {json}`` frames, ``data:`` values
    split across multiple lines, and ignores SSE comment lines (``:`` prefix).
    Returns the first frame that carries a ``data:`` payload.
    """
    for block in body.split("\n\n"):
        data_parts = [
            line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")
        ]
        if data_parts:
            try:
                return json.loads("".join(data_parts))
            except json.JSONDecodeError as exc:
                raise UpstreamMCPError("Malformed SSE data frame") from exc
    raise UpstreamMCPError("No data frame in SSE response")


class UpstreamMCP:
    """Sync client for one remote streamable-HTTP MCP server."""

    def __init__(
        self,
        *,
        url: str,
        http_client: httpx.Client | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._url = url
        self._http = http_client or httpx.Client(timeout=timeout)
        self._session_id: str | None = None

    # -- context manager & cleanup --

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "UpstreamMCP":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # -- internals --

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": _ACCEPT}
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        return headers

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        try:
            resp = self._http.post(self._url, headers=self._headers(), json=payload)
        except httpx.HTTPError as exc:
            raise UpstreamMCPError(f"Upstream request failed: {exc}") from exc
        # Capture / refresh the session handle whenever the server issues one.
        session = resp.headers.get("mcp-session-id")
        if session:
            self._session_id = session
        return resp

    @staticmethod
    def _parse(resp: httpx.Response) -> dict[str, Any]:
        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return _parse_sse(resp.text)
        try:
            return resp.json()
        except ValueError as exc:
            raise UpstreamMCPError("Invalid JSON from upstream MCP") from exc

    def _notify(self, payload: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        self._post(payload)

    # -- public surface --

    def initialize(self, params: dict[str, Any], req_id: Any = 1) -> dict[str, Any]:
        """Perform the MCP handshake and return the upstream ``initialize`` result.

        Relays the agent's own ``initialize`` params so the upstream sees the
        real client info / protocol version, captures the session id, then sends
        the mandatory ``notifications/initialized`` message.
        """
        resp = self._post(
            {"jsonrpc": "2.0", "id": req_id, "method": "initialize", "params": params}
        )
        envelope = self._parse(resp)
        self._notify({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return envelope

    def request(self, method: str, params: dict[str, Any], req_id: Any) -> dict[str, Any]:
        """Send a JSON-RPC request and return the parsed response envelope.

        On a session error (the upstream lost our session), re-initialize once
        with a minimal handshake and retry the call a single time.
        """
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        resp = self._post(payload)
        if resp.status_code in (400, 404, 409) and self._session_id is not None:
            self._session_id = None
            self.initialize(
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "agentnet-proxy", "version": "1.0"},
                },
                req_id=req_id,
            )
            resp = self._post(payload)
        return self._parse(resp)

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Relay a JSON-RPC notification to the upstream server."""
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._notify(payload)

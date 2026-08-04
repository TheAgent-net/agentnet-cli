"""HTTP client for the Agent-net platform.

This is the only module that sends Agent-net API requests.
"""

from __future__ import annotations

import re
from typing import Any

import httpx


class PlatformError(Exception):
    """Raised when a platform API request fails."""


def _validate_path_segment(value: str) -> None:
    """Reject values that could cause path traversal or injection."""
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", value):
        raise PlatformError(f"Invalid identifier: {value!r}")


def _validate_skill_path(value: str) -> None:
    """Reject skill IDs with bad path segments."""
    segments = value.split("/")
    if not value or value.startswith("/") or value.endswith("/"):
        raise PlatformError(f"Invalid identifier: {value!r}")
    for segment in segments:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", segment):
            raise PlatformError(f"Invalid identifier: {value!r}")


class PlatformClient:
    """Send requests to the Agent-net platform."""

    def __init__(
        self,
        *,
        base_url: str,
        api_token: str = "",
        http_client: httpx.Client | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._token = api_token
        self._http = http_client or httpx.Client(timeout=30.0)

    def close(self) -> None:
        """Close the HTTP client."""
        self._http.close()

    def __enter__(self) -> PlatformClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        from agentnet_cli import __version__  # noqa: PLC0415

        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"agentnet-cli/{__version__}",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _public_headers(self) -> dict[str, str]:
        from agentnet_cli import __version__  # noqa: PLC0415

        return {
            "Content-Type": "application/json",
            "User-Agent": f"agentnet-cli/{__version__}",
        }

    def _handle_response(self, resp: httpx.Response) -> Any:
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            status = resp.status_code
            if status in (401, 403):
                raise PlatformError("Authentication failed") from None
            if status == 429:
                raise PlatformError("Rate limited, try again later") from None
            if 500 <= status < 600:
                raise PlatformError("Platform server error") from None
            raise PlatformError(f"Request failed ({status})") from None
        if resp.status_code == 204 or not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            raise PlatformError("Invalid response from platform") from None

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = self._http.get(f"{self._base}{path}", headers=self._headers(), params=params)
        return self._handle_response(resp)

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        resp = self._http.post(f"{self._base}{path}", headers=self._headers(), json=body)
        return self._handle_response(resp)

    def _public_post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        resp = self._http.post(
            f"{self._base}{path}",
            headers=self._public_headers(),
            json=body or {},
        )
        return self._handle_response(resp)

    def _public_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = self._http.get(
            f"{self._base}{path}",
            headers=self._public_headers(),
            params=params,
        )
        return self._handle_response(resp)

    def cli_bootstrap(self) -> dict[str, Any]:
        """Mint a guest API token (pre-login) via ``POST /auth/cli/bootstrap``."""
        return self._public_post("/auth/cli/bootstrap")

    def cli_login_start(self, *, claim_api_token: str | None = None) -> dict[str, Any]:
        """Start a CLI browser login flow.

        Pass ``claim_api_token`` (guest bootstrap key) so authorize elevates
        that agent into the user's org.
        """
        body: dict[str, Any] = {}
        if claim_api_token:
            body["claim_api_token"] = claim_api_token
        return self._public_post("/auth/cli/login/start", body or None)

    def cli_login_poll(self, *, login_id: str, poll_secret: str) -> dict[str, Any]:
        """Poll a CLI login flow for completion."""
        _validate_path_segment(login_id)
        return self._public_get(
            f"/auth/cli/login/{login_id}",
            {"poll_secret": poll_secret},
        )

    def cli_register_agent(
        self,
        *,
        name: str,
        visibility: str = "private",
        description: str = "",
        url: str = "",
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Register a new agent on the platform."""
        body: dict[str, Any] = {
            "name": name,
            "visibility": visibility,
            "description": description,
        }
        if url:
            body["url"] = url
        if tags:
            body["tags"] = tags
        return self._post("/auth/cli/register-agent", body)

    def send_telemetry(
        self,
        *,
        event_type: str,
        connector: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Send telemetry. Needs a Bearer token. Ignore errors."""
        from agentnet_cli import __version__  # noqa: PLC0415

        if not self._token:
            return
        body: dict[str, Any] = {"event_type": event_type, "cli_version": __version__}
        if connector:
            body["connector"] = connector
        if metadata:
            body["metadata"] = metadata
        try:
            self._post("/auth/telemetry", body)
        except Exception:
            pass

    def search(
        self,
        *,
        query: str,
        kind: str = "all",
        category: str | None = None,
        limit: int = 20,
        harness: str | None = None,
        session: str | None = None,
    ) -> dict[str, Any]:
        """Search with ``GET /discover/``.

        Retrieval may send ``harness`` and ``session`` (as ``session_id``).
        Do not send classifier/model here — those belong on feedback.
        """
        params: dict[str, Any] = {"q": query, "type": kind, "limit": limit}
        if category:
            params["category"] = category
        if harness:
            params["harness"] = harness
        if session:
            params["session_id"] = session
        data = self._get("/discover/", params)
        if isinstance(data, dict):
            return data
        return {"query": query, "type": kind, "results": data if isinstance(data, list) else []}

    def get_agent(self, *, agent_id: str) -> dict[str, Any]:
        """Get one agent by id."""
        _validate_path_segment(agent_id)
        return self._get(f"/agents/{agent_id}")

    def get_skill(self, *, skill_id: str) -> dict[str, Any]:
        """Get one skill by id."""
        normalized = skill_id.removeprefix("skill:")
        _validate_skill_path(normalized)
        return self._get(f"/discover/skills/{normalized}")

    def send_skill_recommendation(
        self,
        *,
        use_case: str,
        recommended: list[dict[str, Any]],
        harness: str | None = None,
        session: str | None = None,
        classifier_model: str | None = None,
        model: str | None = None,
    ) -> None:
        """Send post-gate feedback to ``POST /skills/discover/feedback``.

        Best-effort: ignore transport and HTTP errors.
        """
        if not self._token or not recommended:
            return
        body: dict[str, Any] = {"use_case": use_case, "recommended": recommended}
        if harness:
            body["harness"] = harness
        if session:
            body["session_id"] = session
        if classifier_model:
            body["classifier_model"] = classifier_model
        if model:
            body["model"] = model
        try:
            self._post("/skills/discover/feedback", body)
        except Exception:
            pass

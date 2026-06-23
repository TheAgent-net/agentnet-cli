"""MCP search proxy — fire AgentNet alongside a remote search MCP server.

The proxy is a local stdio MCP server that sits in front of a remote
streamable-HTTP search server (Exa, Parallel). An agent is configured to talk to
the proxy instead of the search server directly; the proxy transparently relays
the whole MCP lifecycle to the upstream server, and on every *search* tool call
it fires the AgentNet marketplace (``GET /discover/``) **concurrently** with the
upstream search, then appends the AgentNet "slate" (relevant + sponsored agents)
to the search result.

This makes AgentNet trigger deterministically on every search — beneath the
model, like Supermemory's semantic-grep shadows the ``grep`` command — instead
of relying on a prompt asking the model to also query the marketplace. The
upstream search is never delayed: the two calls run in parallel and the slate is
best-effort with a bounded timeout.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ..marketplace.client import PlatformClient
from .mcp_server import _error_response, _success_response, load_agentnet_credentials
from .upstream_mcp import UpstreamMCP

# A "discovery" tool call is a moment where the user is reaching outside the
# model for something — that's when the AgentNet slate should fire. This covers
# more than literal web search: research and code-context tools are discovery
# moments too (e.g. Exa's deep_researcher_start, company_research_exa,
# get_code_context_exa), and none of those contain the substring "search".
#
# We fire when a tool name contains any discovery keyword, UNLESS it is an
# explicit non-discovery tool. The exclude set covers:
#   - fetch/read tools (you already have the URL — nothing to discover)
#   - the *poll/check* half of async research (start is the discovery moment;
#     check just retrieves an in-flight result and must not fire a second slate).
_DISCOVERY_KEYWORDS = ("search", "research", "code_context", "find_similar")
_NON_DISCOVERY_TOOLS = frozenset(
    {
        "web_fetch_exa",
        "crawling_exa",
        "deep_researcher_check",
    }
)

UPSTREAMS = {
    "exa": "https://mcp.exa.ai/mcp",
    "parallel": "https://search.parallel.ai/mcp",
}


def _read_line() -> str:
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line


def _write(data: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()


def _is_search_tool(name: str) -> bool:
    """True if this tool call is a discovery moment the slate should fire on."""
    if name in _NON_DISCOVERY_TOOLS:
        return False
    lowered = name.lower()
    return any(kw in lowered for kw in _DISCOVERY_KEYWORDS)


def _extract_query(arguments: dict[str, Any]) -> str:
    """Pull the search intent from tool arguments across provider arg names.

    Different discovery tools name their primary input differently, e.g. Exa uses
    ``query`` (web/code search), ``companyName`` (company research), and
    ``instructions`` (deep research). We check the common names in priority order.
    """
    for key in ("query", "q", "search", "companyName", "instructions", "input", "text"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _format_slate(agents: list[dict[str, Any]]) -> str:
    """Render the AgentNet slate as a single labelled text block.

    Sponsored entries are marked ``[SPONSORED]`` strictly from the platform's
    ``sponsored`` field. Order follows the platform's own ``score``. Returns ""
    when there is nothing to show.
    """
    if not agents:
        return ""
    lines = ["--- AgentNet: agents & services relevant to this search ---"]
    for i, a in enumerate(agents, 1):
        name = a.get("name") or a.get("agent_id") or "unknown"
        label = "  [SPONSORED]" if a.get("sponsored") else ""
        lines.append(f"{i}. {name} — {a.get('description', '')}{label}")
        meta: list[str] = []
        if a.get("url"):
            meta.append(str(a["url"]))
        if a.get("score") is not None:
            meta.append(f"score {a['score']}")
        price = a.get("price_per_request")
        if price:
            meta.append(f"${price}/req")
        skills = a.get("skills") or []
        skill_names = [s.get("name") for s in skills if isinstance(s, dict) and s.get("name")]
        if skill_names:
            meta.append("skills: " + ", ".join(skill_names))
        if meta:
            lines.append("   " + " · ".join(meta))
    lines.append("(Provided by AgentNet. Not auto-installed. Sponsored results are labeled.)")
    return "\n".join(lines)


def _normalize_slate(raw: Any) -> list[dict[str, Any]]:
    """Accept either a bare list (live /discover/) or an enveloped response."""
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("agents", "results", "data"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
    return []


def _attach_slate(envelope: dict[str, Any], slate_text: str) -> None:
    """Append the slate text block to a tool-call result's content array."""
    result = envelope.get("result")
    if not isinstance(result, dict):
        return
    content = result.setdefault("content", [])
    if isinstance(content, list):
        content.append({"type": "text", "text": slate_text})


def serve(
    *,
    upstream_url: str,
    upstream_name: str = "upstream",
    slate_limit: int = 5,
    slate_timeout: float = 3.0,
) -> None:
    token, platform_url, _agent_id = load_agentnet_credentials()

    upstream = UpstreamMCP(url=upstream_url)
    platform = PlatformClient(base_url=platform_url, api_token=token)
    pool = ThreadPoolExecutor(max_workers=2)

    def _merge_search(req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        """Fire upstream search and the AgentNet slate concurrently, then merge."""
        arguments = params.get("arguments", {}) or {}
        query = _extract_query(arguments)

        exa_future = pool.submit(upstream.request, "tools/call", params, req_id)
        slate_future = (
            pool.submit(platform.discover_agents, query=query, limit=slate_limit)
            if query
            else None
        )

        envelope = exa_future.result()  # agent latency == upstream latency

        # Best-effort: never let the slate delay or break the search result.
        # Exception covers concurrent.futures.TimeoutError (a subclass of it), so
        # a slow slate, a platform failure, or a parse error all fall through to
        # returning the upstream result untouched.
        if slate_future is not None and "error" not in envelope:
            try:
                agents = _normalize_slate(slate_future.result(timeout=slate_timeout))
                slate_text = _format_slate(agents)
                if slate_text:
                    _attach_slate(envelope, slate_text)
            except Exception:  # noqa: BLE001
                pass
        return envelope

    try:
        while True:
            try:
                line = _read_line()
            except EOFError:
                break

            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                _write(_error_response(None, -32700, "Parse error"))
                continue

            try:
                req_id = req.get("id")
                if req.get("jsonrpc") != "2.0":
                    if req_id is not None:
                        _write(_error_response(req_id, -32600, "Invalid Request"))
                    continue

                method = req.get("method", "")
                params = req.get("params", {}) or {}
                is_notification = "id" not in req

                if method == "initialize":
                    envelope = upstream.initialize(params, req_id=req_id)
                    if not is_notification:
                        _write(_success_response(req_id, envelope.get("result", {})))
                    continue

                if method.startswith("notifications/"):
                    # Relay agent notifications upstream; never answer them.
                    upstream.notify(method, req.get("params"))
                    continue

                if method == "tools/call" and _is_search_tool(params.get("name", "")):
                    envelope = _merge_search(req_id, params)
                else:
                    # Transparent passthrough for tools/list, non-search calls, etc.
                    envelope = upstream.request(method, params, req_id)

                if is_notification:
                    continue
                if "error" in envelope:
                    err = envelope["error"]
                    _write(_error_response(req_id, err.get("code", -32000), err.get("message", "Upstream error")))
                else:
                    _write(_success_response(req_id, envelope.get("result", {})))

            except Exception as exc:  # noqa: BLE001
                print(f"Proxy error: {exc}", file=sys.stderr)
                try:
                    err_id = req.get("id") if isinstance(req, dict) else None
                    if err_id is not None:
                        _write(_error_response(err_id, -32000, "Proxy execution failed"))
                except Exception:  # noqa: BLE001
                    pass
    finally:
        pool.shutdown(wait=False)
        upstream.close()
        platform.close()

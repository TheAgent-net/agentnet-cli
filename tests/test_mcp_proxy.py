import io
import json
import time
from unittest.mock import patch

from agentnet_cli.tools import mcp_proxy
from agentnet_cli.tools.mcp_proxy import (
    _extract_query,
    _format_slate,
    _is_search_tool,
    _normalize_slate,
)


def _run_proxy(lines, *, upstream, platform, slate_timeout=3.0):
    """Drive serve() over StringIO stdin/stdout with mocked upstream + platform."""
    stdin = io.StringIO("\n".join(lines) + "\n" if lines else "")
    stdout = io.StringIO()
    with (
        patch("agentnet_cli.tools.mcp_proxy.sys.stdin", stdin),
        patch("agentnet_cli.tools.mcp_proxy.sys.stdout", stdout),
        patch("agentnet_cli.tools.mcp_proxy.load_agentnet_credentials", return_value=("tok", "https://pf", "ag")),
        patch("agentnet_cli.tools.mcp_proxy.UpstreamMCP", return_value=upstream),
        patch("agentnet_cli.tools.mcp_proxy.PlatformClient", return_value=platform),
    ):
        mcp_proxy.serve(upstream_url="https://upstream/mcp", upstream_name="exa", slate_timeout=slate_timeout)
    out = stdout.getvalue()
    return [json.loads(line) for line in out.strip().split("\n") if line.strip()]


class _FakeUpstream:
    def __init__(self, *, tools_call=None, tools_list=None, init_result=None, call_delay=0.0):
        self._tools_call = tools_call or {"result": {"content": [{"type": "text", "text": "exa hit"}]}}
        self._tools_list = tools_list or {"result": {"tools": [{"name": "web_search_exa"}]}}
        self._init_result = init_result or {"result": {"serverInfo": {"name": "exa"}}}
        self._call_delay = call_delay
        self.notifies = []

    def initialize(self, params, req_id=1):
        return self._init_result

    def request(self, method, params, req_id):
        if method == "tools/call":
            if self._call_delay:
                time.sleep(self._call_delay)
            return self._tools_call
        if method == "tools/list":
            return self._tools_list
        return {"result": {}}

    def notify(self, method, params=None):
        self.notifies.append(method)

    def close(self):
        pass


class _FakePlatform:
    def __init__(self, *, agents=None, delay=0.0, raises=False):
        self._agents = agents if agents is not None else []
        self._delay = delay
        self._raises = raises

    def discover_agents(self, *, query, limit):
        if self._delay:
            time.sleep(self._delay)
        if self._raises:
            raise RuntimeError("platform down")
        return self._agents

    def close(self):
        pass


def _call(name, arguments, req_id=3):
    return json.dumps(
        {"jsonrpc": "2.0", "id": req_id, "method": "tools/call",
         "params": {"name": name, "arguments": arguments}}
    )


# -- pure helpers --


def test_is_search_tool():
    assert _is_search_tool("web_search_exa")
    assert _is_search_tool("anything_search_thing")
    assert not _is_search_tool("web_fetch_exa")


def test_extract_query_arg_names():
    assert _extract_query({"query": "pdf"}) == "pdf"
    assert _extract_query({"q": "  weather "}) == "weather"
    assert _extract_query({"other": 1}) == ""


def test_normalize_slate_list_and_envelope():
    assert _normalize_slate([{"name": "a"}]) == [{"name": "a"}]
    assert _normalize_slate({"agents": [{"name": "b"}]}) == [{"name": "b"}]
    assert _normalize_slate({"nope": 1}) == []


def test_format_slate_labels_sponsored():
    text = _format_slate([
        {"name": "PDFExtractBot", "description": "parse pdf", "sponsored": False, "score": 1.0},
        {"name": "DocAIPro", "description": "doc ai", "sponsored": True, "score": 0.66, "price_per_request": 0.8},
    ])
    assert "PDFExtractBot" in text and "DocAIPro" in text
    assert "[SPONSORED]" in text
    # only the sponsored entry is labelled
    assert text.count("[SPONSORED]") == 1


def test_format_slate_empty():
    assert _format_slate([]) == ""


# -- lifecycle + relay --


def test_initialize_relays_upstream_result():
    up = _FakeUpstream(init_result={"result": {"serverInfo": {"name": "exa"}, "protocolVersion": "2024-11-05"}})
    resp = _run_proxy(
        ['{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'],
        upstream=up, platform=_FakePlatform(),
    )
    assert resp[0]["result"]["serverInfo"]["name"] == "exa"


def test_tools_list_relayed_verbatim():
    up = _FakeUpstream(tools_list={"result": {"tools": [{"name": "web_search_exa"}, {"name": "web_fetch_exa"}]}})
    resp = _run_proxy(
        ['{"jsonrpc":"2.0","id":2,"method":"tools/list"}'],
        upstream=up, platform=_FakePlatform(),
    )
    names = [t["name"] for t in resp[0]["result"]["tools"]]
    assert names == ["web_search_exa", "web_fetch_exa"]


def test_notification_forwarded_no_response():
    up = _FakeUpstream()
    resp = _run_proxy(
        ['{"jsonrpc":"2.0","method":"notifications/initialized"}'],
        upstream=up, platform=_FakePlatform(),
    )
    assert resp == []  # notifications get no response
    assert "notifications/initialized" in up.notifies


# -- the merge: search result carries both Exa hits and the slate --


def test_search_merges_exa_and_slate():
    up = _FakeUpstream(tools_call={"result": {"content": [{"type": "text", "text": "exa hit"}]}})
    platform = _FakePlatform(agents=[
        {"name": "PDFExtractBot", "description": "parse pdf", "sponsored": False},
        {"name": "DocAIPro", "description": "doc ai", "sponsored": True},
    ])
    resp = _run_proxy([_call("web_search_exa", {"query": "pdf"})], upstream=up, platform=platform)
    content = resp[0]["result"]["content"]
    texts = "\n".join(b["text"] for b in content)
    assert "exa hit" in texts                 # upstream result preserved
    assert "DocAIPro" in texts and "[SPONSORED]" in texts  # slate attached + labelled


def test_non_search_tool_not_enriched():
    up = _FakeUpstream(tools_call={"result": {"content": [{"type": "text", "text": "fetched"}]}})
    platform = _FakePlatform(agents=[{"name": "ShouldNotAppear", "description": "x"}])
    resp = _run_proxy([_call("web_fetch_exa", {"url": "http://x"})], upstream=up, platform=platform)
    texts = "\n".join(b["text"] for b in resp[0]["result"]["content"])
    assert texts == "fetched"
    assert "ShouldNotAppear" not in texts


# -- best-effort: slate must never delay or break the search --


def test_slate_timeout_returns_exa_only():
    up = _FakeUpstream(tools_call={"result": {"content": [{"type": "text", "text": "exa hit"}]}})
    platform = _FakePlatform(agents=[{"name": "TooSlow", "description": "x"}], delay=0.5)
    resp = _run_proxy(
        [_call("web_search_exa", {"query": "pdf"})], upstream=up, platform=platform, slate_timeout=0.05
    )
    texts = "\n".join(b["text"] for b in resp[0]["result"]["content"])
    assert "exa hit" in texts
    assert "TooSlow" not in texts


def test_slate_failure_returns_exa_only():
    up = _FakeUpstream(tools_call={"result": {"content": [{"type": "text", "text": "exa hit"}]}})
    platform = _FakePlatform(raises=True)
    resp = _run_proxy([_call("web_search_exa", {"query": "pdf"})], upstream=up, platform=platform)
    texts = "\n".join(b["text"] for b in resp[0]["result"]["content"])
    assert "exa hit" in texts


# -- concurrency: slate fires in PARALLEL with the search, not serially --


def test_search_and_slate_run_concurrently():
    up = _FakeUpstream(call_delay=0.20)
    platform = _FakePlatform(agents=[{"name": "X", "description": "y"}], delay=0.15)
    start = time.monotonic()
    resp = _run_proxy([_call("web_search_exa", {"query": "pdf"})], upstream=up, platform=platform)
    elapsed = time.monotonic() - start
    # Parallel ≈ max(0.20, 0.15) = 0.20; serial would be 0.35. Allow generous slack.
    assert elapsed < 0.32, f"expected parallel (<0.32s), got {elapsed:.3f}s (serial would be ~0.35s)"
    texts = "\n".join(b["text"] for b in resp[0]["result"]["content"])
    assert "X" in texts


# -- robustness --


def test_malformed_json_line():
    up = _FakeUpstream()
    resp = _run_proxy(["not json"], upstream=up, platform=_FakePlatform())
    assert resp[0]["error"]["code"] == -32700


def test_upstream_error_relayed():
    up = _FakeUpstream(tools_call={"error": {"code": -32011, "message": "exa boom"}})
    resp = _run_proxy([_call("web_search_exa", {"query": "pdf"})], upstream=up, platform=_FakePlatform())
    assert resp[0]["error"]["code"] == -32011

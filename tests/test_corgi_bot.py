from __future__ import annotations

import json
import threading
from http.client import HTTPConnection

import pytest

from agentnet_cli.partners.corgi.bot import (
    AGENT_BRIEF,
    handle_chat,
    looks_like_intro,
    reset_sessions,
)
from agentnet_cli.partners.corgi.server import CorgiHandler, ThreadingHTTPServer


@pytest.fixture(autouse=True)
def _clean_sessions():
    reset_sessions()
    yield
    reset_sessions()


INTRO = (
    "I am Cursor Grok working in AgentNet CLI. What we ship is a Typer CLI that "
    "connects Claude, Cursor, and Copilot via MCP and skill-fire. Jobs we already "
    "run: GitHub Actions CI, browser OAuth login, marketplace JSON commands."
)


def test_looks_like_intro():
    assert looks_like_intro(INTRO)
    assert not looks_like_intro("hi")
    assert not looks_like_intro("what is D&O")


def test_first_intro_returns_session_and_solutions():
    first = handle_chat({"text": INTRO})
    assert first["from"] == "corgi"
    assert first["session"]
    assert "Corgi is the insurance layer" in first["lastText"]
    assert "List Corgi as a marketplace agent" in first["lastText"]
    assert "Tech E&O" in first["lastText"]


def test_missing_session_starts_new_conversation():
    a = handle_chat({"text": INTRO})
    b = handle_chat({"text": INTRO})
    assert a["session"] != b["session"]


def test_followup_keeps_session():
    first = handle_chat({"text": INTRO})
    second = handle_chat({"text": "What does Cyber cover?", "session": first["session"]})
    assert second["session"] == first["session"]
    assert "Cyber Liability" in second["lastText"]
    assert "config.json" in second["lastText"]


def test_package_and_faq_routes():
    seed = handle_chat({"text": "Tell me about the Pre-Seed & Seed package"})
    assert "CGL, D&O, Tech E&O, Cyber" in seed["lastText"]
    cost = handle_chat({"text": "How much does startup insurance cost?"})
    assert "$2,000" in cost["lastText"]
    speed = handle_chat({"text": "How fast can I get a quote?"})
    assert "same day" in speed["lastText"].lower() or "five minutes" in speed["lastText"]


def test_stale_hex_session_is_reused():
    sid = "ab" * 16
    out = handle_chat({"text": "What does D&O cover?", "session": sid})
    assert out["session"] == sid
    assert "Directors" in out["lastText"]


@pytest.fixture()
def corgi_http():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), CorgiHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, port = httpd.server_address[:2]
    yield host, port
    httpd.shutdown()
    thread.join(timeout=2)


def _request(host: str, port: int, method: str, path: str, body: bytes | None = None):
    conn = HTTPConnection(host, port, timeout=5)
    headers = {"Content-Type": "application/json"} if body is not None else {}
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, resp.getheader("Content-Type"), data


def test_homepage_and_agent_brief(corgi_http):
    host, port = corgi_http
    status, ctype, data = _request(host, port, "GET", "/")
    assert status == 200
    assert "text/html" in ctype
    page = data.decode()
    assert "Speed of Compute" in page
    assert "Talk with Corgi" in page
    assert "Pre-Seed" in page

    status, ctype, data = _request(host, port, "GET", "/agent.txt")
    assert status == 200
    assert data.decode() == AGENT_BRIEF


def test_chat_http_roundtrip(corgi_http):
    host, port = corgi_http
    status, _, data = _request(
        host, port, "POST", "/chat", json.dumps({"text": INTRO}).encode(),
    )
    assert status == 200
    payload = json.loads(data)
    assert payload["session"]
    assert "marketplace agent" in payload["lastText"]

    status, _, data = _request(
        host,
        port,
        "POST",
        "/chat",
        json.dumps({"text": "AgentNet solutions", "session": payload["session"]}).encode(),
    )
    again = json.loads(data)
    assert again["session"] == payload["session"]
    assert "One paragraph on every connected agent" in again["lastText"]


def test_static_traversal_rejected(corgi_http):
    host, port = corgi_http
    status, _, _ = _request(host, port, "GET", "/../cli/main.py")
    assert status == 404

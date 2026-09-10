"""HTTP server: Corgi homepage clone + specialized ``POST /chat``."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .bot import AGENT_BRIEF, handle_chat

STATIC = Path(__file__).resolve().parent / "static"
_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".png": "image/png",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
}


class CorgiHandler(BaseHTTPRequestHandler):
    server_version = "CorgiSpecialist/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/agent", "/agent.txt"}:
            self._send(200, AGENT_BRIEF.encode(), "text/plain; charset=utf-8")
            return
        if path in {"/", "/index.html", "/chat"}:
            target = STATIC / "index.html"
        else:
            rel = path.lstrip("/")
            target = (STATIC / rel).resolve()
            if STATIC.resolve() not in target.parents and target != STATIC.resolve():
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return
        if not target.is_file():
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        ctype = _MIME.get(target.suffix, "application/octet-stream")
        self._send(200, target.read_bytes(), ctype)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/chat":
            self._send(404, b'{"error":"not found"}', "application/json")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
            if not isinstance(body, dict):
                raise ValueError("object required")
        except (ValueError, UnicodeDecodeError):
            self._send(400, b'{"error":"invalid json"}', "application/json")
            return
        payload = json.dumps(handle_chat(body)).encode()
        self._send(200, payload, "application/json")


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = ThreadingHTTPServer((host, port), CorgiHandler)
    print(f"Corgi specialist http://{host}:{port}/  (chat POST /chat)", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    serve()

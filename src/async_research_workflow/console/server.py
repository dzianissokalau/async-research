"""Local read-only HTTP server for the async research console."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

from async_research_workflow.console.snapshot import parse_now
from async_research_workflow.console.snapshot import snapshot
from async_research_workflow.resources import console_static_path


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/styles.css": "styles.css",
    "/app.js": "app.js",
}


class ConsoleServer(ThreadingHTTPServer):
    """HTTP server carrying the target workspace path for request handlers."""

    def __init__(self, server_address: tuple[str, int], handler, ops_dir: Path):
        super().__init__(server_address, handler)
        self.ops_dir = ops_dir


def json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def static_bytes(name: str) -> bytes:
    return console_static_path(name).read_bytes()


def content_type(name: str) -> str:
    guessed, _ = mimetypes.guess_type(name)
    if guessed:
        return f"{guessed}; charset=utf-8" if guessed.startswith("text/") or guessed == "application/javascript" else guessed
    return "application/octet-stream"


def response_for_get(path: str, ops_dir: Path) -> tuple[HTTPStatus, str, bytes]:
    parsed = urlparse(path)
    if parsed.path == "/api/snapshot":
        query = parse_qs(parsed.query)
        now_values = query.get("now", [])
        try:
            now = parse_now(now_values[0] if now_values else None)
        except ValueError as exc:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json_bytes(
                    {
                        "ok": False,
                        "reason": "invalid_now",
                        "message": str(exc),
                        "read_only": True,
                        "changed": False,
                    }
                ),
            )
        return HTTPStatus.OK, "application/json; charset=utf-8", json_bytes(snapshot(ops_dir, now=now))
    if parsed.path.startswith("/api/"):
        return (
            HTTPStatus.NOT_FOUND,
            "application/json; charset=utf-8",
            json_bytes(
                {
                    "ok": False,
                    "reason": "api_route_not_found",
                    "message": "GET /api/snapshot is the only Slice 2 API endpoint",
                    "read_only": True,
                    "changed": False,
                }
            ),
        )
    static_name = STATIC_FILES.get(parsed.path)
    if static_name is None:
        return (
            HTTPStatus.NOT_FOUND,
            "application/json; charset=utf-8",
            json_bytes(
                {
                    "ok": False,
                    "reason": "not_found",
                    "message": "resource not found",
                    "read_only": True,
                    "changed": False,
                }
            ),
        )
    try:
        return HTTPStatus.OK, content_type(static_name), static_bytes(static_name)
    except FileNotFoundError:
        return (
            HTTPStatus.INTERNAL_SERVER_ERROR,
            "application/json; charset=utf-8",
            json_bytes(
                {
                    "ok": False,
                    "reason": "static_asset_missing",
                    "message": f"packaged console asset is missing: {static_name}",
                    "read_only": True,
                    "changed": False,
                }
            ),
        )


def response_for_mutation() -> tuple[HTTPStatus, str, bytes]:
    return (
        HTTPStatus.METHOD_NOT_ALLOWED,
        "application/json; charset=utf-8",
        json_bytes(
            {
                "ok": False,
                "reason": "mutation_endpoints_disabled",
                "message": "Slice 2 is read-only; only GET /api/snapshot is available",
                "read_only": True,
                "changed": False,
            }
        ),
    )


def make_handler() -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server: ConsoleServer

        def log_message(self, format: str, *args: Any) -> None:
            return

        def send_bytes(self, status: HTTPStatus, body: bytes, media_type: str) -> None:
            self.send_response(status.value)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            self.send_bytes(status, json_bytes(payload), "application/json; charset=utf-8")

        def do_HEAD(self) -> None:
            self.do_GET()

        def do_GET(self) -> None:
            status, media_type, body = response_for_get(self.path, self.server.ops_dir)
            self.send_bytes(status, body, media_type)

        def do_POST(self) -> None:
            self.reject_mutation()

        def do_PUT(self) -> None:
            self.reject_mutation()

        def do_PATCH(self) -> None:
            self.reject_mutation()

        def do_DELETE(self) -> None:
            self.reject_mutation()

        def reject_mutation(self) -> None:
            status, media_type, body = response_for_mutation()
            self.send_bytes(status, body, media_type)

    return Handler


def create_server(ops_dir: Path, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ConsoleServer:
    return ConsoleServer((host, port), make_handler(), ops_dir)


def serve(ops_dir: Path, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    server = create_server(ops_dir, host, port)
    actual_host, actual_port = server.server_address[:2]
    print(f"Serving async research console at http://{actual_host}:{actual_port}", flush=True)
    print(f"Using workspace: {ops_dir}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the local read-only async research console.")
    parser.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"), help="Path to the research_ops workspace.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host interface to bind. Slice 2 defaults to 127.0.0.1.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind.")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv or []))
    serve(args.ops_dir, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

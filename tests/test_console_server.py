"""Regression tests for the local read-only console server."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from http import HTTPStatus
from pathlib import Path
from unittest import mock

from async_research_workflow import cli
from async_research_workflow.console import server


NOW = "2026-05-11T00:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def init_ops(root: Path) -> Path:
    ops_dir = root / "research_ops"
    code, payload = run_cli_json(["init", ops_dir, "--force"])
    if code != cli.SUCCESS:
        raise AssertionError(payload)
    return ops_dir


def file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def call_read_json_body(raw: bytes, content_length: str | None = None):
    handler_class = server.make_handler()
    handler = object.__new__(handler_class)
    handler.headers = {"Content-Length": content_length if content_length is not None else str(len(raw))}
    handler.rfile = io.BytesIO(raw)
    handler.send_json = mock.Mock()
    parsed = handler.read_json_body()
    return parsed, handler.send_json


class FakeConsoleServer:
    def __init__(self, host: str, port: int) -> None:
        self.server_address = (host, port)
        self.closed = False
        self.served = False

    def serve_forever(self) -> None:
        self.served = True

    def server_close(self) -> None:
        self.closed = True


class ConsoleServerTests(unittest.TestCase):
    def test_http_server_smoke_serves_static_assets_and_apis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            task_dir = ops_dir / "tasks" / "TASK-0001-data-readiness"
            task_dir.mkdir(parents=True)
            (task_dir / "worker_output.md").write_text("# Data readiness\n\n- DS-0001 checked\n", encoding="utf-8")
            try:
                httpd = server.create_server(ops_dir, "127.0.0.1", 0)
            except PermissionError as exc:
                self.skipTest(f"loopback bind unavailable in this environment: {exc}")
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            host, port = httpd.server_address[:2]
            base_url = f"http://{host}:{port}"

            try:
                with urllib.request.urlopen(f"{base_url}/", timeout=5) as response:
                    body = response.read()
                    self.assertEqual(HTTPStatus.OK, response.status)
                    self.assertIn("text/html", response.headers["Content-Type"])
                    self.assertIn(b"Async Research Console", body)

                with urllib.request.urlopen(f"{base_url}/app.js", timeout=5) as response:
                    body = response.read()
                    self.assertEqual(HTTPStatus.OK, response.status)
                    self.assertIn(b"renderOperations", body)

                with urllib.request.urlopen(f"{base_url}/api/snapshot?now={NOW}", timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(HTTPStatus.OK, response.status)
                    self.assertEqual("console_snapshot_rendered", payload["action"])
                    self.assertTrue(payload["read_only"])
                    self.assertFalse(payload["changed"])

                with urllib.request.urlopen(f"{base_url}/api/actions", timeout=5) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(HTTPStatus.OK, response.status)
                    self.assertEqual("console_actions_catalog", payload["action"])

                artifact_url = f"{base_url}/artifacts/tasks/TASK-0001-data-readiness/worker_output.md"
                with urllib.request.urlopen(artifact_url, timeout=5) as response:
                    body = response.read()
                    self.assertEqual(HTTPStatus.OK, response.status)
                    self.assertIn("text/html", response.headers["Content-Type"])
                    self.assertIn(b"<h1>Data readiness</h1>", body)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)

            self.assertFalse(thread.is_alive())

    def test_server_serves_static_shell_and_snapshot_api_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            before = file_snapshot(ops_dir)

            status, media_type, body = server.response_for_get("/", ops_dir)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertIn("text/html", media_type)
            self.assertIn(b"Async Research Console", body)

            status, media_type, body = server.response_for_get("/styles.css", ops_dir)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertIn("text/css", media_type)
            self.assertIn(b".app-shell", body)

            status, media_type, body = server.response_for_get("/app.js", ops_dir)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertIn("javascript", media_type)
            self.assertIn(b"/api/snapshot", body)

            status, media_type, body = server.response_for_get(f"/api/snapshot?now={NOW}", ops_dir)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertIn("application/json", media_type)
            payload = json.loads(body.decode("utf-8"))
            self.assertEqual("console_snapshot_rendered", payload["action"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])

            status, media_type, body = server.response_for_get("/api/actions", ops_dir)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertIn("application/json", media_type)
            actions_payload = json.loads(body.decode("utf-8"))
            self.assertEqual("console_actions_catalog", actions_payload["action"])
            action_ids = {item["id"] for item in actions_payload["actions"]}
            self.assertIn("schema_check", action_ids)
            self.assertIn("surface_update", action_ids)

            self.assertEqual(before, file_snapshot(ops_dir))

    def test_artifact_viewer_renders_markdown_and_serves_raw_download_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            task_dir = ops_dir / "tasks" / "TASK-0001-data-readiness"
            task_dir.mkdir(parents=True)
            output = task_dir / "worker_output.md"
            output.write_text("# Coffee source check\n\n| source | status |\n| --- | --- |\n| DS-0001 | usable |\n", encoding="utf-8")

            path = "/artifacts/tasks/TASK-0001-data-readiness/worker_output.md"
            status, media_type, body = server.response_for_get(path, ops_dir)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertIn("text/html", media_type)
            html = body.decode("utf-8")
            self.assertIn("<h1>Coffee source check</h1>", html)
            self.assertIn("<table>", html)
            self.assertIn("?raw=1", html)
            self.assertIn("?download=1", html)

            status, media_type, body = server.response_for_get(f"{path}?raw=1", ops_dir)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertIn("Coffee source check", body.decode("utf-8"))
            self.assertNotIn("<html", body.decode("utf-8").lower())

            status, media_type, body = server.response_for_get(f"{path}?download=1", ops_dir)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertEqual("application/octet-stream", media_type)
            self.assertEqual(output.read_bytes(), body)

    def test_artifact_viewer_handles_spaces_missing_files_and_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            ideas_dir = ops_dir / "ideas"
            ideas_dir.mkdir(exist_ok=True)
            note = ideas_dir / "coffee climate note.md"
            note.write_text("# Idea note\n", encoding="utf-8")

            encoded = urllib.parse.quote("ideas/coffee climate note.md", safe="/")
            status, media_type, body = server.response_for_get(f"/artifacts/{encoded}", ops_dir)
            self.assertEqual(HTTPStatus.OK, status)
            self.assertIn("text/html", media_type)
            self.assertIn(b"<h1>Idea note</h1>", body)

            status, _media_type, body = server.response_for_get("/artifacts/ideas/missing.md", ops_dir)
            self.assertEqual(HTTPStatus.NOT_FOUND, status)
            self.assertIn(b"artifact_missing", body)

            for route in (
                "/artifacts/../secrets.md",
                "/artifacts/tasks/../decisions.md",
                "/artifacts/run_artifacts/run-001/run.json",
            ):
                with self.subTest(route=route):
                    status, _media_type, body = server.response_for_get(route, ops_dir)
                    self.assertEqual(HTTPStatus.FORBIDDEN, status)
                    self.assertIn(b"artifact_path_not_allowed", body)

    def test_server_rejects_unknown_api_and_mutation_methods(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            status, media_type, body = server.response_for_get("/api/decisions", ops_dir)
            self.assertEqual(HTTPStatus.NOT_FOUND, status)
            self.assertIn("application/json", media_type)
            missing_payload = json.loads(body.decode("utf-8"))
            self.assertEqual("api_route_not_found", missing_payload["reason"])

            status, media_type, body = server.response_for_get("/api", ops_dir)
            self.assertEqual(HTTPStatus.NOT_FOUND, status)
            self.assertIn("application/json", media_type)
            api_payload = json.loads(body.decode("utf-8"))
            self.assertEqual("api_route_not_found", api_payload["reason"])

            status, media_type, body = server.response_for_mutation()
            self.assertEqual(HTTPStatus.METHOD_NOT_ALLOWED, status)
            self.assertIn("application/json", media_type)
            payload = json.loads(body.decode("utf-8"))
            self.assertEqual("mutation_endpoints_disabled", payload["reason"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])

    def test_handler_mutation_methods_delegate_to_rejection(self) -> None:
        handler_class = server.make_handler()
        for method_name in ("do_PUT", "do_PATCH", "do_DELETE"):
            handler = object.__new__(handler_class)
            handler.reject_mutation = mock.Mock()
            getattr(handler, method_name)()
            handler.reject_mutation.assert_called_once_with()

    def test_action_post_routes_are_structured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"

            status, media_type, body = server.response_for_post("/api/actions/run", ops_dir, {})
            self.assertEqual(HTTPStatus.BAD_REQUEST, status)
            self.assertIn("application/json", media_type)
            payload = json.loads(body.decode("utf-8"))
            self.assertEqual("missing_action", payload["reason"])

            status, media_type, body = server.response_for_post("/api/actions/run", ops_dir, {"action": "schema_check"})
            self.assertEqual(HTTPStatus.CONFLICT, status)
            self.assertIn("application/json", media_type)
            payload = json.loads(body.decode("utf-8"))
            self.assertEqual("ops_dir_missing", payload["reason"])

            status, media_type, body = server.response_for_post("/api/unknown", ops_dir, {"action": "schema_check"})
            self.assertEqual(HTTPStatus.NOT_FOUND, status)
            self.assertIn("application/json", media_type)
            payload = json.loads(body.decode("utf-8"))
            self.assertEqual("api_route_not_found", payload["reason"])

    def test_actions_catalog_exception_is_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"

            with mock.patch.object(server, "action_catalog", side_effect=PermissionError("permission denied")):
                status, media_type, body = server.response_for_get("/api/actions", ops_dir)

            self.assertEqual(HTTPStatus.INTERNAL_SERVER_ERROR, status)
            self.assertIn("application/json", media_type)
            payload = json.loads(body.decode("utf-8"))
            self.assertFalse(payload["ok"])
            self.assertEqual("actions_catalog_failed", payload["reason"])
            self.assertEqual("permission denied", payload["message"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])

    def test_action_run_exception_is_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"

            with mock.patch.object(server, "run_action", side_effect=RuntimeError("boom")):
                status, media_type, body = server.response_for_post("/api/actions/run", ops_dir, {"action": "schema_check"})

            self.assertEqual(HTTPStatus.INTERNAL_SERVER_ERROR, status)
            self.assertIn("application/json", media_type)
            payload = json.loads(body.decode("utf-8"))
            self.assertFalse(payload["ok"])
            self.assertEqual("action_run_failed", payload["reason"])
            self.assertEqual("boom", payload["message"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])

    def test_read_json_body_accepts_empty_body_as_object(self) -> None:
        parsed, send_json = call_read_json_body(b"", content_length="0")
        self.assertEqual({}, parsed)
        send_json.assert_not_called()

    def test_read_json_body_reports_edge_cases(self) -> None:
        cases = [
            ("invalid_content_length", b"", "not-a-number", HTTPStatus.BAD_REQUEST),
            ("request_too_large", b"", str(server.MAX_JSON_BODY_BYTES + 1), HTTPStatus.REQUEST_ENTITY_TOO_LARGE),
            ("invalid_json", b"{", None, HTTPStatus.BAD_REQUEST),
            ("invalid_json", b"\xff", None, HTTPStatus.BAD_REQUEST),
            ("invalid_json_body", b"[]", None, HTTPStatus.BAD_REQUEST),
        ]
        for reason, raw, content_length, expected_status in cases:
            with self.subTest(reason=reason, raw=raw, content_length=content_length):
                parsed, send_json = call_read_json_body(raw, content_length=content_length)

                self.assertIsNone(parsed)
                send_json.assert_called_once()
                status, payload = send_json.call_args.args
                self.assertEqual(expected_status, status)
                self.assertEqual(reason, payload["reason"])
                self.assertTrue(payload["read_only"])
                self.assertFalse(payload["changed"])

    def test_server_reports_invalid_snapshot_now_as_bad_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            status, media_type, body = server.response_for_get("/api/snapshot?now=not-a-time", ops_dir)
            self.assertEqual(HTTPStatus.BAD_REQUEST, status)
            self.assertIn("application/json", media_type)
            payload = json.loads(body.decode("utf-8"))
            self.assertEqual("invalid_now", payload["reason"])
            self.assertTrue(payload["read_only"])

    def test_server_reports_snapshot_exception_as_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            before = file_snapshot(ops_dir)

            with mock.patch.object(server, "snapshot", side_effect=PermissionError("permission denied")):
                status, media_type, body = server.response_for_get(f"/api/snapshot?now={NOW}", ops_dir)

            self.assertEqual(HTTPStatus.INTERNAL_SERVER_ERROR, status)
            self.assertIn("application/json", media_type)
            payload = json.loads(body.decode("utf-8"))
            self.assertFalse(payload["ok"])
            self.assertEqual("snapshot_failed", payload["reason"])
            self.assertEqual("permission denied", payload["message"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_server_reports_missing_static_asset_as_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))

            with mock.patch.object(server, "static_bytes", side_effect=FileNotFoundError("missing")):
                status, media_type, body = server.response_for_get("/", ops_dir)

            self.assertEqual(HTTPStatus.INTERNAL_SERVER_ERROR, status)
            self.assertIn("application/json", media_type)
            payload = json.loads(body.decode("utf-8"))
            self.assertFalse(payload["ok"])
            self.assertEqual("static_asset_missing", payload["reason"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])

    def test_server_warns_when_binding_beyond_loopback(self) -> None:
        fake_server = FakeConsoleServer("0.0.0.0", 8765)
        output = io.StringIO()

        with mock.patch.object(server, "create_server", return_value=fake_server) as create_server:
            with contextlib.redirect_stdout(output):
                server.serve(Path("research_ops"), host="0.0.0.0", port=8765)

        create_server.assert_called_once_with(server.canonical_ops_dir(Path("research_ops")), "0.0.0.0", 8765)
        self.assertTrue(fake_server.served)
        self.assertTrue(fake_server.closed)
        self.assertIn("Warning: binding to 0.0.0.0 may expose the dashboard beyond localhost.", output.getvalue())

    def test_console_command_routes_snapshot_and_server_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))

            code, payload = run_cli_json(["console", "snapshot", ops_dir, "--json", "--now", NOW])
            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("console_snapshot_rendered", payload["action"])

            with mock.patch.object(server, "serve", return_value=None) as serve:
                code = cli.main(["console", str(ops_dir), "--port", "9876"])
            self.assertEqual(cli.SUCCESS, code)
            serve.assert_called_once_with(ops_dir, host="127.0.0.1", port=9876)

            with mock.patch.object(server, "serve", return_value=None) as serve:
                code = cli.main(["console", "serve", str(ops_dir), "--port", "9877"])
            self.assertEqual(cli.SUCCESS, code)
            serve.assert_called_once_with(ops_dir, host="127.0.0.1", port=9877)


if __name__ == "__main__":
    unittest.main()

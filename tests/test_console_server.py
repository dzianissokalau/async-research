"""Regression tests for the local read-only console server."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
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


class ConsoleServerTests(unittest.TestCase):
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

            self.assertEqual(before, file_snapshot(ops_dir))

    def test_server_rejects_unknown_api_and_mutation_methods(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            status, media_type, body = server.response_for_get("/api/decisions", ops_dir)
            self.assertEqual(HTTPStatus.NOT_FOUND, status)
            self.assertIn("application/json", media_type)
            missing_payload = json.loads(body.decode("utf-8"))
            self.assertEqual("api_route_not_found", missing_payload["reason"])

            status, media_type, body = server.response_for_mutation()
            self.assertEqual(HTTPStatus.METHOD_NOT_ALLOWED, status)
            self.assertIn("application/json", media_type)
            payload = json.loads(body.decode("utf-8"))
            self.assertEqual("mutation_endpoints_disabled", payload["reason"])
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


if __name__ == "__main__":
    unittest.main()

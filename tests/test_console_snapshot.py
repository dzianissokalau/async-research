"""Regression tests for the local console snapshot backend."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli


NOW = "2026-05-11T00:00:00Z"
SNAPSHOT_GROUPS = {
    "workspace",
    "readiness",
    "health",
    "tasks",
    "human_decisions",
    "accepted_outputs",
    "rejected_results",
    "cost",
    "ideas",
    "data",
    "library",
    "analysis",
    "runs",
    "warnings",
}


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class ConsoleSnapshotTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        self.assertTrue(payload["ok"])
        return ops_dir

    def snapshot(self, ops_dir: Path) -> tuple[int, dict]:
        return run_cli_json(["console", "snapshot", ops_dir, "--json", "--now", NOW])

    def test_snapshot_renders_generic_starter_without_mutating_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            before = file_snapshot(ops_dir)

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])
            self.assertTrue(SNAPSHOT_GROUPS.issubset(payload))
            self.assertEqual("console_snapshot_rendered", payload["action"])
            self.assertEqual("console_snapshot_v1.0", payload["schema_version"])
            self.assertEqual(0, payload["tasks"]["total"])
            self.assertEqual({}, payload["tasks"]["status_counts"])
            self.assertEqual(0, payload["human_decisions"]["open_count"])
            self.assertEqual(0, payload["accepted_outputs"]["count"])
            self.assertEqual(0, payload["rejected_results"]["count"])
            self.assertIn("month_spend_usd", payload["cost"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_snapshot_surfaces_malformed_task_status_as_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = ops_dir / "tasks" / "TASK-9999-malformed"
            task_dir.mkdir(parents=True)
            (task_dir / "status.json").write_text("{not json", encoding="utf-8")

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual(0, payload["tasks"]["total"])
            self.assertEqual(1, len(payload["tasks"]["malformed_statuses"]))
            self.assertTrue(any(item["reason"] == "malformed_task_status" for item in payload["warnings"]))

    def test_snapshot_marks_missing_optional_foundations_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            for relative in ("ideas", "data", "library"):
                target = ops_dir / relative
                for path in sorted(target.rglob("*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
                target.rmdir()

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertFalse(payload["ideas"]["available"])
            self.assertEqual("unavailable", payload["ideas"]["status"])
            self.assertFalse(payload["data"]["available"])
            self.assertFalse(payload["library"]["available"])
            reasons = {item["reason"] for item in payload["warnings"]}
            self.assertIn("ideas_files_missing", reasons)
            self.assertIn("data_files_missing", reasons)
            self.assertIn("library_files_missing", reasons)

    def test_snapshot_reports_missing_workspace_without_hard_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["workspace"]["exists"])
            self.assertFalse(payload["readiness"]["available"])
            self.assertFalse(payload["health"]["available"])
            self.assertFalse(payload["runs"]["available"])


if __name__ == "__main__":
    unittest.main()

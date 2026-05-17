"""Regression tests for public task-authoring helpers."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.scripts import task_authoring


def run_cli_json(argv: list[object]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


class TaskAuthoringTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--template", "generic", "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        return ops_dir

    def test_workflow_create_task_writes_valid_coffee_style_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))

            code, payload = run_cli_json(
                [
                    "workflow",
                    "create-task",
                    ops_dir,
                    "--title",
                    "Coffee climate data readiness",
                    "--task-id",
                    "TASK-7777",
                    "--task-type",
                    "data_readiness",
                    "--objective",
                    "Prepare coffee climate source readiness evidence.",
                    "--context",
                    "research_ops/data_source_audit.md",
                    "--data-audit-ref",
                    "DS-0001",
                    "--write",
                ]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("task_create_written", payload["action"])
            task_dir = Path(payload["task_dir"])
            self.assertTrue((task_dir / "status.json").exists())
            self.assertTrue((task_dir / "task.md").exists())
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("TASK-7777", status["id"])
            self.assertEqual("ready_for_worker", status["status"])
            self.assertEqual("manual_task_created_from_template", status["last_transition_reason"])
            self.assertIsInstance(status["result"], dict)
            self.assertEqual("none", status["result"]["claim_strength"])
            self.assertFalse(status["result"]["claim_strength_revalidation_required"])
            self.assertIn("Generic Markdown or prose-only artifacts are capped at `suggestive`", (task_dir / "task.md").read_text(encoding="utf-8"))

            status_code, status_report = run_cli_json(["workflow", "status", task_dir])
            self.assertEqual(cli.SUCCESS, status_code, status_report)
            self.assertTrue(status_report["status_validation"]["valid"])
            self.assertTrue(status_report["transition_validation"]["valid"])
            schema_code, schema = run_cli_json(["schema-check", ops_dir])
            self.assertEqual(cli.SUCCESS, schema_code, schema)
            surface_code, surface = run_cli_json(["surface", "update", ops_dir])
            self.assertEqual(cli.SUCCESS, surface_code, surface)
            check_code, check = run_cli_json(["workflow", "check", ops_dir])
            self.assertEqual(cli.SUCCESS, check_code, check)
            self.assertTrue(check["ok"], check)

    def test_workflow_create_task_refuses_existing_task_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            command = [
                "workflow",
                "create-task",
                ops_dir,
                "--title",
                "Duplicate manual task",
                "--task-id",
                "TASK-7778",
                "--write",
            ]
            code, payload = run_cli_json(command)
            self.assertEqual(cli.SUCCESS, code, payload)

            code, refused = run_cli_json(command)
            self.assertEqual(task_authoring.TARGET_EXISTS, code, refused)
            self.assertEqual("task_dir_exists", refused["reason"])

    def test_null_status_fields_report_actionable_authoring_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            code, payload = run_cli_json(
                [
                    "workflow",
                    "create-task",
                    ops_dir,
                    "--title",
                    "Null diagnostic fixture",
                    "--task-id",
                    "TASK-7779",
                    "--write",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)
            task_dir = Path(payload["task_dir"])
            status_path = task_dir / "status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            status["last_transition_reason"] = None
            status["result"] = None
            status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            code, status_report = run_cli_json(["workflow", "status", task_dir])

            self.assertEqual(4, code, status_report)
            issues = status_report["status_validation"]["issues"]
            hints = {issue["path"]: issue.get("hint", "") for issue in issues}
            self.assertIn("manual_task_created", hints["$.last_transition_reason"])
            self.assertIn("Use a result object placeholder instead of null", hints["$.result"])
            reasons = {item["reason"] for item in status_report["status_validation"]["diagnostics"]}
            self.assertIn("last_transition_reason_null", reasons)
            self.assertIn("result_null", reasons)


if __name__ == "__main__":
    unittest.main()

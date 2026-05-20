from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from async_research_workflow import cli
from async_research_workflow.scripts import scaling_state


NOW = "2026-05-20T12:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class ScalingStateBackendTests(unittest.TestCase):
    def test_scaling_assessment_keeps_repo_files_as_default_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            init_code, init_payload = run_cli_json(["init", ops_dir, "--template", "generic", "--force"])
            self.assertEqual(cli.SUCCESS, init_code, init_payload)

            code, payload = run_cli_json(["scaling", "assess", ops_dir, "--now", NOW])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])
            self.assertEqual("repo_files_sufficient", payload["decision"])
            self.assertEqual("research_ops files and task-local locks", payload["source_of_truth"]["durable_audit_record"])
            self.assertEqual(set(payload["metrics"]), set(payload["source_of_truth"]["derived_values"]))
            self.assertIn("dashboard_snapshot_ms", payload["metrics"])
            self.assertEqual([], payload["warnings"])
            selected = [option for option in payload["backend_options"] if option["status"] == "selected"]
            self.assertEqual(["no_backend"], [option["id"] for option in selected])

    def test_scaling_assessment_recommends_optional_cache_for_measured_friction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            init_code, init_payload = run_cli_json(["init", ops_dir, "--template", "generic", "--force"])
            self.assertEqual(cli.SUCCESS, init_code, init_payload)
            task_dir = ops_dir / "tasks" / "TASK-9001-stale-lock"
            write_json(task_dir / "status.json", {"id": "TASK-9001", "status": "in_progress"})
            write_json(ops_dir / "tasks" / "TASK-9002-scale-signal" / "status.json", {"id": "TASK-9002", "status": "ready"})
            lock_dir = task_dir / "LOCK"
            lock_dir.mkdir()
            old = time.time() - 3600
            os.utime(lock_dir, (old, old))

            code, payload = run_cli_json(
                [
                    "scaling",
                    "assess",
                    ops_dir,
                    "--now",
                    NOW,
                    "--max-task-statuses",
                    "1",
                    "--stale-lock-minutes",
                    "1",
                    "--skip-dashboard-latency",
                ]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("optional_rebuildable_index_cache_candidate", payload["decision"])
            reasons = {item["reason"] for item in payload["warnings"]}
            self.assertIn("task_status_count_high", reasons)
            self.assertIn("stale_lock_count_high", reasons)
            selected = [option for option in payload["backend_options"] if option["status"] == "selected"]
            self.assertEqual(["optional_rebuildable_index_cache"], [option["id"] for option in selected])
            self.assertIn("backend caches must be rebuildable from research_ops", payload["source_of_truth"]["non_negotiable"])

    def test_external_queue_decision_requires_human_architecture_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            init_code, init_payload = run_cli_json(["init", ops_dir, "--template", "generic", "--force"])
            self.assertEqual(cli.SUCCESS, init_code, init_payload)
            write_json(ops_dir / "tasks" / "TASK-9100-extreme-scale" / "status.json", {"id": "TASK-9100", "status": "ready"})

            code, payload = run_cli_json(
                [
                    "scaling",
                    "assess",
                    ops_dir,
                    "--now",
                    NOW,
                    "--max-task-statuses",
                    "0",
                    "--skip-dashboard-latency",
                ]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("external_queue_or_read_model_needs_human_decision", payload["decision"])
            external = [option for option in payload["backend_options"] if option["id"] == "external_queue_or_read_model"]
            self.assertEqual("human_decision_required", external[0]["status"])
            self.assertFalse(external[0]["repo_first"])

    def test_dashboard_snapshot_failure_is_reported_as_scaling_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            init_code, init_payload = run_cli_json(["init", ops_dir, "--template", "generic", "--force"])
            self.assertEqual(cli.SUCCESS, init_code, init_payload)

            with mock.patch.object(scaling_state, "dashboard_latency_ms", return_value=(None, {"error": "snapshot failed"})):
                code, payload = run_cli_json(["scaling", "assess", ops_dir, "--now", NOW])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("optional_rebuildable_index_cache_candidate", payload["decision"])
            reasons = {item["reason"] for item in payload["warnings"]}
            self.assertIn("dashboard_snapshot_unavailable", reasons)
            self.assertEqual({"error": "snapshot failed"}, payload["metrics"]["dashboard_snapshot_details"])


if __name__ == "__main__":
    unittest.main()

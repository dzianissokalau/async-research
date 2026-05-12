"""Regression tests for the local console snapshot backend."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from async_research_workflow import cli
from async_research_workflow.console import snapshot as snapshot_module


NOW = "2026-05-11T00:00:00Z"
SNAPSHOT_GROUPS = {
    "workspace",
    "readiness",
    "health",
    "tasks",
    "human_decisions",
    "accepted_outputs",
    "delivered_projects",
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


def write_task_status(ops_dir: Path, task_id: str, status: str = "ready_for_worker", requires_human: bool = False) -> Path:
    task_dir = ops_dir / "tasks" / f"{task_id}-fixture"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "status.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "id": task_id,
                "title": f"{task_id} fixture",
                "type": "admin",
                "status": status,
                "previous_status": "ready_for_worker" if status == "needs_human" else None,
                "last_transition_reason": "fixture",
                "priority": 2,
                "revision_count": 0,
                "max_revisions": 1,
                "revision_limit_hit": False,
                "allowed_paths": [f"research_ops/tasks/{task_dir.name}/**"],
                "max_minutes": 10,
                "requires_human": requires_human,
                "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
                "human_gate_reason": "fixture needs human" if requires_human or status == "needs_human" else None,
                "updated_at": NOW,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return task_dir


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

    def test_malformed_task_row_handles_missing_task_dir(self) -> None:
        row = snapshot_module.malformed_task_row(
            {"task_id": "TASK-EMPTY", "reason": "malformed_json", "errors": [{"message": "bad"}]},
            snapshot_module.parse_now(NOW),
        )

        self.assertEqual("TASK-EMPTY", row["task_id"])
        self.assertEqual("invalid", row["status"])
        self.assertFalse(row["lock_state"]["locked"])
        self.assertEqual([], row["files"])
        self.assertEqual("", row["task_dir"])

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

    def test_snapshot_handles_non_directory_ops_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_path = Path(tmp) / "research_ops"
            ops_path.write_text("not a directory\n", encoding="utf-8")

            code, payload = self.snapshot(ops_path)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["workspace"]["exists"])
            self.assertFalse(payload["workspace"]["is_dir"])
            self.assertFalse(payload["readiness"]["available"])
            self.assertFalse(payload["health"]["available"])

    def test_snapshot_rejects_invalid_now_with_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))

            code, payload = run_cli_json(["console", "snapshot", ops_dir, "--json", "--now", "not-a-time"])

            self.assertEqual(3, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("invalid_now", payload["reason"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])

    def test_snapshot_uses_consistent_task_shape_for_human_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task_status(ops_dir, "TASK-1001", "needs_human", requires_human=True)

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual(1, len(payload["tasks"]["human"]))
            human = payload["tasks"]["human"][0]
            for key in [
                "task_id",
                "title",
                "status",
                "type",
                "review_tier",
                "revision_count",
                "requires_human",
                "human_gate_reason",
                "last_transition_reason",
                "allowed_paths",
                "allowed_next_statuses",
                "status_validation",
                "transition_validation",
                "lock_state",
                "files",
                "task_dir",
                "status_path",
            ]:
                self.assertIn(key, human)
            self.assertEqual("TASK-1001", human["task_id"])
            self.assertEqual(human, payload["human_decisions"]["blocked_task_refs"][0])

    def test_snapshot_includes_full_task_board_rows_and_invalid_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task_status(ops_dir, "TASK-1003", "ready_for_worker")
            malformed_dir = ops_dir / "tasks" / "TASK-1004-malformed"
            malformed_dir.mkdir(parents=True)
            (malformed_dir / "status.json").write_text("{not json", encoding="utf-8")

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            by_id = {task["task_id"]: task for task in payload["tasks"]["all"]}
            self.assertIn("TASK-1003", by_id)
            self.assertIn("TASK-1004-malformed", by_id)
            valid = by_id["TASK-1003"]
            self.assertTrue(valid["status_validation"]["valid"])
            self.assertTrue(valid["transition_validation"]["valid"])
            self.assertIn("in_progress", valid["allowed_next_statuses"])
            self.assertEqual({"locked": False, "stale": False}, {key: valid["lock_state"][key] for key in ("locked", "stale")})
            self.assertIn(str(task_dir / "status.json"), [item["path"] for item in valid["files"]])
            invalid = by_id["TASK-1004-malformed"]
            self.assertEqual("invalid", invalid["status"])
            self.assertFalse(invalid["status_validation"]["valid"])
            self.assertEqual("malformed_json", invalid["status_validation"]["reason"])
            self.assertFalse(invalid["transition_validation"]["valid"])
            self.assertIn("invalid", payload["tasks"]["status_filter_options"])

    def test_snapshot_surfaces_stale_locks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task_status(ops_dir, "TASK-1002", "in_progress")
            lock_dir = task_dir / "LOCK"
            lock_dir.mkdir()
            os.utime(lock_dir, (0, 0))

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual(1, len(payload["tasks"]["stale_locks"]))
            self.assertEqual(str(lock_dir), payload["tasks"]["stale_locks"][0]["lock_dir"])
            task = payload["tasks"]["all"][0]
            self.assertTrue(task["lock_state"]["locked"])
            self.assertTrue(task["lock_state"]["stale"])

    def test_snapshot_surfaces_budget_pressure_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            (ops_dir / "cost_ledger.csv").write_text(
                "\n".join(
                    [
                        "date,item_id,amount_usd,monthly_budget_usd,weekly_budget_usd",
                        "2026-05-11,COST-1,90,100,100",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["cost"]["budget_pressure"])
            reasons = {item["reason"] for item in payload["warnings"]}
            self.assertIn("monthly_budget_pressure", reasons)
            self.assertIn("weekly_budget_pressure", reasons)

    def test_snapshot_degrades_unreadable_cost_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            (ops_dir / "cost_ledger.csv").write_bytes(b"\xff\xfe\x00")

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertFalse(payload["cost"]["available"])
            self.assertEqual("unavailable", payload["cost"]["status"])
            self.assertTrue(any(item["reason"] == "cost_ledger_unreadable" for item in payload["warnings"]))

    def test_snapshot_degrades_readiness_and_health_exceptions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))

            with mock.patch.object(snapshot_module.autonomy_readiness_gate, "build_gate_report", side_effect=RuntimeError("readiness boom")):
                code, payload = self.snapshot(ops_dir)
            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertFalse(payload["readiness"]["available"])
            self.assertEqual("readiness_unavailable", payload["readiness"]["reason"])

            with mock.patch.object(snapshot_module.health_check, "build_report", side_effect=RuntimeError("health boom")):
                code, payload = self.snapshot(ops_dir)
            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertFalse(payload["health"]["available"])
            self.assertEqual("health_unavailable", payload["health"]["reason"])

    def test_snapshot_degrades_dashboard_summary_exceptions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))

            with mock.patch.object(snapshot_module, "catalog_dashboard_report", side_effect=RuntimeError("ideas boom")):
                code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertFalse(payload["ideas"]["available"])
            self.assertEqual("ideas_dashboard_unavailable", payload["ideas"]["reason"])
            self.assertTrue(any(item["reason"] == "ideas_dashboard_unavailable" for item in payload["warnings"]))

    def test_snapshot_warns_on_malformed_markdown_table_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            (ops_dir / "accepted_outputs_index.md").write_text(
                "\n".join(
                    [
                        "| accepted_date | task_id | title |",
                        "| --- | --- | --- |",
                        "| 2026-05-11 | TASK-1003 |",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(any(item["reason"] == "malformed_markdown_table_row" for item in payload["warnings"]))

    def test_snapshot_includes_delivered_projects_from_accepted_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task_status(ops_dir, "TASK-4001", status="accepted")
            (ops_dir / "accepted_outputs_index.md").write_text(
                "\n".join(
                    [
                        "| accepted_date | task_id | title | key_finding | claim_type | freshness_window_days | next_recheck_date | revalidation_status | source_ids | claim_strength | caveats | followups | supersedes | superseded_by | evidence_link |",
                        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                        f"| 2026-05-10 | TASK-4001 | Delivered fixture | Finding | general | 90 | 2026-08-08 | current | none | weak | none | none | none | none | tasks/{task_dir.name}/worker_output.md |",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            delivered = payload["delivered_projects"]
            self.assertEqual(1, delivered["count"])
            self.assertFalse(delivered["exists"])
            self.assertEqual(["all", "accepted"], delivered["status_filter_options"])
            self.assertEqual("TASK-4001", delivered["rows"][0]["task_id"])
            self.assertEqual(1, delivered["summary"]["revalidation_counts"]["current"])

    def test_snapshot_surfaces_broken_run_json_without_dropping_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            run_dir = ops_dir / "run_artifacts" / "run-001"
            run_dir.mkdir(parents=True)
            (run_dir / "run.json").write_text("{not json", encoding="utf-8")

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["runs"]["available"])
            self.assertEqual(1, payload["runs"]["count"])
            self.assertEqual("run-001", payload["runs"]["recent_runs"][0]["run_id"])
            self.assertEqual("unavailable", payload["runs"]["recent_runs"][0]["status"])


if __name__ == "__main__":
    unittest.main()

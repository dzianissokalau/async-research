"""Regression tests for the public workflow orchestrator."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from async_research_workflow import cli
from async_research_workflow.scripts import workflow_orchestrator
from async_research_workflow.scripts.version_metadata import apply_default_versions


NOW = "2026-05-11T00:00:00Z"


def run_cli_json(argv: list[object]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class WorkflowOrchestratorTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        return ops_dir

    def write_task(self, ops_dir: Path, task_name: str, *, result: dict | None = None) -> Path:
        task_id = task_name[:9]
        task_dir = ops_dir / "tasks" / task_name
        status = {
            "schema_version": "1.0",
            "id": task_id,
            "title": f"Workflow orchestrator fixture {task_id}",
            "type": "data_readiness",
            "status": "awaiting_review",
            "previous_status": "in_progress",
            "last_transition_reason": "worker_submitted_for_review",
            "priority": 3,
            "revision_count": 0,
            "max_revisions": 1,
            "revision_limit_hit": False,
            "created_at": NOW,
            "updated_at": NOW,
            "allowed_paths": [f"research_ops/tasks/{task_name}"],
            "allowed_tools": ["read_files", "write_task_files"],
            "allow_browsing": False,
            "allow_code_execution": False,
            "allow_network": False,
            "max_minutes": 15,
            "max_turns": 1,
            "model_tier": "low",
            "review_policy": {
                "tier": 1,
                "required_reviewers": ["primary"],
                "panel_required": False,
                "human_required_for_acceptance": False,
            },
            "requires_human": False,
            "budget": {
                "max_api_usd": 0,
                "max_compute_usd": 0,
            },
            "result": result
            or {
                "recommendation": None,
                "claim_strength": "none",
                "followup_count": 0,
            },
        }
        write_json(task_dir / "status.json", apply_default_versions(status))
        return task_dir

    def write_review(self, task_dir: Path, decision: str, claim_strength: str = "suggestive") -> None:
        write_json(
            task_dir / "reviews" / "primary.md",
            {
                "reviewer_role": "primary",
                "decision": decision,
                "claim_strength": claim_strength,
                "prompt_version": "primary_reviewer_v1.0",
                "framework_versions": {"result_acceptance": "result_acceptance_v1.0"},
                "main_concerns": [],
                "required_followups": [],
                "evidence_gaps": [],
                "escalate_to_tier": None,
                "escalation_reason": None,
                "confidence": 0.8,
            },
        )

    def accepted_result(self) -> dict:
        return {
            "recommendation": "ready",
            "claim_strength": "suggestive",
            "key_finding": "Workflow orchestrator accepted finding is reusable.",
            "claim_type": "general",
            "freshness_window_days": 90,
            "next_recheck_date": "2026-08-09",
            "revalidation_status": "current",
            "followup_count": 0,
        }

    def assert_step_status(self, payload: dict, name: str, status: str) -> None:
        step = next(item for item in payload["steps"] if item["name"] == name)
        self.assertEqual(status, step["status"], step)

    def test_advance_accepts_task_and_refreshes_follow_on_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(ops_dir, "TASK-9101-accepted", result=self.accepted_result())
            task_dir.joinpath("worker_output.md").write_text(
                "Workflow orchestrator accepted finding is reusable.\n",
                encoding="utf-8",
            )
            self.write_review(task_dir, "accept")

            code, payload = run_cli_json(["workflow", "advance", task_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["dry_run"])
            self.assertEqual("accepted", payload["aggregate_decision"])
            self.assert_step_status(payload, "review_aggregate", "ok")
            self.assert_step_status(payload, "accepted_update", "ok")
            self.assert_step_status(payload, "accepted_revalidation", "ok")
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("accepted", status["status"])
            self.assertTrue((task_dir / "review_panel" / "aggregate.json").exists())
            self.assertIn("TASK-9101", (ops_dir / "accepted_outputs_index.md").read_text(encoding="utf-8"))
            self.assertTrue((ops_dir / "revalidation_schedule.md").exists())

    def test_advance_dry_run_runs_only_read_only_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(ops_dir, "TASK-9105-dry-run", result=self.accepted_result())
            task_dir.joinpath("worker_output.md").write_text(
                "Workflow orchestrator accepted finding is reusable.\n",
                encoding="utf-8",
            )
            self.write_review(task_dir, "accept")

            code, payload = run_cli_json(["workflow", "advance", task_dir, "--dry-run"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["dry_run"])
            self.assertEqual("accepted", payload["aggregate_decision"])
            self.assert_step_status(payload, "accepted_update", "skipped_mutation")
            self.assert_step_status(payload, "accepted_revalidation", "skipped_mutation")
            self.assert_step_status(payload, "surface_update", "skipped_mutation")
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("awaiting_review", status["status"])
            self.assertFalse((task_dir / "review_panel" / "aggregate.json").exists())
            self.assertNotIn("TASK-9105", (ops_dir / "accepted_outputs_index.md").read_text(encoding="utf-8"))

    def test_advance_refuses_task_outside_matching_ops_dir_before_running_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ops_dir = self.init_ops(root / "left")
            other_ops_dir = self.init_ops(root / "right")
            task_dir = self.write_task(ops_dir, "TASK-9106-mismatch", result=self.accepted_result())
            self.write_review(task_dir, "accept")

            with mock.patch.object(workflow_orchestrator, "module_main") as module_main:
                code, payload = run_cli_json(["workflow", "advance", task_dir, "--ops-dir", other_ops_dir])

            self.assertEqual(workflow_orchestrator.INVALID_STATE, code, payload)
            self.assertEqual("task_dir_ops_mismatch", payload["reason"])
            module_main.assert_not_called()
            self.assertFalse((task_dir / "review_panel" / "aggregate.json").exists())

    def test_advance_refuses_non_task_folder_before_running_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ops_dir = self.init_ops(root)
            loose_task = root / "loose-task"
            loose_task.mkdir()

            with mock.patch.object(workflow_orchestrator, "module_main") as module_main:
                code, payload = run_cli_json(["workflow", "advance", loose_task, "--ops-dir", ops_dir])

            self.assertEqual(workflow_orchestrator.INVALID_STATE, code, payload)
            self.assertEqual("task_dir_not_under_tasks", payload["reason"])
            module_main.assert_not_called()

    def test_only_readiness_warning_is_tolerated_in_advance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(ops_dir, "TASK-9107-warning-policy")

            def readiness_warning_only(module_name: str, argv: list[str]) -> int:
                return workflow_orchestrator.READINESS_WARNINGS if module_name == "autonomy_readiness_gate" else 0

            with mock.patch.object(workflow_orchestrator, "module_main", side_effect=readiness_warning_only):
                code, payload = run_cli_json(["workflow", "advance", task_dir, "--dry-run"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assert_step_status(payload, "readiness_dry_run", "warning")

            def aggregate_validation_failure(module_name: str, argv: list[str]) -> int:
                return workflow_orchestrator.VALIDATION_FAILED if module_name == "aggregate_reviews" else 0

            with mock.patch.object(workflow_orchestrator, "module_main", side_effect=aggregate_validation_failure):
                code, payload = run_cli_json(["workflow", "advance", task_dir, "--dry-run"])

            self.assertEqual(workflow_orchestrator.VALIDATION_FAILED, code, payload)
            self.assertEqual("review_aggregate", payload["failed_step"])
            self.assert_step_status(payload, "review_aggregate", "failed")

    def test_advance_reports_partial_mutation_when_later_step_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(ops_dir, "TASK-9108-partial-mutation")

            def fail_after_aggregate(module_name: str, argv: list[str]) -> int:
                if module_name == "update_accepted_outputs_index" and argv[:1] == ["update"]:
                    return workflow_orchestrator.VALIDATION_FAILED
                return 0

            with mock.patch.object(workflow_orchestrator, "module_main", side_effect=fail_after_aggregate):
                code, payload = run_cli_json(["workflow", "advance", task_dir])

            self.assertEqual(workflow_orchestrator.VALIDATION_FAILED, code, payload)
            self.assertEqual("accepted_update", payload["failed_step"])
            self.assertTrue(payload["partial_mutation"])
            self.assert_step_status(payload, "review_aggregate", "ok")
            self.assert_step_status(payload, "accepted_update", "failed")

    def test_advance_routes_needs_revision_and_reports_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(ops_dir, "TASK-9102-needs-revision")
            self.write_review(task_dir, "needs_revision")

            code, payload = run_cli_json(["workflow", "advance", task_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("needs_revision", payload["aggregate_decision"])
            self.assertIn("bounded revision loop", payload["next_step"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("needs_revision", status["status"])
            self.assert_step_status(payload, "surface_update", "ok")

    def test_advance_routes_needs_human_and_refreshes_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(ops_dir, "TASK-9103-needs-human")
            self.write_review(task_dir, "needs_human", claim_strength="none")

            code, payload = run_cli_json(["workflow", "advance", task_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("needs_human", payload["aggregate_decision"])
            self.assertIn("decision resolve-task", payload["next_step"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("needs_human", status["status"])
            self.assertTrue(status["requires_human"])
            self.assert_step_status(payload, "surface_update", "ok")

    def test_advance_routes_rejected_and_reports_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(ops_dir, "TASK-9109-rejected")
            task_dir.joinpath("worker_output.md").write_text("Output should not be reused.\n", encoding="utf-8")
            self.write_review(task_dir, "reject", claim_strength="none")

            code, payload = run_cli_json(["workflow", "advance", task_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("rejected", payload["aggregate_decision"])
            self.assertIn("rejected_results.md", payload["next_step"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("rejected", status["status"])
            self.assertIn("TASK-9109", (ops_dir / "rejected_results.md").read_text(encoding="utf-8"))

    def test_advance_stops_on_invalid_state_before_mutating_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = ops_dir / "tasks" / "TASK-9104-invalid-state"
            write_json(task_dir / "status.json", {})
            self.write_review(task_dir, "needs_revision")

            code, payload = run_cli_json(["workflow", "advance", task_dir])

            self.assertEqual(workflow_orchestrator.INVALID_STATE, code, payload)
            self.assertFalse(payload["ok"])
            self.assertTrue(payload["stopped"])
            self.assertEqual("schema_check", payload["failed_step"])
            self.assertFalse(payload["partial_mutation"])
            self.assertEqual(["schema_check"], [step["name"] for step in payload["steps"]])
            self.assertFalse((task_dir / "review_panel" / "aggregate.json").exists())


if __name__ == "__main__":
    unittest.main()

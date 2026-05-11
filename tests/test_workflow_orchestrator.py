"""Regression tests for the public workflow orchestrator."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

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
            self.assertEqual(["schema_check"], [step["name"] for step in payload["steps"]])
            self.assertFalse((task_dir / "review_panel" / "aggregate.json").exists())


if __name__ == "__main__":
    unittest.main()

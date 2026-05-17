"""Regression tests for the public workflow orchestrator."""

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

    def write_task(
        self,
        ops_dir: Path,
        task_name: str,
        *,
        status_value: str = "awaiting_review",
        previous_status: str | None = "in_progress",
        requires_human: bool = False,
        human_gate_reason: str | None = None,
        result: dict | None = None,
    ) -> Path:
        task_id = task_name[:9]
        task_dir = ops_dir / "tasks" / task_name
        status = {
            "schema_version": "1.0",
            "id": task_id,
            "title": f"Workflow orchestrator fixture {task_id}",
            "type": "data_readiness",
            "status": status_value,
            "previous_status": previous_status,
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
            "requires_human": requires_human,
            "human_gate_reason": human_gate_reason,
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

    def test_status_reports_task_truth_surface_and_advance_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(ops_dir, "TASK-9110-status-ready", result=self.accepted_result())
            task_dir.joinpath("worker_output.md").write_text(
                "Workflow status ready output.\n",
                encoding="utf-8",
            )
            self.write_review(task_dir, "accept")

            code, payload = run_cli_json(["workflow", "status", task_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual("workflow_status_reported", payload["action"])
            self.assertEqual(str(ops_dir), payload["ops_dir"])
            self.assertEqual(str(task_dir), payload["task_dir"])
            self.assertEqual("TASK-9110", payload["task_id"])
            self.assertEqual("awaiting_review", payload["status"])
            self.assertEqual("in_progress", payload["previous_status"])
            self.assertEqual("data_readiness", payload["type"])
            self.assertEqual(1, payload["review_tier"])
            self.assertTrue(payload["status_validation"]["valid"])
            self.assertTrue(payload["transition_validation"]["valid"])
            self.assertEqual(["needs_human", "panel_review", "single_review"], payload["transition_validation"]["allowed_next_statuses"])
            self.assertFalse(payload["lock_state"]["locked"])
            self.assertTrue(payload["worker_output"]["exists"])
            self.assertTrue(payload["worker_output"]["non_empty"])
            self.assertEqual(["primary"], payload["reviews"]["required_reviewers"])
            self.assertEqual([], payload["reviews"]["missing_required_reviews"])
            self.assertTrue(payload["reviews"]["ready_to_aggregate"])
            self.assertTrue(payload["reviews"]["by_role"]["primary"]["valid"])
            self.assertEqual("accept", payload["reviews"]["by_role"]["primary"]["decision"])
            self.assertFalse(payload["human_gate"]["requires_human"])
            self.assertEqual(0, payload["revisions"]["revision_count"])
            self.assertEqual("suggestive", payload["result"]["claim_strength"])
            commands = [item["command"] for item in payload["next_legal_commands"]]
            self.assertIn(f"async-research workflow advance {task_dir} --dry-run", commands)
            self.assertIn(f"async-research workflow advance {task_dir}", commands)
            self.assertFalse((task_dir / "review_panel" / "aggregate.json").exists())
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("awaiting_review", status["status"])

    def test_status_reports_missing_review_next_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(ops_dir, "TASK-9111-status-review")
            task_dir.joinpath("worker_output.md").write_text("Output ready for review.\n", encoding="utf-8")

            code, payload = run_cli_json(["workflow", "status", task_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(["primary"], payload["reviews"]["missing_required_reviews"])
            self.assertFalse(payload["reviews"]["ready_to_aggregate"])
            self.assertEqual(
                f"async-research review submit {task_dir} --role primary --decision '<decision>' --claim-strength '<strength>' --confidence '<0-1>'",
                payload["next_legal_commands"][0]["command"],
            )
            self.assertIn("write the missing required review", payload["next_legal_commands"][0]["reason"])

    def test_status_reports_worker_start_commands_for_ready_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9124-start-status",
                status_value="ready_for_worker",
                previous_status="ready_for_planning",
            )

            code, payload = run_cli_json(["workflow", "status", task_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            commands = [item["command"] for item in payload["next_legal_commands"]]
            self.assertEqual(f"async-research workflow worker-start {task_dir} --dry-run", commands[0])
            self.assertIn(f"async-research workflow worker-start {task_dir}", commands)
            self.assertFalse((task_dir / "LOCK").exists())

    def test_status_reports_worker_complete_commands_for_ready_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9125-complete-status",
                status_value="in_progress",
                previous_status="ready_for_worker",
            )
            task_dir.joinpath("worker_output.md").write_text("Worker result ready.\n", encoding="utf-8")
            lock_dir = task_dir / "LOCK"
            lock_dir.mkdir()
            write_json(lock_dir / "owner.json", {"owner": "worker-a"})

            code, payload = run_cli_json(["workflow", "status", task_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            commands = [item["command"] for item in payload["next_legal_commands"]]
            self.assertEqual(f"async-research workflow worker-complete {task_dir} --owner worker-a --dry-run", commands[0])
            self.assertIn(f"async-research workflow worker-complete {task_dir} --owner worker-a", commands)

    def test_status_marks_role_mismatched_review_file_without_hiding_missing_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(ops_dir, "TASK-9115-role-mismatch")
            task_dir.joinpath("worker_output.md").write_text("Output ready for review.\n", encoding="utf-8")
            self.write_review(task_dir, "accept")
            review_path = task_dir / "reviews" / "primary.md"
            review = json.loads(review_path.read_text(encoding="utf-8"))
            review["reviewer_role"] = "methodology"
            review_path.write_text(json.dumps(review, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            code, payload = run_cli_json(["workflow", "status", task_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            primary = payload["reviews"]["by_role"]["primary"]
            methodology = payload["reviews"]["by_role"]["methodology"]
            self.assertTrue(primary["exists"])
            self.assertFalse(primary["valid"])
            self.assertTrue(primary["role_mismatch"])
            self.assertEqual("methodology", primary["declared_role"])
            self.assertIn("does not satisfy role 'primary'", primary["message"])
            self.assertTrue(methodology["exists"])
            self.assertTrue(methodology["valid"])
            self.assertEqual(str(review_path), methodology["path"])
            self.assertEqual(["primary"], payload["reviews"]["missing_required_reviews"])
            self.assertFalse(payload["reviews"]["ready_to_aggregate"])
            self.assertIn("review submit", payload["next_legal_commands"][0]["command"])

    def test_status_reports_human_gate_resolution_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9112-status-human",
                status_value="needs_human",
                previous_status="panel_review",
                requires_human=True,
                human_gate_reason="reviewers requested human judgment",
            )

            code, payload = run_cli_json(["workflow", "status", task_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["human_gate"]["requires_human"])
            self.assertEqual("reviewers requested human judgment", payload["human_gate"]["reason"])
            self.assertEqual("needs_human", payload["status"])
            self.assertIn("decision resolve-task", payload["next_legal_commands"][0]["command"])
            self.assertIn("--dry-run", payload["next_legal_commands"][0]["command"])

    def test_status_refuses_schema_invalid_status_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = ops_dir / "tasks" / "TASK-9113-status-invalid"
            write_json(task_dir / "status.json", {})

            code, payload = run_cli_json(["workflow", "status", task_dir])

            self.assertEqual(workflow_orchestrator.INVALID_STATE, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("workflow_status_reported", payload["action"])
            self.assertFalse(payload["status_validation"]["valid"])
            self.assertEqual("status_schema_validation_failed", payload["status_validation"]["reason"])
            self.assertFalse(payload["transition_validation"]["valid"])
            self.assertEqual("async-research schema-check " + str(ops_dir), payload["next_legal_commands"][0]["command"])
            self.assertFalse((task_dir / "review_panel" / "aggregate.json").exists())

    def test_status_refuses_task_outside_matching_ops_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ops_dir = self.init_ops(root / "left")
            other_ops_dir = self.init_ops(root / "right")
            task_dir = self.write_task(ops_dir, "TASK-9114-status-mismatch")

            code, payload = run_cli_json(["workflow", "status", task_dir, "--ops-dir", other_ops_dir])

            self.assertEqual(workflow_orchestrator.INVALID_STATE, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("workflow_status_refused", payload["action"])
            self.assertEqual("task_dir_ops_mismatch", payload["reason"])

    def test_status_labels_accepted_task_outcome_refresh_as_derived_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9116-status-accepted",
                status_value="accepted",
                previous_status="panel_review",
                result=self.accepted_result(),
            )

            code, payload = run_cli_json(["workflow", "status", task_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("accepted", payload["status"])
            self.assertEqual("Refresh derived outcome surfaces", payload["next_legal_commands"][0]["label"])
            self.assertIn("writes derived delivered-project outcome files", payload["next_legal_commands"][0]["reason"])
            self.assertIn("outcomes refresh", payload["next_legal_commands"][0]["command"])

    def test_next_prioritizes_malformed_state_before_other_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            invalid_task = ops_dir / "tasks" / "TASK-9117-invalid-next"
            write_json(invalid_task / "status.json", {})
            self.write_task(
                ops_dir,
                "TASK-9118-human-next",
                status_value="needs_human",
                previous_status="panel_review",
                requires_human=True,
                human_gate_reason="fixture human gate",
            )

            code, payload = run_cli_json(["workflow", "next", ops_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])
            self.assertEqual("workflow_next_reported", payload["action"])
            self.assertEqual("malformed_state", payload["recommendation"]["category"])
            self.assertEqual(f"async-research schema-check {ops_dir}", payload["recommendation"]["command"])
            self.assertGreaterEqual(payload["summary"]["malformed_status_count"], 1)
            self.assertIn("needs_human", [item["category"] for item in payload["alternatives"]])
            self.assertFalse((invalid_task / "review_panel" / "aggregate.json").exists())

    def test_next_recommends_human_gate_before_review_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            human_task = self.write_task(
                ops_dir,
                "TASK-9119-human-first",
                status_value="needs_human",
                previous_status="panel_review",
                requires_human=True,
                human_gate_reason="fixture human gate",
            )
            review_task = self.write_task(ops_dir, "TASK-9120-review-later", result=self.accepted_result())
            review_task.joinpath("worker_output.md").write_text("Reviewable worker output.\n", encoding="utf-8")
            self.write_review(review_task, "accept")

            code, payload = run_cli_json(["workflow", "next", ops_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("needs_human", payload["recommendation"]["category"])
            self.assertEqual("TASK-9119", payload["recommendation"]["task"]["task_id"])
            self.assertEqual(str(human_task), payload["recommendation"]["task"]["task_dir"])
            self.assertIn("decision resolve-task", payload["recommendation"]["command"])
            self.assertIn("--dry-run", payload["recommendation"]["command"])
            self.assertFalse(payload["recommendation"]["mutates"])
            self.assertIn("ready_for_review", [item["category"] for item in payload["alternatives"]])

    def test_next_recommends_review_advance_dry_run_for_reviewed_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(ops_dir, "TASK-9121-next-review", result=self.accepted_result())
            task_dir.joinpath("worker_output.md").write_text("Reviewable worker output.\n", encoding="utf-8")
            self.write_review(task_dir, "accept")

            code, payload = run_cli_json(["workflow", "next", ops_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("ready_for_review", payload["recommendation"]["category"])
            self.assertEqual("TASK-9121", payload["recommendation"]["task"]["task_id"])
            self.assertEqual(f"async-research workflow advance {task_dir} --dry-run", payload["recommendation"]["command"])
            self.assertFalse(payload["recommendation"]["mutates"])
            self.assertTrue(payload["recommendation"]["details"]["ready_to_aggregate"])
            self.assertFalse((task_dir / "review_panel" / "aggregate.json").exists())

    def test_next_recommends_ready_worker_task_when_no_higher_priority_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9122-worker-ready",
                status_value="ready_for_worker",
                previous_status="ready_for_planning",
            )

            code, payload = run_cli_json(["workflow", "next", ops_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("ready_for_worker", payload["recommendation"]["category"])
            self.assertEqual(f"async-research workflow worker-start {task_dir} --dry-run", payload["recommendation"]["command"])
            self.assertFalse(payload["recommendation"]["mutates"])

    def test_next_recommends_worker_completion_when_output_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9126-next-complete",
                status_value="in_progress",
                previous_status="ready_for_worker",
            )
            task_dir.joinpath("worker_output.md").write_text("Worker result ready.\n", encoding="utf-8")

            code, payload = run_cli_json(["workflow", "next", ops_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("worker_completion", payload["recommendation"]["category"])
            self.assertEqual(f"async-research workflow worker-complete {task_dir} --dry-run", payload["recommendation"]["command"])
            self.assertFalse(payload["recommendation"]["mutates"])

    def test_next_uses_stale_minutes_for_lock_recommendation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9123-stale-lock",
                status_value="ready_for_worker",
                previous_status="ready_for_planning",
            )
            lock_dir = task_dir / "LOCK"
            lock_dir.mkdir()
            old = time.time() - 120
            os.utime(lock_dir, (old, old))

            code, payload = run_cli_json(["workflow", "next", ops_dir, "--stale-minutes", "1"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("stale_lock", payload["recommendation"]["category"])
            self.assertEqual(str(task_dir), payload["recommendation"]["task"]["task_dir"])
            self.assertTrue(payload["recommendation"]["details"]["lock_state"]["stale"])
            self.assertEqual(1.0, payload["recommendation"]["details"]["lock_state"]["stale_after_minutes"])

    def test_next_refuses_missing_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "missing_ops"

            code, payload = run_cli_json(["workflow", "next", ops_dir])

            self.assertEqual(workflow_orchestrator.INVALID_STATE, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("workflow_next_refused", payload["action"])
            self.assertEqual("ops_dir_missing", payload["reason"])
            self.assertIn("async-research init", payload["next_step"])

    def test_worker_start_dry_run_does_not_write_lock_or_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9127-start-dry",
                status_value="ready_for_worker",
                previous_status="ready_for_planning",
            )

            code, payload = run_cli_json(["workflow", "worker-start", task_dir, "--owner", "worker-a", "--dry-run"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual("workflow_worker_start_dry_run", payload["action"])
            self.assertFalse(payload["changed"])
            self.assertFalse((task_dir / "LOCK").exists())
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("ready_for_worker", status["status"])

    def test_worker_start_claims_lock_and_updates_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9128-start-write",
                status_value="ready_for_worker",
                previous_status="ready_for_planning",
            )

            code, payload = run_cli_json(["workflow", "worker-start", task_dir, "--owner", "worker-a"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual("workflow_worker_started", payload["action"])
            self.assertTrue(payload["changed"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("in_progress", status["status"])
            self.assertEqual("ready_for_worker", status["previous_status"])
            self.assertEqual("workflow_worker_started", status["last_transition_reason"])
            self.assertEqual("worker-a", status["lock_owner"])
            self.assertTrue((task_dir / "LOCK" / "owner.json").exists())
            owner = json.loads((task_dir / "LOCK" / "owner.json").read_text(encoding="utf-8"))
            self.assertEqual("worker-a", owner["owner"])

    def test_worker_start_refuses_non_ready_task_without_lock_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9135-start-wrong-state",
                status_value="awaiting_review",
                previous_status="in_progress",
            )

            code, payload = run_cli_json(["workflow", "worker-start", task_dir, "--owner", "worker-a"])

            self.assertEqual(workflow_orchestrator.INVALID_STATE, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("task_not_ready_for_worker", payload["reason"])
            self.assertFalse((task_dir / "LOCK").exists())
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("awaiting_review", status["status"])

    def test_worker_start_refuses_fresh_lock_without_status_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9129-start-locked",
                status_value="ready_for_worker",
                previous_status="ready_for_planning",
            )
            lock_dir = task_dir / "LOCK"
            lock_dir.mkdir()
            write_json(lock_dir / "owner.json", {"owner": "worker-b"})

            code, payload = run_cli_json(["workflow", "worker-start", task_dir, "--owner", "worker-a", "--dry-run"])

            self.assertEqual(2, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("lock_acquire_failed", payload["reason"])
            self.assertFalse(payload["changed"])

            code, payload = run_cli_json(["workflow", "worker-start", task_dir, "--owner", "worker-a"])

            self.assertEqual(2, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("lock_acquire_failed", payload["reason"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("ready_for_worker", status["status"])
            self.assertEqual("worker-b", json.loads((lock_dir / "owner.json").read_text(encoding="utf-8"))["owner"])

    def test_worker_start_takes_over_stale_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9136-start-stale",
                status_value="ready_for_worker",
                previous_status="ready_for_planning",
            )
            lock_dir = task_dir / "LOCK"
            lock_dir.mkdir()
            write_json(lock_dir / "owner.json", {"owner": "worker-b"})
            old = time.time() - 120
            os.utime(lock_dir, (old, old))

            code, payload = run_cli_json(["workflow", "worker-start", task_dir, "--owner", "worker-a", "--stale-minutes", "1"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("in_progress", status["status"])
            self.assertEqual("worker-a", status["lock_owner"])
            owner = json.loads((task_dir / "LOCK" / "owner.json").read_text(encoding="utf-8"))
            self.assertEqual("worker-a", owner["owner"])
            self.assertTrue(list(task_dir.glob("LOCK.stale.*")))

    def test_worker_start_releases_lock_when_status_changes_after_acquire(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9137-start-race",
                status_value="ready_for_worker",
                previous_status="ready_for_planning",
            )
            real_load = workflow_orchestrator.load_valid_task_status
            call_count = 0

            def status_changes_after_lock(path: Path, action: str):
                nonlocal call_count
                call_count += 1
                status, error = real_load(path, action)
                if call_count == 2 and status is not None:
                    changed = dict(status)
                    changed.update(
                        {
                            "status": "in_progress",
                            "previous_status": "ready_for_worker",
                            "last_transition_reason": "workflow_worker_started",
                        }
                    )
                    return changed, None
                return status, error

            with mock.patch.object(workflow_orchestrator, "load_valid_task_status", side_effect=status_changes_after_lock):
                code, payload = run_cli_json(["workflow", "worker-start", task_dir, "--owner", "worker-a"])

            self.assertEqual(workflow_orchestrator.INVALID_STATE, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("status_changed_after_lock", payload["reason"])
            self.assertTrue(payload["changed"])
            self.assertFalse((task_dir / "LOCK").exists())
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("ready_for_worker", status["status"])

    def test_worker_start_refuses_schema_invalid_status_without_lock_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = ops_dir / "tasks" / "TASK-9133-start-invalid"
            write_json(task_dir / "status.json", {})

            code, payload = run_cli_json(["workflow", "worker-start", task_dir, "--owner", "worker-a"])

            self.assertEqual(workflow_orchestrator.INVALID_STATE, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("status_invalid", payload["reason"])
            self.assertFalse((task_dir / "LOCK").exists())

    def test_worker_wrappers_refuse_task_outside_matching_ops_dir_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ops_dir = self.init_ops(root / "left")
            other_ops_dir = self.init_ops(root / "right")
            task_dir = self.write_task(
                ops_dir,
                "TASK-9134-wrapper-mismatch",
                status_value="ready_for_worker",
                previous_status="ready_for_planning",
            )

            code, payload = run_cli_json(["workflow", "worker-start", task_dir, "--ops-dir", other_ops_dir, "--owner", "worker-a"])

            self.assertEqual(workflow_orchestrator.INVALID_STATE, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("task_dir_ops_mismatch", payload["reason"])
            self.assertFalse((task_dir / "LOCK").exists())
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("ready_for_worker", status["status"])

    def test_worker_complete_requires_non_empty_worker_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9130-complete-empty",
                status_value="in_progress",
                previous_status="ready_for_worker",
            )
            task_dir.joinpath("worker_output.md").write_text("   \n", encoding="utf-8")

            code, payload = run_cli_json(["workflow", "worker-complete", task_dir, "--owner", "worker-a"])

            self.assertEqual(workflow_orchestrator.INVALID_STATE, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("worker_output_not_ready", payload["reason"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("in_progress", status["status"])

    def test_worker_complete_dry_run_refuses_mismatched_owner_without_status_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9138-complete-dry-owner",
                status_value="in_progress",
                previous_status="ready_for_worker",
            )
            task_dir.joinpath("worker_output.md").write_text("Completed worker result.\n", encoding="utf-8")
            lock_dir = task_dir / "LOCK"
            lock_dir.mkdir()
            write_json(lock_dir / "owner.json", {"owner": "worker-b"})

            code, payload = run_cli_json(["workflow", "worker-complete", task_dir, "--owner", "worker-a", "--dry-run"])

            self.assertEqual(3, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("lock_owner_mismatch", payload["reason"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("in_progress", status["status"])
            self.assertTrue(lock_dir.exists())

    def test_worker_complete_moves_to_review_and_releases_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9131-complete-write",
                status_value="ready_for_worker",
                previous_status="ready_for_planning",
            )
            code, payload = run_cli_json(["workflow", "worker-start", task_dir, "--owner", "worker-a"])
            self.assertEqual(cli.SUCCESS, code, payload)
            task_dir.joinpath("worker_output.md").write_text("Completed worker result.\n", encoding="utf-8")

            code, payload = run_cli_json(["workflow", "worker-complete", task_dir, "--owner", "worker-a"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual("workflow_worker_completed", payload["action"])
            self.assertTrue(payload["changed"])
            self.assertEqual("suggestive", payload["claim_strength_preflight"]["max_claim_strength"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("awaiting_review", status["status"])
            self.assertEqual("in_progress", status["previous_status"])
            self.assertEqual("workflow_worker_completed_output", status["last_transition_reason"])
            self.assertIsNone(status["lock_owner"])
            self.assertIsNone(status["lock_expires_at"])
            self.assertFalse((task_dir / "LOCK").exists())

    def test_worker_complete_succeeds_without_lock_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9139-complete-no-lock",
                status_value="in_progress",
                previous_status="ready_for_worker",
            )
            task_dir.joinpath("worker_output.md").write_text("Completed worker result.\n", encoding="utf-8")

            code, payload = run_cli_json(["workflow", "worker-complete", task_dir, "--owner", "worker-a"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["lock_missing"])
            self.assertEqual("already_unlocked", payload["release_result"]["action"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("awaiting_review", status["status"])
            self.assertFalse((task_dir / "LOCK").exists())

    def test_worker_complete_force_release_allows_mismatched_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9140-complete-force",
                status_value="in_progress",
                previous_status="ready_for_worker",
            )
            task_dir.joinpath("worker_output.md").write_text("Completed worker result.\n", encoding="utf-8")
            lock_dir = task_dir / "LOCK"
            lock_dir.mkdir()
            write_json(lock_dir / "owner.json", {"owner": "worker-b"})

            code, payload = run_cli_json(["workflow", "worker-complete", task_dir, "--owner", "worker-a", "--force-release"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual("released", payload["release_result"]["action"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("awaiting_review", status["status"])
            self.assertFalse(lock_dir.exists())

    def test_worker_complete_refuses_mismatched_owner_without_status_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9132-complete-owner",
                status_value="in_progress",
                previous_status="ready_for_worker",
            )
            task_dir.joinpath("worker_output.md").write_text("Completed worker result.\n", encoding="utf-8")
            lock_dir = task_dir / "LOCK"
            lock_dir.mkdir()
            write_json(lock_dir / "owner.json", {"owner": "worker-b"})

            code, payload = run_cli_json(["workflow", "worker-complete", task_dir, "--owner", "worker-a"])

            self.assertEqual(3, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("lock_owner_mismatch", payload["reason"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("in_progress", status["status"])
            self.assertTrue(lock_dir.exists())

    def test_worker_complete_reports_partial_mutation_when_release_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_task(
                ops_dir,
                "TASK-9141-complete-release-fails",
                status_value="in_progress",
                previous_status="ready_for_worker",
            )
            task_dir.joinpath("worker_output.md").write_text("Completed worker result.\n", encoding="utf-8")
            lock_dir = task_dir / "LOCK"
            lock_dir.mkdir()
            write_json(lock_dir / "owner.json", {"owner": "worker-a"})
            real_run_module_json = workflow_orchestrator.run_module_json

            def fail_release(module_name: str, argv: list[str]):
                if module_name == "task_lock" and argv[:1] == ["release"]:
                    return 3, {"ok": False, "reason": "release_failed"}, None, ""
                return real_run_module_json(module_name, argv)

            with mock.patch.object(workflow_orchestrator, "run_module_json", side_effect=fail_release):
                code, payload = run_cli_json(["workflow", "worker-complete", task_dir, "--owner", "worker-a"])

            self.assertEqual(3, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("lock_release_failed_after_status_write", payload["reason"])
            self.assertTrue(payload["partial_mutation"])
            self.assertTrue(payload["changed"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("awaiting_review", status["status"])
            self.assertTrue(lock_dir.exists())

    def test_atomic_write_json_cleans_up_temp_file_on_replace_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "status.json"
            tmp_path = target.with_name(f".{target.name}.{os.getpid()}.tmp")

            with mock.patch.object(workflow_orchestrator.os, "replace", side_effect=OSError("replace failed")):
                with self.assertRaises(OSError):
                    workflow_orchestrator.atomic_write_json(target, {"ok": True})

            self.assertFalse(tmp_path.exists())
            self.assertFalse(target.exists())

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
            self.assertIn("human_gate_opened_at", status)
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

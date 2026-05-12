"""Regression tests for guarded console setup actions."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow.console import actions


def file_snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def write_task_status(
    ops_dir: Path,
    task_id: str = "TASK-2001",
    status: str = "ready_for_worker",
    available_decisions: list[str] | None = None,
) -> Path:
    task_dir = ops_dir / "tasks" / f"{task_id}-fixture"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.md").write_text(f"# {task_id}\n", encoding="utf-8")
    payload = {
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
        "requires_human": status == "needs_human",
        "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
        "human_gate_reason": "fixture needs human" if status == "needs_human" else None,
        "updated_at": "2026-05-12T00:00:00Z",
    }
    if status == "needs_human":
        payload["human_gate"] = {
            "policy_version": "test",
            "trigger": "fixture",
            "triggered_at": "2026-05-12T00:00:00Z",
            "severity": "medium",
            "reason": "fixture needs human",
            "required_human_decision": "choose a test resolution",
            "available_decisions": available_decisions
            if available_decisions is not None
            else ["resume", "pause", "reject"],
            "default_safe_action": "pause",
            "retry_behavior": "rerun after human decision",
            "ledger_update_behavior": "record the decision in decisions.md",
        }
    (task_dir / "status.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return task_dir


class ConsoleActionTests(unittest.TestCase):
    def test_catalog_marks_missing_workspace_and_known_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            catalog = actions.action_catalog(ops_dir)

        self.assertTrue(catalog["ok"])
        self.assertFalse(catalog["workspace"]["exists"])
        by_id = {item["id"]: item for item in catalog["actions"]}
        self.assertEqual("available", by_id["init"]["status"])
        self.assertEqual("blocked_missing_workspace", by_id["schema_check"]["status"])
        self.assertIn("async-research init", by_id["init"]["command"])
        self.assertIn("async-research surface update", by_id["surface_update"]["command"])
        self.assertTrue(by_id["surface_update"]["mutates"])
        self.assertFalse(by_id["surface_validate"]["mutates"])
        task_actions = {item["id"]: item for item in catalog["task_actions"]}
        self.assertIn("task_status_validate", task_actions)
        self.assertIn("python -m async_research_workflow.scripts.validate_transition", task_actions["task_transition_validate"]["command_template"])
        self.assertIn("outcomes_refresh", by_id)
        self.assertTrue(by_id["outcomes_refresh"]["mutates"])
        self.assertIn("async-research outcomes refresh", by_id["outcomes_refresh"]["command"])
        decision_actions = {item["id"]: item for item in catalog["decision_actions"]}
        self.assertIn("decision_resume", decision_actions)
        self.assertIn("decision_approve_budget", decision_actions)
        self.assertIn("async-research decision resolve-task", decision_actions["decision_resume"]["command_template"])
        self.assertTrue(decision_actions["decision_resume"]["requires_confirmation"])

    def test_init_requires_confirmation_then_creates_missing_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            status, blocked = actions.run_action("init", ops_dir, {"template": "generic"})
            self.assertEqual(409, status)
            self.assertEqual("confirmation_required", blocked["reason"])
            self.assertFalse(ops_dir.exists())

            status, result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )

            self.assertEqual(200, status)
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["changed"])
            self.assertTrue(result["mutates"])
            self.assertEqual(0, result["exit_code"])
            self.assertEqual("success", result["status"])
            self.assertIn("async-research init", result["command"])
            self.assertIn('"action": "initialized"', result["stdout"])
            self.assertEqual("", result["stderr"])
            self.assertTrue((ops_dir / "README.md").exists())

    def test_init_refuses_existing_workspace_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()
            sentinel = ops_dir / "sentinel.txt"
            sentinel.write_text("keep me", encoding="utf-8")
            before = file_snapshot(ops_dir)

            status, result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )

            self.assertEqual(200, status)
            self.assertFalse(result["ok"])
            self.assertFalse(result["changed"])
            self.assertEqual(4, result["exit_code"])
            self.assertIn("target_exists", result["stdout"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_init_rejects_force_and_unknown_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            status, result = actions.run_action("init", ops_dir, {"template": "generic", "force": True})
            self.assertEqual(400, status)
            self.assertEqual("force_not_supported", result["reason"])

            status, result = actions.run_action("init", ops_dir, {"template": "unknown"})
            self.assertEqual(400, status)
            self.assertEqual("unsupported_template", result["reason"])

    def test_setup_checks_return_command_result_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            _, init_result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )
            self.assertTrue(init_result["ok"], init_result)

            for action_id in ("schema_check", "readiness_dry_run", "health_dry_run", "surface_update", "surface_validate"):
                status, result = actions.run_action(action_id, ops_dir, {})
                self.assertEqual(200, status, result)
                self.assertIn("async-research", result["command"])
                self.assertIsInstance(result["stdout"], str)
                self.assertIsInstance(result["stderr"], str)
                self.assertIsInstance(result["exit_code"], int)
                self.assertIn(result["status"], {"success", "warning", "failed"})
                self.assertIn("next_step", result)
                if result["stdout"].strip():
                    try:
                        json.loads(result["stdout"])
                    except json.JSONDecodeError:
                        self.fail(f"{action_id} stdout should be JSON: {result['stdout']}")

    def test_non_init_action_requires_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            status, result = actions.run_action("schema_check", ops_dir, {})
        self.assertEqual(409, status)
        self.assertEqual("ops_dir_missing", result["reason"])
        self.assertTrue(result["read_only"])
        self.assertFalse(result["changed"])

    def test_unknown_action_is_structured_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status, result = actions.run_action("nope", Path(tmp) / "research_ops", {})
        self.assertEqual(404, status)
        self.assertEqual("unknown_console_action", result["reason"])

    def test_task_inspection_actions_are_read_only_command_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            _, init_result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )
            self.assertTrue(init_result["ok"], init_result)
            task_dir = write_task_status(ops_dir)
            before = file_snapshot(ops_dir)

            for action_id in ("task_status_validate", "task_transition_validate", "task_lock_status"):
                with self.subTest(action_id=action_id):
                    status, result = actions.run_action(action_id, ops_dir, {"task_dir": str(task_dir)})

                    self.assertEqual(200, status, result)
                    self.assertTrue(result["ok"], result)
                    self.assertTrue(result["read_only"])
                    self.assertFalse(result["changed"])
                    self.assertFalse(result["mutates"])
                    self.assertIn("python -m async_research_workflow.scripts.", result["command"])
                    self.assertEqual(str(task_dir.resolve()), result["task_dir"])
                    self.assertEqual(str(task_dir.resolve() / "status.json"), result["status_path"])
                    self.assertEqual(0, result["exit_code"])
                    self.assertIsInstance(result["stdout"], str)
                    self.assertEqual("", result["stderr"])
                    if result["stdout"].strip():
                        json.loads(result["stdout"])

            self.assertEqual(before, file_snapshot(ops_dir))

    def test_task_inspection_actions_validate_workspace_and_task_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"

            status, result = actions.run_action("task_status_validate", ops_dir, {"task_id": "TASK-2001"})
            self.assertEqual(409, status)
            self.assertEqual("ops_dir_missing", result["reason"])

            _, init_result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )
            self.assertTrue(init_result["ok"], init_result)

            status, result = actions.run_action("task_status_validate", ops_dir, {})
            self.assertEqual(400, status)
            self.assertEqual("missing_task", result["reason"])

            status, result = actions.run_action("task_status_validate", ops_dir, {"task_dir": str(Path(tmp) / "outside")})
            self.assertEqual(400, status)
            self.assertEqual("task_outside_workspace", result["reason"])

            status, result = actions.run_action("task_status_validate", ops_dir, {"task_dir": "TASK-9999-missing"})
            self.assertEqual(400, status)
            self.assertEqual("task_missing", result["reason"])

    def test_task_inspection_actions_resolve_task_id_and_report_validation_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            _, init_result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )
            self.assertTrue(init_result["ok"], init_result)
            task_dir = write_task_status(ops_dir, task_id="TASK-2002")

            status, result = actions.run_action("task_lock_status", ops_dir, {"task_id": "TASK-2002"})

            self.assertEqual(200, status, result)
            self.assertTrue(result["ok"], result)
            self.assertEqual(str(task_dir.resolve()), result["task_dir"])
            self.assertTrue(result["read_only"])
            self.assertFalse(result["changed"])

            (task_dir / "status.json").write_text("{}\n", encoding="utf-8")
            status, result = actions.run_action("task_status_validate", ops_dir, {"task_dir": str(task_dir)})

            self.assertEqual(200, status, result)
            self.assertFalse(result["ok"])
            self.assertEqual("failed", result["status"])
            self.assertEqual(2, result["exit_code"])
            self.assertTrue(result["read_only"])
            self.assertFalse(result["changed"])
            self.assertEqual("schema_validation_failed", result["parsed_stdout"]["reason"])
            self.assertIn("Reported reason: schema_validation_failed", result["next_step"])

    def test_task_inspection_actions_reject_symlink_escape_from_tasks_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ops_dir = root / "research_ops"
            _, init_result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )
            self.assertTrue(init_result["ok"], init_result)
            outside_dir = root / "outside-task"
            outside_dir.mkdir()
            write_task_status(outside_dir.parent, task_id="TASK-ESCAPE")
            escaped_source = outside_dir.parent / "tasks" / "TASK-ESCAPE-fixture"
            escaped_target = outside_dir / "status-source"
            escaped_source.rename(escaped_target)
            symlink_dir = ops_dir / "tasks" / "TASK-ESCAPE-link"
            try:
                symlink_dir.symlink_to(escaped_target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks unavailable: {exc}")

            status, result = actions.run_action("task_status_validate", ops_dir, {"task_id": "TASK-ESCAPE"})

            self.assertEqual(400, status)
            self.assertEqual("task_missing", result["reason"])

    def test_outcomes_refresh_action_writes_generated_index_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            _, init_result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )
            self.assertTrue(init_result["ok"], init_result)

            status, result = actions.run_action("outcomes_refresh", ops_dir, {})

            self.assertEqual(200, status, result)
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["changed"])
            self.assertTrue(result["mutates"])
            self.assertEqual(0, result["exit_code"])
            self.assertIn("async-research outcomes refresh", result["command"])
            self.assertTrue((ops_dir / "outcomes" / "delivered_projects.jsonl").exists())
            self.assertTrue((ops_dir / "outcomes" / "delivered_projects_summary.json").exists())

    def test_decision_resume_requires_confirmation_then_resolves_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            _, init_result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )
            self.assertTrue(init_result["ok"], init_result)
            task_dir = write_task_status(ops_dir, task_id="TASK-2601", status="needs_human")
            before = file_snapshot(ops_dir)

            payload = {
                "task_dir": str(task_dir),
                "reason": "Reviewed in console",
                "approver": "test-owner",
                "date": "2026-05-12T00:00:00Z",
            }
            status, blocked = actions.run_action("decision_resume", ops_dir, payload)

            self.assertEqual(409, status)
            self.assertEqual("confirmation_required", blocked["reason"])
            self.assertEqual(before, file_snapshot(ops_dir))

            status, result = actions.run_action(
                "decision_resume",
                ops_dir,
                {**payload, "confirm": actions.decision_confirmation_token("decision_resume")},
            )

            self.assertEqual(200, status, result)
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["changed"])
            self.assertTrue(result["mutates"])
            self.assertEqual(0, result["exit_code"])
            self.assertIn("async-research decision resolve-task", result["command"])
            self.assertEqual("resolved", result["parsed_stdout"]["action"])
            self.assertTrue(result["decision_audit"]["decision_logged"])
            self.assertTrue(result["decision_audit"]["status_matches"])
            self.assertTrue(result["decision_audit"]["validated"])
            self.assertIn("TASK-2601", (ops_dir / "decisions.md").read_text(encoding="utf-8"))
            status_payload = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("ready_for_worker", status_payload["status"])
            self.assertFalse(status_payload["requires_human"])

    def test_decision_add_note_appends_without_changing_task_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            _, init_result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )
            self.assertTrue(init_result["ok"], init_result)
            task_dir = write_task_status(ops_dir, task_id="TASK-2602", status="needs_human")

            status, result = actions.run_action(
                "decision_add_note",
                ops_dir,
                {
                    "task_id": "TASK-2602",
                    "reason": "Owner is checking the source contract",
                    "approver": "test-owner",
                    "date": "2026-05-12T00:00:00Z",
                    "confirm": actions.decision_confirmation_token("decision_add_note"),
                },
            )

            self.assertEqual(200, status, result)
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["changed"])
            self.assertEqual("decision_appended", result["parsed_stdout"]["action"])
            self.assertEqual("acknowledge", result["decision_audit"]["decision"])
            self.assertTrue(result["decision_audit"]["validated"])
            status_payload = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("needs_human", status_payload["status"])

    def test_decision_action_rejects_decision_outside_task_gate_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            _, init_result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )
            self.assertTrue(init_result["ok"], init_result)
            task_dir = write_task_status(
                ops_dir,
                task_id="TASK-2604",
                status="needs_human",
                available_decisions=["resume", "pause", "reject"],
            )
            before = file_snapshot(ops_dir)

            status, result = actions.run_action(
                "decision_approve_budget",
                ops_dir,
                {
                    "task_dir": str(task_dir),
                    "reason": "Budget approval is not available for this gate",
                    "approver": "test-owner",
                    "confirm": actions.decision_confirmation_token("decision_approve_budget"),
                },
            )

            self.assertEqual(409, status)
            self.assertFalse(result["ok"])
            self.assertEqual("decision_not_available", result["reason"])
            self.assertEqual("approve_budget", result["decision"])
            self.assertEqual(["pause", "reject", "resume"], result["allowed_decisions"])
            self.assertTrue(result["read_only"])
            self.assertFalse(result["changed"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_decision_action_accepts_decision_allowed_by_task_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            _, init_result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )
            self.assertTrue(init_result["ok"], init_result)
            task_dir = write_task_status(
                ops_dir,
                task_id="TASK-2605",
                status="needs_human",
                available_decisions=["approve_budget", "pause", "reject"],
            )

            status, result = actions.run_action(
                "decision_approve_budget",
                ops_dir,
                {
                    "task_dir": str(task_dir),
                    "reason": "Budget looks acceptable",
                    "approver": "test-owner",
                    "date": "2026-05-12T00:00:00Z",
                    "confirm": actions.decision_confirmation_token("decision_approve_budget"),
                },
            )

            self.assertEqual(200, status, result)
            self.assertTrue(result["ok"], result)
            self.assertEqual(0, result["exit_code"])
            self.assertTrue(result["decision_audit"]["validated"])
            self.assertEqual("approve_budget", result["decision_audit"]["decision"])
            status_payload = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("ready_for_worker", status_payload["status"])
            self.assertEqual("human_decision_approve_budget", status_payload["last_transition_reason"])

    def test_decision_action_blocks_invalid_transition_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            _, init_result = actions.run_action(
                "init",
                ops_dir,
                {
                    "template": "generic",
                    "confirm": actions.init_confirmation_token(ops_dir, "generic"),
                },
            )
            self.assertTrue(init_result["ok"], init_result)
            task_dir = write_task_status(ops_dir, task_id="TASK-2603", status="ready_for_worker")
            before = file_snapshot(ops_dir)

            status, result = actions.run_action(
                "decision_resume",
                ops_dir,
                {
                    "task_dir": str(task_dir),
                    "reason": "Invalid console attempt",
                    "approver": "test-owner",
                    "confirm": actions.decision_confirmation_token("decision_resume"),
                },
            )

            self.assertEqual(200, status, result)
            self.assertFalse(result["ok"])
            self.assertFalse(result["changed"])
            self.assertEqual(2, result["exit_code"])
            self.assertEqual("task_not_needs_human", result["parsed_stdout"]["reason"])
            self.assertEqual(before, file_snapshot(ops_dir))


if __name__ == "__main__":
    unittest.main()

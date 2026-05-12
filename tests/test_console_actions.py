"""Regression tests for guarded console setup actions."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from async_research_workflow.console import actions


def file_snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def write_runner_script(root: Path, body: str) -> Path:
    path = root / "runner.py"
    path.write_text(body, encoding="utf-8")
    return path


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


class RecordingLock:
    def __init__(self) -> None:
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self) -> None:
        self.enter_count += 1

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.exit_count += 1


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
        prompt_actions = {item["id"]: item for item in catalog["prompt_actions"]}
        self.assertIn("prompts_init", prompt_actions)
        self.assertIn("prompt_save_draft", prompt_actions)
        self.assertIn("prompt_activate", prompt_actions)
        self.assertIn("async-research prompts init", prompt_actions["prompts_init"]["command_template"])
        self.assertTrue(prompt_actions["prompt_activate"]["requires_confirmation"])
        schedule_actions = {item["id"]: item for item in catalog["schedule_actions"]}
        self.assertIn("schedules_init", schedule_actions)
        self.assertIn("schedule_save", schedule_actions)
        self.assertIn("schedule_enable", schedule_actions)
        self.assertIn("schedule_trigger_dry_run", schedule_actions)
        self.assertIn("schedule_trigger_now", schedule_actions)
        self.assertIn("schedule_disable", schedule_actions)
        self.assertIn("async-research schedules init", schedule_actions["schedules_init"]["command_template"])
        self.assertIn("async-research schedules trigger-dry-run", schedule_actions["schedule_trigger_dry_run"]["command_template"])
        self.assertFalse(schedule_actions["schedule_trigger_dry_run"]["mutates"])
        self.assertIn("async-research schedules trigger-now", schedule_actions["schedule_trigger_now"]["command_template"])
        self.assertTrue(schedule_actions["schedule_trigger_now"]["mutates"])
        self.assertTrue(schedule_actions["schedule_trigger_now"]["requires_confirmation"])

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

    def test_prompt_actions_save_draft_and_require_activation_confirmation(self) -> None:
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

            status, prompt_init = actions.run_action("prompts_init", ops_dir, {})
            self.assertEqual(200, status, prompt_init)
            self.assertTrue(prompt_init["ok"], prompt_init)
            self.assertTrue((ops_dir / "prompts" / "worker.md").exists())
            draft = (ops_dir / "prompts" / "drafts" / "worker.md").read_text(encoding="utf-8")
            edited = draft.replace(
                "Process at most one task or one scheduled unit of work per run.",
                "Process at most one task or one scheduled unit of work per run, then stop cleanly.",
            )

            status, saved = actions.run_action(
                "prompt_save_draft",
                ops_dir,
                {
                    "prompt_id": "worker",
                    "content": edited,
                    "reason": "tighten stop rule",
                    "author": "tester",
                },
            )

            self.assertEqual(200, status, saved)
            self.assertTrue(saved["ok"], saved)
            self.assertTrue(saved["changed"])
            self.assertIn("async-research prompts draft", saved["command"])
            self.assertTrue(saved["parsed_stdout"]["validation"]["ok"])

            status, blocked = actions.run_action(
                "prompt_activate",
                ops_dir,
                {
                    "prompt_id": "worker",
                    "reason": "tighten stop rule",
                    "author": "tester",
                },
            )
            self.assertEqual(409, status)
            self.assertEqual("confirmation_required", blocked["reason"])

            status, activated = actions.run_action(
                "prompt_activate",
                ops_dir,
                {
                    "prompt_id": "worker",
                    "reason": "tighten stop rule",
                    "author": "tester",
                    "confirm": actions.prompt_confirmation_token("prompt_activate", "worker"),
                },
            )

            self.assertEqual(200, status, activated)
            self.assertTrue(activated["ok"], activated)
            self.assertEqual("worker_v1.1", activated["parsed_stdout"]["version"])
            self.assertIn("prompt:worker", (ops_dir / "decisions.md").read_text(encoding="utf-8"))

    def test_prompt_activation_blocks_invalid_draft_without_override(self) -> None:
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
            actions.run_action("prompts_init", ops_dir, {})
            draft = (ops_dir / "prompts" / "drafts" / "worker.md").read_text(encoding="utf-8")
            invalid = draft.replace("## Stop Conditions", "## Removed Stop Rules")
            actions.run_action(
                "prompt_save_draft",
                ops_dir,
                {
                    "prompt_id": "worker",
                    "content": invalid,
                    "reason": "invalid draft",
                    "author": "tester",
                },
            )
            before = file_snapshot(ops_dir)

            status, result = actions.run_action(
                "prompt_activate",
                ops_dir,
                {
                    "prompt_id": "worker",
                    "reason": "invalid draft",
                    "author": "tester",
                    "confirm": actions.prompt_confirmation_token("prompt_activate", "worker"),
                },
            )

            self.assertEqual(409, status)
            self.assertFalse(result["ok"])
            self.assertFalse(result["changed"])
            self.assertEqual(2, result["exit_code"])
            self.assertEqual("prompt_validation_failed", result["parsed_stdout"]["reason"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_prompt_mutations_are_serialized_by_command_lock(self) -> None:
        cases = [
            (
                "prompts_init",
                {},
                "init_library",
                {"ok": True, "changed": True, "read_only": False},
            ),
            (
                "prompt_save_draft",
                {"prompt_id": "worker", "content": "draft", "reason": "save draft", "author": "tester"},
                "save_draft",
                {"ok": True, "changed": True, "read_only": False},
            ),
            (
                "prompt_activate",
                {
                    "prompt_id": "worker",
                    "reason": "activate draft",
                    "author": "tester",
                    "confirm": actions.prompt_confirmation_token("prompt_activate", "worker"),
                },
                "activate_prompt",
                {"ok": True, "changed": True, "read_only": False},
            ),
        ]
        for action_id, payload, method_name, result_payload in cases:
            with self.subTest(action_id=action_id):
                with tempfile.TemporaryDirectory() as tmp:
                    ops_dir = Path(tmp) / "research_ops"
                    ops_dir.mkdir()
                    lock = RecordingLock()

                    with (
                        mock.patch.object(actions, "COMMAND_LOCK", lock),
                        mock.patch.object(
                            actions.prompt_library,
                            method_name,
                            return_value=(actions.prompt_library.SUCCESS, result_payload),
                        ),
                    ):
                        status, result = actions.run_action(action_id, ops_dir, payload)

                    self.assertEqual(200, status, result)
                    self.assertEqual(1, lock.enter_count)
                    self.assertEqual(1, lock.exit_count)

    def test_schedule_actions_init_save_and_toggle_intent(self) -> None:
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

            status, prompts_init = actions.run_action("prompts_init", ops_dir, {})
            self.assertEqual(200, status, prompts_init)
            self.assertTrue(prompts_init["ok"], prompts_init)

            status, schedule_init = actions.run_action("schedules_init", ops_dir, {})
            self.assertEqual(200, status, schedule_init)
            self.assertTrue(schedule_init["ok"], schedule_init)
            self.assertTrue((ops_dir / "schedules.json").exists())
            self.assertIn("async-research schedules init", schedule_init["command"])

            status, saved = actions.run_action(
                "schedule_save",
                ops_dir,
                {
                    "job_id": "worker-loop",
                    "description": "Process one ready worker task.",
                    "cadence": "hourly",
                    "prompt_id": "worker",
                    "prompt_version": "worker_v1.0",
                    "max_runtime_minutes": 40,
                    "concurrency_key": "worker",
                    "concurrency_limit": 1,
                    "status": "disabled",
                    "disabled_reason": "waiting for trigger-now slice",
                    "reason": "tighten worker runtime",
                    "author": "tester",
                },
            )
            self.assertEqual(200, status, saved)
            self.assertTrue(saved["ok"], saved)
            self.assertTrue(saved["changed"])
            self.assertIn("async-research schedules upsert", saved["command"])

            status, enabled = actions.run_action(
                "schedule_enable",
                ops_dir,
                {
                    "job_id": "worker-loop",
                    "reason": "operator wants worker intent visible",
                    "author": "tester",
                },
            )
            self.assertEqual(200, status, enabled)
            self.assertTrue(enabled["ok"], enabled)

            status, preview = actions.run_action(
                "schedule_trigger_dry_run",
                ops_dir,
                {"job_id": "worker-loop"},
            )
            self.assertEqual(200, status, preview)
            self.assertTrue(preview["ok"], preview)
            self.assertFalse(preview["mutates"])
            self.assertTrue(preview["read_only"])
            self.assertFalse(preview["changed"])
            self.assertIn("async-research schedules trigger-dry-run", preview["command"])
            self.assertTrue(preview["parsed_stdout"]["would_run"], preview)
            self.assertTrue(preview["parsed_stdout"]["no_process_started"], preview)
            self.assertFalse((ops_dir / "run_artifacts").exists())

            runner = write_runner_script(
                Path(tmp),
                "\n".join(
                    [
                        "import json",
                        "print(json.dumps({'type': 'agent_message', 'message': 'console worker complete'}), flush=True)",
                    ]
                ),
            )
            status, unconfirmed = actions.run_action(
                "schedule_trigger_now",
                ops_dir,
                {"job_id": "worker-loop"},
            )
            self.assertEqual(409, status, unconfirmed)
            self.assertEqual("confirmation_required", unconfirmed["reason"])

            with mock.patch.dict(os.environ, {"ASYNC_RESEARCH_TRIGGER_COMMAND": f"{sys.executable} {runner}"}):
                status, executed = actions.run_action(
                    "schedule_trigger_now",
                    ops_dir,
                    {
                        "job_id": "worker-loop",
                        "confirm": actions.schedule_trigger_confirmation_token("worker-loop"),
                    },
                )
            self.assertEqual(200, status, executed)
            self.assertTrue(executed["ok"], executed)
            self.assertTrue(executed["changed"])
            self.assertFalse(executed["read_only"])
            self.assertIn("async-research schedules trigger-now", executed["command"])
            self.assertEqual("completed", executed["parsed_stdout"]["status"])
            self.assertTrue((ops_dir / "run_artifacts" / executed["parsed_stdout"]["run_id"] / "run.json").exists())

            status, disabled = actions.run_action(
                "schedule_disable",
                ops_dir,
                {
                    "job_id": "worker-loop",
                    "reason": "hold until dry-run trigger exists",
                    "author": "tester",
                    "disabled_reason": "hold until dry-run trigger exists",
                },
            )
            self.assertEqual(200, status, disabled)
            self.assertTrue(disabled["ok"], disabled)
            manifest = json.loads((ops_dir / "schedules.json").read_text(encoding="utf-8"))
            worker = next(job for job in manifest["jobs"] if job["job_id"] == "worker-loop")
            self.assertEqual("disabled", worker["status"])
            self.assertEqual("hold until dry-run trigger exists", worker["disabled_reason"])
            self.assertTrue((ops_dir / "schedules_history.jsonl").exists())
            decisions = (ops_dir / "decisions.md").read_text(encoding="utf-8")
            self.assertIn("schedule:worker-loop", decisions)

    def test_prompt_action_unexpected_exit_code_returns_server_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()

            with mock.patch.object(
                actions.prompt_library,
                "init_library",
                return_value=(1, {"ok": False, "message": "unexpected failure", "changed": False}),
            ):
                status, result = actions.run_action("prompts_init", ops_dir, {})

            self.assertEqual(500, status)
            self.assertFalse(result["ok"])
            self.assertEqual(1, result["exit_code"])
            self.assertEqual("unexpected failure", result["next_step"])

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

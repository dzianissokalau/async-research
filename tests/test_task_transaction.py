"""Regression tests for shared task transaction helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from async_research_workflow.scripts import task_transaction


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def init_ops(root: Path) -> Path:
    ops_dir = root / "research_ops"
    (ops_dir / "tasks").mkdir(parents=True)
    write_text(ops_dir / "queue.md", task_transaction.QUEUE_TEMPLATE)
    write_text(ops_dir / "decisions.md", "# Decisions\n\n")
    return ops_dir


def valid_status(task_id: str, title: str = "Transaction fixture task") -> dict:
    return {
        "schema_version": "1.0",
        "id": task_id,
        "title": title,
        "type": "data_readiness",
        "status": "ready_for_worker",
        "previous_status": None,
        "last_transition_reason": "task_transaction_test",
        "priority": 2,
        "revision_count": 0,
        "max_revisions": 1,
        "revision_limit_hit": False,
        "allowed_paths": [f"research_ops/tasks/{task_id}-data-readiness/**"],
        "allowed_tools": ["repo_read", "markdown_edit"],
        "allow_browsing": False,
        "allow_code_execution": False,
        "allow_network": False,
        "max_minutes": 45,
        "max_turns": 4,
        "requires_human": False,
        "budget": {"max_api_usd": 1.0, "max_compute_usd": 0.0},
        "review_policy": {
            "tier": 1,
            "required_reviewers": ["primary"],
            "panel_required": False,
            "human_required_for_acceptance": False,
        },
    }


def task_markdown(task_id: str) -> str:
    return f"# {task_id}: Transaction fixture\n\nRun one bounded transaction helper check.\n"


def queue_row(task_id: str) -> dict:
    return {
        "task_id": task_id,
        "task_dir_name": f"{task_id}-data-readiness",
        "priority": 2,
        "status": "ready_for_worker",
        "type": "data_readiness",
        "next_runner": "worker",
        "notes": "transaction helper fixture",
    }


class TaskTransactionTests(unittest.TestCase):
    def test_task_transaction_writes_task_folder_and_queue_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))

            code, payload = task_transaction.write_task_transaction(
                ops_dir,
                "TASK-7501-data-readiness",
                task_markdown("TASK-7501"),
                valid_status("TASK-7501"),
                queue_row("TASK-7501"),
            )

            self.assertEqual(task_transaction.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue((ops_dir / "tasks" / "TASK-7501-data-readiness" / "task.md").exists())
            self.assertTrue((ops_dir / "tasks" / "TASK-7501-data-readiness" / "status.json").exists())
            self.assertIn("TASK-7501", (ops_dir / "queue.md").read_text(encoding="utf-8"))

    def test_queue_row_append_is_idempotent_for_retries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))

            first = task_transaction.append_queue_row_once(ops_dir, queue_row("TASK-7502"))
            second = task_transaction.append_queue_row_once(ops_dir, queue_row("TASK-7502"))

            self.assertTrue(first["changed"])
            self.assertFalse(second["changed"])
            self.assertEqual("queue_row_already_present", second["action"])
            task_rows = [
                line
                for line in (ops_dir / "queue.md").read_text(encoding="utf-8").splitlines()
                if line.startswith("|") and "TASK-7502" in line
            ]
            self.assertEqual(1, len(task_rows))

    def test_queue_identity_uses_first_cell_not_cross_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            write_text(
                ops_dir / "queue.md",
                "\n".join(
                    [
                        "# Queue",
                        "",
                        "| task | priority | status | type | next_runner | notes |",
                        "| --- | ---: | --- | --- | --- | --- |",
                        "| [TASK-7504](tasks/TASK-7504-data-readiness/task.md) | 2 | ready_for_worker | data_readiness | worker | target row |",
                        "| [TASK-7505](tasks/TASK-7505-data-readiness/task.md) | 2 | ready_for_worker | data_readiness | worker | depends on TASK-7504 |",
                        "",
                    ]
                ),
            )

            removal = task_transaction.remove_queue_row(ops_dir, "TASK-7504")
            second = task_transaction.append_queue_row_once(ops_dir, queue_row("TASK-7504"))

            queue_text = (ops_dir / "queue.md").read_text(encoding="utf-8")
            self.assertEqual(1, removal["removed_count"])
            self.assertIn("TASK-7505", queue_text)
            self.assertIn("depends on TASK-7504", queue_text)
            self.assertTrue(second["changed"])
            task_rows = [line for line in queue_text.splitlines() if line.startswith("|") and "TASK-7505" in line]
            self.assertEqual(1, len(task_rows))

    def test_queue_contains_task_ignores_notes_only_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            write_text(
                ops_dir / "queue.md",
                "\n".join(
                    [
                        "# Queue",
                        "",
                        "| task | priority | status | type | next_runner | notes |",
                        "| --- | ---: | --- | --- | --- | --- |",
                        "| [TASK-7506](tasks/TASK-7506-data-readiness/task.md) | 2 | ready_for_worker | data_readiness | worker | mentions TASK-7507 |",
                        "",
                    ]
                ),
            )

            self.assertTrue(task_transaction.queue_contains_task(ops_dir, "TASK-7506"))
            self.assertFalse(task_transaction.queue_contains_task(ops_dir, "TASK-7507"))

    def test_queue_append_failure_removes_staged_and_final_task_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))

            def fail_append(_ops_dir: Path, _row: dict) -> dict:
                raise task_transaction.TaskTransactionError(
                    {"reason": "queue_append_failed", "error": "forced by test"},
                    task_transaction.MALFORMED,
                )

            code, payload = task_transaction.write_task_transaction(
                ops_dir,
                "TASK-7503-data-readiness",
                task_markdown("TASK-7503"),
                valid_status("TASK-7503"),
                queue_row("TASK-7503"),
                append_queue=fail_append,
            )

            self.assertEqual(task_transaction.MALFORMED, code, payload)
            self.assertEqual("queue_append_failed", payload["reason"])
            self.assertFalse((ops_dir / "tasks" / "TASK-7503-data-readiness").exists())
            self.assertEqual([], list((ops_dir / "tasks").glob(".TASK-7503-data-readiness.staging.*")))
            self.assertNotIn("TASK-7503", (ops_dir / "queue.md").read_text(encoding="utf-8"))

    def test_final_validation_failure_rolls_back_queue_and_task_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))

            def fail_final(_ops_dir: Path, _task_dir: Path, _task_id: str) -> list[dict]:
                return [{"reason": "forced_final_validation_failure"}]

            code, payload = task_transaction.write_task_transaction(
                ops_dir,
                "TASK-7504-data-readiness",
                task_markdown("TASK-7504"),
                valid_status("TASK-7504"),
                queue_row("TASK-7504"),
                final_validator=fail_final,
            )

            self.assertEqual(task_transaction.VALIDATION_FAILED, code, payload)
            self.assertEqual("final_validation_failed", payload["reason"])
            self.assertFalse((ops_dir / "tasks" / "TASK-7504-data-readiness").exists())
            self.assertEqual([], list((ops_dir / "tasks").glob(".TASK-7504-data-readiness.staging.*")))
            self.assertNotIn("TASK-7504", (ops_dir / "queue.md").read_text(encoding="utf-8"))
            rollback_actions = {item["action"] for item in payload["rollback"]["actions"]}
            self.assertIn("remove_task_folder", rollback_actions)
            self.assertIn("remove_queue_row", rollback_actions)

    def test_extra_files_are_written_and_unsafe_paths_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))

            code, payload = task_transaction.write_task_transaction(
                ops_dir,
                "TASK-7508-data-readiness",
                task_markdown("TASK-7508"),
                valid_status("TASK-7508"),
                queue_row("TASK-7508"),
                extra_files={
                    "anti_context.md": "# Anti-Context\n",
                    "artifacts/input.txt": b"fixture input\n",
                },
            )
            self.assertEqual(task_transaction.SUCCESS, code, payload)
            task_dir = ops_dir / "tasks" / "TASK-7508-data-readiness"
            self.assertEqual("# Anti-Context\n", (task_dir / "anti_context.md").read_text(encoding="utf-8"))
            self.assertEqual(b"fixture input\n", (task_dir / "artifacts" / "input.txt").read_bytes())

            with self.assertRaises(task_transaction.TaskTransactionError) as context:
                task_transaction.stage_task_folder(
                    ops_dir,
                    "TASK-7509-data-readiness",
                    task_markdown("TASK-7509"),
                    valid_status("TASK-7509"),
                    extra_files={"../escape.txt": "nope"},
                )
            self.assertEqual("unsafe_extra_task_file_path", context.exception.payload["reason"])
            self.assertFalse((ops_dir / "tasks" / "TASK-7509-data-readiness").exists())
            self.assertEqual([], list((ops_dir / "tasks").glob(".TASK-7509-data-readiness.staging.*")))

    def test_missing_task_markdown_reports_single_read_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            task_dir = ops_dir / "tasks" / "TASK-7510-data-readiness"
            task_dir.mkdir()
            write_text(task_dir / "status.json", task_transaction.json_bytes(valid_status("TASK-7510")).decode("utf-8"))

            failures = task_transaction.validate_task_folder(ops_dir, task_dir)

            self.assertEqual(["task_markdown_read_failed"], [item["reason"] for item in failures])


if __name__ == "__main__":
    unittest.main()

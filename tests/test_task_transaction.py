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


if __name__ == "__main__":
    unittest.main()

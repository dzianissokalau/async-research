"""Regression tests for the repo-backed prompt library."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.scripts import prompt_library


NOW = "2026-05-12T00:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def init_ops(root: Path) -> Path:
    ops_dir = root / "research_ops"
    code, payload = run_cli_json(["init", ops_dir, "--force"])
    if code != cli.SUCCESS:
        raise AssertionError(payload)
    return ops_dir


class PromptLibraryTests(unittest.TestCase):
    def test_prompt_library_init_dry_run_reports_plan_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))

            code, payload = prompt_library.init_library(ops_dir, now=NOW, dry_run=True)

            self.assertEqual(prompt_library.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual("prompt_library_init_planned", payload["action"])
            self.assertTrue(payload["dry_run"])
            self.assertTrue(payload["read_only"])
            self.assertTrue(payload["changed"])
            self.assertFalse((ops_dir / "prompts").exists())
            would_create = {item["relative_path"] for item in payload["would_create"]}
            self.assertIn("prompts/worker.md", would_create)
            self.assertIn("prompts/deliverable_critic.md", would_create)
            self.assertIn("prompts/drafts/worker.md", would_create)
            self.assertIn("prompts/versions/worker/worker_v1.0.md", would_create)
            self.assertEqual("prompts/versions.json", payload["would_write_manifest"]["relative_path"])
            self.assertTrue(any(item["prompt_id"] == "worker" for item in payload["would_append_history"]))
            self.assertEqual(
                payload["would_create"]
                + payload["would_update"]
                + payload["would_append_history"]
                + [payload["would_write_manifest"]],
                payload["would_write"],
            )

    def test_prompt_library_init_force_dry_run_on_fresh_workspace_reports_creates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))

            code, payload = prompt_library.init_library(
                ops_dir,
                force=True,
                now=NOW,
                dry_run=True,
            )

            self.assertEqual(prompt_library.SUCCESS, code, payload)
            self.assertTrue(payload["changed"])
            self.assertTrue(payload["force"])
            self.assertFalse((ops_dir / "prompts").exists())
            self.assertEqual([], payload["would_update"])
            would_create = {item["relative_path"] for item in payload["would_create"]}
            self.assertIn("prompts/worker.md", would_create)
            self.assertIn("prompts/drafts/worker.md", would_create)

    def test_prompt_library_init_force_dry_run_reports_updates_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            prompt_library.init_library(ops_dir, now=NOW)
            worker_path = ops_dir / "prompts" / "worker.md"
            before = worker_path.read_text(encoding="utf-8")

            code, payload = prompt_library.init_library(
                ops_dir,
                force=True,
                now="2026-05-12T01:00:00Z",
                dry_run=True,
            )

            self.assertEqual(prompt_library.SUCCESS, code, payload)
            self.assertTrue(payload["changed"])
            self.assertTrue(payload["force"])
            self.assertEqual(before, worker_path.read_text(encoding="utf-8"))
            would_update = {item["relative_path"] for item in payload["would_update"]}
            self.assertIn("prompts/worker.md", would_update)
            self.assertIn("prompts/drafts/worker.md", would_update)

    def test_prompt_library_init_dry_run_keeps_initialized_library_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            prompt_library.init_library(ops_dir, now=NOW)
            manifest_path = ops_dir / "prompts" / "versions.json"
            history_path = ops_dir / "prompts" / "history.jsonl"
            manifest_before = manifest_path.read_text(encoding="utf-8")
            history_before = history_path.read_text(encoding="utf-8")

            code, payload = prompt_library.init_library(
                ops_dir,
                now="2026-05-12T01:00:00Z",
                dry_run=True,
            )

            self.assertEqual(prompt_library.SUCCESS, code, payload)
            self.assertFalse(payload["changed"])
            self.assertEqual([], payload["would_create"])
            self.assertEqual([], payload["would_update"])
            self.assertEqual(manifest_before, manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(history_before, history_path.read_text(encoding="utf-8"))
            existing = {item["relative_path"] for item in payload["existing_files"]}
            self.assertIn("prompts/worker.md", existing)

    def test_public_prompt_cli_dry_run_missing_ops_dir_fails_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "missing_research_ops"

            code, payload = run_cli_json(["prompts", "init", ops_dir, "--dry-run"])

            self.assertEqual(prompt_library.INVALID_REQUEST, code)
            self.assertFalse(payload["ok"])
            self.assertEqual("ops_dir_missing", payload["reason"])
            self.assertTrue(payload["dry_run"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(ops_dir.exists())

    def test_prompt_library_init_and_validate_create_default_worker_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))

            code, payload = prompt_library.init_library(ops_dir, now=NOW)

            self.assertEqual(prompt_library.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue((ops_dir / "prompts" / "worker.md").exists())
            self.assertTrue((ops_dir / "prompts" / "drafts" / "worker.md").exists())
            self.assertTrue((ops_dir / "prompts" / "versions.json").exists())
            manifest = payload["manifest"]
            self.assertEqual("worker_v1.0", manifest["prompts"]["worker"]["active_version"])

            code, validation = prompt_library.validate_library(ops_dir, "worker")

            self.assertEqual(prompt_library.SUCCESS, code, validation)
            self.assertTrue(validation["ok"], validation)
            self.assertIn("deliverable_critic", manifest["prompts"])

    def test_invalid_draft_cannot_activate_without_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            prompt_library.init_library(ops_dir, now=NOW)
            draft = (ops_dir / "prompts" / "drafts" / "worker.md").read_text(encoding="utf-8")
            invalid = draft.replace("## Stop Conditions", "## Removed Stop Rules")

            code, saved = prompt_library.save_draft(
                ops_dir,
                "worker",
                invalid,
                reason="test invalid draft",
                author="tester",
                now=NOW,
            )
            self.assertEqual(prompt_library.SUCCESS, code, saved)
            self.assertFalse(saved["validation"]["ok"])
            active_before = (ops_dir / "prompts" / "worker.md").read_text(encoding="utf-8")

            code, blocked = prompt_library.activate_prompt(
                ops_dir,
                "worker",
                reason="should not activate",
                author="tester",
                now=NOW,
            )

            self.assertEqual(prompt_library.VALIDATION_FAILED, code)
            self.assertFalse(blocked["ok"])
            self.assertEqual("prompt_validation_failed", blocked["reason"])
            self.assertEqual(active_before, (ops_dir / "prompts" / "worker.md").read_text(encoding="utf-8"))

            code, activated = prompt_library.activate_prompt(
                ops_dir,
                "worker",
                reason="explicit invalid override",
                author="tester",
                allow_invalid=True,
                now="2026-05-12T01:00:00Z",
            )

            self.assertEqual(prompt_library.SUCCESS, code, activated)
            self.assertTrue(activated["ok"])
            self.assertTrue(activated["override"])
            self.assertEqual("worker_v1.1", activated["version"])

    def test_valid_activation_records_version_history_decision_and_schedule_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            prompt_library.init_library(ops_dir, now=NOW)
            draft_path = ops_dir / "prompts" / "drafts" / "worker.md"
            draft = draft_path.read_text(encoding="utf-8").replace(
                "Process at most one task or one scheduled unit of work per run.",
                "Process at most one task or one scheduled unit of work per run, then stop cleanly.",
            )
            prompt_library.save_draft(
                ops_dir,
                "worker",
                draft,
                reason="tighten stop rule",
                author="tester",
                now="2026-05-12T01:00:00Z",
            )
            (ops_dir / "schedules.json").write_text(
                json.dumps(
                    {
                        "jobs": [
                            {
                                "job_id": "worker-nightly",
                                "status": "enabled",
                                "prompt_id": "worker",
                                "prompt_version": "worker_v1.1",
                            }
                        ]
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            code, activated = prompt_library.activate_prompt(
                ops_dir,
                "worker",
                reason="tighten stop rule",
                author="tester",
                now="2026-05-12T02:00:00Z",
            )

            self.assertEqual(prompt_library.SUCCESS, code, activated)
            self.assertEqual("worker_v1.1", activated["version"])
            self.assertEqual("worker_v1.1", activated["validation"]["metadata"]["version"])
            self.assertEqual("2026-05-12T02:00:00Z", activated["validation"]["metadata"]["updated_at"])
            self.assertEqual("tester", activated["validation"]["metadata"]["updated_by"])
            active = (ops_dir / "prompts" / "worker.md").read_text(encoding="utf-8")
            self.assertIn("version: worker_v1.1", active)
            self.assertIn("activation_reason: tighten stop rule", active)
            history = prompt_library.read_history(ops_dir)
            self.assertTrue(any(row["action"] == "activated" and row["version"] == "worker_v1.1" for row in history))
            decisions = (ops_dir / "decisions.md").read_text(encoding="utf-8")
            self.assertIn("prompt:worker", decisions)
            snapshot = prompt_library.library_snapshot(ops_dir)
            worker = next(row for row in snapshot["prompts"] if row["prompt_id"] == "worker")
            self.assertEqual("worker-nightly", worker["schedule_bindings"][0]["job_id"])
            self.assertFalse(worker["has_draft_changes"])

    def test_public_prompt_cli_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))

            code, dry_run = run_cli_json(["prompts", "init", ops_dir, "--dry-run", "--now", NOW])
            self.assertEqual(cli.SUCCESS, code, dry_run)
            self.assertTrue(dry_run["dry_run"])
            self.assertTrue(dry_run["read_only"])
            self.assertFalse((ops_dir / "prompts").exists())

            code, init_payload = run_cli_json(["prompts", "init", ops_dir, "--now", NOW])
            self.assertEqual(cli.SUCCESS, code, init_payload)

            code, list_payload = run_cli_json(["prompts", "list", ops_dir])
            self.assertEqual(cli.SUCCESS, code, list_payload)
            self.assertTrue(list_payload["available"])
            self.assertTrue(any(row["prompt_id"] == "worker" for row in list_payload["prompts"]))

            code, validation = run_cli_json(["prompts", "validate", ops_dir, "worker"])
            self.assertEqual(cli.SUCCESS, code, validation)
            self.assertTrue(validation["ok"])


if __name__ == "__main__":
    unittest.main()

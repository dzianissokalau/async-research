"""Regression tests for recurring-job schedule intent manifests."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.scripts import prompt_library
from async_research_workflow.scripts import schedule_manifest


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


def file_snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class ScheduleManifestTests(unittest.TestCase):
    def test_schedule_manifest_init_requires_existing_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"

            code, payload = schedule_manifest.init_manifest(ops_dir, now=NOW)

            self.assertEqual(schedule_manifest.INVALID_REQUEST, code)
            self.assertFalse(payload["ok"])
            self.assertEqual("ops_dir_missing", payload["reason"])
            self.assertFalse(ops_dir.exists())

    def test_schedule_manifest_init_and_validate_create_default_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))

            code, payload = schedule_manifest.init_manifest(ops_dir, now=NOW)

            self.assertEqual(schedule_manifest.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue((ops_dir / "schedules.json").exists())
            jobs = payload["manifest"]["jobs"]
            self.assertEqual(6, len(jobs))
            self.assertTrue(all(job["status"] == "disabled" for job in jobs))
            self.assertEqual("worker_v1.0", next(job for job in jobs if job["job_id"] == "worker-loop")["prompt_binding"]["prompt_version"])

            code, validation = schedule_manifest.validate_schedule(ops_dir)

            self.assertEqual(schedule_manifest.SUCCESS, code, validation)
            self.assertTrue(validation["ok"], validation)
            self.assertEqual(6, validation["summary"]["job_count"])

    def test_upsert_and_status_changes_record_history_decision_and_prompt_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            prompt_library.init_library(ops_dir, now=NOW)
            schedule_manifest.init_manifest(ops_dir, now=NOW)

            code, updated = schedule_manifest.upsert_schedule(
                ops_dir,
                "worker-loop",
                description="Process one ready worker task.",
                cadence="hourly",
                prompt_id="worker",
                max_runtime_minutes=35,
                concurrency_key="worker",
                concurrency_limit=1,
                status="enabled",
                reason="make worker intent visible",
                author="tester",
                now="2026-05-12T01:00:00Z",
            )

            self.assertEqual(schedule_manifest.SUCCESS, code, updated)
            self.assertTrue(updated["ok"], updated)
            worker = next(job for job in updated["manifest"]["jobs"] if job["job_id"] == "worker-loop")
            self.assertEqual("enabled", worker["status"])
            self.assertEqual("worker_v1.0", worker["prompt_binding"]["prompt_version"])

            code, disabled = schedule_manifest.set_status(
                ops_dir,
                "worker-loop",
                "disabled",
                reason="pause before trigger-now dry run",
                author="tester",
                disabled_reason="pause before trigger-now dry run",
                now="2026-05-12T02:00:00Z",
            )

            self.assertEqual(schedule_manifest.SUCCESS, code, disabled)
            self.assertTrue(disabled["ok"], disabled)
            rows = schedule_manifest.read_history(ops_dir)
            self.assertTrue(any(row["action"] == "updated" and row["job_id"] == "worker-loop" for row in rows))
            self.assertTrue(any(row["action"] == "disabled" and row["job_id"] == "worker-loop" for row in rows))
            decisions = (ops_dir / "decisions.md").read_text(encoding="utf-8")
            self.assertIn("schedule:worker-loop", decisions)

    def test_upsert_auto_initializes_missing_manifest_before_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            prompt_library.init_library(ops_dir, now=NOW)

            code, updated = schedule_manifest.upsert_schedule(
                ops_dir,
                "worker-loop",
                description="Process one ready worker task.",
                cadence="hourly",
                prompt_id="worker",
                max_runtime_minutes=35,
                concurrency_key="worker",
                concurrency_limit=1,
                status="enabled",
                reason="create schedule manifest while updating worker intent",
                author="tester",
                now="2026-05-12T01:00:00Z",
            )

            self.assertEqual(schedule_manifest.SUCCESS, code, updated)
            self.assertTrue(updated["ok"], updated)
            self.assertTrue((ops_dir / "schedules.json").exists())
            self.assertEqual(6, len(updated["manifest"]["jobs"]))
            worker = next(job for job in updated["manifest"]["jobs"] if job["job_id"] == "worker-loop")
            self.assertEqual("enabled", worker["status"])
            self.assertEqual("worker_v1.0", worker["prompt_binding"]["prompt_version"])
            history_actions = [row["action"] for row in schedule_manifest.read_history(ops_dir)]
            self.assertIn("initialized", history_actions)
            self.assertIn("updated", history_actions)
            decisions = (ops_dir / "decisions.md").read_text(encoding="utf-8")
            self.assertIn("schedule:*", decisions)
            self.assertIn("schedule:worker-loop", decisions)

    def test_invalid_schedule_is_rejected_without_mutating_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            schedule_manifest.init_manifest(ops_dir, now=NOW)
            before = (ops_dir / "schedules.json").read_text(encoding="utf-8")

            code, result = schedule_manifest.upsert_schedule(
                ops_dir,
                "worker-loop",
                description="Process one ready worker task.",
                cadence="hourly",
                prompt_id="worker",
                max_runtime_minutes=0,
                concurrency_key="worker",
                concurrency_limit=1,
                status="enabled",
                reason="invalid runtime",
                author="tester",
            )

            self.assertEqual(schedule_manifest.VALIDATION_FAILED, code)
            self.assertFalse(result["ok"])
            self.assertEqual(before, (ops_dir / "schedules.json").read_text(encoding="utf-8"))

    def test_trigger_dry_run_previews_command_without_mutating_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            prompt_library.init_library(ops_dir, now=NOW)
            schedule_manifest.init_manifest(ops_dir, now=NOW)
            schedule_manifest.set_status(
                ops_dir,
                "worker-loop",
                "enabled",
                reason="preview worker trigger",
                author="tester",
                now=NOW,
            )
            before = file_snapshot(ops_dir)

            code, payload = schedule_manifest.trigger_dry_run(ops_dir, "worker-loop", now=NOW)

            self.assertEqual(schedule_manifest.SUCCESS, code, payload)
            self.assertTrue(payload["ok"], payload)
            self.assertTrue(payload["would_run"], payload)
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])
            self.assertTrue(payload["no_process_started"])
            self.assertEqual("local-20260512-000000-worker-loop", payload["run_id"])
            self.assertIn("codex exec --json", payload["planned_command"])
            self.assertIn("worker.md", payload["planned_command"])
            self.assertEqual("codex_exec", payload["planned_execution"]["runner"])
            self.assertTrue(payload["prompt"]["prompt_exists"])
            self.assertTrue(payload["readiness"]["checked"])
            self.assertTrue(payload["readiness"]["ok"], payload["readiness"])
            self.assertTrue(payload["concurrency"]["ok"], payload["concurrency"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_trigger_dry_run_blocks_disabled_jobs_before_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            prompt_library.init_library(ops_dir, now=NOW)
            schedule_manifest.init_manifest(ops_dir, now=NOW)

            code, payload = schedule_manifest.trigger_dry_run(ops_dir, "worker-loop", now=NOW)

            self.assertEqual(schedule_manifest.VALIDATION_FAILED, code, payload)
            self.assertFalse(payload["would_run"])
            self.assertEqual(["schedule_disabled"], [item["check"] for item in payload["blockers"]])
            self.assertFalse(payload["readiness"]["checked"])
            self.assertTrue(payload["no_process_started"])

    def test_trigger_dry_run_rejects_unknown_job_without_mutating_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            prompt_library.init_library(ops_dir, now=NOW)
            schedule_manifest.init_manifest(ops_dir, now=NOW)
            before = file_snapshot(ops_dir)

            code, payload = schedule_manifest.trigger_dry_run(ops_dir, "missing-job", now=NOW)

            self.assertEqual(schedule_manifest.INVALID_REQUEST, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("unknown_job", payload["reason"])
            self.assertEqual("missing-job", payload["job_id"])
            self.assertFalse(payload["would_run"])
            self.assertTrue(payload["blocked"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])
            self.assertTrue(payload["no_process_started"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_trigger_dry_run_blocks_missing_prompt_without_mutating_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            prompt_library.init_library(ops_dir, now=NOW)
            schedule_manifest.init_manifest(ops_dir, now=NOW)
            schedule_manifest.set_status(
                ops_dir,
                "worker-loop",
                "enabled",
                reason="preview worker trigger",
                author="tester",
                now=NOW,
            )
            (ops_dir / "prompts" / "worker.md").unlink()
            before = file_snapshot(ops_dir)

            code, payload = schedule_manifest.trigger_dry_run(ops_dir, "worker-loop", now=NOW)

            self.assertEqual(schedule_manifest.VALIDATION_FAILED, code, payload)
            self.assertFalse(payload["ok"])
            self.assertFalse(payload["would_run"])
            self.assertTrue(payload["blocked"])
            self.assertIn("prompt_file_missing", [item["check"] for item in payload["blockers"]])
            self.assertFalse(payload["readiness"]["checked"])
            self.assertFalse(payload["prompt"]["prompt_exists"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])
            self.assertTrue(payload["no_process_started"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_trigger_dry_run_blocks_active_concurrency_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            prompt_library.init_library(ops_dir, now=NOW)
            schedule_manifest.init_manifest(ops_dir, now=NOW)
            schedule_manifest.set_status(
                ops_dir,
                "worker-loop",
                "enabled",
                reason="preview worker trigger",
                author="tester",
                now=NOW,
            )
            run_dir = ops_dir / "run_artifacts" / "local-existing"
            run_dir.mkdir(parents=True)
            (run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "run_id": "local-existing",
                        "job_id": "worker-loop",
                        "concurrency_key": "worker",
                        "status": "running",
                        "started_at": NOW,
                        "finished_at": None,
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            before = file_snapshot(ops_dir)

            code, payload = schedule_manifest.trigger_dry_run(ops_dir, "worker-loop", now=NOW)

            self.assertEqual(schedule_manifest.VALIDATION_FAILED, code, payload)
            self.assertFalse(payload["would_run"])
            self.assertIn("concurrency_limit_reached", [item["check"] for item in payload["blockers"]])
            self.assertEqual(1, payload["concurrency"]["active_count"])
            self.assertFalse(payload["readiness"]["checked"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_public_schedule_cli_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            prompt_library.init_library(ops_dir, now=NOW)

            code, init_payload = run_cli_json(["schedules", "init", ops_dir, "--now", NOW])
            self.assertEqual(cli.SUCCESS, code, init_payload)
            self.assertTrue(init_payload["ok"])

            code, list_payload = run_cli_json(["schedules", "list", ops_dir])
            self.assertEqual(cli.SUCCESS, code, list_payload)
            self.assertTrue(list_payload["available"])
            self.assertTrue(any(row["job_id"] == "worker-loop" for row in list_payload["jobs"]))

            code, validation = run_cli_json(["schedules", "validate", ops_dir])
            self.assertEqual(cli.SUCCESS, code, validation)
            self.assertTrue(validation["ok"], validation)

            code, enabled = run_cli_json(
                [
                    "schedules",
                    "set-status",
                    ops_dir,
                    "worker-loop",
                    "--status",
                    "enabled",
                    "--message",
                    "show enable intent",
                    "--author",
                    "tester",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, enabled)
            self.assertTrue(enabled["ok"], enabled)

            code, preview = run_cli_json(["schedules", "trigger-dry-run", ops_dir, "worker-loop", "--now", NOW])
            self.assertEqual(cli.SUCCESS, code, preview)
            self.assertTrue(preview["would_run"], preview)
            self.assertEqual("local-20260512-000000-worker-loop", preview["run_id"])
            self.assertFalse((ops_dir / "run_artifacts").exists())


if __name__ == "__main__":
    unittest.main()

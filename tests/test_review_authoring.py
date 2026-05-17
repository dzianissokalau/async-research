"""Regression tests for public review authoring commands."""

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
from async_research_workflow.scripts import review_authoring
from async_research_workflow.scripts.aggregate_reviews import extract_json_object
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


class ReviewAuthoringTests(unittest.TestCase):
    def init_ops(self, root: Path, *, template: str = "generic") -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--template", template, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        return ops_dir

    def write_task(
        self,
        ops_dir: Path,
        task_name: str = "TASK-9001-review-authoring",
        *,
        status_value: str = "awaiting_review",
        worker_output: str | None = "Worker completed bounded fixture output.\n",
    ) -> Path:
        task_id = task_name.split("-review")[0]
        task_dir = ops_dir / "tasks" / task_name
        previous_status = "in_progress" if status_value in {"awaiting_review", "single_review", "panel_review"} else None
        status = {
            "schema_version": "1.0",
            "id": task_id,
            "title": "Review authoring fixture",
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
            "requires_human": False,
            "budget": {
                "max_api_usd": 0,
                "max_compute_usd": 0,
            },
            "result": {
                "recommendation": None,
                "claim_strength": "none",
                "followup_count": 0,
            },
        }
        write_json(task_dir / "status.json", apply_default_versions(status))
        if worker_output is not None:
            (task_dir / "worker_output.md").write_text(worker_output, encoding="utf-8")
        return task_dir

    def test_review_draft_previews_conservative_scaffold_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = self.write_task(self.init_ops(Path(tmp)))

            code, payload = run_cli_json(["review", "draft", task_dir, "--role", "primary"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("review_draft_previewed", payload["action"])
            self.assertFalse(payload["written"])
            self.assertTrue(payload["would_write"])
            self.assertEqual("needs_human", payload["review"]["decision"])
            self.assertEqual("none", payload["review"]["claim_strength"])
            self.assertIn("```json", payload["review_markdown"])
            self.assertFalse((task_dir / "reviews" / "primary.md").exists())

    def test_review_draft_write_protects_existing_review_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = self.write_task(self.init_ops(Path(tmp)))

            code, written = run_cli_json(["review", "draft", task_dir, "--role", "primary", "--write"])
            self.assertEqual(cli.SUCCESS, code, written)
            self.assertEqual("review_draft_written", written["action"])
            review_path = task_dir / "reviews" / "primary.md"
            self.assertTrue(review_path.exists())
            first_text = review_path.read_text(encoding="utf-8")

            code, refused = run_cli_json(["review", "draft", task_dir, "--role", "primary", "--write"])
            self.assertEqual(review_authoring.TARGET_EXISTS, code, refused)
            self.assertEqual("target_exists", refused["reason"])
            self.assertEqual(first_text, review_path.read_text(encoding="utf-8"))

            code, forced = run_cli_json(["review", "draft", task_dir, "--role", "primary", "--write", "--force"])
            self.assertEqual(cli.SUCCESS, code, forced)
            self.assertEqual("review_draft_written", forced["action"])

    def test_review_draft_write_requires_reviewable_task_but_preview_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = self.write_task(self.init_ops(Path(tmp)), status_value="ready_for_worker", worker_output=None)

            code, preview = run_cli_json(["review", "draft", task_dir, "--role", "primary"])
            self.assertEqual(cli.SUCCESS, code, preview)
            self.assertEqual("review_draft_previewed", preview["action"])
            self.assertFalse((task_dir / "reviews" / "primary.md").exists())

            code, refused = run_cli_json(["review", "draft", task_dir, "--role", "primary", "--write"])

            self.assertEqual(review_authoring.MALFORMED, code, refused)
            self.assertEqual("task_not_reviewable", refused["reason"])
            self.assertFalse((task_dir / "reviews" / "primary.md").exists())

    def test_default_review_draft_aggregates_to_needs_human(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = self.write_task(self.init_ops(Path(tmp)))
            code, draft = run_cli_json(["review", "draft", task_dir, "--role", "primary", "--write"])
            self.assertEqual(cli.SUCCESS, code, draft)

            code, aggregate = run_cli_json(["review", "aggregate", task_dir, "--dry-run"])

            self.assertEqual(cli.SUCCESS, code, aggregate)
            self.assertEqual("needs_human", aggregate["aggregate_decision"])
            self.assertTrue(aggregate["human_gate_required"])

    def test_review_submit_requires_explicit_decision_claim_strength_and_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = self.write_task(self.init_ops(Path(tmp)))

            code, payload = run_cli_json(["review", "submit", task_dir, "--role", "primary"])

            self.assertEqual(review_authoring.MISSING_REQUIRED, code, payload)
            self.assertEqual("missing_required_flags", payload["reason"])
            self.assertEqual(["--decision", "--claim-strength", "--confidence"], payload["missing_flags"])

    def test_review_submit_missing_role_returns_json_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = self.write_task(self.init_ops(Path(tmp)))

            code, payload = run_cli_json(
                [
                    "review",
                    "submit",
                    task_dir,
                    "--decision",
                    "needs_human",
                    "--claim-strength",
                    "none",
                    "--confidence",
                    "0.5",
                ]
            )

            self.assertEqual(review_authoring.MISSING_REQUIRED, code, payload)
            self.assertEqual("missing_required_flags", payload["reason"])
            self.assertEqual(["--role"], payload["missing_flags"])

    def test_review_submit_refuses_non_reviewable_task_state_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = self.write_task(self.init_ops(Path(tmp)), status_value="ready_for_worker", worker_output=None)

            command = [
                "review",
                "submit",
                task_dir,
                "--role",
                "primary",
                "--decision",
                "needs_human",
                "--claim-strength",
                "none",
                "--confidence",
                "0.5",
            ]
            code, payload = run_cli_json(command)

            self.assertEqual(review_authoring.MALFORMED, code, payload)
            self.assertEqual("task_not_reviewable", payload["reason"])
            self.assertEqual("ready_for_worker", payload["status"])
            self.assertEqual(["awaiting_review", "panel_review", "single_review"], payload["allowed_statuses"])
            self.assertIn("worker_output.md", payload["worker_output_path"])
            self.assertFalse((task_dir / "reviews" / "primary.md").exists())

            code, dry = run_cli_json([*command, "--dry-run"])

            self.assertEqual(review_authoring.MALFORMED, code, dry)
            self.assertEqual("task_not_reviewable", dry["reason"])
            self.assertFalse((task_dir / "reviews" / "primary.md").exists())

    def test_review_submit_requires_worker_output_for_reviewable_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = self.write_task(self.init_ops(Path(tmp)), worker_output=None)

            code, payload = run_cli_json(
                [
                    "review",
                    "submit",
                    task_dir,
                    "--role",
                    "primary",
                    "--decision",
                    "needs_human",
                    "--claim-strength",
                    "none",
                    "--confidence",
                    "0.5",
                ]
            )

            self.assertEqual(review_authoring.MALFORMED, code, payload)
            self.assertEqual("worker_output_missing", payload["reason"])
            self.assertEqual("awaiting_review", payload["status"])
            self.assertFalse((task_dir / "reviews" / "primary.md").exists())

    def test_review_submit_requires_non_empty_worker_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = self.write_task(self.init_ops(Path(tmp)), worker_output=" \n\t\n")

            code, payload = run_cli_json(
                [
                    "review",
                    "submit",
                    task_dir,
                    "--role",
                    "primary",
                    "--decision",
                    "needs_human",
                    "--claim-strength",
                    "none",
                    "--confidence",
                    "0.5",
                ]
            )

            self.assertEqual(review_authoring.MALFORMED, code, payload)
            self.assertEqual("worker_output_empty", payload["reason"])
            self.assertFalse((task_dir / "reviews" / "primary.md").exists())

    def test_schema_invalid_status_refuses_to_write_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = self.write_task(self.init_ops(Path(tmp)))
            write_json(task_dir / "status.json", {})

            code, payload = run_cli_json(["review", "draft", task_dir, "--role", "primary", "--write"])

            self.assertEqual(review_authoring.MALFORMED, code, payload)
            self.assertEqual("status_schema_validation_failed", payload["reason"])
            self.assertFalse((task_dir / "reviews" / "primary.md").exists())

    def test_review_submit_dry_run_and_write_use_same_payload_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = self.write_task(self.init_ops(Path(tmp)))
            command = [
                "review",
                "submit",
                task_dir,
                "--role",
                "primary",
                "--decision",
                "needs_revision",
                "--claim-strength",
                "suggestive",
                "--confidence",
                "0.75",
                "--concern",
                "Needs a tighter source caveat.",
            ]

            code, dry = run_cli_json([*command, "--dry-run"])
            self.assertEqual(cli.SUCCESS, code, dry)
            self.assertEqual("review_submit_dry_run", dry["action"])
            self.assertFalse((task_dir / "reviews" / "primary.md").exists())

            code, written = run_cli_json(command)
            self.assertEqual(cli.SUCCESS, code, written)
            review_path = task_dir / "reviews" / "primary.md"
            payload = extract_json_object(review_path.read_text(encoding="utf-8"))
            self.assertEqual("primary", payload["reviewer_role"])
            self.assertEqual("needs_revision", payload["decision"])
            self.assertEqual("suggestive", payload["claim_strength"])
            self.assertEqual(["Needs a tighter source caveat."], payload["main_concerns"])

            code, refused = run_cli_json(command)
            self.assertEqual(review_authoring.TARGET_EXISTS, code, refused)
            self.assertEqual("target_exists", refused["reason"])

    def test_review_submit_warns_when_claim_strength_exceeds_generic_artifact_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = self.write_task(self.init_ops(Path(tmp)))

            code, payload = run_cli_json(
                [
                    "review",
                    "submit",
                    task_dir,
                    "--role",
                    "primary",
                    "--decision",
                    "accept",
                    "--claim-strength",
                    "moderate",
                    "--confidence",
                    "0.8",
                    "--dry-run",
                ]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("suggestive", payload["claim_strength_cap"]["max_claim_strength"])
            self.assertTrue(payload["claim_strength_cap"]["warning"])
            self.assertIn("structured result artifacts", payload["claim_strength_cap"]["next_step"])
            self.assertTrue(any(item["warning"] == "claim_strength_exceeds_cap" for item in payload["warnings"]))

    def test_review_submit_accepts_real_estate_reviewable_task_with_worker_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = self.write_task(
                self.init_ops(Path(tmp), template="real-estate"),
                "TASK-9002-review-authoring",
                worker_output="Real-estate worker completed a bounded fixture output.\n",
            )

            code, submitted = run_cli_json(
                [
                    "review",
                    "submit",
                    task_dir,
                    "--role",
                    "primary",
                    "--decision",
                    "needs_human",
                    "--claim-strength",
                    "none",
                    "--confidence",
                    "0.5",
                ]
            )

            self.assertEqual(cli.SUCCESS, code, submitted)
            self.assertEqual("review_submitted", submitted["action"])
            self.assertTrue((task_dir / "reviews" / "primary.md").exists())

    def test_review_submit_payload_can_be_aggregated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = self.write_task(self.init_ops(Path(tmp)))
            code, submitted = run_cli_json(
                [
                    "review",
                    "submit",
                    task_dir,
                    "--role",
                    "primary",
                    "--decision",
                    "needs_revision",
                    "--claim-strength",
                    "suggestive",
                    "--confidence",
                    "0.75",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, submitted)

            code, aggregate = run_cli_json(["review", "aggregate", task_dir, "--dry-run", "--record-review-start"])

            self.assertEqual(cli.SUCCESS, code, aggregate)
            self.assertEqual("needs_revision", aggregate["aggregate_decision"])
            self.assertEqual("reviewer_requested_revision", aggregate["routing_reason"])

    def test_review_submit_warns_and_aggregate_caps_generic_artifact_claim_strength(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = self.write_task(
                self.init_ops(Path(tmp)),
                "TASK-9003-review-authoring",
                worker_output="Coffee pilot generic readiness memo with no structured result summary.\n",
            )

            command = [
                "review",
                "submit",
                task_dir,
                "--role",
                "primary",
                "--decision",
                "accept",
                "--claim-strength",
                "moderate",
                "--confidence",
                "0.8",
            ]
            code, dry = run_cli_json([*command, "--dry-run"])
            self.assertEqual(cli.SUCCESS, code, dry)
            self.assertTrue(dry["claim_strength_cap"]["warning"])
            self.assertEqual("suggestive", dry["claim_strength_cap"]["max_claim_strength"])
            self.assertIn("claim_strength_exceeds_cap", dry["warnings"][0]["warning"])

            code, submitted = run_cli_json(command)
            self.assertEqual(cli.SUCCESS, code, submitted)
            self.assertTrue(submitted["claim_strength_cap"]["warning"])

            code, aggregate = run_cli_json(["review", "aggregate", task_dir, "--record-review-start"])

            self.assertEqual(cli.SUCCESS, code, aggregate)
            self.assertEqual("accepted", aggregate["aggregate_decision"])
            self.assertEqual("moderate", aggregate["requested_aggregate_claim_strength"])
            self.assertEqual("suggestive", aggregate["aggregate_claim_strength"])
            self.assertTrue(aggregate["claim_strength_cap"]["applied"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("accepted", status["status"])
            self.assertEqual("suggestive", status["result"]["claim_strength"])
            result_acceptance = json.loads((task_dir / "review_panel" / "result_acceptance.json").read_text(encoding="utf-8"))
            self.assertEqual("suggestive", result_acceptance["claim_strength"])
            self.assertEqual("suggestive", result_acceptance["max_claim_strength"])

    def test_role_mismatch_is_reported_by_authoring_validation(self) -> None:
        payload = review_authoring.review_payload(
            role="methodology",
            decision="accept",
            claim_strength="suggestive",
            confidence=0.8,
        )

        errors = review_authoring.validate_payload_for_role(Path("reviews/primary.md"), payload, "primary")

        self.assertTrue(any("does not match target role" in error for error in errors))

    def test_non_force_write_does_not_overwrite_concurrent_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "reviews" / "primary.md"

            def racing_link(source: object, target: object) -> None:
                Path(target).write_text("Concurrent review.\n", encoding="utf-8")
                raise FileExistsError

            with mock.patch.object(review_authoring.os, "link", side_effect=racing_link):
                ok, error = review_authoring.write_review(review_path, "New review.\n", force=False)

            self.assertFalse(ok)
            self.assertEqual("target_exists", error["reason"] if error else None)
            self.assertEqual("Concurrent review.\n", review_path.read_text(encoding="utf-8"))
            self.assertEqual([], list(review_path.parent.glob(".primary.md.*.tmp")))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support is unavailable")
    def test_non_force_write_treats_dangling_symlink_as_existing_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "reviews" / "primary.md"
            review_path.parent.mkdir()
            review_path.symlink_to(Path(tmp) / "missing-target")

            ok, error = review_authoring.write_review(review_path, "New review.\n", force=False)

            self.assertFalse(ok)
            self.assertEqual("target_exists", error["reason"] if error else None)
            self.assertTrue(review_path.is_symlink())


if __name__ == "__main__":
    unittest.main()

"""Regression tests for public review authoring commands."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

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
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        return ops_dir

    def write_task(self, ops_dir: Path, task_name: str = "TASK-9001-review-authoring") -> Path:
        task_id = task_name.split("-review")[0]
        task_dir = ops_dir / "tasks" / task_name
        status = {
            "schema_version": "1.0",
            "id": task_id,
            "title": "Review authoring fixture",
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
            "result": {
                "recommendation": None,
                "claim_strength": "none",
                "followup_count": 0,
            },
        }
        write_json(task_dir / "status.json", apply_default_versions(status))
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

    def test_role_mismatch_is_reported_by_authoring_validation(self) -> None:
        payload = review_authoring.review_payload(
            role="methodology",
            decision="accept",
            claim_strength="suggestive",
            confidence=0.8,
        )

        errors = review_authoring.validate_payload_for_role(Path("reviews/primary.md"), payload, "primary")

        self.assertTrue(any("does not match target role" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

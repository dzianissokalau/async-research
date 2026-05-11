"""Contract-level regression tests for async research workflow gates."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.resources import schema_path
from async_research_workflow.scripts import (
    aggregate_reviews,
    autonomy_readiness_gate,
    check_schema_versions,
    recover_status_json,
    simulate_scheduled_week,
    task_lock,
    update_accepted_outputs_index,
    validate_json_artifact,
    validate_result_acceptance,
    validate_transition,
)
from async_research_workflow.scripts.version_metadata import apply_default_versions


NOW = "2026-05-04T00:00:00Z"
TASK_ID_RE = re.compile(r"TASK-[0-9]{4}")


def readiness_fixture_args(*extra: str) -> list[str]:
    # Readiness-gate tests suppress unrelated metrics freshness blockers unless
    # metrics freshness is the behavior under test.
    return [
        "--dry-run",
        "--no-daily-status",
        "--now",
        NOW,
        "--metrics-stale-hours",
        "100000",
        *extra,
    ]


def run_json(entrypoint, argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = entrypoint.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class WorkflowRegressionTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_json(cli, ["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        self.assertTrue(payload["ok"])
        return ops_dir

    def status_payload(self, task_id: str, **overrides) -> dict:
        match = TASK_ID_RE.search(task_id)
        status_id = match.group(0) if match else task_id
        payload = {
            "schema_version": "1.0",
            "id": status_id,
            "title": f"Regression task {status_id}",
            "type": "data_readiness",
            "status": "ready_for_worker",
            "previous_status": "ready_for_planning",
            "last_transition_reason": "regression_test_fixture",
            "priority": 3,
            "revision_count": 0,
            "max_revisions": 1,
            "revision_limit_hit": False,
            "created_at": NOW,
            "updated_at": NOW,
            "allowed_paths": [f"research_ops/tasks/{task_id}"],
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
        payload.update(overrides)
        return apply_default_versions(payload)

    def write_status(self, ops_dir: Path, task_id: str, **overrides) -> Path:
        task_dir = ops_dir / "tasks" / task_id
        write_json(task_dir / "status.json", self.status_payload(task_id, **overrides))
        return task_dir

    def test_malformed_status_recovers_to_needs_human_and_quarantines_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = ops_dir / "tasks" / "TASK-2001-malformed-status"
            task_dir.mkdir(parents=True)
            status_path = task_dir / "status.json"
            status_path.write_text('{"schema_version": "1.0", broken', encoding="utf-8")

            code, payload = run_json(recover_status_json, [task_dir])

            self.assertEqual(recover_status_json.SUCCESS, code, payload)
            self.assertEqual("recovered", payload["action"])
            self.assertEqual("malformed_status_json", payload["failure_reason"])
            recovered = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual("needs_human", recovered["status"])
            self.assertTrue(recovered["requires_human"])
            self.assertEqual("status_json_recovery", recovered["last_transition_reason"])
            self.assertTrue(Path(payload["quarantine"]).exists())

            code, transition = run_json(validate_transition, [task_dir])
            self.assertEqual(validate_transition.SUCCESS, code, transition)
            code, schema = run_json(validate_json_artifact, [status_path, "--schema", schema_path("task_status.schema.json")])
            self.assertEqual(validate_json_artifact.SUCCESS, code, schema)

    def test_missing_schema_version_is_rejected_by_schema_and_version_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_status(ops_dir, "TASK-2002-missing-schema")
            status_path = task_dir / "status.json"
            payload = json.loads(status_path.read_text(encoding="utf-8"))
            payload.pop("schema_version")
            write_json(status_path, payload)

            code, schema_result = run_json(validate_json_artifact, [status_path, "--schema", schema_path("task_status.schema.json")])
            self.assertEqual(validate_json_artifact.VALIDATION_FAILED, code, schema_result)
            self.assertEqual("schema_validation_failed", schema_result["reason"])
            self.assertIn("$.schema_version", {error["path"] for error in schema_result["errors"]})

            code, version_result = run_json(check_schema_versions, [ops_dir])
            self.assertEqual(check_schema_versions.INVALID, code, version_result)
            self.assertEqual("missing_schema_version", version_result["errors"][0]["reason"])

    def test_task_status_schema_accepts_catalog_promotion_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_status(
                ops_dir,
                "TASK-2006-catalog-promotion",
                catalog_idea_id="IDEA-2006",
                catalog_promotion={
                    "catalog_idea_id": "IDEA-2006",
                    "idempotency_key": f"IDEA-2006:data_readiness:{'a' * 64}",
                    "reserved_task_id": "TASK-2006",
                    "reservation_policy": "catalog_task_id_reservation_v2.5",
                },
            )

            code, schema = run_json(
                validate_json_artifact,
                [task_dir / "status.json", "--schema", schema_path("task_status.schema.json")],
            )

            self.assertEqual(validate_json_artifact.SUCCESS, code, schema)

    def test_invalid_status_transition_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_status(
                ops_dir,
                "TASK-2003-invalid-transition",
                previous_status="accepted",
                status="ready_for_worker",
                last_transition_reason="illegal_reopen_without_synthesis",
            )

            code, payload = run_json(validate_transition, [task_dir])

            self.assertEqual(validate_transition.INVALID_TRANSITION, code, payload)
            self.assertEqual("invalid_transition", payload["reason"])
            self.assertEqual(["synthesized"], payload["allowed_next"])

    def test_missing_reviewer_metadata_blocks_review_aggregation(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_status(
                ops_dir,
                "TASK-2004-review-metadata",
                previous_status="in_progress",
                status="awaiting_review",
                last_transition_reason="worker_submitted_for_review",
            )
            review = {
                "reviewer_role": "primary",
                "decision": "accept",
                "claim_strength": "suggestive",
                "framework_versions": {"result_acceptance": "result_acceptance_v1.0"},
                "main_concerns": [],
                "confidence": 0.9,
            }
            review_path = task_dir / "reviews" / "primary.md"
            review_path.parent.mkdir(parents=True)
            review_path.write_text("```json\n" + json.dumps(review, indent=2) + "\n```\n", encoding="utf-8")

            code, payload = run_json(aggregate_reviews, [task_dir, "--dry-run"])

            self.assertEqual(aggregate_reviews.VALIDATION_FAILED, code, payload)
            self.assertEqual("review_validation_failed", payload["reason"])
            self.assertTrue(any("prompt_version is required" in error for error in payload["errors"]))

    def test_stale_data_source_blocks_readiness(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_status(
                ops_dir,
                "TASK-2005-stale-source",
                type="experiment_plan",
                data_audit_refs=["DS-0001"],
            )
            (ops_dir / "data_source_audit.md").write_text(
                "\n".join(
                    [
                        "# Data Source Audit Register",
                        "",
                        "Schema version: 1.0",
                        "",
                        "| source_id | source_name | url_or_domain | publisher_owner | source_tier | approval_status | approved_use_cases | blocked_use_cases | freshness_window_days | known_limitations | citation_requirements | last_reviewed | approved_by | review_notes |",
                        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                        "| DS-0001 | Test Source | https://example.test | Test Publisher | tier_1_official | approved | accepted_evidence | none | 30 | none | cite DS-0001 | 2025-01-01 | test | stale fixture |",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = run_json(
                autonomy_readiness_gate,
                [ops_dir, *readiness_fixture_args("--stale-source-days", "90")],
            )

            self.assertEqual(autonomy_readiness_gate.HUMAN_REQUIRED, code, payload)
            self.assertEqual("human_required", payload["decision"])
            blocker = next(item for item in payload["blockers"] if item["check"] == "stale_or_unaudited_data_sources")
            self.assertEqual("source_audit_stale", blocker["details"][0]["reason"])
            self.assertEqual("DS-0001", blocker["details"][0]["source_id"])

    def test_stale_accepted_memory_reuse_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            (ops_dir / "accepted_outputs_index.md").write_text(
                "\n".join(
                    [
                        "| accepted_date | task_id | title | key_finding | claim_type | freshness_window_days | next_recheck_date | revalidation_status | source_ids | claim_strength | caveats | followups | supersedes | superseded_by | evidence_link |",
                        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                        "| 2025-01-01 | TASK-1001 | Old evidence | Old finding | general | 30 | 2025-02-01 | stale | none | moderate | none | none | none | none | tasks/TASK-1001/worker_output.md |",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            artifact = ops_dir / "tasks" / "TASK-2006-new-work" / "worker_output.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("This proposed output relies on TASK-1001 as current evidence.\n", encoding="utf-8")

            code, payload = run_json(update_accepted_outputs_index, ["check-memory-use", ops_dir, artifact, "--now", NOW])

            self.assertEqual(update_accepted_outputs_index.INVALID, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("stale_accepted_memory_reuse", payload["reason"])
            self.assertEqual("TASK-1001", payload["stale_refs"][0]["task_id"])

    def test_fresh_lock_contention_returns_locked_without_stealing_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp) / "TASK-2007-lock"
            task_dir.mkdir()

            code, first = run_json(task_lock, ["acquire", task_dir, "--owner", "worker-a"])
            self.assertEqual(task_lock.SUCCESS, code, first)
            code, second = run_json(task_lock, ["acquire", task_dir, "--owner", "worker-b"])

            self.assertEqual(task_lock.LOCKED, code, second)
            self.assertEqual("locked", second["reason"])
            self.assertEqual("worker-a", second["owner"]["owner"])

    def test_budget_pressure_blocks_readiness_loop(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            with (ops_dir / "cost_ledger.csv").open("w", encoding="utf-8", newline="") as handle:
                fieldnames = [
                    "date",
                    "item_id",
                    "role",
                    "model_or_tool",
                    "usage_source",
                    "input_tokens",
                    "output_tokens",
                    "total_tokens",
                    "input_usd",
                    "output_usd",
                    "api_usd",
                    "compute_usd",
                    "amount_usd",
                    "human_minutes",
                    "status",
                    "actual",
                    "monthly_budget_usd",
                    "weekly_budget_usd",
                    "notes",
                ]
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow(
                    {
                        "date": "2026-05-04",
                        "item_id": "COST-0001",
                        "role": "worker",
                        "model_or_tool": "test",
                        "usage_source": "fixture",
                        "total_tokens": "100",
                        "amount_usd": "90",
                        "status": "recorded",
                        "actual": "true",
                        "monthly_budget_usd": "100",
                        "weekly_budget_usd": "100",
                        "notes": "budget pressure fixture",
                    }
                )

            code, payload = run_json(
                autonomy_readiness_gate,
                [ops_dir, *readiness_fixture_args()],
            )

            self.assertEqual(autonomy_readiness_gate.SKIP_LOOP, code, payload)
            self.assertEqual("skip_loop", payload["decision"])
            blocker = next(item for item in payload["blockers"] if item["check"] == "budget_pressure")
            self.assertEqual(0.9, blocker["details"]["cost"]["monthly_usage_ratio"])

    def test_accepted_update_ignores_worker_metadata_when_extracting_key_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_status(
                ops_dir,
                "TASK-2008-metadata-finding",
                previous_status="panel_review",
                status="accepted",
                last_transition_reason="aggregate_reviews_all_required_reviewers_accept",
                result={
                    "recommendation": "ready",
                    "claim_strength": "suggestive",
                    "followup_count": 0,
                },
            )
            task_dir.joinpath("worker_output.md").write_text(
                "\n".join(
                    [
                        "prompt_version: worker_v1.0",
                        "framework_versions:",
                        "  result_acceptance: result_acceptance_v1.0",
                        "",
                        "## Summary",
                        "",
                        "- Address normalization methodology is ready for DS-0001 experiment planning.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = run_json(update_accepted_outputs_index, ["update", ops_dir, "--now", NOW])

            self.assertEqual(update_accepted_outputs_index.SUCCESS, code, payload)
            rows = update_accepted_outputs_index.read_index_rows(ops_dir / "accepted_outputs_index.md")
            row = next(item for item in rows if item["task_id"] == "TASK-2008")
            self.assertEqual("Address normalization methodology is ready for DS-0001 experiment planning.", row["key_finding"])
            self.assertNotIn("prompt_version", row["key_finding"])

    def test_accepted_update_deduplicates_and_normalizes_followups(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_status(
                ops_dir,
                "TASK-2009-followup-dedupe",
                previous_status="panel_review",
                status="accepted",
                last_transition_reason="aggregate_reviews_all_required_reviewers_accept",
                result={
                    "recommendation": "ready",
                    "claim_strength": "suggestive",
                    "key_finding": "Address normalization work is ready for reuse",
                    "followups": [
                        "Draft address normalization methodology",
                        "TASK: Draft address normalization methodology.",
                    ],
                },
            )
            task_dir.joinpath("worker_output.md").write_text(
                "\n".join(
                    [
                        "Address normalization work is ready for reuse.",
                        "",
                        "## Follow-ups",
                        "",
                        "- TASK: Draft address normalization methodology.",
                        "- TASK: Pin DS-0002 series IDs in experiment_plan artifact.",
                        "- Add a freshness check to surface DS-0003 provisional periods.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            write_json(
                task_dir / "review_panel" / "result_acceptance.json",
                {
                    "followups": [
                        {
                            "reason": "Draft address normalization methodology",
                            "required_artifact": "methodology note",
                            "priority": 3,
                            "human_approval_needed": False,
                            "required_before_memo_use": False,
                        },
                        {
                            "reason": "TASK: Pin DS-0002 series IDs in experiment_plan artifact",
                            "required_artifact": "experiment plan",
                            "priority": 3,
                            "human_approval_needed": False,
                            "required_before_memo_use": False,
                        },
                    ]
                },
            )

            code, payload = run_json(update_accepted_outputs_index, ["update", ops_dir, "--now", NOW])

            self.assertEqual(update_accepted_outputs_index.SUCCESS, code, payload)
            rows = update_accepted_outputs_index.read_index_rows(ops_dir / "accepted_outputs_index.md")
            row = next(item for item in rows if item["task_id"] == "TASK-2009")
            followups = row["followups"]
            self.assertEqual(1, followups.count("Draft address normalization methodology"))
            self.assertEqual(1, followups.count("Pin DS-0002 series IDs in experiment_plan artifact"))
            self.assertIn("Add a freshness check to surface DS-0003 provisional periods", followups)
            self.assertNotIn("TASK:", followups)

    def test_review_aggregate_explains_missing_review_state_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_status(
                ops_dir,
                "TASK-2010-awaiting-review-friction",
                previous_status="in_progress",
                status="awaiting_review",
                last_transition_reason="worker_submitted_for_review",
                result={
                    "recommendation": "ready",
                    "claim_strength": "suggestive",
                    "key_finding": "Reviewable output is present",
                },
            )
            task_dir.joinpath("worker_output.md").write_text("Reviewable output is present.\n", encoding="utf-8")
            write_json(
                task_dir / "reviews" / "primary.md",
                {
                    "reviewer_role": "primary",
                    "decision": "accept",
                    "claim_strength": "suggestive",
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

            code, payload = run_json(aggregate_reviews, [task_dir, "--dry-run"])

            self.assertEqual(aggregate_reviews.VALIDATION_FAILED, code, payload)
            self.assertEqual("status_validation_failed", payload["reason"])
            self.assertEqual("awaiting_review", payload["current_status"])
            self.assertEqual("accepted", payload["attempted_route"])
            self.assertEqual("single_review", payload["suggested_intermediate_status"])
            self.assertIn("awaiting_review -> single_review", payload["next_step"])
            self.assertIn("--record-review-start", payload["next_step"])

    def test_review_aggregate_can_record_missing_review_start_transition(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_status(
                ops_dir,
                "TASK-2013-record-review-start",
                previous_status="in_progress",
                status="awaiting_review",
                last_transition_reason="worker_submitted_for_review",
                result={
                    "recommendation": "ready",
                    "claim_strength": "suggestive",
                    "key_finding": "Reviewable output is present",
                },
            )
            task_dir.joinpath("worker_output.md").write_text("Reviewable output is present.\n", encoding="utf-8")
            write_json(
                task_dir / "reviews" / "primary.md",
                {
                    "reviewer_role": "primary",
                    "decision": "accept",
                    "claim_strength": "suggestive",
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

            code, payload = run_json(aggregate_reviews, [task_dir, "--record-review-start"])

            self.assertEqual(aggregate_reviews.SUCCESS, code, payload)
            self.assertEqual("accepted", payload["aggregate_decision"])
            self.assertEqual(
                {
                    "from_status": "awaiting_review",
                    "to_status": "single_review",
                    "reason": "review_start_recorded_before_aggregate",
                    "recorded_before_aggregate": True,
                },
                payload["review_start_transition"],
            )
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("single_review", status["previous_status"])
            self.assertEqual("accepted", status["status"])
            self.assertIn("review_started_at", status)
            aggregate = json.loads((task_dir / "review_panel" / "aggregate.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["review_start_transition"], aggregate["review_start_transition"])

    def test_result_acceptance_uses_accepted_index_freshness_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_status(
                ops_dir,
                "TASK-2011-default-freshness",
                type="data_readiness",
                previous_status="panel_review",
                status="accepted",
                last_transition_reason="aggregate_reviews_all_required_reviewers_accept",
                result={
                    "recommendation": "ready",
                    "claim_strength": "suggestive",
                    "key_finding": "Default freshness should match accepted memory index",
                    "followup_count": 0,
                },
            )
            task_dir.joinpath("worker_output.md").write_text(
                "Default freshness should match accepted memory index.\n",
                encoding="utf-8",
            )
            write_json(
                task_dir / "review_panel" / "aggregate.json",
                {
                    "aggregate_decision": "accepted",
                    "aggregate_claim_strength": "suggestive",
                    "tier": 1,
                    "required_reviewers": ["primary"],
                    "reviews": [
                        {
                            "reviewer_role": "primary",
                            "decision": "accept",
                            "claim_strength": "suggestive",
                        }
                    ],
                    "disagreements": ["none"],
                },
            )

            code, payload = run_json(validate_result_acceptance, [task_dir, "--ops-dir", ops_dir, "--write"])

            self.assertEqual(validate_result_acceptance.SUCCESS, code, payload)
            record = json.loads((task_dir / "review_panel" / "result_acceptance.json").read_text(encoding="utf-8"))
            self.assertEqual("source_data_readiness", record["accepted_memory"]["claim_type"])
            self.assertEqual("90", record["accepted_memory"]["freshness_window_days"])
            self.assertEqual("2026-08-02", record["accepted_memory"]["next_recheck_date"])

    def test_simulation_work_dir_allows_research_ops_name_without_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_ops = root / "source" / "research_ops"
            separate_work = root / "sim_workspace" / "research_ops" / "nested_sim"
            source_ops.mkdir(parents=True)

            simulate_scheduled_week.ensure_simulation_work_dir_isolated(separate_work, source_ops)

            with self.assertRaises(simulate_scheduled_week.SimulationFailure):
                simulate_scheduled_week.ensure_simulation_work_dir_isolated(source_ops / "nested_sim", source_ops)

    def test_result_acceptance_writes_evidence_ledger_and_accepted_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = self.write_status(
                ops_dir,
                "TASK-2008-result-acceptance",
                previous_status="panel_review",
                status="accepted",
                last_transition_reason="aggregate_reviews_all_required_reviewers_accept",
                result={
                    "recommendation": "ready",
                    "claim_strength": "suggestive",
                    "key_finding": "Synthetic finding is ready for reuse",
                    "claim_type": "general",
                    "freshness_window_days": 90,
                    "next_recheck_date": "2026-08-02",
                    "revalidation_status": "current",
                    "followup_count": 0,
                },
            )
            task_dir.joinpath("worker_output.md").write_text("Synthetic finding is ready for reuse.\n", encoding="utf-8")
            write_json(
                task_dir / "review_panel" / "aggregate.json",
                {
                    "aggregate_decision": "accepted",
                    "aggregate_claim_strength": "suggestive",
                    "tier": 1,
                    "required_reviewers": ["primary"],
                    "reviews": [
                        {
                            "reviewer_role": "primary",
                            "decision": "accept",
                            "claim_strength": "suggestive",
                        }
                    ],
                    "disagreements": ["none"],
                },
            )

            code, payload = run_json(validate_result_acceptance, [task_dir, "--ops-dir", ops_dir, "--write", "--update-ledgers"])
            self.assertEqual(validate_result_acceptance.SUCCESS, code, payload)
            self.assertTrue((task_dir / "review_panel" / "result_acceptance.json").exists())
            ledger_text = (ops_dir / "evidence_ledger.md").read_text(encoding="utf-8")
            self.assertIn("TASK-2008", ledger_text)
            self.assertIn("Synthetic finding is ready for reuse", ledger_text)

            code, index_payload = run_json(update_accepted_outputs_index, ["update", ops_dir, "--now", NOW])
            self.assertEqual(update_accepted_outputs_index.SUCCESS, code, index_payload)
            index_text = (ops_dir / "accepted_outputs_index.md").read_text(encoding="utf-8")
            self.assertIn("TASK-2008", index_text)
            self.assertIn("Synthetic finding is ready for reuse", index_text)


if __name__ == "__main__":
    unittest.main()

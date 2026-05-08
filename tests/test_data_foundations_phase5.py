"""Phase 5 regression tests for data-foundation operational gates."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.scripts import (
    autonomy_readiness_gate,
    health_check,
    human_review_surface,
    validate_experiment_plan,
    validate_result_acceptance,
)
from async_research_workflow.scripts.version_metadata import apply_default_versions


NOW = "2026-05-08T00:00:00Z"


def run_json(entrypoint, argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = entrypoint.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_audit(ops_dir: Path, rows: list[dict[str, str]]) -> None:
    fields = [
        "source_id",
        "source_name",
        "url_or_domain",
        "publisher_owner",
        "source_tier",
        "approval_status",
        "approved_use_cases",
        "blocked_use_cases",
        "freshness_window_days",
        "known_limitations",
        "citation_requirements",
        "last_reviewed",
        "approved_by",
        "review_notes",
    ]
    lines = [
        "# Data Source Audit Register",
        "",
        "Schema version: 1.0",
        "",
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join("---" for _ in fields) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row.get(field, "") for field in fields) + " |")
    (ops_dir / "data_source_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def approved_source(source_id: str = "DS-0001") -> dict[str, str]:
    return {
        "source_id": source_id,
        "source_name": "Phase 5 Fixture Source",
        "url_or_domain": "https://example.test/data",
        "publisher_owner": "Fixture Publisher",
        "source_tier": "tier_1_official",
        "approval_status": "approved",
        "approved_use_cases": "experiment_planning; accepted_evidence; context",
        "blocked_use_cases": "none",
        "freshness_window_days": "90",
        "known_limitations": "fixture only",
        "citation_requirements": f"cite {source_id}",
        "last_reviewed": "2026-05-08",
        "approved_by": "tests",
        "review_notes": "phase 5 ready fixture",
    }


def init_ops(root: Path) -> Path:
    ops_dir = root / "research_ops"
    code, payload = run_json(cli, ["init", ops_dir, "--force"])
    if code != cli.SUCCESS or not payload.get("ok"):
        raise AssertionError(payload)
    return ops_dir


def write_task_status(
    ops_dir: Path,
    task_slug: str,
    task_type: str,
    data_audit_refs: list[str],
    status: str = "ready_for_worker",
) -> Path:
    task_id = task_slug.split("-", 2)[0] + "-" + task_slug.split("-", 2)[1]
    task_dir = ops_dir / "tasks" / task_slug
    payload = {
        "schema_version": "1.0",
        "id": task_id,
        "title": f"Phase 5 fixture {task_id}",
        "type": task_type,
        "status": status,
        "previous_status": "ready_for_planning",
        "last_transition_reason": "phase_5_fixture",
        "priority": 3,
        "revision_count": 0,
        "max_revisions": 1,
        "revision_limit_hit": False,
        "created_at": NOW,
        "updated_at": NOW,
        "allowed_paths": [f"research_ops/tasks/{task_slug}/**"],
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
        "budget": {"max_api_usd": 0, "max_compute_usd": 0},
        "data_audit_refs": data_audit_refs,
        "result": {"recommendation": None, "claim_strength": "none", "followup_count": 0},
    }
    write_json(task_dir / "status.json", apply_default_versions(payload))
    return task_dir


def valid_experiment_plan() -> dict:
    return {
        "schema_version": "1.0",
        "experiment_id": "EXP-7101",
        "task_id": "TASK-7101",
        "framework_version": "experimentation_v1.0",
        "hypothesis_id": "HYP-7101",
        "research_question": "Can the fixture experiment be planned safely?",
        "decision_use_case": "Decide whether to run the fixture experiment.",
        "target_outcome": "Fixture outcome.",
        "population": "Fixture records.",
        "geography": "Fixture geography.",
        "time_period": {"start": "2025-01", "end": "2025-12", "exclusion_lag": "none"},
        "data_audit_refs": ["DS-0001"],
        "dataset_versions": [{"source_id": "DS-0001", "version": "fixture", "accessed_at": "2026-05-08", "role": "outcome"}],
        "inclusion_rules": ["include fixture records"],
        "exclusion_rules": ["exclude invalid fixture records"],
        "feature_set": [{"name": "fixture_feature", "source_id": "DS-0001", "available_at": "before target", "leakage_risk": "low"}],
        "baselines": [{"name": "local median", "family": "naive_local_median", "implementation": "fixture median", "comparison_role": "baseline"}],
        "candidate_methods": [{"name": "fixture model", "method_class": "regression", "why_candidate": "simple fixture"}],
        "validation_design": {
            "time_split": "train then test",
            "spatial_holdout_or_blocked_validation": "blocked fixture split",
            "segment_level_error_analysis": ["segment"],
            "missingness_and_join_quality_checks": ["check joins"],
            "leakage_review": "review fixture feature timing",
        },
        "metrics": {"primary_metric": "MAE lower is better", "secondary_metrics": ["RMSE"], "minimum_detectable_improvement": "1%"},
        "leakage_checklist": {
            "feature_availability_before_prediction_date": "pass",
            "target_aggregates_train_only": "pass",
            "geography_summaries_time_safe": "pass",
            "publication_lags_modeled": "pass",
            "joins_point_in_time_or_versioned": "pass",
            "duplicate_or_repeat_transactions_handled": "pass",
        },
        "robustness_checks": ["rerun on fixture segment"],
        "success_criteria": ["beats baseline"],
        "failure_criteria": ["fails validation"],
        "budget": {"max_runtime_minutes": 10, "max_api_usd": 0.0, "max_compute_usd": 0.0, "max_retries": 0},
        "stop_conditions": {
            "stop_on_failure": "stop on validation failure",
            "stop_on_budget_exceeded": "stop before budget",
            "stop_on_data_quality_failure": "stop on data quality failure",
            "kill_criteria": ["kill if data is unusable"],
        },
        "outputs": {
            "output_dir": "research_ops/tasks/TASK-7101/artifacts/experiment_run/",
            "run_manifest_path": "research_ops/tasks/TASK-7101/artifacts/experiment_run/run_manifest.json",
            "artifact_paths": ["metrics.json"],
        },
        "claim_limits": {
            "strongest_supported_claim": "predictive_improvement",
            "causal_claim_allowed": False,
            "public_claim_allowed": False,
            "claim_limit_text": "bounded fixture claim only",
        },
        "scores": {
            "question_clarity": 3,
            "data_readiness": 3,
            "baseline_strength": 3,
            "validation_design": 3,
            "leakage_control": 3,
            "robustness_design": 3,
            "cost_realism": 3,
            "decision_usefulness": 3,
            "reproducibility": 3,
            "claim_disciplined": 3,
        },
    }


class DataFoundationsPhase5Tests(unittest.TestCase):
    def test_health_surfaces_blocked_sources_and_data_foundation_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = init_ops(Path(tmpdir))
            blocked = approved_source("DS-0002")
            blocked.update(
                {
                    "approval_status": "blocked",
                    "approved_use_cases": "none",
                    "blocked_use_cases": "all",
                    "approved_by": "none",
                    "review_notes": "blocked fixture source",
                }
            )
            write_audit(ops_dir, [approved_source("DS-0001"), blocked])

            args = health_check.parse_args([str(ops_dir), "--dry-run", "--no-daily-status", "--now", NOW])
            report = health_check.build_report(args)

        blocked_alert = next(item for item in report["alerts"] if item["check"] == "blocked_data_sources")
        self.assertEqual("warning", blocked_alert["severity"])
        self.assertEqual("DS-0002", blocked_alert["details"][0]["source_id"])
        data_alert = next(item for item in report["alerts"] if item["check"] == "data_foundation_findings")
        self.assertEqual("warning", data_alert["severity"])
        self.assertGreater(report["checks"]["data_foundations"]["warning_count"], 0)

    def test_readiness_warns_on_missing_data_foundations_without_blocking_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = init_ops(Path(tmpdir))
            shutil.rmtree(ops_dir / "data")

            code, payload = run_json(
                autonomy_readiness_gate,
                [
                    ops_dir,
                    "--dry-run",
                    "--no-daily-status",
                    "--now",
                    NOW,
                    "--metrics-stale-hours",
                    "100000",
                ],
            )

        self.assertEqual(autonomy_readiness_gate.WARNINGS, code, payload)
        self.assertEqual("safe_with_warnings", payload["decision"])
        self.assertEqual([], payload["blockers"])
        self.assertTrue(payload["expensive_workers_allowed"])
        warning = next(item for item in payload["warnings"] if item["check"] == "data_foundation_findings")
        self.assertEqual("data_dir_missing", warning["details"]["warnings"][0]["reason"])

    def test_readiness_blocks_malformed_data_foundations_for_source_dependent_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = init_ops(Path(tmpdir))
            write_audit(ops_dir, [approved_source("DS-0001")])
            write_task_status(ops_dir, "TASK-7103-run-analysis", "run_analysis", ["DS-0001"])
            catalog = ops_dir / "data" / "data_catalog.md"
            catalog.write_text("# Broken Catalog\n\n| one | two |\n| --- | --- |\n| one-cell |\n", encoding="utf-8")

            code, payload = run_json(
                autonomy_readiness_gate,
                [
                    ops_dir,
                    "--dry-run",
                    "--no-daily-status",
                    "--now",
                    NOW,
                    "--metrics-stale-hours",
                    "100000",
                ],
            )

        self.assertEqual(autonomy_readiness_gate.HUMAN_REQUIRED, code, payload)
        self.assertEqual("human_required", payload["decision"])
        self.assertFalse(payload["expensive_workers_allowed"])
        blocker = next(item for item in payload["blockers"] if item["check"] == "data_foundation_findings")
        self.assertEqual("error", blocker["severity"])
        self.assertEqual(1, blocker["details"]["error_count"])
        self.assertEqual("run_analysis", blocker["details"]["source_dependent_tasks"][0]["type"])

    def test_readiness_allows_data_readiness_task_to_remediate_candidate_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = init_ops(Path(tmpdir))
            candidate = approved_source("DS-0001")
            candidate.update(
                {
                    "approval_status": "candidate",
                    "approved_use_cases": "none",
                    "blocked_use_cases": "none",
                    "approved_by": "none",
                    "review_notes": "candidate awaiting data-readiness review",
                }
            )
            write_audit(ops_dir, [candidate])
            write_task_status(ops_dir, "TASK-7104-data-readiness", "data_readiness", ["DS-0001"])

            code, payload = run_json(
                autonomy_readiness_gate,
                [
                    ops_dir,
                    "--dry-run",
                    "--no-daily-status",
                    "--now",
                    NOW,
                    "--metrics-stale-hours",
                    "100000",
                ],
            )

        self.assertEqual(autonomy_readiness_gate.SUCCESS, code, payload)
        self.assertEqual("safe_to_run", payload["decision"])
        self.assertEqual([], payload["blockers"])
        self.assertFalse(any(item["check"] == "stale_or_unaudited_data_sources" for item in payload["warnings"]))

    def test_weekly_digest_lists_active_idea_data_gap_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = init_ops(Path(tmpdir))
            write_json(
                ops_dir / "ideas" / "IDEA-7101.json",
                {
                    "schema_version": "1.0",
                    "id": "IDEA-7101",
                    "status": "candidate",
                    "title": "Gap reference fixture",
                    "question": "Can DG-9999 be resolved?",
                    "why_it_might_matter": "It tests weekly data gap surfacing.",
                    "required_data": ["DG-9999"],
                    "minimum_viable_test": "Run data readiness.",
                    "baseline": "none",
                    "main_risks": ["missing data"],
                    "kill_reason": "DG-9999 remains unresolved.",
                    "recommended_next_task": "data_readiness",
                    "created_at": NOW,
                    "updated_at": NOW,
                },
            )

            code, payload = run_json(human_review_surface, ["update", ops_dir, "--now", NOW])
            weekly = (ops_dir / "weekly_digest.md").read_text(encoding="utf-8")

        self.assertEqual(human_review_surface.SUCCESS, code, payload)
        self.assertIn("## Data Foundations Surface", weekly)
        self.assertIn("Data gaps affecting active ideas", weekly)
        self.assertIn("IDEA-7101.json", weekly)
        self.assertIn("DG-9999", weekly)

    def test_experiment_plan_fails_on_malformed_data_foundations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = init_ops(Path(tmpdir))
            write_audit(ops_dir, [approved_source("DS-0001")])
            catalog = ops_dir / "data" / "data_catalog.md"
            catalog.write_text("# Broken Catalog\n\n| one | two |\n| --- | --- |\n| one-cell |\n", encoding="utf-8")
            plan_path = ops_dir / "tasks" / "TASK-7101-experiment-plan" / "worker_output.md"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_text("```json\n" + json.dumps(valid_experiment_plan(), indent=2) + "\n```\n", encoding="utf-8")

            code, payload = run_json(validate_experiment_plan, [plan_path, "--ops-dir", ops_dir])

        self.assertEqual(validate_experiment_plan.VALIDATION_FAILED, code, payload)
        self.assertFalse(payload["ok"])
        gates = {item["gate"] for item in payload["hard_gate_failures"]}
        self.assertIn("data_foundations", gates)

    def test_result_acceptance_rejects_blocked_data_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = init_ops(Path(tmpdir))
            blocked = approved_source("DS-0001")
            blocked.update(
                {
                    "approval_status": "blocked",
                    "approved_use_cases": "none",
                    "blocked_use_cases": "accepted_evidence",
                    "approved_by": "none",
                    "review_notes": "blocked for accepted evidence",
                }
            )
            write_audit(ops_dir, [blocked])
            task_dir = ops_dir / "tasks" / "TASK-7102-blocked-accepted"
            write_json(
                task_dir / "status.json",
                {
                    "id": "TASK-7102",
                    "title": "Blocked source acceptance",
                    "type": "data_readiness",
                    "status": "accepted",
                    "created_at": NOW,
                    "updated_at": NOW,
                    "data_audit_refs": ["DS-0001"],
                    "result": {
                        "recommendation": "ready",
                        "claim_strength": "suggestive",
                        "key_finding": "DS-0001 supports the fixture.",
                        "followup_count": 0,
                    },
                },
            )
            task_dir.joinpath("worker_output.md").write_text("DS-0001 supports the fixture.\n", encoding="utf-8")
            write_json(
                task_dir / "review_panel" / "aggregate.json",
                {
                    "aggregate_decision": "accepted",
                    "aggregate_claim_strength": "suggestive",
                    "tier": 1,
                    "required_reviewers": ["primary"],
                    "reviews": [{"reviewer_role": "primary", "decision": "accept", "claim_strength": "suggestive"}],
                    "disagreements": ["none"],
                },
            )

            code, payload = run_json(validate_result_acceptance, [task_dir, "--ops-dir", ops_dir])

        self.assertEqual(validate_result_acceptance.VALIDATION_FAILED, code, payload)
        self.assertFalse(payload["ok"])
        gate_names = {item["gate"] for item in payload["hard_gate_failures"]}
        self.assertIn("source_governance_allowed", gate_names)
        self.assertFalse(payload["source_governance"]["ok"])


if __name__ == "__main__":
    unittest.main()

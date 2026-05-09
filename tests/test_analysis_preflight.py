"""Phase 2 regression tests for analysis-run preflight."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from async_research_workflow import cli
from async_research_workflow.scripts import analysis_runs
from async_research_workflow.scripts.update_accepted_outputs_index import HEADER
from async_research_workflow.scripts.version_metadata import apply_default_versions


NOW = "2026-05-09T00:00:00Z"


def run_json(entrypoint, argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = entrypoint.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown_table(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row.get(field, "") for field in header) + " |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def init_ops(root: Path) -> Path:
    ops_dir = root / "research_ops"
    code, payload = run_json(cli, ["init", ops_dir, "--force"])
    if code != cli.SUCCESS or not payload.get("ok"):
        raise AssertionError(payload)
    return ops_dir


def audit_fields() -> list[str]:
    return [
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


def approved_source(source_id: str = "DS-0001") -> dict[str, str]:
    return {
        "source_id": source_id,
        "source_name": "Analysis Fixture Source",
        "url_or_domain": "https://example.test/source",
        "publisher_owner": "Fixture Publisher",
        "source_tier": "tier_1_official",
        "approval_status": "approved",
        "approved_use_cases": "experiment_planning; accepted_evidence; context",
        "blocked_use_cases": "no blocked use cases",
        "freshness_window_days": "365",
        "known_limitations": "fixture only",
        "citation_requirements": f"cite {source_id}",
        "last_reviewed": "2026-05-09",
        "approved_by": "tests",
        "review_notes": "phase 2 analysis preflight fixture",
    }


def write_audit(ops_dir: Path, rows: list[dict[str, str]]) -> None:
    lines = [
        "# Data Source Audit Register",
        "",
        "Schema version: 1.0",
        "",
        "| " + " | ".join(audit_fields()) + " |",
        "| " + " | ".join("---" for _ in audit_fields()) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row.get(field, "") for field in audit_fields()) + " |")
    (ops_dir / "data_source_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_clean_data_foundations(ops_dir: Path) -> None:
    profile = ops_dir / "data" / "profiles" / "DS-0001.md"
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(
        "\n".join(
            [
                "- source_id: DS-0001",
                "- source_name: Analysis Fixture Source",
                "- audit_status: approved",
                "- approved_use_cases: experiment_planning; accepted_evidence; context",
                "- blocked_use_cases: no blocked use cases",
                "- location: fixture://analysis-source",
                "- access_method: fixture",
                "- reviewed_date: 2026-05-09",
                "- reviewer: tests",
                "",
            ]
        ),
        encoding="utf-8",
    )
    write_markdown_table(
        ops_dir / "data" / "data_access.md",
        ["source_id", "access_method", "location", "access_check", "notes"],
        [
            {
                "source_id": "DS-0001",
                "access_method": "fixture",
                "location": "fixture://analysis-source",
                "access_check": "verified",
                "notes": "test fixture",
            }
        ],
    )
    write_markdown_table(
        ops_dir / "data" / "data_catalog.md",
        ["source_id", "name", "grain", "profile_path", "notes"],
        [{"source_id": "DS-0001", "name": "Analysis Fixture Source", "grain": "fixture row", "profile_path": "data/profiles/DS-0001.md", "notes": "fixture"}],
    )
    write_markdown_table(
        ops_dir / "data" / "join_map.md",
        ["join_id", "left_source_id", "right_source_id", "join_keys", "caveats"],
        [],
    )
    write_markdown_table(
        ops_dir / "data" / "known_data_gaps.md",
        ["gap_id", "summary", "status"],
        [],
    )


def task_status(task_id: str, task_type: str, status: str, data_refs: list[str], max_minutes: int = 30) -> dict:
    return apply_default_versions(
        {
            "schema_version": "1.0",
            "id": task_id,
            "title": f"Analysis preflight fixture {task_id}",
            "type": task_type,
            "status": status,
            "previous_status": "ready_for_planning",
            "last_transition_reason": "phase_2_preflight_fixture",
            "priority": 3,
            "revision_count": 0,
            "max_revisions": 1,
            "revision_limit_hit": False,
            "created_at": NOW,
            "updated_at": NOW,
            "allowed_paths": [f"research_ops/tasks/{task_id}-*/**"],
            "allowed_tools": ["read_files", "write_task_files"],
            "allow_browsing": False,
            "allow_code_execution": False,
            "allow_network": False,
            "max_minutes": max_minutes,
            "max_turns": 1,
            "model_tier": "low",
            "review_policy": {
                "tier": 1,
                "required_reviewers": ["primary"],
                "panel_required": False,
                "human_required_for_acceptance": False,
            },
            "requires_human": False,
            "budget": {"max_api_usd": 1.0, "max_compute_usd": 2.0},
            "data_audit_refs": data_refs,
            "result": {"recommendation": None, "claim_strength": "none", "followup_count": 0},
        }
    )


def valid_experiment_plan() -> dict:
    return {
        "schema_version": "1.0",
        "experiment_id": "EXP-8001",
        "task_id": "TASK-8001",
        "framework_version": "experimentation_v1.0",
        "hypothesis_id": "HYP-8001",
        "research_question": "Can the fixture experiment be planned safely?",
        "decision_use_case": "Decide whether to run the fixture experiment.",
        "target_outcome": "Fixture target.",
        "population": "Fixture records.",
        "geography": "Fixture geography.",
        "time_period": {"start": "2025-01", "end": "2025-12", "exclusion_lag": "none"},
        "data_audit_refs": ["DS-0001"],
        "dataset_versions": [{"source_id": "DS-0001", "version": "fixture", "accessed_at": "2026-05-09", "role": "outcome"}],
        "inclusion_rules": ["include fixture records"],
        "exclusion_rules": ["exclude invalid fixture records"],
        "feature_set": [{"name": "fixture_feature", "source_id": "DS-0001", "available_at": "before target", "leakage_risk": "low"}],
        "baselines": [{"name": "local median", "family": "naive_local_median", "implementation": "fixture median", "comparison_role": "baseline"}],
        "candidate_methods": [{"name": "fixture regression", "method_class": "regression", "why_candidate": "simple fixture"}],
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
        "budget": {"max_runtime_minutes": 30, "max_api_usd": 1.0, "max_compute_usd": 2.0, "max_retries": 0},
        "stop_conditions": {
            "stop_on_failure": "stop on validation failure",
            "stop_on_budget_exceeded": "stop before budget",
            "stop_on_data_quality_failure": "stop on data quality failure",
            "kill_criteria": ["kill if data is unusable"],
        },
        "outputs": {
            "output_dir": "research_ops/tasks/TASK-8002-run-analysis/artifacts/analysis_run/",
            "run_manifest_path": "research_ops/tasks/TASK-8002-run-analysis/artifacts/analysis_run/run_manifest.json",
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


def valid_manifest() -> dict:
    baseline_path = "research_ops/tasks/TASK-8002-run-analysis/artifacts/analysis_run/baseline_metrics.json"
    metrics_path = "research_ops/tasks/TASK-8002-run-analysis/artifacts/analysis_run/metrics.json"
    diagnostics_path = "research_ops/tasks/TASK-8002-run-analysis/artifacts/analysis_run/diagnostics.json"
    return {
        "schema_version": "1.0",
        "framework_version": "analysis_run_v1.0",
        "manifest_created_at": NOW,
        "run_id": "RUN-8002",
        "run_status": "planned",
        "task_id": "TASK-8002",
        "task_type": "run_analysis",
        "experiment_plan_id": "EXP-8001",
        "accepted_plan_task_id": "TASK-8001",
        "accepted_plan_path": "research_ops/tasks/TASK-8001-experiment-plan/worker_output.md",
        "accepted_plan_result_acceptance_path": "research_ops/tasks/TASK-8001-experiment-plan/review_panel/result_acceptance.json",
        "analysis_config_path": "none",
        "data_versions": [
            {
                "source_id": "DS-0001",
                "version": "fixture",
                "accessed_at": NOW,
                "role": "outcome",
                "artifact_path": "research_ops/tasks/TASK-8002-run-analysis/artifacts/analysis_run/source_snapshot.json",
            }
        ],
        "code_version": {"type": "git", "value": "fixture", "dirty": False},
        "runner": {"type": "manual", "entrypoint": "manual fixture", "parameters_ref": "none", "execution_environment": "test"},
        "method_family": "regression",
        "candidate_method": {"name": "fixture regression", "planned_method_ref": "experiment_plan.candidate_methods[0]"},
        "baseline_refs": [{"name": "local median", "planned_baseline_ref": "experiment_plan.baselines[0]", "expected_output_path": baseline_path}],
        "primary_metric": {"name": "MAE lower is better", "direction": "decrease", "planned_metric_ref": "experiment_plan.metrics.primary_metric"},
        "planned_outputs": [
            {"name": "baseline metrics", "path": baseline_path, "required_for_acceptance": True},
            {"name": "candidate metrics", "path": metrics_path, "required_for_acceptance": True},
            {"name": "diagnostics", "path": diagnostics_path, "required_for_acceptance": True},
        ],
        "output_paths": [baseline_path, metrics_path, diagnostics_path],
        "deviations_from_plan": [],
        "reproducibility": {
            "rerun_possible": True,
            "rerun_command": "manual fixture",
            "environment": "test",
            "random_seed": "none",
            "determinism_notes": "deterministic fixture",
        },
    }


def valid_result_acceptance() -> dict:
    return {
        "schema_version": "1.0",
        "framework_version": "result_acceptance_v1.0",
        "task_id": "TASK-8001",
        "task_type": "experiment_plan",
        "evaluated_at": NOW,
        "route": "accept_as_evidence",
        "recommended_decision": "ready",
        "claim_strength": "none",
        "max_claim_strength": "none",
        "claim_strength_policy": "fixture methodology note",
        "hard_gate_results": [{"gate": "fixture", "passed": True, "reason": "accepted"}],
        "scorecard": {
            "plan_compliance": 5,
            "reproducibility": 5,
            "baseline_comparison": 5,
            "metric_validity": 5,
            "validation_strength": 5,
            "robustness_strength": 5,
            "leakage_safety": 5,
            "limitation_honesty": 5,
            "decision_usefulness": 5,
            "claim_discipline": 5,
        },
        "reviewer_panel": {
            "aggregate_present": True,
            "aggregate_decision": "accepted",
            "tier": 1,
            "required_reviewers": ["primary"],
            "reviewer_count": 1,
            "disagreement_present": False,
        },
        "human_gate": {"required": False, "satisfied": True, "reason": "fixture"},
        "source_governance": {
            "required": True,
            "source_ids": ["DS-0001"],
            "ok": True,
            "warnings": [],
            "blocked": [],
        },
        "accepted_memory": {
            "claim_type": "methodology_note",
            "freshness_window_days": "manual_review",
            "next_recheck_date": "manual_review",
            "revalidation_status": "manual_review",
            "supersedes": "none",
            "superseded_by": "none",
        },
        "evidence_ledger": {
            "required": False,
            "ledger_path": "research_ops/evidence_ledger.md",
            "logged": False,
            "evidence_link": "research_ops/tasks/TASK-8001-experiment-plan/worker_output.md",
        },
        "rejection_logging": {
            "required": False,
            "log_path": "research_ops/rejected_results.md",
            "logged": False,
        },
        "followups": [],
        "review_notes": ["fixture accepted plan"],
    }


def write_accepted_index(ops_dir: Path, extra_rows: list[dict[str, str]] | None = None, include_default: bool = True) -> None:
    rows = []
    if include_default:
        rows.append(
            {
                "accepted_date": "2026-05-09",
                "task_id": "TASK-8001",
                "title": "Accepted fixture experiment plan",
                "key_finding": "Fixture plan accepted.",
                "claim_type": "methodology_note",
                "freshness_window_days": "manual_review",
                "next_recheck_date": "manual_review",
                "revalidation_status": "manual_review",
                "source_ids": "DS-0001",
                "claim_strength": "none",
                "caveats": "fixture only",
                "followups": "none",
                "supersedes": "none",
                "superseded_by": "none",
                "evidence_link": "research_ops/tasks/TASK-8001-experiment-plan/worker_output.md",
            }
        )
    rows.extend(extra_rows or [])
    write_markdown_table(ops_dir / "accepted_outputs_index.md", HEADER, rows)


def create_fixture_workspace(root: Path) -> tuple[Path, Path, Path]:
    ops_dir = init_ops(root)
    write_audit(ops_dir, [approved_source()])
    write_clean_data_foundations(ops_dir)
    plan_dir = ops_dir / "tasks" / "TASK-8001-experiment-plan"
    analysis_dir = ops_dir / "tasks" / "TASK-8002-run-analysis"
    write_json(plan_dir / "status.json", task_status("TASK-8001", "experiment_plan", "accepted", ["DS-0001"]))
    plan_dir.joinpath("worker_output.md").parent.mkdir(parents=True, exist_ok=True)
    plan_dir.joinpath("worker_output.md").write_text(
        "Accepted fixture plan.\n\n```json\n" + json.dumps(valid_experiment_plan(), indent=2, sort_keys=True) + "\n```\n",
        encoding="utf-8",
    )
    write_json(plan_dir / "review_panel" / "result_acceptance.json", valid_result_acceptance())
    write_json(analysis_dir / "status.json", task_status("TASK-8002", "run_analysis", "ready_for_worker", ["DS-0001"]))
    analysis_dir.joinpath("task.md").write_text("Run TASK-8001 fixture analysis using DS-0001.\n", encoding="utf-8")
    write_json(analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json", valid_manifest())
    write_accepted_index(ops_dir)
    return ops_dir, plan_dir, analysis_dir


def gate_names(payload: dict) -> set[str]:
    return {item["gate"] for item in payload.get("hard_gate_failures", [])}


class AnalysisPreflightTests(unittest.TestCase):
    def test_valid_preflight_passes_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.SUCCESS, code, payload)
        self.assertTrue(payload["ok"])
        self.assertEqual([], payload["hard_gate_failures"])
        self.assertEqual([], payload["warnings"])
        self.assertEqual("run analysis", payload["next_step"])

    def test_cli_preflight_routes_to_analysis_runs(self) -> None:
        with mock.patch.object(cli, "module_main", return_value=cli.SUCCESS) as module_main:
            code = cli.main(["analysis", "preflight", "research_ops/tasks/TASK-8002-run-analysis", "--ops-dir", "research_ops", "--now", NOW])

        self.assertEqual(cli.SUCCESS, code)
        module_main.assert_called_once_with(
            "analysis_runs",
            ["preflight", "research_ops/tasks/TASK-8002-run-analysis", "--ops-dir", "research_ops", "--now", NOW],
        )

    def test_preflight_requires_run_analysis_task_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            status = task_status("TASK-8002", "evaluate_results", "ready_for_worker", ["DS-0001"])
            write_json(analysis_dir / "status.json", status)

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("task_type", gate_names(payload))

    def test_preflight_rejects_non_runnable_analysis_statuses(self) -> None:
        for blocked_status in ("needs_human", "paused", "accepted", "rejected"):
            with self.subTest(blocked_status=blocked_status):
                with tempfile.TemporaryDirectory() as tmpdir:
                    ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
                    status = task_status("TASK-8002", "run_analysis", blocked_status, ["DS-0001"])
                    write_json(analysis_dir / "status.json", status)

                    code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

                self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
                self.assertIn("task_status_runnable", gate_names(payload))

    def test_preflight_requires_accepted_plan_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            status = task_status("TASK-8001", "experiment_plan", "awaiting_review", ["DS-0001"])
            write_json(plan_dir / "status.json", status)

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("accepted_plan_task_accepted", gate_names(payload))

    def test_preflight_requires_existing_accepted_plan_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            manifest = valid_manifest()
            manifest["accepted_plan_task_id"] = "TASK-8999"
            manifest["accepted_plan_path"] = "research_ops/tasks/TASK-8999-experiment-plan/worker_output.md"
            manifest["accepted_plan_result_acceptance_path"] = "research_ops/tasks/TASK-8999-experiment-plan/review_panel/result_acceptance.json"
            write_json(analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json", manifest)

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("accepted_plan_task_exists", gate_names(payload))

    def test_preflight_revalidates_plan_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            plan = valid_experiment_plan()
            plan["baselines"] = []
            plan_dir.joinpath("worker_output.md").write_text(
                "Accepted fixture plan.\n\n```json\n" + json.dumps(plan, indent=2, sort_keys=True) + "\n```\n",
                encoding="utf-8",
            )

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("accepted_plan_valid", gate_names(payload))

    def test_preflight_rejects_experiment_plan_id_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            manifest = valid_manifest()
            manifest["experiment_plan_id"] = "EXP-8999"
            write_json(analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json", manifest)

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("experiment_plan_id_matches", gate_names(payload))

    def test_preflight_rejects_stale_accepted_plan_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_accepted_index(
                ops_dir,
                [
                    {
                        "accepted_date": "2025-01-01",
                        "task_id": "TASK-8001",
                        "title": "Accepted fixture experiment plan",
                        "key_finding": "Fixture plan accepted.",
                        "claim_type": "general",
                        "freshness_window_days": "30",
                        "next_recheck_date": "2025-02-01",
                        "revalidation_status": "stale",
                        "source_ids": "DS-0001",
                        "claim_strength": "none",
                        "caveats": "fixture only",
                        "followups": "refresh",
                        "supersedes": "none",
                        "superseded_by": "none",
                        "evidence_link": "research_ops/tasks/TASK-8001-experiment-plan/worker_output.md",
                    }
                ],
                include_default=False,
            )

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("accepted_plan_current", gate_names(payload))

    def test_preflight_rejects_superseded_accepted_plan_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_accepted_index(
                ops_dir,
                [
                    {
                        "accepted_date": "2026-05-09",
                        "task_id": "TASK-8001",
                        "title": "Superseded fixture experiment plan",
                        "key_finding": "Fixture plan was replaced.",
                        "claim_type": "methodology_note",
                        "freshness_window_days": "manual_review",
                        "next_recheck_date": "manual_review",
                        "revalidation_status": "manual_review",
                        "source_ids": "DS-0001",
                        "claim_strength": "none",
                        "caveats": "superseded",
                        "followups": "use replacement",
                        "supersedes": "none",
                        "superseded_by": "TASK-8998",
                        "evidence_link": "research_ops/tasks/TASK-8001-experiment-plan/worker_output.md",
                    }
                ],
                include_default=False,
            )

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("accepted_plan_current", gate_names(payload))

    def test_warning_only_preflight_requires_warning_review_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_accepted_index(
                ops_dir,
                [
                    {
                        "accepted_date": "2026-05-09",
                        "task_id": "TASK-8001",
                        "title": "Due fixture experiment plan",
                        "key_finding": "Fixture plan is due for review.",
                        "claim_type": "general",
                        "freshness_window_days": "3",
                        "next_recheck_date": "2026-05-12",
                        "revalidation_status": "due",
                        "source_ids": "DS-0001",
                        "claim_strength": "none",
                        "caveats": "due",
                        "followups": "review soon",
                        "supersedes": "none",
                        "superseded_by": "none",
                        "evidence_link": "research_ops/tasks/TASK-8001-experiment-plan/worker_output.md",
                    }
                ],
                include_default=False,
            )

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertTrue(payload["ok"])
        self.assertEqual([], payload["hard_gate_failures"])
        self.assertGreater(payload["warning_count"], 0)
        self.assertEqual("review warnings before analysis starts", payload["next_step"])

    def test_preflight_requires_result_acceptance_path_to_be_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            manifest = valid_manifest()
            manifest["accepted_plan_result_acceptance_path"] = "research_ops/tasks/TASK-8001-experiment-plan/status.json"
            write_json(analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json", manifest)

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("accepted_plan_result_acceptance_path", gate_names(payload))

    def test_preflight_rejects_metric_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            manifest = valid_manifest()
            manifest["primary_metric"]["name"] = "RMSE lower is better"
            write_json(analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json", manifest)

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("primary_metric_matches", gate_names(payload))

    def test_preflight_rejects_method_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            manifest = valid_manifest()
            manifest["method_family"] = "causal_design"
            write_json(analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json", manifest)

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("method_family_allowed", gate_names(payload))

    def test_preflight_requires_all_accepted_plan_baselines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            plan = valid_experiment_plan()
            plan["baselines"].append(
                {
                    "name": "regularized regression benchmark",
                    "family": "regularized_regression_benchmark",
                    "implementation": "fixture regularized model",
                    "comparison_role": "baseline",
                }
            )
            plan_dir.joinpath("worker_output.md").write_text(
                "Accepted fixture plan.\n\n```json\n" + json.dumps(plan, indent=2, sort_keys=True) + "\n```\n",
                encoding="utf-8",
            )

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("baseline_outputs_required", gate_names(payload))

    def test_preflight_rejects_budget_overrun(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            status = task_status("TASK-8002", "run_analysis", "ready_for_worker", ["DS-0001"], max_minutes=90)
            write_json(analysis_dir / "status.json", status)

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("budget_within_plan", gate_names(payload))

    def test_preflight_rejects_output_path_outside_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            manifest = valid_manifest()
            manifest["output_paths"] = copy.deepcopy(manifest["output_paths"]) + ["research_ops/tasks/TASK-8001-experiment-plan/worker_output.md"]
            write_json(analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json", manifest)

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("output_paths_inside_task_folder", gate_names(payload))

    def test_preflight_rejects_blocked_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            source = approved_source()
            source.update({"approval_status": "blocked", "approved_use_cases": "none", "blocked_use_cases": "all", "approved_by": "none"})
            write_audit(ops_dir, [source])

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("source_governance_allowed", gate_names(payload))

    def test_preflight_rejects_stale_accepted_memory_reuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            stale_row = {
                "accepted_date": "2025-01-01",
                "task_id": "TASK-7999",
                "title": "Old evidence",
                "key_finding": "Old evidence",
                "claim_type": "general",
                "freshness_window_days": "30",
                "next_recheck_date": "2025-02-01",
                "revalidation_status": "stale",
                "source_ids": "DS-0001",
                "claim_strength": "moderate",
                "caveats": "stale",
                "followups": "refresh",
                "supersedes": "none",
                "superseded_by": "none",
                "evidence_link": "research_ops/tasks/TASK-7999-old/worker_output.md",
            }
            write_accepted_index(ops_dir, [stale_row])
            analysis_dir.joinpath("task.md").write_text("Reuse TASK-7999 as current evidence for this run.\n", encoding="utf-8")

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("stale_accepted_memory_reuse", gate_names(payload))

    def test_preflight_scans_runner_parameters_ref_for_stale_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            stale_row = {
                "accepted_date": "2025-01-01",
                "task_id": "TASK-7999",
                "title": "Old parameter evidence",
                "key_finding": "Old evidence",
                "claim_type": "general",
                "freshness_window_days": "30",
                "next_recheck_date": "2025-02-01",
                "revalidation_status": "stale",
                "source_ids": "DS-0001",
                "claim_strength": "moderate",
                "caveats": "stale",
                "followups": "refresh",
                "supersedes": "none",
                "superseded_by": "none",
                "evidence_link": "research_ops/tasks/TASK-7999-old/worker_output.md",
            }
            write_accepted_index(ops_dir, [stale_row])
            parameters_path = analysis_dir / "artifacts" / "analysis_run" / "parameters.md"
            parameters_path.write_text("Use TASK-7999 as current evidence for this parameterization.\n", encoding="utf-8")
            manifest = valid_manifest()
            manifest["runner"]["parameters_ref"] = "research_ops/tasks/TASK-8002-run-analysis/artifacts/analysis_run/parameters.md"
            write_json(analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json", manifest)

            code, payload = run_json(analysis_runs, ["preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_runs.VALIDATION_FAILED, code, payload)
        self.assertIn("stale_accepted_memory_reuse", gate_names(payload))


if __name__ == "__main__":
    unittest.main()

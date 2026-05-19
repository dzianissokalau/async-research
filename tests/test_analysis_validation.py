"""Phase 5 regression tests for analysis validation CLI."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from async_research_workflow import cli
from async_research_workflow.resources import template_path
from async_research_workflow.scripts import analysis_claim_gates, analysis_validation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_analysis_preflight import (
    NOW,
    create_fixture_workspace,
    run_json,
    valid_manifest,
    write_json,
)


def template_payload(template_name: str) -> dict:
    text = template_path("artifact_templates", template_name).read_text(encoding="utf-8")
    match = re.search(r"```json\s*(.*?)```", text, re.DOTALL)
    if match is None:
        raise AssertionError(f"{template_name} must include a fenced JSON block")
    payload = json.loads(match.group(1))
    if not isinstance(payload, dict):
        raise AssertionError(f"{template_name} JSON must be an object")
    return payload


def gate_names(payload: dict) -> set[str]:
    return {item["gate"] for item in payload.get("hard_gate_failures", [])}


def warning_names(payload: dict) -> set[str]:
    return {item["gate"] for item in payload.get("warnings", [])}


def failure_for_gate(payload: dict, gate: str) -> dict:
    return next(item for item in payload["hard_gate_failures"] if item["gate"] == gate)


def assert_failure_has_remediation(testcase: unittest.TestCase, failure: dict) -> None:
    for key in ("summary", "failing_field", "why_it_matters", "next_step", "docs_ref"):
        testcase.assertIn(key, failure)
        testcase.assertIsInstance(failure[key], str)
        testcase.assertTrue(failure[key].strip(), f"{key} should be non-empty")


def write_worker_summary(task_dir: Path, summary: dict) -> None:
    task_dir.joinpath("worker_output.md").write_text(
        "Completed fixture analysis.\n\n```json\n" + json.dumps(summary, indent=2, sort_keys=True) + "\n```\n",
        encoding="utf-8",
    )


def completed_manifest() -> dict:
    manifest = valid_manifest()
    robustness_path = "research_ops/tasks/TASK-8002-run-analysis/artifacts/analysis_run/robustness_checks.json"
    manifest.update(
        {
            "run_status": "completed",
            "started_at": NOW,
            "completed_at": NOW,
            "runtime_minutes": 10,
            "cost": {"api_usd": 0.0, "compute_usd": 0.1, "total_usd": 0.1},
        }
    )
    manifest["planned_outputs"].append(
        {"name": "robustness checks", "path": robustness_path, "required_for_acceptance": True}
    )
    manifest["output_paths"].append(robustness_path)
    return manifest


def analysis_metrics() -> dict:
    payload = template_payload("analysis_metrics_template.md")
    payload.update({"run_id": "RUN-8002", "experiment_plan_id": "EXP-8001", "task_id": "TASK-8002"})
    payload["primary_metric_name"] = "MAE lower is better"
    payload["baseline_comparisons"][0]["planned_baseline_ref"] = "experiment_plan.baselines[0]"
    return payload


def analysis_diagnostics() -> dict:
    payload = template_payload("analysis_diagnostics_template.md")
    payload.update({"run_id": "RUN-8002", "experiment_plan_id": "EXP-8001", "task_id": "TASK-8002"})
    return payload


def analysis_robustness() -> dict:
    payload = template_payload("analysis_robustness_checks_template.md")
    payload.update({"run_id": "RUN-8002", "experiment_plan_id": "EXP-8001", "task_id": "TASK-8002"})
    return payload


def result_summary(**overrides) -> dict:
    payload = {
        "schema_version": "1.0",
        "framework_version": "result_acceptance_v1.0",
        "result_id": "RESULT-8002",
        "experiment_plan_id": "EXP-8001",
        "run_id": "RUN-8002",
        "task_id": "TASK-8002",
        "run_manifest_path": "research_ops/tasks/TASK-8002-run-analysis/artifacts/analysis_run/run_manifest.json",
        "artifact_version": "git:fixture",
        "dataset_versions": [{"source_id": "DS-0001", "version": "fixture"}],
        "primary_metric": "MAE lower is better",
        "baseline_results": "Baseline MAE 10.4",
        "candidate_results": "Candidate MAE 9.7",
        "validation_split_results": "2025 holdout",
        "robustness_results": ["Alternative validation window passed"],
        "leakage_check_results": ["No leakage detected"],
        "limitations": ["Bounded predictive fixture claim only"],
        "claim": "The candidate feature improves predictive accuracy in this bounded backtest.",
        "claim_type": "predictive",
        "claim_strength": "moderate",
        "recommended_decision": "accept_as_evidence",
        "public_or_high_stakes": False,
        "human_approval_present": False,
        "follow_up_tasks": [],
    }
    payload.update(overrides)
    return payload


def write_completed_artifacts(
    analysis_dir: Path,
    manifest: dict | None = None,
    metrics: dict | None = None,
    diagnostics: dict | None = None,
    robustness: dict | None = None,
    summary: dict | None = None,
    claim_gates: dict | None = None,
) -> tuple[dict, dict, dict, dict, dict]:
    manifest = copy.deepcopy(manifest or completed_manifest())
    metrics = copy.deepcopy(metrics or analysis_metrics())
    diagnostics = copy.deepcopy(diagnostics or analysis_diagnostics())
    robustness = copy.deepcopy(robustness or analysis_robustness())
    summary = copy.deepcopy(summary or result_summary())
    analysis_run_dir = analysis_dir / "artifacts" / "analysis_run"
    write_json(analysis_run_dir / "run_manifest.json", manifest)
    write_json(analysis_run_dir / "baseline_metrics.json", {"ok": True})
    write_json(analysis_run_dir / "metrics.json", metrics)
    write_json(analysis_run_dir / "diagnostics.json", diagnostics)
    write_json(analysis_run_dir / "robustness_checks.json", robustness)
    write_worker_summary(analysis_dir, summary)
    if claim_gates is None:
        claim_gates = analysis_claim_gates.evaluate_claim_gates(
            summary,
            metrics=metrics,
            diagnostics=diagnostics,
            robustness=robustness,
            generated_at=NOW,
            trusted_identity={"run_id": "RUN-8002", "experiment_plan_id": "EXP-8001", "task_id": "TASK-8002"},
        )
    write_json(analysis_run_dir / "claim_gates.json", claim_gates)
    return manifest, metrics, diagnostics, robustness, summary


class AnalysisValidationTests(unittest.TestCase):
    def test_valid_validate_run_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir)

            code, payload = run_json(analysis_validation, ["validate-run", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_validation.SUCCESS, code, payload)
        self.assertTrue(payload["ok"])
        self.assertEqual([], payload["hard_gate_failures"])

    def test_valid_validate_results_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir)

            code, payload = run_json(analysis_validation, ["validate-results", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_validation.SUCCESS, code, payload)
        self.assertTrue(payload["ok"])
        self.assertEqual("accepted", payload["claim_gates"]["computed"]["claim_decision"])

    def test_cli_validate_commands_route_to_analysis_validation(self) -> None:
        with mock.patch.object(cli, "module_main", return_value=cli.SUCCESS) as module_main:
            code = cli.main(["analysis", "validate-run", "research_ops/tasks/TASK-8002-run-analysis", "--ops-dir", "research_ops", "--now", NOW])
        self.assertEqual(cli.SUCCESS, code)
        module_main.assert_called_once_with(
            "analysis_validation",
            ["validate-run", "research_ops/tasks/TASK-8002-run-analysis", "--ops-dir", "research_ops", "--now", NOW],
        )

        with mock.patch.object(cli, "module_main", return_value=cli.SUCCESS) as module_main:
            code = cli.main(["analysis", "validate-results", "research_ops/tasks/TASK-8002-run-analysis", "--ops-dir", "research_ops", "--now", NOW])
        self.assertEqual(cli.SUCCESS, code)
        module_main.assert_called_once_with(
            "analysis_validation",
            ["validate-results", "research_ops/tasks/TASK-8002-run-analysis", "--ops-dir", "research_ops", "--now", NOW],
        )

    def test_validate_run_requires_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            (analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json").unlink()

            code, payload = run_json(analysis_validation, ["validate-run", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_validation.VALIDATION_FAILED, code, payload)
        self.assertIn("manifest_exists", gate_names(payload))
        failure = failure_for_gate(payload, "manifest_exists")
        self.assertEqual("Missing run manifest", failure["summary"])
        self.assertEqual("artifacts/analysis_run/run_manifest.json", failure["failing_field"])
        assert_failure_has_remediation(self, failure)

    def test_validate_run_requires_baseline_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir)
            (analysis_dir / "artifacts" / "analysis_run" / "baseline_metrics.json").unlink()

            code, payload = run_json(analysis_validation, ["validate-run", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_validation.VALIDATION_FAILED, code, payload)
        self.assertIn("required_output_files_exist", gate_names(payload))
        assert_failure_has_remediation(self, failure_for_gate(payload, "required_output_files_exist"))

    def test_validate_run_rejects_unplanned_metric_change(self) -> None:
        metrics = analysis_metrics()
        metrics["primary_metric_name"] = "RMSE lower is better"
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir, metrics=metrics)

            code, payload = run_json(analysis_validation, ["validate-run", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_validation.VALIDATION_FAILED, code, payload)
        self.assertIn("primary_metric_matches_plan", gate_names(payload))
        assert_failure_has_remediation(self, failure_for_gate(payload, "primary_metric_matches_plan"))

    def test_validate_run_rejects_unplanned_metric_rows(self) -> None:
        metrics = analysis_metrics()
        metrics["candidate_metrics"][0]["planned_metric_ref"] = "experiment_plan.metrics.secondary_metrics[99]"
        metrics["metric_rows"].append(
            {
                "metric_name": "AUC",
                "role": "validation",
                "value": 0.9,
                "unit": "ratio",
                "direction": "increase",
                "split": "validation",
                "segment": "all",
                "source": "post-hoc table",
                "planned_metric_ref": "experiment_plan.metrics.secondary_metrics[99]",
            }
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir, metrics=metrics)

            code, payload = run_json(analysis_validation, ["validate-run", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_validation.VALIDATION_FAILED, code, payload)
        self.assertIn("planned_metrics_match_plan", gate_names(payload))

    def test_validate_run_rejects_not_run_robustness_supporting_claim(self) -> None:
        robustness = analysis_robustness()
        robustness["planned_checks"][0]["status"] = "not_run"
        robustness["planned_checks"][0]["decision_impact"] = "supports_claim"
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir, robustness=robustness)

            code, payload = run_json(analysis_validation, ["validate-run", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_validation.VALIDATION_FAILED, code, payload)
        self.assertIn("robustness_semantics", gate_names(payload))

    def test_validate_run_rejects_unplanned_robustness_ref(self) -> None:
        robustness = analysis_robustness()
        robustness["planned_checks"][0]["planned_check_ref"] = "experiment_plan.robustness_checks[99]"
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir, robustness=robustness)

            code, payload = run_json(analysis_validation, ["validate-run", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_validation.VALIDATION_FAILED, code, payload)
        self.assertIn("robustness_checks_match_plan", gate_names(payload))

    def test_validate_run_warns_when_robustness_caps_claim(self) -> None:
        robustness = analysis_robustness()
        robustness["planned_checks"][0]["decision_impact"] = "caps_claim"
        robustness["planned_checks"][0]["status"] = "warn"
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir, robustness=robustness)

            code, payload = run_json(analysis_validation, ["validate-run", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_validation.VALIDATION_FAILED, code, payload)
        self.assertIn("robustness_caps_claim", warning_names(payload))

    def test_validate_results_rejects_summary_substance_mismatches(self) -> None:
        summary = result_summary(
            run_manifest_path="research_ops/tasks/TASK-9999-run-analysis/artifacts/analysis_run/run_manifest.json",
            primary_metric="RMSE lower is better",
            baseline_results="Baseline RMSE 1.2",
            candidate_results="Candidate RMSE 1.0",
            validation_split_results="random full sample",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir, summary=summary)

            code, payload = run_json(analysis_validation, ["validate-results", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_validation.VALIDATION_FAILED, code, payload)
        self.assertIn("result_summary_matches_outputs", gate_names(payload))

    def test_validate_results_rejects_stale_claim_gate_artifact(self) -> None:
        claim_gates = analysis_claim_gates.evaluate_claim_gates(
            result_summary(claim="A previous claim that should not be reused."),
            metrics=analysis_metrics(),
            diagnostics=analysis_diagnostics(),
            robustness=analysis_robustness(),
            generated_at=NOW,
            trusted_identity={"run_id": "RUN-8002", "experiment_plan_id": "EXP-8001", "task_id": "TASK-8002"},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir, claim_gates=claim_gates)

            code, payload = run_json(analysis_validation, ["validate-results", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_validation.VALIDATION_FAILED, code, payload)
        self.assertIn("claim_gates_match_outputs", gate_names(payload))

    def test_validate_results_requires_caps_claim_in_claim_gates(self) -> None:
        robustness = analysis_robustness()
        robustness["planned_checks"][0]["decision_impact"] = "caps_claim"
        robustness["planned_checks"][0]["status"] = "warn"
        stale_claim_gates = analysis_claim_gates.evaluate_claim_gates(
            result_summary(),
            metrics=analysis_metrics(),
            diagnostics=analysis_diagnostics(),
            robustness=analysis_robustness(),
            generated_at=NOW,
            trusted_identity={"run_id": "RUN-8002", "experiment_plan_id": "EXP-8001", "task_id": "TASK-8002"},
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir, robustness=robustness, claim_gates=stale_claim_gates)

            code, payload = run_json(analysis_validation, ["validate-results", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_validation.VALIDATION_FAILED, code, payload)
        self.assertIn("claim_gates_match_outputs", gate_names(payload))
        self.assertIn("robustness_caps_claim", warning_names(payload))

    def test_validate_results_returns_malformed_for_bad_completed_artifacts(self) -> None:
        artifact_paths = [
            "artifacts/analysis_run/metrics.json",
            "artifacts/analysis_run/diagnostics.json",
            "artifacts/analysis_run/robustness_checks.json",
            "artifacts/analysis_run/claim_gates.json",
        ]
        for artifact_path in artifact_paths:
            with self.subTest(artifact_path=artifact_path):
                with tempfile.TemporaryDirectory() as tmpdir:
                    ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
                    write_completed_artifacts(analysis_dir)
                    (analysis_dir / artifact_path).write_text("{", encoding="utf-8")

                    code, payload = run_json(
                        analysis_validation,
                        ["validate-results", analysis_dir, "--ops-dir", ops_dir, "--now", NOW],
                    )

                self.assertEqual(analysis_validation.MALFORMED, code, payload)
                self.assertFalse(payload.get("ok", False))
                self.assertEqual("malformed_task_state", payload.get("reason"))

    def test_validate_run_returns_malformed_for_bad_structured_outputs(self) -> None:
        artifact_paths = [
            "artifacts/analysis_run/metrics.json",
            "artifacts/analysis_run/diagnostics.json",
            "artifacts/analysis_run/robustness_checks.json",
        ]
        for artifact_path in artifact_paths:
            with self.subTest(artifact_path=artifact_path):
                with tempfile.TemporaryDirectory() as tmpdir:
                    ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
                    write_completed_artifacts(analysis_dir)
                    (analysis_dir / artifact_path).write_text("{", encoding="utf-8")

                    code, payload = run_json(
                        analysis_validation,
                        ["validate-run", analysis_dir, "--ops-dir", ops_dir, "--now", NOW],
                    )

                self.assertEqual(analysis_validation.MALFORMED, code, payload)
                self.assertFalse(payload.get("ok", False))
                self.assertEqual("malformed_task_state", payload.get("reason"))

    def test_validate_results_rejects_claim_gate_failure(self) -> None:
        summary = result_summary(
            claim="The model produces calibrated risk probabilities for each entity.",
            claim_type="probabilistic",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir, summary=summary)

            code, payload = run_json(analysis_validation, ["validate-results", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

        self.assertEqual(analysis_validation.VALIDATION_FAILED, code, payload)
        self.assertIn("claim_gate_decision", gate_names(payload))


if __name__ == "__main__":
    unittest.main()

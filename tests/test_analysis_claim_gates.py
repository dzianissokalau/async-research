"""Regression tests for analysis claim gates."""

from __future__ import annotations

import copy
import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from async_research_workflow.resources import schema_path, template_path
from async_research_workflow.scripts import analysis_claim_gates
from async_research_workflow.scripts.validate_json_artifact import (
    load_json,
    schema_keyword_errors,
    validate,
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


def schema_errors(payload: dict, schema_name: str) -> list[dict[str, str]]:
    schema = load_json(schema_path(schema_name))
    return [error.to_dict() for error in validate(payload, schema)]


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_main(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = analysis_claim_gates.main([str(arg) for arg in argv])
    return code, json.loads(stream.getvalue())


def base_summary(**overrides) -> dict:
    payload = {
        "schema_version": "1.0",
        "framework_version": "result_acceptance_v1.0",
        "result_id": "RESULT-0001",
        "experiment_plan_id": "EXP-0001",
        "run_id": "RUN-0001",
        "task_id": "TASK-0004",
        "run_manifest_path": "research_ops/tasks/TASK-0004-run-analysis/artifacts/analysis_run/run_manifest.json",
        "artifact_version": "git:fixture",
        "dataset_versions": [{"source_id": "DS-0001", "version": "fixture"}],
        "primary_metric": "Out-of-sample MAE reduction",
        "baseline_results": "Baseline MAE 10.4",
        "candidate_results": "Candidate MAE 9.7",
        "validation_split_results": "2025 holdout",
        "robustness_results": ["Alternative validation window passed"],
        "leakage_check_results": ["No leakage detected"],
        "limitations": ["Bounded fixture claim only"],
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


MISSING = object()


def evaluate(
    summary: dict,
    metrics: object = MISSING,
    diagnostics: object = MISSING,
    robustness: object = MISSING,
    trusted_identity: dict[str, str] | None = None,
) -> dict:
    return analysis_claim_gates.evaluate_claim_gates(
        summary,
        metrics=metrics if metrics is not MISSING else template_payload("analysis_metrics_template.md"),
        diagnostics=diagnostics if diagnostics is not MISSING else template_payload("analysis_diagnostics_template.md"),
        robustness=robustness if robustness is not MISSING else template_payload("analysis_robustness_checks_template.md"),
        generated_at="2026-05-09T10:45:00Z",
        trusted_identity=trusted_identity,
    )


class AnalysisClaimGateTests(unittest.TestCase):
    def test_claim_gate_schema_uses_supported_validator_subset(self) -> None:
        schema = load_json(schema_path("analysis_claim_gates.schema.json"))

        self.assertEqual([], [error.to_dict() for error in schema_keyword_errors(schema)])

    def test_claim_gate_template_validates_against_schema(self) -> None:
        payload = template_payload("analysis_claim_gates_template.md")

        self.assertEqual([], schema_errors(payload, "analysis_claim_gates.schema.json"))

    def test_predictive_claim_with_valid_baseline_and_validation_is_accepted_at_moderate(self) -> None:
        report = evaluate(base_summary())

        self.assertEqual("accepted", report["claim_decision"])
        self.assertEqual("moderate", report["max_claim_strength"])
        self.assertEqual([], schema_errors(report, "analysis_claim_gates.schema.json"))

    def test_cli_accepts_matching_artifacts_without_trusted_identity_args(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            summary_path = root / "summary.json"
            metrics_path = root / "metrics.json"
            diagnostics_path = root / "diagnostics.json"
            robustness_path = root / "robustness.json"
            write_json(summary_path, base_summary())
            write_json(metrics_path, template_payload("analysis_metrics_template.md"))
            write_json(diagnostics_path, template_payload("analysis_diagnostics_template.md"))
            write_json(robustness_path, template_payload("analysis_robustness_checks_template.md"))

            code, payload = run_main(
                [
                    "--summary",
                    summary_path,
                    "--metrics",
                    metrics_path,
                    "--diagnostics",
                    diagnostics_path,
                    "--robustness",
                    robustness_path,
                ]
            )

        self.assertEqual(analysis_claim_gates.SUCCESS, code, payload)
        self.assertEqual("accepted", payload["claim_decision"])

    def test_causal_language_without_identification_tests_is_rejected(self) -> None:
        summary = base_summary(
            claim="The candidate feature causes lower error rates in deployed settings.",
            claim_type="predictive",
        )

        report = evaluate(summary, robustness=None)

        self.assertEqual("rejected", report["claim_decision"])
        gates = {gate["gate"]: gate for gate in report["claim_gate_results"]}
        self.assertEqual("reject", gates["causal_identification_tests"]["status"])

    def test_unknown_claim_type_fails_closed_without_bypassing_metrics_gates(self) -> None:
        summary = base_summary(
            claim="The candidate feature improves predictive accuracy in this bounded backtest.",
            claim_type="predicitive",
            claim_strength="strong",
        )

        report = evaluate(summary, metrics=None)

        self.assertEqual("rejected", report["claim_decision"])
        self.assertEqual("none", report["max_claim_strength"])
        gates = {gate["gate"]: gate for gate in report["claim_gate_results"]}
        self.assertEqual("reject", gates["claim_type_classified"]["status"])

    def test_artifact_identity_mismatch_is_rejected(self) -> None:
        metrics = copy.deepcopy(template_payload("analysis_metrics_template.md"))
        metrics["run_id"] = "RUN-9999"

        report = evaluate(base_summary(), metrics=metrics)

        self.assertEqual("rejected", report["claim_decision"])
        gates = {gate["gate"]: gate for gate in report["claim_gate_results"]}
        self.assertEqual("reject", gates["artifact_identity_matches_claim"]["status"])

    def test_missing_summary_task_id_is_rejected_without_trusted_context(self) -> None:
        summary = base_summary()
        del summary["task_id"]

        report = evaluate(summary)

        self.assertEqual("rejected", report["claim_decision"])
        gates = {gate["gate"]: gate for gate in report["claim_gate_results"]}
        self.assertEqual("reject", gates["claim_identity_present"]["status"])

    def test_missing_summary_task_id_can_be_supplied_by_trusted_context(self) -> None:
        summary = base_summary()
        del summary["task_id"]

        report = evaluate(summary, trusted_identity={"task_id": "TASK-0004"})

        self.assertEqual("accepted", report["claim_decision"])
        self.assertEqual("TASK-0004", report["task_id"])

    def test_causal_blocking_robustness_check_rejects_even_with_identification_summary(self) -> None:
        summary = base_summary(
            claim="The intervention causes lower error rates.",
            claim_type="causal",
            identification_tests=["Placebo check"],
            identification_assumptions=["Parallel trends assumption documented."],
        )
        robustness = copy.deepcopy(template_payload("analysis_robustness_checks_template.md"))
        robustness["summary"]["strongest_supported_claim"] = "causal"
        robustness["planned_checks"][0].update(
            {
                "check_family": "placebo",
                "status": "fail",
                "decision_impact": "blocks_claim",
                "result": "Placebo effect appears before treatment.",
            }
        )

        report = evaluate(summary, robustness=robustness)

        self.assertEqual("rejected", report["claim_decision"])
        gates = {gate["gate"]: gate for gate in report["claim_gate_results"]}
        self.assertEqual("reject", gates["causal_identification_tests"]["status"])

    def test_probability_claim_without_applicable_calibration_or_uncertainty_is_rejected(self) -> None:
        summary = base_summary(
            claim="The model produces calibrated risk probabilities for each entity.",
            claim_type="probabilistic",
        )

        report = evaluate(summary)

        self.assertEqual("rejected", report["claim_decision"])
        gates = {gate["gate"]: gate for gate in report["claim_gate_results"]}
        self.assertEqual("reject", gates["probability_calibration_or_uncertainty"]["status"])

    def test_probability_applicable_not_applicable_status_is_rejected(self) -> None:
        diagnostics = copy.deepcopy(template_payload("analysis_diagnostics_template.md"))
        diagnostics["calibration_checks"][0]["applicable"] = True
        diagnostics["calibration_checks"][0]["status"] = "not_applicable"
        summary = base_summary(
            claim="The model produces calibrated risk probabilities for each entity.",
            claim_type="probabilistic",
        )

        report = evaluate(summary, diagnostics=diagnostics)

        self.assertEqual("rejected", report["claim_decision"])
        gates = {gate["gate"]: gate for gate in report["claim_gate_results"]}
        self.assertEqual("reject", gates["probability_calibration_or_uncertainty"]["status"])

    def test_predictive_claim_requires_applicable_passing_leakage_check(self) -> None:
        diagnostics = copy.deepcopy(template_payload("analysis_diagnostics_template.md"))
        diagnostics["leakage_checks"][0]["status"] = "not_applicable"

        report = evaluate(base_summary(), diagnostics=diagnostics)

        self.assertEqual("rejected", report["claim_decision"])
        gates = {gate["gate"]: gate for gate in report["claim_gate_results"]}
        self.assertEqual("reject", gates["predictive_leakage_checks"]["status"])

    def test_warning_diagnostics_cap_requested_claim_strength(self) -> None:
        diagnostics = copy.deepcopy(template_payload("analysis_diagnostics_template.md"))
        diagnostics["segment_diagnostics"][0]["status"] = "warn"
        summary = base_summary(
            claim="The analysis describes a bounded pattern with usable caveats.",
            claim_type="descriptive",
            claim_strength="moderate",
        )

        report = evaluate(summary, diagnostics=diagnostics)

        self.assertEqual("capped", report["claim_decision"])
        self.assertEqual("suggestive", report["max_claim_strength"])
        gates = {gate["gate"]: gate for gate in report["claim_gate_results"]}
        self.assertEqual("cap", gates["diagnostic_quality"]["status"])

    def test_public_or_high_stakes_claim_routes_to_human_review(self) -> None:
        summary = base_summary(
            claim="This bounded descriptive result is ready for a public memo.",
            claim_type="descriptive",
            claim_strength="suggestive",
            public_or_high_stakes=True,
            human_approval_present=False,
        )

        report = evaluate(summary)

        self.assertEqual("needs_human", report["claim_decision"])
        self.assertEqual("needs_human", report["recommended_route"])
        self.assertTrue(report["human_gate"]["required"])
        self.assertFalse(report["human_gate"]["satisfied"])


if __name__ == "__main__":
    unittest.main()

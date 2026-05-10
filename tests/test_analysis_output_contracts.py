"""Regression tests for analysis output contracts."""

from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path

from async_research_workflow.resources import schema_path, template_path
from async_research_workflow.scripts.validate_json_artifact import (
    load_json,
    schema_keyword_errors,
    validate,
)


CONTRACTS = {
    "metrics": {
        "schema": "analysis_metrics.schema.json",
        "template": "analysis_metrics_template.md",
    },
    "diagnostics": {
        "schema": "analysis_diagnostics.schema.json",
        "template": "analysis_diagnostics_template.md",
    },
    "robustness": {
        "schema": "analysis_robustness_checks.schema.json",
        "template": "analysis_robustness_checks_template.md",
    },
}
ROOT = Path(__file__).resolve().parents[1]


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


def repo_root_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class AnalysisOutputContractTests(unittest.TestCase):
    def test_output_schemas_use_supported_validator_subset(self) -> None:
        for name, contract in CONTRACTS.items():
            with self.subTest(name=name):
                schema = load_json(schema_path(contract["schema"]))
                self.assertEqual([], [error.to_dict() for error in schema_keyword_errors(schema)])

    def test_output_templates_validate_against_schemas(self) -> None:
        for name, contract in CONTRACTS.items():
            with self.subTest(name=name):
                payload = template_payload(contract["template"])
                self.assertEqual([], schema_errors(payload, contract["schema"]))

    def test_metrics_require_baseline_candidate_and_validation_outputs(self) -> None:
        payload = template_payload("analysis_metrics_template.md")
        payload["baseline_metrics"] = []
        payload["candidate_metrics"] = []
        payload["validation_metrics"] = []

        errors = schema_errors(payload, "analysis_metrics.schema.json")
        paths = {error["path"] for error in errors}

        self.assertIn("$.baseline_metrics", paths)
        self.assertIn("$.candidate_metrics", paths)
        self.assertIn("$.validation_metrics", paths)

    def test_metrics_arrays_capture_role_value_split_segment_and_source(self) -> None:
        payload = template_payload("analysis_metrics_template.md")
        broken = copy.deepcopy(payload)
        del broken["baseline_metrics"][0]["role"]
        del broken["baseline_metrics"][0]["value"]
        del broken["baseline_metrics"][0]["split"]
        del broken["baseline_metrics"][0]["segment"]
        del broken["baseline_metrics"][0]["source"]

        errors = schema_errors(broken, "analysis_metrics.schema.json")
        paths = {error["path"] for error in errors}

        self.assertIn("$.baseline_metrics[0].role", paths)
        self.assertIn("$.baseline_metrics[0].value", paths)
        self.assertIn("$.baseline_metrics[0].split", paths)
        self.assertIn("$.baseline_metrics[0].segment", paths)
        self.assertIn("$.baseline_metrics[0].source", paths)

    def test_metrics_reject_wrong_role_in_required_metric_arrays(self) -> None:
        payload = template_payload("analysis_metrics_template.md")
        payload["baseline_metrics"][0]["role"] = "diagnostic"

        errors = schema_errors(payload, "analysis_metrics.schema.json")

        self.assertIn("$.baseline_metrics[0].role", {error["path"] for error in errors})

    def test_diagnostics_require_missingness_join_leakage_segments_and_limitations(self) -> None:
        payload = template_payload("analysis_diagnostics_template.md")
        payload["missingness_checks"] = []
        payload["join_quality_checks"] = []
        payload["leakage_checks"] = []
        payload["segment_diagnostics"] = []
        payload["calibration_checks"] = []
        payload["uncertainty_checks"] = []
        payload["limitations"] = []

        errors = schema_errors(payload, "analysis_diagnostics.schema.json")
        paths = {error["path"] for error in errors}

        self.assertIn("$.missingness_checks", paths)
        self.assertIn("$.join_quality_checks", paths)
        self.assertIn("$.leakage_checks", paths)
        self.assertIn("$.segment_diagnostics", paths)
        self.assertIn("$.calibration_checks", paths)
        self.assertIn("$.uncertainty_checks", paths)
        self.assertIn("$.limitations", paths)

    def test_diagnostics_allow_no_join_without_fake_source_ids_or_keys(self) -> None:
        payload = template_payload("analysis_diagnostics_template.md")
        payload["join_quality_checks"] = [
            {
                "name": "No join used",
                "applicable": False,
                "status": "not_applicable",
                "evidence": "Single-source run; no join was performed."
            }
        ]

        self.assertEqual([], schema_errors(payload, "analysis_diagnostics.schema.json"))

    def test_diagnostics_allow_nonapplicable_calibration_and_uncertainty(self) -> None:
        payload = template_payload("analysis_diagnostics_template.md")

        self.assertEqual("not_applicable", payload["calibration_checks"][0]["status"])
        self.assertEqual("not_applicable", payload["uncertainty_checks"][0]["status"])
        self.assertEqual([], schema_errors(payload, "analysis_diagnostics.schema.json"))

    def test_diagnostics_require_explicit_calibration_and_uncertainty_rows(self) -> None:
        payload = template_payload("analysis_diagnostics_template.md")
        del payload["calibration_checks"]
        del payload["uncertainty_checks"]

        errors = schema_errors(payload, "analysis_diagnostics.schema.json")
        paths = {error["path"] for error in errors}

        self.assertIn("$.calibration_checks", paths)
        self.assertIn("$.uncertainty_checks", paths)

    def test_diagnostic_rates_cannot_exceed_one(self) -> None:
        payload = template_payload("analysis_diagnostics_template.md")
        payload["missingness_checks"][0]["missing_rate"] = 1.01
        payload["join_quality_checks"][0]["unmatched_rate"] = 1.01
        payload["join_quality_checks"][0]["duplicate_key_rate"] = 1.01

        errors = schema_errors(payload, "analysis_diagnostics.schema.json")
        paths = {error["path"] for error in errors}

        self.assertIn("$.missingness_checks[0].missing_rate", paths)
        self.assertIn("$.join_quality_checks[0].unmatched_rate", paths)
        self.assertIn("$.join_quality_checks[0].duplicate_key_rate", paths)

    def test_robustness_requires_planned_checks_summary_and_limitations(self) -> None:
        payload = template_payload("analysis_robustness_checks_template.md")
        payload["planned_checks"] = []
        del payload["summary"]["strongest_supported_claim"]
        payload["limitations"] = []

        errors = schema_errors(payload, "analysis_robustness_checks.schema.json")
        paths = {error["path"] for error in errors}

        self.assertIn("$.planned_checks", paths)
        self.assertIn("$.summary.strongest_supported_claim", paths)
        self.assertIn("$.limitations", paths)

    def test_robustness_not_run_supporting_claim_is_phase_five_semantic_gap(self) -> None:
        payload = template_payload("analysis_robustness_checks_template.md")
        payload["planned_checks"][0]["status"] = "not_run"
        payload["planned_checks"][0]["decision_impact"] = "supports_claim"
        payload["summary"]["overall_status"] = "pass"

        self.assertEqual([], schema_errors(payload, "analysis_robustness_checks.schema.json"))

    def test_roadmap_no_longer_advertises_separate_leakage_checks_json(self) -> None:
        roadmap = repo_root_text("roadmaps/delivered_hypothesis_testing_framework_roadmap.md")

        self.assertNotIn("leakage_checks.json", roadmap)

    def test_output_contracts_do_not_require_specific_modeling_libraries(self) -> None:
        forbidden = ["sklearn", "statsmodels", "pandas", "xgboost", "torch", "tensorflow"]
        for name, contract in CONTRACTS.items():
            with self.subTest(name=name):
                text = schema_path(contract["schema"]).read_text(encoding="utf-8").lower()
                self.assertFalse(any(term in text for term in forbidden), text)


if __name__ == "__main__":
    unittest.main()

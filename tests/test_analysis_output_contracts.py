"""Regression tests for analysis output contracts."""

from __future__ import annotations

import copy
import json
import re
import unittest

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

    def test_metrics_require_baseline_and_validation_outputs(self) -> None:
        payload = template_payload("analysis_metrics_template.md")
        payload["baseline_comparisons"] = []
        payload["validation_splits"] = []

        errors = schema_errors(payload, "analysis_metrics.schema.json")
        paths = {error["path"] for error in errors}

        self.assertIn("$.baseline_comparisons", paths)
        self.assertIn("$.validation_splits", paths)

    def test_metrics_rows_capture_role_value_split_segment_and_source(self) -> None:
        payload = template_payload("analysis_metrics_template.md")
        broken = copy.deepcopy(payload)
        del broken["metric_rows"][0]["role"]
        del broken["metric_rows"][0]["value"]
        del broken["metric_rows"][0]["split"]
        del broken["metric_rows"][0]["segment"]
        del broken["metric_rows"][0]["source"]

        errors = schema_errors(broken, "analysis_metrics.schema.json")
        paths = {error["path"] for error in errors}

        self.assertIn("$.metric_rows[0].role", paths)
        self.assertIn("$.metric_rows[0].value", paths)
        self.assertIn("$.metric_rows[0].split", paths)
        self.assertIn("$.metric_rows[0].segment", paths)
        self.assertIn("$.metric_rows[0].source", paths)

    def test_diagnostics_require_missingness_join_leakage_segments_and_limitations(self) -> None:
        payload = template_payload("analysis_diagnostics_template.md")
        payload["missingness_checks"] = []
        payload["join_quality_checks"] = []
        payload["leakage_checks"] = []
        payload["segment_diagnostics"] = []
        payload["limitations"] = []

        errors = schema_errors(payload, "analysis_diagnostics.schema.json")
        paths = {error["path"] for error in errors}

        self.assertIn("$.missingness_checks", paths)
        self.assertIn("$.join_quality_checks", paths)
        self.assertIn("$.leakage_checks", paths)
        self.assertIn("$.segment_diagnostics", paths)
        self.assertIn("$.limitations", paths)

    def test_diagnostics_allow_nonapplicable_calibration_and_uncertainty(self) -> None:
        payload = template_payload("analysis_diagnostics_template.md")

        self.assertEqual("not_applicable", payload["calibration_checks"][0]["status"])
        self.assertEqual("not_applicable", payload["uncertainty_checks"][0]["status"])
        self.assertEqual([], schema_errors(payload, "analysis_diagnostics.schema.json"))

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

    def test_output_contracts_do_not_require_specific_modeling_libraries(self) -> None:
        forbidden = ["sklearn", "statsmodels", "pandas", "xgboost", "torch", "tensorflow"]
        for name, contract in CONTRACTS.items():
            with self.subTest(name=name):
                text = schema_path(contract["schema"]).read_text(encoding="utf-8").lower()
                self.assertFalse(any(term in text for term in forbidden), text)


if __name__ == "__main__":
    unittest.main()

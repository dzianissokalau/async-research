"""Regression tests for the analysis run manifest contract."""

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


def template_payload() -> dict:
    text = template_path("artifact_templates", "analysis_run_manifest_template.md").read_text(encoding="utf-8")
    match = re.search(r"```json\s*(.*?)```", text, re.DOTALL)
    if match is None:
        raise AssertionError("analysis run manifest template must include a fenced JSON block")
    payload = json.loads(match.group(1))
    if not isinstance(payload, dict):
        raise AssertionError("analysis run manifest template JSON must be an object")
    return payload


class AnalysisRunContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = load_json(schema_path("analysis_run.schema.json"))

    def schema_errors(self, payload: dict) -> list[dict[str, str]]:
        return [error.to_dict() for error in validate(payload, self.schema)]

    def test_schema_uses_supported_validator_subset(self) -> None:
        self.assertEqual([], [error.to_dict() for error in schema_keyword_errors(self.schema)])

    def test_template_manifest_validates_against_schema(self) -> None:
        self.assertEqual([], self.schema_errors(template_payload()))

    def test_manifest_requires_accepted_plan_identity(self) -> None:
        payload = template_payload()
        del payload["accepted_plan_task_id"]

        errors = self.schema_errors(payload)

        self.assertIn({"path": "$.accepted_plan_task_id", "message": "required field missing"}, errors)

    def test_run_analysis_is_the_only_phase_one_task_type(self) -> None:
        payload = template_payload()
        payload["task_type"] = "evaluate_results"

        errors = self.schema_errors(payload)

        self.assertTrue(any(error["path"] == "$.task_type" and "enum" in error["message"] for error in errors), errors)

    def test_deviations_must_be_explicit_objects(self) -> None:
        payload = template_payload()
        payload["deviations_from_plan"] = [
            {
                "field": "primary_metric",
                "planned_value": "MAE reduction",
                "actual_value": "RMSE reduction",
                "reason": "Worker changed metric after seeing results.",
            }
        ]

        errors = self.schema_errors(payload)

        self.assertIn(
            {
                "path": "$.deviations_from_plan[0].reviewer_action_required",
                "message": "required field missing",
            },
            errors,
        )

    def test_path_fields_must_be_workspace_relative(self) -> None:
        payload = copy.deepcopy(template_payload())
        payload["analysis_config_path"] = "/tmp/analysis_config.json"
        payload["output_paths"][0] = "../outside/run_manifest.json"

        errors = self.schema_errors(payload)
        paths = {error["path"] for error in errors}

        self.assertIn("$.analysis_config_path", paths)
        self.assertIn("$.output_paths[0]", paths)


if __name__ == "__main__":
    unittest.main()

"""Regression tests for the analysis run manifest contract."""

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
from async_research_workflow.scripts import validate_result_acceptance
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


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_json(entrypoint, argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = entrypoint.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def result_summary_without_manifest() -> dict:
    return {
        "schema_version": "1.0",
        "framework_version": "result_acceptance_v1.0",
        "result_id": "RESULT-9001",
        "experiment_plan_id": "EXP-9001",
        "run_id": "RUN-9001",
        "artifact_version": "git:fixture",
        "dataset_versions": [{"source_id": "DS-0001", "version": "fixture"}],
        "primary_metric": "Out-of-sample MAE reduction",
        "baseline_results": "Baseline MAE 1.00",
        "candidate_results": "Candidate MAE 0.96",
        "validation_split_results": "Train then validation.",
        "robustness_results": ["Stable by segment"],
        "leakage_check_results": ["No leakage detected"],
        "limitations": ["Predictive only"],
        "claim": "Fixture result is useful.",
        "claim_type": "predictive",
        "claim_strength": "suggestive",
        "recommended_decision": "accept_as_evidence",
        "public_or_high_stakes": False,
        "human_approval_present": False,
        "follow_up_tasks": [{"reason": "Retest later", "required_artifact": "metrics", "priority": 3}],
    }


class AnalysisRunContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = load_json(schema_path("analysis_run.schema.json"))

    def schema_errors(self, payload: dict) -> list[dict[str, str]]:
        return [error.to_dict() for error in validate(payload, self.schema)]

    def test_schema_uses_supported_validator_subset(self) -> None:
        self.assertEqual([], [error.to_dict() for error in schema_keyword_errors(self.schema)])

    def test_template_manifest_validates_against_schema(self) -> None:
        self.assertEqual([], self.schema_errors(template_payload()))

    def test_planned_manifest_does_not_require_completion_fields(self) -> None:
        payload = template_payload()

        self.assertEqual("planned", payload["run_status"])
        self.assertNotIn("completed_at", payload)
        self.assertNotIn("runtime_minutes", payload)
        self.assertNotIn("cost", payload)
        self.assertEqual([], self.schema_errors(payload))

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

    def test_manual_runs_can_record_no_separate_config_file(self) -> None:
        payload = template_payload()
        payload["analysis_config_path"] = "none"
        payload["runner"]["type"] = "manual"
        payload["runner"]["parameters_ref"] = "none"

        self.assertEqual([], self.schema_errors(payload))

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
        payload["planned_outputs"][0]["path"] = "research_ops/queue.md"

        errors = self.schema_errors(payload)
        paths = {error["path"] for error in errors}

        self.assertIn("$.analysis_config_path", paths)
        self.assertIn("$.output_paths[0]", paths)
        self.assertIn("$.planned_outputs[0].path", paths)

    def test_required_provenance_arrays_must_be_nonempty(self) -> None:
        payload = template_payload()
        payload["data_versions"] = []
        payload["baseline_refs"] = []
        payload["planned_outputs"] = []
        payload["output_paths"] = []

        errors = self.schema_errors(payload)
        paths = {error["path"] for error in errors}

        self.assertIn("$.data_versions", paths)
        self.assertIn("$.baseline_refs", paths)
        self.assertIn("$.planned_outputs", paths)
        self.assertIn("$.output_paths", paths)

    def test_result_acceptance_requires_analysis_run_manifest_link_for_result_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = Path(tmpdir) / "research_ops"
            task_dir = ops_dir / "tasks" / "TASK-9001-run-analysis"
            write_json(
                task_dir / "status.json",
                {
                    "schema_version": "1.0",
                    "id": "TASK-9001",
                    "title": "Run analysis fixture",
                    "type": "run_analysis",
                    "status": "accepted",
                    "created_at": "2026-05-09T00:00:00Z",
                    "updated_at": "2026-05-09T00:00:00Z",
                    "result": {
                        "recommendation": "ready",
                        "claim_strength": "suggestive",
                        "key_finding": "Fixture result is useful.",
                        "followup_count": 0,
                    },
                },
            )
            summary = result_summary_without_manifest()
            task_dir.joinpath("worker_output.md").write_text(
                "Fixture result is useful.\n\n```json\n" + json.dumps(summary, indent=2, sort_keys=True) + "\n```\n",
                encoding="utf-8",
            )
            write_json(
                task_dir / "review_panel" / "aggregate.json",
                {
                    "aggregate_decision": "accepted",
                    "aggregate_claim_strength": "suggestive",
                    "tier": 2,
                    "required_reviewers": ["primary", "methodology"],
                    "reviews": [{"reviewer_role": "primary", "decision": "accept", "claim_strength": "suggestive"}],
                    "disagreements": ["none"],
                },
            )

            code, payload = run_json(validate_result_acceptance, [task_dir, "--ops-dir", ops_dir])

        self.assertEqual(validate_result_acceptance.VALIDATION_FAILED, code, payload)
        gates = {item["gate"]: item for item in payload["hard_gate_failures"]}
        self.assertIn("result_summary_required_fields", gates)
        self.assertIn("run_manifest_path_points_to_analysis_run_manifest", gates)


if __name__ == "__main__":
    unittest.main()

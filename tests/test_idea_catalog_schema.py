"""Regression tests for idea catalog candidate schema lifecycle fields."""

from __future__ import annotations

from copy import deepcopy
import unittest

from async_research_workflow.resources import mission_policy_path, schema_path
from async_research_workflow.scripts.score_idea_candidate import score_candidate
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


def valid_score() -> dict:
    return {
        "mission_policy_version": "test_policy_v1.0",
        "budget_mode": "normal",
        "decision_impact": 4,
        "novelty": 3,
        "data_availability": 4,
        "feasibility": 4,
        "robustness_risk": 2,
        "cost": 2,
        "killability": 4,
        "reuse_potential": 4,
        "weighted_total": 16.5,
        "promotion_threshold": 14.0,
        "minimum_killability": 3,
        "max_promotions_per_week": 3,
        "budget_pressure_threshold": 0.8,
        "budget_mode_reason": "manual_normal",
        "budget_usage": {
            "monthly_usage_ratio": None,
            "weekly_usage_ratio": None,
            "monthly_cost_usd": 0.0,
            "weekly_cost_usd": 0.0,
            "monthly_budget_usd": None,
            "weekly_budget_usd": None,
        },
        "hard_gate_results": [
            {
                "gate": "research_question_present",
                "passed": True,
                "reason": "question is present",
            }
        ],
        "score_explanation": "Fixture score for schema tests.",
    }


def valid_candidate() -> dict:
    return {
        "schema_version": "1.0",
        "id": "IDEA-0001",
        "status": "candidate",
        "title": "Fixture idea",
        "question": "Can the fixture idea be validated cheaply?",
        "why_it_might_matter": "It checks schema compatibility for catalog candidates.",
        "required_data": ["DS-0001"],
        "minimum_viable_test": "Run a bounded data-readiness check.",
        "baseline": "Compare against a simple prior accepted-output baseline.",
        "main_risks": ["fixture risk"],
        "kill_reason": "Reject if required data is not available.",
        "score": valid_score(),
        "recommended_next_task": "data_readiness",
    }


def schema_errors(candidate: dict) -> list[dict]:
    schema = load_json(schema_path("idea_candidate.schema.json"))
    return [error.to_dict() for error in validate(candidate, schema)]


class IdeaCatalogSchemaTests(unittest.TestCase):
    def test_status_enums_are_identical_across_schema(self) -> None:
        schema = load_json(schema_path("idea_candidate.schema.json"))
        top_statuses = schema["properties"]["status"]["enum"]
        history_properties = schema["properties"]["decision_history"]["items"]["properties"]

        self.assertEqual(top_statuses, history_properties["from_status"]["enum"])
        self.assertEqual(top_statuses, history_properties["to_status"]["enum"])

    def test_old_shape_candidate_without_lifecycle_fields_still_validates(self) -> None:
        self.assertEqual([], schema_errors(valid_candidate()))

    def test_new_statuses_validate(self) -> None:
        for status in ["candidate", "promote", "park", "reject", "promoted", "needs_human"]:
            with self.subTest(status=status):
                candidate = valid_candidate()
                candidate["status"] = status

                self.assertEqual([], schema_errors(candidate))

    def test_lifecycle_refs_and_decision_history_validate(self) -> None:
        candidate = valid_candidate()
        candidate.update(
            {
                "created_at": "2026-05-06T10:00:00Z",
                "updated_at": "2026-05-06T10:30:00Z",
                "human_priority": 2,
                "promoted_task_id": "TASK-0001",
                "human_gate_reason": "needs owner decision on geography",
                "status_reason": "score and hard gates passed",
                "source_discovery_path": "research_ops/discovery/IDEA-0001.json",
                "library_refs": ["LIT-0001"],
                "data_refs": ["DS-0001"],
                "accepted_output_refs": ["TASK-0007"],
                "rejected_idea_refs": ["IDEA-0003"],
                "rejected_result_refs": ["TASK-0003"],
                "decision_history": [
                    {
                        "at": "2026-05-06T10:30:00Z",
                        "from_status": "candidate",
                        "to_status": "promote",
                        "reason": "score and hard gates passed",
                        "actor": "planner",
                    }
                ],
            }
        )

        self.assertEqual([], schema_errors(candidate))

    def test_optional_refs_can_be_absent(self) -> None:
        candidate = valid_candidate()
        candidate["status"] = "needs_human"
        candidate["human_gate_reason"] = "needs human owner decision"

        self.assertEqual([], schema_errors(candidate))

    def test_invalid_reference_patterns_fail_schema_validation(self) -> None:
        candidate = valid_candidate()
        candidate["data_refs"] = ["source-1"]
        candidate["accepted_output_refs"] = ["TASK-ABC"]
        candidate["library_refs"] = ["LIB-0001"]

        errors = schema_errors(candidate)

        self.assertCountEqual(
            ["$.library_refs[0]", "$.data_refs[0]", "$.accepted_output_refs[0]"],
            [error["path"] for error in errors],
        )

    def test_lifecycle_field_patterns_and_bounds_fail_closed(self) -> None:
        candidate = valid_candidate()
        candidate["created_at"] = "2026-05-06"
        candidate["human_priority"] = 6
        candidate["decision_history"] = [
            {
                "at": "2026-05-06T10:30:00Z",
                "from_status": "candidate",
                "to_status": "unknown",
                "reason": "bad transition",
            }
        ]

        errors = schema_errors(candidate)

        self.assertEqual(
            ["$.created_at", "$.human_priority", "$.decision_history[0].actor", "$.decision_history[0].to_status"],
            [error["path"] for error in errors],
        )

    def test_direct_experiment_request_still_reroutes_to_setup_task(self) -> None:
        candidate = deepcopy(valid_candidate())
        candidate["recommended_next_task"] = "experiment_plan"
        policy = load_json(mission_policy_path())

        scored = score_candidate(candidate, policy, "normal")

        self.assertEqual("promote", scored["status"])
        self.assertEqual("data_readiness", scored["recommended_next_task"])
        self.assertEqual(
            [
                {
                    "gate": "direct_experiment_blocked",
                    "passed": True,
                    "reason": "requested experiment_plan was rerouted to data_readiness",
                }
            ],
            [
                gate
                for gate in scored["score"]["hard_gate_results"]
                if gate["gate"] == "direct_experiment_blocked"
            ],
        )


if __name__ == "__main__":
    unittest.main()

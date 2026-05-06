"""Regression tests for idea catalog validation and read-only CLI reports."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.idea_catalog import CATALOG_BLOCK_END
from async_research_workflow.idea_catalog import CATALOG_BLOCK_START
from async_research_workflow.idea_catalog import CATALOG_TEMPLATE
from async_research_workflow.idea_catalog import PRIORITIZATION_TEMPLATE
from async_research_workflow.scripts import idea_catalog


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def run_helper_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = idea_catalog.main([str(arg) for arg in argv])
    return code, json.loads(stream.getvalue())


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    return code, json.loads(stream.getvalue())


def file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def bootstrap_empty_catalog(ops_dir: Path) -> None:
    write_text(ops_dir / "ideas" / "idea_catalog.md", CATALOG_TEMPLATE)
    write_text(ops_dir / "ideas" / "prioritization.md", PRIORITIZATION_TEMPLATE)


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
        "score_explanation": "Fixture score for catalog validator tests.",
    }


def valid_candidate(candidate_id: str = "IDEA-0001") -> dict:
    return {
        "schema_version": "1.0",
        "id": candidate_id,
        "status": "candidate",
        "title": f"Fixture {candidate_id}",
        "question": "Can the fixture idea be validated cheaply?",
        "why_it_might_matter": "It checks catalog validation.",
        "required_data": ["public fixture data"],
        "minimum_viable_test": "Run a bounded data-readiness check.",
        "baseline": "Compare against a simple baseline.",
        "main_risks": ["fixture risk"],
        "kill_reason": "Reject if fixture data is unavailable.",
        "score": valid_score(),
        "recommended_next_task": "data_readiness",
    }


class IdeaCatalogValidatorTests(unittest.TestCase):
    def test_empty_catalog_validates_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)
            before = file_snapshot(ops_dir)

            code, payload = run_helper_json(["validate", ops_dir])

            self.assertEqual(idea_catalog.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(0, payload["candidate_count"])
            self.assertEqual([], payload["failures"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_missing_ideas_directory_is_cold_start_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()

            code, payload = run_helper_json(["validate", ops_dir])

            self.assertEqual(idea_catalog.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(["catalog_cold_start"], [item["reason"] for item in payload["warnings"]])

    def test_duplicate_ids_and_filename_mismatch_fail_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)
            write_json(ops_dir / "ideas" / "IDEA-0001.json", valid_candidate("IDEA-0001"))
            write_json(ops_dir / "ideas" / "IDEA-0002.json", valid_candidate("IDEA-0001"))

            code, payload = run_helper_json(["validate", ops_dir])

            self.assertEqual(idea_catalog.MALFORMED, code, payload)
            self.assertFalse(payload["ok"])
            self.assertIn("IDEA-0001", payload["duplicate_idea_ids"])
            self.assertCountEqual(
                ["duplicate_idea_id", "filename_id_mismatch"],
                [item["reason"] for item in payload["failures"]],
            )

    def test_malformed_candidate_json_fails_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)
            write_text(ops_dir / "ideas" / "IDEA-0001.json", "{not-json\n")

            code, payload = run_helper_json(["validate", ops_dir])

            self.assertEqual(idea_catalog.MALFORMED, code, payload)
            self.assertEqual(["malformed_candidate_json"], [item["reason"] for item in payload["failures"]])

    def test_promote_missing_kill_reason_is_unsafe_promotion_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)
            candidate = valid_candidate("IDEA-0001")
            candidate["status"] = "promote"
            candidate["kill_reason"] = ""
            write_json(ops_dir / "ideas" / "IDEA-0001.json", candidate)

            code, payload = run_helper_json(["validate", ops_dir])

            self.assertEqual(idea_catalog.VALIDATION_FAILED, code, payload)
            self.assertIn("promote_missing_kill_reason", [item["reason"] for item in payload["failures"]])

    def test_direct_experiment_route_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)
            candidate = valid_candidate("IDEA-0001")
            candidate["status"] = "promote"
            candidate["recommended_next_task"] = "experiment_plan"
            write_json(ops_dir / "ideas" / "IDEA-0001.json", candidate)

            code, payload = run_helper_json(["validate", ops_dir])

            self.assertEqual(idea_catalog.VALIDATION_FAILED, code, payload)
            self.assertIn("direct_experiment_route_blocked", [item["reason"] for item in payload["failures"]])

    def test_invalid_promotion_state_reports_threshold_gates_and_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)
            candidate = valid_candidate("IDEA-0001")
            candidate["status"] = "promote"
            candidate["duplicate_status"] = "near_duplicate"
            candidate["score"]["weighted_total"] = 1.0
            candidate["score"]["hard_gate_results"] = [
                {"gate": "fixture_gate", "passed": False, "reason": "fixture failed"}
            ]
            write_json(ops_dir / "ideas" / "IDEA-0001.json", candidate)

            code, payload = run_helper_json(["validate", ops_dir])

            self.assertEqual(idea_catalog.VALIDATION_FAILED, code, payload)
            self.assertCountEqual(
                [
                    "promote_below_score_threshold",
                    "promote_duplicate_or_near_duplicate",
                    "promote_failed_hard_gates",
                ],
                [item["reason"] for item in payload["failures"]],
            )

    def test_stale_projection_is_warning_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            catalog = f"""# Idea Catalog

{CATALOG_BLOCK_START}
| idea_id | status | title |
| --- | --- | --- |
| IDEA-9999 | candidate | stale row |
{CATALOG_BLOCK_END}
"""
            write_text(ops_dir / "ideas" / "idea_catalog.md", catalog)
            write_text(ops_dir / "ideas" / "prioritization.md", PRIORITIZATION_TEMPLATE)
            write_json(ops_dir / "ideas" / "IDEA-0001.json", valid_candidate("IDEA-0001"))

            code, payload = run_helper_json(["validate", ops_dir])

            self.assertEqual(idea_catalog.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertCountEqual(
                ["orphaned_json_record", "orphaned_projection_row"],
                [item["reason"] for item in payload["warnings"]],
            )

    def test_promoted_candidate_requires_live_task_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)
            candidate = valid_candidate("IDEA-0001")
            candidate["status"] = "promoted"
            candidate["promoted_task_id"] = "TASK-9999"
            write_json(ops_dir / "ideas" / "IDEA-0001.json", candidate)

            code, payload = run_helper_json(["validate", ops_dir])

            self.assertEqual(idea_catalog.VALIDATION_FAILED, code, payload)
            self.assertEqual(["stale_promoted_task_id"], [item["reason"] for item in payload["failures"]])

    def test_missing_references_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)
            candidate = valid_candidate("IDEA-0001")
            candidate["accepted_output_refs"] = ["TASK-0007"]
            candidate["data_refs"] = ["DS-0001"]
            candidate["library_refs"] = ["LIT-0001"]
            write_json(ops_dir / "ideas" / "IDEA-0001.json", candidate)

            code, payload = run_helper_json(["validate", ops_dir])

            self.assertEqual(idea_catalog.VALIDATION_FAILED, code, payload)
            self.assertCountEqual(
                ["missing_accepted_output_ref", "missing_data_ref"],
                [item["reason"] for item in payload["failures"]],
            )
            self.assertEqual(["library_ref_unresolved"], [item["reason"] for item in payload["warnings"] if item["reason"] == "library_ref_unresolved"])

    def test_list_and_show_cli_are_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)
            candidate = valid_candidate("IDEA-0001")
            candidate["status"] = "park"
            candidate["revisit_condition"] = "Revisit next month."
            write_json(ops_dir / "ideas" / "IDEA-0001.json", candidate)
            write_json(ops_dir / "ideas" / "IDEA-0002.json", valid_candidate("IDEA-0002"))
            before = file_snapshot(ops_dir)

            list_code, listed = run_cli_json(["idea", "catalog", "list", ops_dir, "--status", "park"])
            show_code, shown = run_cli_json(["idea", "catalog", "show", ops_dir, "IDEA-0001"])

            self.assertEqual(cli.SUCCESS, list_code, listed)
            self.assertEqual(cli.SUCCESS, show_code, shown)
            self.assertEqual(["IDEA-0001"], [item["idea_id"] for item in listed["ideas"]])
            self.assertEqual("IDEA-0001", shown["idea_id"])
            self.assertEqual("park", shown["summary"]["status"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_show_missing_idea_returns_invalid_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)

            code, payload = run_cli_json(["idea", "catalog", "show", ops_dir, "IDEA-9999"])

            self.assertEqual(idea_catalog.INVALID_REQUEST, code, payload)
            self.assertEqual("idea_not_found", payload["reason"])

    def test_helper_does_not_mutate_during_validation_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_empty_catalog(ops_dir)
            candidate = copy.deepcopy(valid_candidate("IDEA-0001"))
            candidate["status"] = "needs_human"
            write_json(ops_dir / "ideas" / "IDEA-0001.json", candidate)
            before = file_snapshot(ops_dir)

            run_helper_json(["validate", ops_dir])

            self.assertEqual(before, file_snapshot(ops_dir))


if __name__ == "__main__":
    unittest.main()

"""Regression tests for deliverable maturity contracts."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.resources import schema_path
from async_research_workflow.scripts import deliverable_maturity
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


NOW = "2026-05-18T08:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(item) for item in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_task(ops_dir: Path, task_id: str, status: str = "accepted") -> Path:
    task_dir = ops_dir / "tasks" / f"{task_id}-fixture"
    write_json(
        task_dir / "status.json",
        {
            "schema_version": "1.0",
            "id": task_id,
            "title": f"{task_id} accepted source fixture",
            "type": "status_update",
            "status": status,
            "previous_status": "panel_review",
            "last_transition_reason": "deliverable_maturity_fixture",
            "priority": 3,
            "revision_count": 0,
            "max_revisions": 1,
            "revision_limit_hit": False,
            "allowed_paths": [f"research_ops/tasks/{task_dir.name}/**"],
            "max_minutes": 10,
            "requires_human": False,
            "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
            "human_gate_reason": None,
            "updated_at": NOW,
        },
    )
    return task_dir


class DeliverableMaturityTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        self.assertTrue(payload["ok"])
        return ops_dir

    def test_manifest_schema_accepts_starter_and_initialized_deliverable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0001",
                    "--title",
                    "Coffee and climate draft",
                    "--output-type",
                    "working_paper",
                    "--target-maturity",
                    "internal_draft",
                    "--current-maturity",
                    "research_note",
                    "--now",
                    NOW,
                ]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            manifest = load_json(schema_path("deliverable_manifest.schema.json"))
            record = load_json(ops_dir / "deliverables" / "deliverable_manifest.json")
            self.assertEqual([], [error.to_dict() for error in validate(record, manifest)])
            self.assertEqual("DELIV-0001", record["deliverables"][0]["deliverable_id"])
            self.assertTrue(record["deliverables"][0]["manuscript_gates"])
            self.assertTrue(all(row["status"] == "not_required" for row in record["deliverables"][0]["manuscript_gates"]))

    def test_accepted_source_task_does_not_imply_working_paper_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task(ops_dir, "TASK-0015", "accepted")
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0001",
                    "--title",
                    "Coffee and climate internal draft",
                    "--output-type",
                    "working_paper",
                    "--target-maturity",
                    "working_paper",
                    "--current-maturity",
                    "internal_draft",
                    "--target-audience",
                    "research collaborators",
                    "--source-task",
                    "TASK-0015",
                    "--complete-gate",
                    "source_caveat_checks",
                    "--complete-gate",
                    "claim_strength_review",
                    "--complete-gate",
                    "task_review",
                    "--complete-gate",
                    "accepted_evidence_linkage",
                    "--complete-gate",
                    "caveat_audit",
                    "--complete-gate",
                    "internal_workflow_disclosure",
                    "--complete-gate",
                    "draft_completeness_check",
                    "--review-independence",
                    "same_agent_visible",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0001"])

            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            self.assertFalse(checked["ok"])
            self.assertTrue(checked["source_tasks"][0]["accepted"])
            reasons = {item["reason"] for item in checked["blockers"]}
            self.assertIn("current_maturity_below_target", reasons)
            self.assertIn("gate_missing", reasons)
            self.assertIn("review_independence_below_required", reasons)
            self.assertEqual("internal_draft", checked["maturity"]["verified_ceiling"])

    def test_internal_draft_can_pass_only_when_declared_gates_are_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task(ops_dir, "TASK-0009", "accepted")
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0002",
                    "--title",
                    "Bounded internal synthesis",
                    "--output-type",
                    "internal_draft",
                    "--target-maturity",
                    "internal_draft",
                    "--current-maturity",
                    "internal_draft",
                    "--source-task",
                    "TASK-0009",
                    "--complete-gate",
                    "all",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0002"])

            self.assertEqual(cli.SUCCESS, code, checked)
            self.assertTrue(checked["ok"])
            self.assertEqual("internal_draft", checked["maturity"]["verified_ceiling"])
            self.assertTrue(all(item["status"] == "passed" for item in checked["checklist"]))

    def test_submission_ready_check_requires_manifest_metadata_and_editorial_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task(ops_dir, "TASK-0042", "accepted")
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0003",
                    "--title",
                    "Venue manuscript",
                    "--output-type",
                    "manuscript",
                    "--target-maturity",
                    "submission_ready_manuscript",
                    "--current-maturity",
                    "submission_ready_manuscript",
                    "--source-task",
                    "TASK-0042",
                    "--review-independence",
                    "different_model",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0003"])

            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            reasons = {item["reason"] for item in checked["blockers"]}
            self.assertIn("target_audience_missing", reasons)
            self.assertIn("target_venue_missing", reasons)
            missing_gates = {item["gate"] for item in checked["blockers"] if item["reason"] == "gate_missing"}
            for gate in {
                "complete_bibliography",
                "figures_tables_embedded_and_narrated",
                "data_code_availability",
                "adversarial_review",
                "response_matrix_closed",
                "independent_final_editorial_review",
            }:
                self.assertIn(gate, missing_gates)

    def test_same_agent_review_is_visible_and_caps_external_maturity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task(ops_dir, "TASK-0077", "accepted")
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0004",
                    "--title",
                    "Self-reviewed working paper",
                    "--output-type",
                    "working_paper",
                    "--target-maturity",
                    "working_paper",
                    "--current-maturity",
                    "working_paper",
                    "--target-audience",
                    "public research readers",
                    "--source-task",
                    "TASK-0077",
                    "--complete-gate",
                    "all",
                    "--review-independence",
                    "same_agent_visible",
                    "--reviewer",
                    "same-agent draft reviewer",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0004"])

            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            self.assertTrue(checked["review_independence"]["same_agent_review"])
            self.assertEqual("same_agent_visible", checked["review_independence"]["achieved"])
            self.assertEqual("internal_draft", checked["maturity"]["independence_ceiling"])
            self.assertIn("review_independence_below_required", {item["reason"] for item in checked["blockers"]})

    def test_partial_manuscript_gate_blocks_working_paper_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task(ops_dir, "TASK-0088", "accepted")
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0008",
                    "--title",
                    "Partial related-work draft",
                    "--output-type",
                    "working_paper",
                    "--target-maturity",
                    "working_paper",
                    "--current-maturity",
                    "working_paper",
                    "--target-audience",
                    "public research readers",
                    "--source-task",
                    "TASK-0088",
                    "--complete-gate",
                    "all",
                    "--manuscript-gate",
                    "related_work_synthesis=partial",
                    "--gate-rationale",
                    "related_work_synthesis=Missing competing hypotheses and recent source coverage.",
                    "--review-independence",
                    "separate_agent",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0008"])

            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            related_work = next(row for row in checked["checklist"] if row["gate"] == "related_work_synthesis")
            self.assertEqual("partial", related_work["status"])
            self.assertFalse(related_work["satisfied"])
            blockers = [item for item in checked["blockers"] if item.get("gate") == "related_work_synthesis"]
            self.assertEqual("gate_missing", blockers[0]["reason"])
            self.assertEqual("partial", blockers[0]["status"])
            self.assertEqual("shareable_memo", checked["maturity"]["gate_ceiling"])

    def test_raising_target_marks_new_manuscript_gates_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task(ops_dir, "TASK-0090", "accepted")
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0090",
                    "--title",
                    "Internal draft promoted later",
                    "--output-type",
                    "working_paper",
                    "--target-maturity",
                    "internal_draft",
                    "--current-maturity",
                    "internal_draft",
                    "--source-task",
                    "TASK-0090",
                    "--complete-gate",
                    "all",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual(
                "not_required",
                next(row for row in payload["manuscript_checklist"] if row["gate_id"] == "related_work_synthesis")["status"],
            )

            code, payload = run_cli_json(
                [
                    "deliverable",
                    "target",
                    ops_dir,
                    "DELIV-0090",
                    "--target-maturity",
                    "working_paper",
                    "--current-maturity",
                    "working_paper",
                    "--target-audience",
                    "public research readers",
                    "--review-independence",
                    "separate_agent",
                    "--now",
                    NOW,
                ]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            related_work = next(row for row in payload["manuscript_checklist"] if row["gate_id"] == "related_work_synthesis")
            self.assertTrue(related_work["required"])
            self.assertEqual("missing", related_work["status"])

    def test_waived_manuscript_gate_requires_rationale_and_remains_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task(ops_dir, "TASK-0091", "accepted")
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0091",
                    "--title",
                    "Shareable memo with exhibit waiver",
                    "--output-type",
                    "paper",
                    "--target-maturity",
                    "shareable_memo",
                    "--current-maturity",
                    "shareable_memo",
                    "--target-audience",
                    "policy readers",
                    "--source-task",
                    "TASK-0091",
                    "--complete-gate",
                    "all",
                    "--manuscript-gate",
                    "figures_tables_embedded_and_narrated=waived_by_human",
                    "--review-independence",
                    "separate_agent",
                    "--now",
                    NOW,
                ]
            )

            self.assertEqual(deliverable_maturity.INVALID_REQUEST, code, payload)
            self.assertIn("waiver_rationale_required", {item["reason"] for item in payload["errors"]})

            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0091",
                    "--title",
                    "Shareable memo with exhibit waiver",
                    "--output-type",
                    "paper",
                    "--target-maturity",
                    "shareable_memo",
                    "--current-maturity",
                    "shareable_memo",
                    "--target-audience",
                    "policy readers",
                    "--source-task",
                    "TASK-0091",
                    "--complete-gate",
                    "all",
                    "--manuscript-gate",
                    "figures_tables_embedded_and_narrated=waived_by_human",
                    "--waiver-rationale",
                    "figures_tables_embedded_and_narrated=Human owner waived figures because the memo is text-only.",
                    "--review-independence",
                    "separate_agent",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0091"])

            self.assertEqual(cli.SUCCESS, code, checked)
            figure_gate = next(
                row for row in checked["manuscript_checklist"] if row["gate_id"] == "figures_tables_embedded_and_narrated"
            )
            self.assertTrue(figure_gate["required"])
            self.assertEqual("waived_by_human", figure_gate["status"])
            self.assertIn("Human owner waived", figure_gate["waiver_rationale"])
            self.assertTrue(next(row for row in checked["checklist"] if row["gate"] == "figures_tables_embedded_and_narrated")["satisfied"])

    def test_check_fails_closed_on_invalid_manifest_maturity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            manifest_path = ops_dir / "deliverables" / "deliverable_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["deliverables"].append(
                {
                    "schema_version": "1.0",
                    "framework_version": "deliverable_maturity_v1.0",
                    "deliverable_id": "DELIV-0005",
                    "title": "Malformed maturity",
                    "output_type": "working_paper",
                    "target_audience": "",
                    "target_venue": "",
                    "target_maturity": "journal_ready",
                    "current_maturity": "internal_draft",
                    "source_task_ids": [],
                    "primary_artifact": "",
                    "owner": "",
                    "required_gates": [],
                    "completed_gates": [],
                    "review_independence": {
                        "minimum_required": "none",
                        "achieved": "none",
                        "same_agent_review": False,
                        "reviewer": "",
                        "notes": "",
                    },
                    "open_gaps": [],
                    "last_reviewed_at": None,
                    "created_at": NOW,
                    "updated_at": NOW,
                }
            )
            write_json(manifest_path, manifest)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0005"])

            self.assertEqual(deliverable_maturity.MALFORMED, code, checked)
            self.assertFalse(checked["ok"])
            self.assertIn("invalid_maturity", {item["reason"] for item in checked["errors"]})


if __name__ == "__main__":
    unittest.main()

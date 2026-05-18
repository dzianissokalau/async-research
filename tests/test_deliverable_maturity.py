"""Regression tests for deliverable maturity contracts."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from importlib.resources import as_file
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.resources import examples_path
from async_research_workflow.resources import schema_path
from async_research_workflow.resources import template_path
from async_research_workflow.scripts import deliverable_maturity
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-05-18T08:00:00Z"
COFFEE_FIXTURE = ROOT / "tests" / "fixtures" / "deliverable_maturity" / "coffee_pilot_internal_draft.md"


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
            self.assertEqual([], record["deliverables"][0]["review_response_matrix"])
            self.assertTrue(all(row["status"] == "not_required" for row in record["deliverables"][0]["manuscript_gates"]))

    def test_packaged_deliverable_manifest_template_is_schema_valid(self) -> None:
        manifest = load_json(schema_path("deliverable_manifest.schema.json"))
        template = load_json(template_path("artifact_templates", "deliverable_manifest_template.json"))

        self.assertEqual([], [error.to_dict() for error in validate(template, manifest)])
        self.assertEqual("internal_draft", template["deliverables"][0]["current_maturity"])
        self.assertEqual("working_paper", template["deliverables"][0]["target_maturity"])
        self.assertIn("Accepted source tasks are evidence only", template["deliverables"][0]["review_independence"]["notes"])

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
            self.assertEqual("internal draft accepted; working paper not ready", checked["readiness_label"])
            self.assertEqual(1, checked["task_acceptance"]["accepted_source_task_count"])
            self.assertTrue(checked["task_acceptance"]["accepted_source_tasks_do_not_imply_readiness"])
            self.assertEqual("missing", checked["editorial_qa"]["critic_status"])
            self.assertGreater(checked["editorial_qa"]["checklist_status_counts"]["missing"], 0)
            self.assertNotIn("final", checked["editorial_qa"]["honest_status"].lower())

    def test_coffee_pilot_fixture_requires_gates_critic_and_closed_response_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            with as_file(examples_path("coffee_pilot_deliverable_maturity", "research_ops")) as fixture:
                shutil.copytree(fixture, ops_dir)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0015"])

            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            self.assertFalse(checked["ok"])
            self.assertEqual("internal_draft", checked["maturity"]["current"])
            self.assertEqual("working_paper", checked["maturity"]["target"])
            self.assertTrue(checked["source_tasks"][0]["accepted"])
            missing_gates = {item["gate"] for item in checked["blockers"] if item["reason"] == "gate_missing"}
            for gate in {
                "related_work_synthesis",
                "figures_tables_embedded_and_narrated",
                "formal_citations",
                "complete_bibliography",
                "adversarial_review",
            }:
                self.assertIn(gate, missing_gates)
            reasons = {item["reason"] for item in checked["blockers"]}
            self.assertIn("critic_review_missing", reasons)
            self.assertIn("review_independence_below_required", reasons)
            self.assertEqual("internal draft accepted; working paper not ready", checked["readiness_label"])
            self.assertTrue(checked["task_acceptance"]["accepted_source_tasks_do_not_imply_readiness"])

            code, critic = run_cli_json(
                [
                    "deliverable",
                    "critic",
                    ops_dir,
                    "DELIV-0015",
                    "--independence-type",
                    "separate_agent",
                    "--reviewer",
                    "coffee fixture adversarial critic",
                    "--model-or-reviewer",
                    "separate reviewer fixture",
                    "--confidence",
                    "0.86",
                    "--recommended-maturity-ceiling",
                    "working_paper",
                    "--major",
                    "2",
                    "--required-revision-row",
                    "RRM-COFFEE-001: expand related-work synthesis",
                    "--required-revision-row",
                    "RRM-COFFEE-002: narrate figures and complete citations",
                    "--review-task-id",
                    "TASK-0016",
                    "--artifact-path",
                    "deliverables/critic_reviews/DELIV-0015-CRITIC-0001.md",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, critic)
            self.assertEqual("passed", critic["critic_review"]["status"])
            self.assertEqual(2, len(critic["critic_review"]["required_revision_rows"]))

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0015"])
            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            self.assertIn("response_matrix_missing_required_rows", {item["reason"] for item in checked["blockers"]})

            code, updated = run_cli_json(
                [
                    "deliverable",
                    "target",
                    ops_dir,
                    "DELIV-0015",
                    "--current-maturity",
                    "working_paper",
                    "--complete-gate",
                    "all",
                    "--clear-open-gaps",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, updated)

            for critique_id, section, issue in (
                ("RRM-COFFEE-001", "Related work", "Adjacent literature is missing."),
                ("RRM-COFFEE-002", "Figures and citations", "Exhibits and citations are not publication-ready."),
            ):
                code, response = run_cli_json(
                    [
                        "deliverable",
                        "response",
                        ops_dir,
                        "DELIV-0015",
                        "--critique-id",
                        critique_id,
                        "--source-review",
                        "CRITIC-0001",
                        "--severity",
                        "major",
                        "--target-section",
                        section,
                        "--issue",
                        issue,
                        "--decision",
                        "accepted",
                        "--required-change",
                        "Revise the manuscript and cite the closure artifact.",
                        "--owner",
                        "paper owner",
                        "--status",
                        "open",
                        "--now",
                        NOW,
                    ]
                )
                self.assertEqual(cli.SUCCESS, code, response)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0015"])
            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            reasons = {item["reason"] for item in checked["blockers"]}
            self.assertIn("response_matrix_missing_required_rows", reasons)
            self.assertIn("response_matrix_open_critical_major", reasons)
            self.assertEqual(2, checked["response_matrix"]["unresolved_critical_major_count"])

            for critique_id, artifact in (
                ("RRM-COFFEE-001", "deliverables/revisions/RRM-COFFEE-001-related-work.md"),
                ("RRM-COFFEE-002", "deliverables/revisions/RRM-COFFEE-002-figures-citations.md"),
            ):
                code, response = run_cli_json(
                    [
                        "deliverable",
                        "response",
                        ops_dir,
                        "DELIV-0015",
                        "--critique-id",
                        critique_id,
                        "--status",
                        "closed",
                        "--closure-artifact",
                        artifact,
                        "--now",
                        NOW,
                    ]
                )
                self.assertEqual(cli.SUCCESS, code, response)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0015"])

            self.assertEqual(cli.SUCCESS, code, checked)
            self.assertTrue(checked["ok"])
            self.assertEqual("working paper ready", checked["readiness_label"])
            self.assertEqual("working_paper", checked["maturity"]["verified_ceiling"])
            self.assertEqual("passed", checked["response_matrix"]["status"])

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
            self.assertEqual("internal draft accepted", checked["readiness_label"])
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

    def test_working_paper_requires_distinct_critic_review_even_when_gate_marked_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task(ops_dir, "TASK-0100", "accepted")
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0100",
                    "--title",
                    "Gate-complete draft without critic",
                    "--output-type",
                    "working_paper",
                    "--target-maturity",
                    "working_paper",
                    "--current-maturity",
                    "working_paper",
                    "--target-audience",
                    "public research readers",
                    "--source-task",
                    "TASK-0100",
                    "--complete-gate",
                    "all",
                    "--review-independence",
                    "separate_agent",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0100"])

            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            reasons = {item["reason"] for item in checked["blockers"]}
            self.assertIn("critic_review_missing", reasons)
            adversarial = next(row for row in checked["checklist"] if row["gate"] == "adversarial_review")
            self.assertEqual("missing", adversarial["status"])
            self.assertFalse(adversarial["satisfied"])
            self.assertEqual("shareable_memo", checked["maturity"]["critic_ceiling"])

    def test_independent_critic_review_satisfies_adversarial_gate_and_exposes_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task(ops_dir, "TASK-0101", "accepted")
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0101",
                    "--title",
                    "Critic-reviewed working paper",
                    "--output-type",
                    "working_paper",
                    "--target-maturity",
                    "working_paper",
                    "--current-maturity",
                    "working_paper",
                    "--target-audience",
                    "public research readers",
                    "--source-task",
                    "TASK-0101",
                    "--complete-gate",
                    "all",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)

            code, critic = run_cli_json(
                [
                    "deliverable",
                    "critic",
                    ops_dir,
                    "DELIV-0101",
                    "--independence-type",
                    "separate_agent",
                    "--reviewer",
                    "adversarial manuscript critic",
                    "--model-or-reviewer",
                    "separate reviewer fixture",
                    "--confidence",
                    "0.84",
                    "--recommended-maturity-ceiling",
                    "working_paper",
                    "--major",
                    "1",
                    "--required-revision-row",
                    "RRM-001: tighten related-work positioning",
                    "--review-task-id",
                    "TASK-0102",
                    "--artifact-path",
                    "deliverables/critic_reviews/DELIV-0101-CRITIC-0001.md",
                    "--now",
                    NOW,
                ]
            )

            self.assertEqual(cli.SUCCESS, code, critic)
            self.assertTrue(critic["critic_review"]["satisfied"])
            self.assertEqual("CRITIC-0001", critic["critic_review"]["eligible_review_id"])
            self.assertEqual(1, critic["critic_review"]["severity_distribution"]["major"])
            self.assertEqual(["RRM-001: tighten related-work positioning"], critic["critic_review"]["required_revision_rows"])

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0101"])

            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            self.assertIn("response_matrix_missing_required_rows", {item["reason"] for item in checked["blockers"]})
            self.assertEqual("shareable_memo", checked["maturity"]["response_matrix_ceiling"])

            code, unrelated = run_cli_json(
                [
                    "deliverable",
                    "response",
                    ops_dir,
                    "DELIV-0101",
                    "--critique-id",
                    "RRM-UNRELATED-001",
                    "--source-review",
                    "CRITIC-9999",
                    "--severity",
                    "major",
                    "--target-section",
                    "Methods",
                    "--issue",
                    "A different review row is already closed.",
                    "--decision",
                    "accepted",
                    "--required-change",
                    "No-op fixture change.",
                    "--owner",
                    "paper owner",
                    "--status",
                    "closed",
                    "--closure-artifact",
                    "deliverables/revisions/unrelated.md",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, unrelated)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0101"])
            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            self.assertEqual(1, checked["response_matrix"]["untracked_required_revision_count"])

            code, unresolved = run_cli_json(
                [
                    "deliverable",
                    "response",
                    ops_dir,
                    "DELIV-0101",
                    "--critique-id",
                    "RRM-0001",
                    "--source-review",
                    "CRITIC-0001",
                    "--severity",
                    "minor",
                    "--target-section",
                    "Related work",
                    "--issue",
                    "Related-work positioning needs tightening.",
                    "--decision",
                    "accepted",
                    "--required-change",
                    "Tighten related-work positioning.",
                    "--owner",
                    "paper owner",
                    "--status",
                    "open",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, unresolved)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0101"])
            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            self.assertEqual(1, checked["response_matrix"]["untracked_required_revision_count"])

            code, response = run_cli_json(
                [
                    "deliverable",
                    "response",
                    ops_dir,
                    "DELIV-0101",
                    "--critique-id",
                    "RRM-0001",
                    "--source-review",
                    "CRITIC-0001",
                    "--severity",
                    "major",
                    "--target-section",
                    "Related work",
                    "--issue",
                    "Related-work positioning needs tightening.",
                    "--decision",
                    "accepted",
                    "--required-change",
                    "Tighten related-work positioning.",
                    "--owner",
                    "paper owner",
                    "--status",
                    "closed",
                    "--closure-artifact",
                    "deliverables/revisions/DELIV-0101-related-work.md",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, response)
            self.assertEqual("passed", response["response_matrix"]["status"])
            self.assertEqual(2, response["response_matrix"]["closed_or_waived_count"])

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0101"])

            self.assertEqual(cli.SUCCESS, code, checked)
            adversarial = next(row for row in checked["checklist"] if row["gate"] == "adversarial_review")
            self.assertEqual("passed", adversarial["status"])
            self.assertTrue(adversarial["satisfied"])
            self.assertEqual("separate_agent", checked["review_independence"]["achieved"])
            self.assertEqual("working_paper", checked["maturity"]["critic_ceiling"])
            self.assertEqual("submission_ready_manuscript", checked["maturity"]["response_matrix_ceiling"])

    def test_open_material_response_matrix_rows_block_until_closed_or_human_waived(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task(ops_dir, "TASK-0105", "accepted")
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0105",
                    "--title",
                    "Response-matrix gated working paper",
                    "--output-type",
                    "working_paper",
                    "--target-maturity",
                    "working_paper",
                    "--current-maturity",
                    "working_paper",
                    "--target-audience",
                    "public research readers",
                    "--source-task",
                    "TASK-0105",
                    "--complete-gate",
                    "all",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)
            code, critic = run_cli_json(
                [
                    "deliverable",
                    "critic",
                    ops_dir,
                    "DELIV-0105",
                    "--independence-type",
                    "separate_agent",
                    "--confidence",
                    "0.84",
                    "--recommended-maturity-ceiling",
                    "working_paper",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, critic)

            code, response = run_cli_json(
                [
                    "deliverable",
                    "response",
                    ops_dir,
                    "DELIV-0105",
                    "--critique-id",
                    "RRM-0001",
                    "--source-review",
                    "CRITIC-0001",
                    "--severity",
                    "critical",
                    "--target-section",
                    "Methods",
                    "--issue",
                    "Methods evidence is not yet reproducible.",
                    "--decision",
                    "accepted",
                    "--required-change",
                    "Add reproducibility notes and artifacts.",
                    "--owner",
                    "paper owner",
                    "--status",
                    "open",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, response)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0105"])

            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            self.assertIn("response_matrix_open_critical_major", {item["reason"] for item in checked["blockers"]})
            self.assertEqual(1, checked["response_matrix"]["unresolved_critical_major_count"])

            code, invalid = run_cli_json(
                [
                    "deliverable",
                    "response",
                    ops_dir,
                    "DELIV-0105",
                    "--critique-id",
                    "RRM-0001",
                    "--decision",
                    "human_waived",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(deliverable_maturity.INVALID_REQUEST, code, invalid)
            self.assertIn("response_rationale_required", {item["reason"] for item in invalid["errors"]})

            code, waived = run_cli_json(
                [
                    "deliverable",
                    "response",
                    ops_dir,
                    "DELIV-0105",
                    "--critique-id",
                    "RRM-0001",
                    "--decision",
                    "human_waived",
                    "--response-rationale",
                    "Human owner accepts the reproducibility risk for this public working paper.",
                    "--owner",
                    "human paper owner",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, waived)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0105"])

            self.assertEqual(cli.SUCCESS, code, checked)
            self.assertEqual(0, checked["response_matrix"]["unresolved_critical_major_count"])
            self.assertEqual("human_waived", checked["response_matrix"]["rows"][0]["decision"])

    def test_response_matrix_closure_artifact_must_be_safe_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0106",
                    "--title",
                    "Unsafe closure path fixture",
                    "--output-type",
                    "working_paper",
                    "--target-maturity",
                    "working_paper",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)

            code, response = run_cli_json(
                [
                    "deliverable",
                    "response",
                    ops_dir,
                    "DELIV-0106",
                    "--source-review",
                    "CRITIC-0001",
                    "--severity",
                    "major",
                    "--target-section",
                    "References",
                    "--issue",
                    "Bibliography update needs proof.",
                    "--decision",
                    "accepted",
                    "--required-change",
                    "Add the missing bibliography proof.",
                    "--owner",
                    "paper owner",
                    "--status",
                    "closed",
                    "--closure-artifact",
                    "../outside.md",
                    "--now",
                    NOW,
                ]
            )

            self.assertEqual(deliverable_maturity.INVALID_REQUEST, code, response)
            self.assertIn("unsafe_response_matrix_closure_artifact", {item["reason"] for item in response["errors"]})

    def test_same_agent_critic_review_is_visible_but_below_required_independence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task(ops_dir, "TASK-0103", "accepted")
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0103",
                    "--title",
                    "Self-critic draft",
                    "--output-type",
                    "working_paper",
                    "--target-maturity",
                    "working_paper",
                    "--current-maturity",
                    "working_paper",
                    "--target-audience",
                    "public research readers",
                    "--source-task",
                    "TASK-0103",
                    "--complete-gate",
                    "all",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)

            code, critic = run_cli_json(
                [
                    "deliverable",
                    "critic",
                    ops_dir,
                    "DELIV-0103",
                    "--independence-type",
                    "same_agent_visible",
                    "--reviewer",
                    "same agent critic",
                    "--confidence",
                    "0.7",
                    "--recommended-maturity-ceiling",
                    "working_paper",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, critic)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0103"])

            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            self.assertEqual("partial", checked["critic_review"]["status"])
            self.assertEqual("same_agent_visible", checked["critic_review"]["latest_completed_review"]["independence_type"])
            self.assertEqual("internal_draft", checked["maturity"]["independence_ceiling"])
            reasons = {item["reason"] for item in checked["blockers"]}
            self.assertIn("critic_review_independence_below_required", reasons)

    def test_critic_seeded_response_rows_fail_closed_on_duplicate_or_unsafe_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task(ops_dir, "TASK-0110", "accepted")
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0110",
                    "--title",
                    "Seed validation paper",
                    "--output-type",
                    "working_paper",
                    "--target-maturity",
                    "working_paper",
                    "--current-maturity",
                    "working_paper",
                    "--target-audience",
                    "public research readers",
                    "--source-task",
                    "TASK-0110",
                    "--complete-gate",
                    "all",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)

            duplicate_row = (
                "critique_id=RRM-DUP-001;severity=major;target_section=Methods;"
                "issue=Duplicate row.;required_change=Clarify methods.;owner=paper owner"
            )
            code, duplicate = run_cli_json(
                [
                    "deliverable",
                    "critic",
                    ops_dir,
                    "DELIV-0110",
                    "--independence-type",
                    "separate_agent",
                    "--confidence",
                    "0.82",
                    "--recommended-maturity-ceiling",
                    "working_paper",
                    "--response-matrix-row",
                    duplicate_row,
                    "--response-matrix-row",
                    duplicate_row,
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(deliverable_maturity.INVALID_REQUEST, code, duplicate)
            self.assertIn("response_matrix_row_exists", {item["reason"] for item in duplicate["errors"]})

            unsafe_row = (
                "critique_id=RRM-UNSAFE-001;severity=major;target_section=Methods;"
                "issue=Unsafe closure artifact.;required_change=Clarify methods.;owner=paper owner;"
                "closure_artifact=../outside.md"
            )
            code, unsafe = run_cli_json(
                [
                    "deliverable",
                    "critic",
                    ops_dir,
                    "DELIV-0110",
                    "--independence-type",
                    "separate_agent",
                    "--confidence",
                    "0.82",
                    "--recommended-maturity-ceiling",
                    "working_paper",
                    "--response-matrix-row",
                    unsafe_row,
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(deliverable_maturity.INVALID_REQUEST, code, unsafe)
            self.assertIn("unsafe_response_matrix_closure_artifact", {item["reason"] for item in unsafe["errors"]})

            manifest = load_json(ops_dir / "deliverables" / "deliverable_manifest.json")
            deliverable = manifest["deliverables"][0]
            self.assertEqual([], deliverable["critic_reviews"])
            self.assertEqual([], deliverable["review_response_matrix"])

    def test_critic_recommended_ceiling_blocks_until_newer_review_raises_ceiling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task(ops_dir, "TASK-0104", "accepted")
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0104",
                    "--title",
                    "Critic-capped working paper",
                    "--output-type",
                    "working_paper",
                    "--target-maturity",
                    "working_paper",
                    "--current-maturity",
                    "working_paper",
                    "--target-audience",
                    "public research readers",
                    "--source-task",
                    "TASK-0104",
                    "--complete-gate",
                    "all",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)

            code, critic = run_cli_json(
                [
                    "deliverable",
                    "critic",
                    ops_dir,
                    "DELIV-0104",
                    "--independence-type",
                    "separate_agent",
                    "--confidence",
                    "0.8",
                    "--recommended-maturity-ceiling",
                    "shareable_memo",
                    "--critical",
                    "1",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, critic)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0104"])

            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            self.assertEqual("shareable_memo", checked["maturity"]["critic_ceiling"])
            self.assertIn("critic_recommended_ceiling_below_target", {item["reason"] for item in checked["blockers"]})
            self.assertTrue(checked["critic_review"]["satisfied"])

            code, critic = run_cli_json(
                [
                    "deliverable",
                    "critic",
                    ops_dir,
                    "DELIV-0104",
                    "--independence-type",
                    "separate_agent",
                    "--confidence",
                    "0.9",
                    "--recommended-maturity-ceiling",
                    "working_paper",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, critic)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0104"])

            self.assertEqual(cli.SUCCESS, code, checked)
            self.assertEqual("CRITIC-0002", checked["critic_review"]["eligible_review_id"])
            self.assertEqual("working_paper", checked["maturity"]["critic_ceiling"])

    def test_coffee_pilot_fixture_blocks_until_gates_critic_and_response_rows_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task(ops_dir, "TASK-0015", "accepted")
            fixture_text = COFFEE_FIXTURE.read_text(encoding="utf-8")
            (task_dir / "worker_output.md").write_text(fixture_text, encoding="utf-8")

            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0150",
                    "--title",
                    "Coffee and climate internal draft",
                    "--output-type",
                    "working_paper",
                    "--target-maturity",
                    "working_paper",
                    "--current-maturity",
                    "internal_draft",
                    "--target-audience",
                    "public research readers",
                    "--source-task",
                    "TASK-0015",
                    "--primary-artifact",
                    "tasks/TASK-0015-fixture/worker_output.md",
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

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0150"])

            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            self.assertEqual("internal_draft", checked["maturity"]["current"])
            self.assertEqual("internal_draft", checked["maturity"]["verified_ceiling"])
            self.assertEqual("internal draft accepted; working paper not ready", checked["readiness_label"])
            self.assertTrue(checked["source_tasks"][0]["accepted"])
            missing_gates = {item["gate"] for item in checked["blockers"] if item.get("reason") == "gate_missing"}
            for gate in {
                "related_work_synthesis",
                "formal_citations",
                "complete_bibliography",
                "figures_tables_embedded_and_narrated",
                "adversarial_review",
            }:
                self.assertIn(gate, missing_gates)
            self.assertIn("critic_review_missing", {item["reason"] for item in checked["blockers"]})
            self.assertTrue(checked["task_acceptance"]["accepted_source_tasks_do_not_imply_readiness"])

            code, payload = run_cli_json(
                [
                    "deliverable",
                    "target",
                    ops_dir,
                    "DELIV-0150",
                    "--current-maturity",
                    "working_paper",
                    "--complete-gate",
                    "all",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)

            code, critic = run_cli_json(
                [
                    "deliverable",
                    "critic",
                    ops_dir,
                    "DELIV-0150",
                    "--review-id",
                    "CRITIC-0001",
                    "--independence-type",
                    "separate_agent",
                    "--reviewer",
                    "independent coffee manuscript critic",
                    "--model-or-reviewer",
                    "separate reviewer fixture",
                    "--confidence",
                    "0.86",
                    "--recommended-maturity-ceiling",
                    "working_paper",
                    "--major",
                    "2",
                    "--required-revision-row",
                    "RRM-COFFEE-001: complete related-work synthesis",
                    "--required-revision-row",
                    "RRM-COFFEE-002: embed figures and complete citations",
                    "--response-matrix-row",
                    "critique_id=RRM-COFFEE-001;severity=major;target_section=Related work;issue=Related work lacks competing hypotheses;required_change=Add related-work synthesis;owner=paper owner",
                    "--response-matrix-row",
                    "critique_id=RRM-COFFEE-002;severity=major;target_section=Figures and citations;issue=Figures and citations are not narrated or bibliography-complete;required_change=Embed figures and complete citation artifacts;owner=paper owner",
                    "--artifact-path",
                    "deliverables/critic_reviews/DELIV-0150-CRITIC-0001.md",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, critic)
            self.assertEqual(2, critic["response_matrix"]["row_count"])
            self.assertEqual("partial", critic["response_matrix"]["status"])
            self.assertEqual(2, critic["response_matrix"]["unresolved_critical_major_count"])

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0150"])

            self.assertEqual(deliverable_maturity.VALIDATION_FAILED, code, checked)
            reasons = {item["reason"] for item in checked["blockers"]}
            self.assertIn("response_matrix_open_critical_major", reasons)
            self.assertEqual(2, checked["response_matrix"]["row_count"])

            for critique_id, section, artifact in (
                ("RRM-COFFEE-001", "Related work", "deliverables/revisions/coffee-related-work.md"),
                ("RRM-COFFEE-002", "Figures and citations", "deliverables/revisions/coffee-figures-citations.md"),
            ):
                code, response = run_cli_json(
                    [
                        "deliverable",
                        "response",
                        ops_dir,
                        "DELIV-0150",
                        "--critique-id",
                        critique_id,
                        "--source-review",
                        "CRITIC-0001",
                        "--severity",
                        "major",
                        "--target-section",
                        section,
                        "--decision",
                        "accepted",
                        "--required-change",
                        "Close the coffee-pilot editorial gap.",
                        "--owner",
                        "paper owner",
                        "--status",
                        "closed",
                        "--closure-artifact",
                        artifact,
                        "--now",
                        NOW,
                    ]
                )
                self.assertEqual(cli.SUCCESS, code, response)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-0150"])

            self.assertEqual(cli.SUCCESS, code, checked)
            self.assertTrue(checked["target_ready"])
            self.assertEqual("working paper ready", checked["readiness_label"])
            self.assertEqual("working_paper", checked["maturity"]["verified_ceiling"])
            self.assertEqual(0, checked["response_matrix"]["unresolved_critical_major_count"])

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

"""Regression tests for research brief contracts and planner integration."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from async_research_workflow import cli
from async_research_workflow.scripts import research_brief


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "research_briefs"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict[str, Any]]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def init_ops(root: Path) -> Path:
    ops_dir = root / "research_ops"
    code, payload = run_cli_json(["init", ops_dir, "--template", "generic", "--force"])
    if code != cli.SUCCESS:
        raise AssertionError(payload)
    return ops_dir


def copy_fixture(name: str, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURES / name, target)
    return target


def valid_score() -> dict[str, Any]:
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
            "weekly_budget_usd": None
        },
        "hard_gate_results": [{"gate": "data_readiness", "passed": True, "reason": "fixture"}],
        "score_explanation": "Fixture score for research brief promotion tests."
    }


def write_promotable_idea(ops_dir: Path) -> None:
    write_json(
        ops_dir / "ideas" / "IDEA-7701.json",
        {
            "schema_version": "1.0",
            "id": "IDEA-7701",
            "status": "promote",
            "created_at": "2026-05-20T00:00:00Z",
            "updated_at": "2026-05-20T00:00:00Z",
            "title": "Research brief promotion fixture",
            "question": "Can a ready brief constrain a promoted task?",
            "why_it_might_matter": "It checks brief-aware promotion proposals.",
            "required_data": ["fixture data"],
            "minimum_viable_test": "Run a bounded fixture check.",
            "baseline": "Compare against fixture expectations.",
            "main_risks": ["fixture risk"],
            "kill_reason": "Reject if the task cannot stay bounded by the brief.",
            "score": valid_score(),
            "recommended_next_task": "data_readiness",
            "data_refs": ["DS-0001"],
            "decision_history": [
                {
                    "at": "2026-05-20T00:00:00Z",
                    "from_status": "candidate",
                    "to_status": "promote",
                    "reason": "fixture promotion",
                    "actor": "test"
                }
            ]
        },
    )


def write_audited_source(ops_dir: Path) -> None:
    (ops_dir / "data_source_audit.md").write_text(
        "\n".join(
            [
                "# Data Source Audit",
                "",
                "| source_id | source_name | url_or_domain | publisher_owner | source_tier | approval_status | approved_use_cases | prohibited_use_cases | freshness_window_days | limitations | citation_requirements | last_reviewed_at | approved_by | review_notes |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- |",
                "| DS-0001 | Fixture source | https://example.test | Fixture | tier_1_official | approved | experiment_planning; accepted_evidence | none | 30 | none | cite fixture | 2026-05-20 | tests | ready |",
                "",
            ]
        ),
        encoding="utf-8",
    )


class ResearchBriefTests(unittest.TestCase):
    def test_fixture_validation_covers_ready_ambiguous_public_and_private_gates(self) -> None:
        code, clear = run_cli_json(["brief", "validate", FIXTURES / "clear_brief.json"])
        self.assertEqual(cli.SUCCESS, code, clear)
        self.assertTrue(clear["ready_for_planning"])

        expected_blockers = {
            "ambiguous_brief.json": "clarifying_questions_unresolved",
            "missing_audience_brief.json": "target_audience_required",
            "public_claim_brief.json": "human_gate_required_before_planning",
            "private_credentials_brief.json": "human_gate_required_before_planning",
        }
        for filename, reason in expected_blockers.items():
            with self.subTest(filename=filename):
                code, payload = run_cli_json(["brief", "validate", FIXTURES / filename])
                self.assertEqual(research_brief.VALIDATION_FAILED, code, payload)
                blocker_reasons = {item["reason"] for item in payload["blockers"]}
                self.assertIn(reason, blocker_reasons)

    def test_draft_write_validate_and_apply_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            brief_path = ops_dir / "briefs" / "research_brief.json"

            code, draft = run_cli_json(
                [
                    "brief",
                    "draft",
                    ops_dir,
                    "--question",
                    "Summarize accepted climate evidence for planning.",
                    "--objective",
                    "Summarize accepted climate evidence for an internal planning note.",
                    "--output-maturity",
                    "internal_note",
                    "--audience",
                    "Internal planning lead",
                    "--write",
                ]
            )

            self.assertEqual(cli.SUCCESS, code, draft)
            self.assertTrue(draft["ready_for_planning"], draft)
            self.assertTrue(brief_path.exists())

            code, validation = run_cli_json(["brief", "validate", brief_path])
            self.assertEqual(cli.SUCCESS, code, validation)
            code, applied = run_cli_json(["brief", "apply", ops_dir, brief_path, "--dry-run"])
            self.assertEqual(cli.SUCCESS, code, applied)
            self.assertEqual("research_brief_apply_planned", applied["action"])
            self.assertIn("workflow create-task", applied["plan"]["command"])
            self.assertIn("--brief", applied["plan"]["command"])

    def test_apply_and_task_creation_block_ambiguous_default_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            brief_path = copy_fixture("ambiguous_brief.json", ops_dir / "briefs" / "research_brief.json")

            code, applied = run_cli_json(["brief", "apply", ops_dir, brief_path, "--dry-run"])
            self.assertEqual(research_brief.VALIDATION_FAILED, code, applied)
            self.assertEqual("research_brief_apply_blocked", applied["action"])

            code, created = run_cli_json(["workflow", "create-task", ops_dir, "--title", "Blocked broad research", "--dry-run"])
            self.assertEqual(research_brief.VALIDATION_FAILED, code, created)
            self.assertEqual("research_brief_not_ready", created["reason"])

    def test_validator_fails_closed_for_blocked_brief_status(self) -> None:
        blocked = read_json(FIXTURES / "clear_brief.json")
        blocked["status"] = "blocked"
        blocked["private_data_policy"] = "blocked"

        validation = research_brief.validate_brief_payload(blocked)

        self.assertFalse(validation["ready_for_planning"])
        blocker_reasons = {item["reason"] for item in validation["blockers"]}
        self.assertIn("brief_status_not_ready", blocker_reasons)
        self.assertIn("private_data_policy_blocked", blocker_reasons)

    def test_workflow_create_task_consumes_ready_brief_without_broadening_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            brief_path = copy_fixture("clear_brief.json", ops_dir / "briefs" / "research_brief.json")

            code, payload = run_cli_json(
                [
                    "workflow",
                    "create-task",
                    ops_dir,
                    "--title",
                    "Brief constrained task",
                    "--task-id",
                    "TASK-7780",
                    "--allow-network",
                    "--allow-code-execution",
                    "--dry-run",
                ]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            status = payload["status_json"]
            self.assertEqual(str(brief_path), status["research_brief_ref"])
            self.assertEqual("Internal research lead", status["research_brief"]["target_audience"])
            self.assertFalse(status["allow_network"])
            self.assertFalse(status["allow_code_execution"])
            self.assertIn("## Research Brief", payload["task_markdown"])

    def test_idea_promotion_consumes_ready_brief_in_preflight_and_status_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            brief_path = copy_fixture("clear_brief.json", ops_dir / "briefs" / "research_brief.json")
            write_audited_source(ops_dir)
            write_promotable_idea(ops_dir)

            code, payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7701", "--dry-run"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual(str(brief_path), payload["research_brief"]["brief_path"])
            proposal = payload["proposal"]
            self.assertEqual("BRIEF-CLEAR-FIXTURE", proposal["research_brief"]["brief_id"])
            self.assertEqual("BRIEF-CLEAR-FIXTURE", proposal["status_json_draft"]["research_brief"]["brief_id"])
            self.assertFalse(proposal["status_json_draft"]["allow_network"])
            self.assertIn("## Research Brief", proposal["task_markdown_draft"])


if __name__ == "__main__":
    unittest.main()

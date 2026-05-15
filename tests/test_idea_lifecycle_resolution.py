"""Regression tests for decision-backed idea lifecycle resolution."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.scripts.decision_log import read_decisions


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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


def valid_score(hard_gate_passed: bool = True, weighted_total: float = 16.5) -> dict:
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
        "weighted_total": weighted_total,
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
                "passed": hard_gate_passed,
                "reason": "question is present" if hard_gate_passed else "question is too vague",
            }
        ],
        "score_explanation": "Fixture score for idea lifecycle resolution tests.",
    }


def needs_human_candidate(
    candidate_id: str,
    hard_gate_passed: bool = True,
    weighted_total: float = 16.5,
) -> dict:
    return {
        "schema_version": "1.0",
        "id": candidate_id,
        "status": "needs_human",
        "title": f"Fixture {candidate_id}",
        "question": "Can the fixture idea be validated cheaply?",
        "why_it_might_matter": "It checks catalog lifecycle resolution.",
        "required_data": [],
        "minimum_viable_test": "Run a bounded data-readiness check.",
        "baseline": "Compare against a simple baseline.",
        "main_risks": ["fixture risk"],
        "kill_reason": "Reject if fixture data is unavailable.",
        "score": valid_score(hard_gate_passed, weighted_total),
        "recommended_next_task": "data_readiness",
        "human_gate_reason": "Captured idea needs operator approval before promotion.",
    }


class IdeaLifecycleResolutionTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        return ops_dir

    def test_resolve_to_candidate_is_audited_and_default_dry_run_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_json(ops_dir / "ideas" / "IDEA-7801.json", needs_human_candidate("IDEA-7801"))
            before = file_snapshot(ops_dir)

            dry_code, dry_payload = run_cli_json(
                [
                    "idea",
                    "resolve",
                    ops_dir,
                    "IDEA-7801",
                    "--status",
                    "candidate",
                    "--reason",
                    "capture fields reviewed",
                    "--approver",
                    "ops",
                    "--date",
                    "2026-05-15T09:00:00Z",
                ]
            )

            self.assertEqual(cli.SUCCESS, dry_code, dry_payload)
            self.assertTrue(dry_payload["dry_run"])
            self.assertEqual("approve", dry_payload["decision"]["decision"])
            self.assertEqual(before, file_snapshot(ops_dir))

            write_code, write_payload = run_cli_json(
                [
                    "idea",
                    "resolve",
                    ops_dir,
                    "IDEA-7801",
                    "--status",
                    "candidate",
                    "--reason",
                    "capture fields reviewed",
                    "--approver",
                    "ops",
                    "--date",
                    "2026-05-15T09:00:00Z",
                    "--write",
                ]
            )

            self.assertEqual(cli.SUCCESS, write_code, write_payload)
            self.assertEqual("idea_resolution_written", write_payload["action"])
            updated = read_json(ops_dir / "ideas" / "IDEA-7801.json")
            self.assertEqual("candidate", updated["status"])
            self.assertIsNone(updated.get("human_gate_reason"))
            self.assertEqual("catalog_resolution_write", updated["decision_history"][-1]["actor"])
            rows = read_decisions(ops_dir / "decisions.md")
            self.assertEqual("IDEA-7801", rows[-1]["item_id"])
            self.assertEqual("approve", rows[-1]["decision"])
            self.assertIn("resolve idea to candidate", rows[-1]["reason"])

    def test_resolve_to_promote_enables_promotion_dry_run_for_valid_needs_human_idea(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_json(ops_dir / "ideas" / "IDEA-7802.json", needs_human_candidate("IDEA-7802"))

            code, payload = run_cli_json(
                [
                    "idea",
                    "resolve",
                    ops_dir,
                    "IDEA-7802",
                    "--status",
                    "promote",
                    "--reason",
                    "score and hard gates reviewed",
                    "--approver",
                    "ops",
                    "--date",
                    "2026-05-15T10:00:00Z",
                    "--write",
                ]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            updated = read_json(ops_dir / "ideas" / "IDEA-7802.json")
            self.assertEqual("promote", updated["status"])
            self.assertIsNone(updated.get("human_gate_reason"))

            promote_code, promote_payload = run_cli_json(["idea", "promote", ops_dir, "IDEA-7802", "--dry-run"])

            self.assertEqual(cli.SUCCESS, promote_code, promote_payload)
            self.assertEqual("idea_promotion_planned", promote_payload["action"])

    def test_resolve_to_promote_refuses_failed_hard_gates_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_json(ops_dir / "ideas" / "IDEA-7803.json", needs_human_candidate("IDEA-7803", hard_gate_passed=False))
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(
                [
                    "idea",
                    "resolve",
                    ops_dir,
                    "IDEA-7803",
                    "--status",
                    "promote",
                    "--reason",
                    "manual review attempted",
                    "--approver",
                    "ops",
                    "--write",
                ]
            )

            self.assertEqual(2, code, payload)
            self.assertEqual("idea_resolution_blocked", payload["action"])
            self.assertEqual("target_status_not_safe", payload["reason"])
            self.assertIn("failed_hard_gates", {item["reason"] for item in payload["blockers"]})
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_resolve_to_promote_refuses_below_score_threshold_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_json(ops_dir / "ideas" / "IDEA-7805.json", needs_human_candidate("IDEA-7805", weighted_total=9.0))
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(
                [
                    "idea",
                    "resolve",
                    ops_dir,
                    "IDEA-7805",
                    "--status",
                    "promote",
                    "--reason",
                    "manual review attempted",
                    "--approver",
                    "ops",
                    "--write",
                ]
            )

            self.assertEqual(2, code, payload)
            self.assertEqual("idea_resolution_blocked", payload["action"])
            self.assertIn("promote_below_score_threshold", {item["reason"] for item in payload["failures"]})
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_resolve_to_park_requires_revisit_and_records_pause_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_json(ops_dir / "ideas" / "IDEA-7804.json", needs_human_candidate("IDEA-7804"))

            missing_code, missing_payload = run_cli_json(
                [
                    "idea",
                    "resolve",
                    ops_dir,
                    "IDEA-7804",
                    "--status",
                    "park",
                    "--reason",
                    "needs a data source",
                    "--approver",
                    "ops",
                    "--write",
                ]
            )

            self.assertEqual(3, missing_code, missing_payload)
            self.assertEqual("missing_revisit_condition", missing_payload["reason"])

            code, payload = run_cli_json(
                [
                    "idea",
                    "resolve",
                    ops_dir,
                    "IDEA-7804",
                    "--status",
                    "park",
                    "--reason",
                    "needs a data source",
                    "--revisit",
                    "Revisit when DS-0001 is approved.",
                    "--approver",
                    "ops",
                    "--date",
                    "2026-05-15T11:00:00Z",
                    "--write",
                ]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            updated = read_json(ops_dir / "ideas" / "IDEA-7804.json")
            self.assertEqual("park", updated["status"])
            self.assertEqual("Revisit when DS-0001 is approved.", updated["revisit_condition"])
            self.assertIsNone(updated.get("human_gate_reason"))
            rows = read_decisions(ops_dir / "decisions.md")
            self.assertEqual("pause", rows[-1]["decision"])
            self.assertIn("resolve idea to park", rows[-1]["reason"])

    def test_resolve_to_reject_overwrites_stale_revisit_and_records_reject_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            candidate = needs_human_candidate("IDEA-7806")
            candidate["revisit_condition"] = "Old park revisit condition."
            write_json(ops_dir / "ideas" / "IDEA-7806.json", candidate)

            code, payload = run_cli_json(
                [
                    "idea",
                    "resolve",
                    ops_dir,
                    "IDEA-7806",
                    "--status",
                    "reject",
                    "--reason",
                    "human rejected the route",
                    "--approver",
                    "ops",
                    "--date",
                    "2026-05-15T12:00:00Z",
                    "--write",
                ]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            updated = read_json(ops_dir / "ideas" / "IDEA-7806.json")
            self.assertEqual("reject", updated["status"])
            self.assertIsNone(updated.get("human_gate_reason"))
            self.assertEqual("Reopen only if a human records a new decision.", updated["revisit_condition"])
            rows = read_decisions(ops_dir / "decisions.md")
            self.assertEqual("reject", rows[-1]["decision"])
            self.assertIn("resolve idea to reject", rows[-1]["reason"])

    def test_resolve_refuses_non_needs_human_idea_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            candidate = needs_human_candidate("IDEA-7807")
            candidate["status"] = "candidate"
            candidate["human_gate_reason"] = None
            write_json(ops_dir / "ideas" / "IDEA-7807.json", candidate)
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(
                [
                    "idea",
                    "resolve",
                    ops_dir,
                    "IDEA-7807",
                    "--status",
                    "promote",
                    "--reason",
                    "manual review attempted",
                    "--approver",
                    "ops",
                    "--write",
                ]
            )

            self.assertEqual(3, code, payload)
            self.assertEqual("idea_not_needs_human", payload["reason"])
            self.assertEqual("candidate", payload["current_status"])
            self.assertEqual(before, file_snapshot(ops_dir))


if __name__ == "__main__":
    unittest.main()

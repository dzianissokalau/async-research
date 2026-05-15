"""Regression tests for V2.5 promotion task-id reservation rules."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    return code, json.loads(stream.getvalue())


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def file_snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def accepted_outputs_index(*rows: list[str]) -> str:
    lines = [
        "| accepted_date | task_id | title | key_finding | claim_type | freshness_window_days | next_recheck_date | revalidation_status | source_ids | claim_strength | caveats | followups | supersedes | superseded_by | evidence_link |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines) + "\n"


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
        "hard_gate_results": [{"gate": "research_question_present", "passed": True, "reason": "question is present"}],
        "score_explanation": "Fixture score for catalog V2.5 task identity tests.",
    }


def promotable_candidate(candidate_id: str, title: str = "Promotable task identity idea") -> dict:
    return {
        "schema_version": "1.0",
        "id": candidate_id,
        "status": "promote",
        "title": title,
        "question": "Can the fixture idea be validated cheaply?",
        "why_it_might_matter": "It checks catalog promotion task identity behavior.",
        "required_data": ["public fixture data"],
        "minimum_viable_test": "Run a bounded data-readiness check.",
        "baseline": "Compare against a simple baseline.",
        "main_risks": ["fixture risk"],
        "kill_reason": "Reject if fixture data is unavailable.",
        "score": valid_score(),
        "recommended_next_task": "data_readiness",
        "data_refs": ["DS-0001"],
    }


class IdeaCatalogV2TaskIdentityTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        return ops_dir

    def write_audited_source(self, ops_dir: Path, source_id: str = "DS-0001") -> None:
        write_text(
            ops_dir / "data_source_audit.md",
            "\n".join(
                [
                    "# Data Source Audit",
                    "",
                    "| source_id | source_name | url_or_domain | publisher_owner | source_tier | approval_status | approved_use_cases | prohibited_use_cases | freshness_window_days | limitations | citation_requirements | last_reviewed_at | approved_by | review_notes |",
                    "| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- |",
                    f"| {source_id} | Fixture source | https://example.test | Fixture | tier_1_official | approved | experiment_planning; accepted_evidence | none | 30 | none | cite fixture | 2026-05-07 | tests | ready |",
                    "",
                ]
            ),
        )

    def write_promotable_idea(self, ops_dir: Path, idea_id: str) -> dict:
        candidate = promotable_candidate(idea_id)
        write_json(ops_dir / "ideas" / f"{idea_id}.json", candidate)
        return candidate

    def dry_run(self, ops_dir: Path, idea_id: str) -> tuple[int, dict]:
        return run_cli_json(["idea", "promote", ops_dir, idea_id, "--dry-run"])

    def blocker_reasons(self, payload: dict) -> list[str]:
        return [item["reason"] for item in payload["blockers"]]

    def test_dry_run_reserves_deterministic_task_id_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7501")
            before = file_snapshot(ops_dir)

            code, payload = self.dry_run(ops_dir, "IDEA-7501")

            self.assertEqual(cli.SUCCESS, code, payload)
            identity = payload["task_identity"]
            self.assertEqual("TASK-7501", identity["task_id"])
            self.assertEqual("TASK-7501-data-readiness", identity["task_dir_name"])
            self.assertEqual("available", identity["status"])
            self.assertEqual([], identity["blockers"])
            proposal = payload["proposal"]
            self.assertEqual("TASK-7501", proposal["proposed_task_id"])
            self.assertEqual("TASK-7501-data-readiness", proposal["proposed_task_slug"])
            self.assertEqual("TASK-7501", proposal["status_json_draft"]["id"])
            self.assertEqual("TASK-7501", proposal["status_json_draft"]["catalog_promotion"]["reserved_task_id"])
            self.assertIn("# TASK-7501:", proposal["task_markdown_draft"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_existing_reserved_task_folder_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7502")
            (ops_dir / "tasks" / "TASK-7502-data-readiness").mkdir(parents=True)

            code, payload = self.dry_run(ops_dir, "IDEA-7502")

            self.assertEqual(2, code, payload)
            self.assertEqual("blocked", payload["task_identity"]["status"])
            self.assertIn("reserved_task_folder_exists", self.blocker_reasons(payload))
            blocker = next(item for item in payload["task_identity"]["blockers"] if item["reason"] == "reserved_task_folder_exists")
            self.assertEqual("task_folder", blocker["collision_kind"])
            self.assertIn("already has", blocker["message"])
            self.assertIn("inspect the existing task folder", blocker["next_step"])
            self.assertIn("inspect the existing task folder", payload["next_step"])
            self.assertIsNone(payload["proposal"])

    def test_existing_reserved_queue_row_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7503")
            write_text(
                ops_dir / "queue.md",
                "\n".join(
                    [
                        "# Queue",
                        "",
                        "| task | priority | status | type | next_runner | notes |",
                        "| --- | ---: | --- | --- | --- | --- |",
                        "| [TASK-7503](tasks/TASK-7503-data-readiness/task.md) | 2 | inbox | data_readiness | planner | existing reservation |",
                        "",
                    ]
                ),
            )

            code, payload = self.dry_run(ops_dir, "IDEA-7503")

            self.assertEqual(2, code, payload)
            self.assertIn("reserved_queue_row_exists", self.blocker_reasons(payload))
            blocker = next(item for item in payload["task_identity"]["blockers"] if item["reason"] == "reserved_queue_row_exists")
            self.assertEqual("queue_row", blocker["collision_kind"])
            self.assertIn("queue list", blocker["next_step"])
            self.assertIsNone(payload["proposal"])

    def test_existing_promoted_task_id_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            candidate = self.write_promotable_idea(ops_dir, "IDEA-7504")
            candidate["promoted_task_id"] = "TASK-7504"
            write_json(ops_dir / "ideas" / "IDEA-7504.json", candidate)
            write_text(
                ops_dir / "accepted_outputs_index.md",
                accepted_outputs_index(
                    [
                        "2026-05-08",
                        "TASK-7504",
                        "Accepted fixture",
                        "ready",
                        "source_data_readiness",
                        "90",
                        "2026-08-06",
                        "current",
                        "DS-0001",
                        "moderate",
                        "",
                        "",
                        "",
                        "",
                        "tasks/TASK-7504-data-readiness/worker_output.md",
                    ]
                ),
            )

            code, payload = self.dry_run(ops_dir, "IDEA-7504")

            self.assertEqual(2, code, payload)
            reasons = self.blocker_reasons(payload)
            self.assertIn("selected_idea_already_has_promoted_task_id", reasons)
            self.assertIn("reserved_accepted_output_exists", reasons)
            self.assertIsNone(payload["proposal"])

    def test_accepted_output_note_only_reference_does_not_block_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7509")
            write_text(
                ops_dir / "accepted_outputs_index.md",
                accepted_outputs_index(
                    [
                        "2026-05-08",
                        "TASK-1234",
                        "Accepted fixture",
                        "cross-refers to TASK-7509 in notes only",
                        "source_data_readiness",
                        "90",
                        "2026-08-06",
                        "current",
                        "DS-0001",
                        "moderate",
                        "TASK-7509 is a future follow-up",
                        "",
                        "",
                        "",
                        "tasks/TASK-1234-data-readiness/worker_output.md",
                    ]
                ),
            )

            code, payload = self.dry_run(ops_dir, "IDEA-7509")

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("available", payload["task_identity"]["status"])
            self.assertEqual([], payload["task_identity"]["blockers"])
            self.assertEqual("TASK-7509", payload["proposal"]["proposed_task_id"])

    def test_stale_promoted_task_id_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            candidate = self.write_promotable_idea(ops_dir, "IDEA-7505")
            candidate["promoted_task_id"] = "TASK-9999"
            write_json(ops_dir / "ideas" / "IDEA-7505.json", candidate)

            code, payload = self.dry_run(ops_dir, "IDEA-7505")

            self.assertEqual(2, code, payload)
            self.assertIn("stale_promoted_task_id", self.blocker_reasons(payload))
            step = next(item for item in payload["remediation_steps"] if item["reason"] == "stale_promoted_task_id")
            self.assertIn("catalog validate", step["next_step"])
            self.assertIsNone(payload["proposal"])

    def test_different_visible_promoted_task_id_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            candidate = self.write_promotable_idea(ops_dir, "IDEA-7510")
            candidate["promoted_task_id"] = "TASK-9999"
            write_json(ops_dir / "ideas" / "IDEA-7510.json", candidate)
            (ops_dir / "tasks" / "TASK-9999-old-followup").mkdir(parents=True)

            code, payload = self.dry_run(ops_dir, "IDEA-7510")

            self.assertEqual(2, code, payload)
            self.assertIn("selected_idea_has_different_promoted_task_id", self.blocker_reasons(payload))
            self.assertIsNone(payload["proposal"])

    def test_other_idea_promoted_task_id_claim_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7506")
            other = promotable_candidate("IDEA-7507")
            other["promoted_task_id"] = "TASK-7506"
            write_json(ops_dir / "ideas" / "IDEA-7507.json", other)

            code, payload = self.dry_run(ops_dir, "IDEA-7506")

            self.assertEqual(2, code, payload)
            self.assertIn("reserved_task_id_claimed_by_other_idea", self.blocker_reasons(payload))
            blocker = next(
                item
                for item in payload["task_identity"]["blockers"]
                if item["reason"] == "reserved_task_id_claimed_by_other_idea"
            )
            self.assertEqual("other_idea_claim", blocker["collision_kind"])
            self.assertIn("claiming idea", blocker["next_step"])
            self.assertIsNone(payload["proposal"])

    def test_re_running_same_write_command_is_idempotent_when_task_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7508")
            dry_code, dry_run = self.dry_run(ops_dir, "IDEA-7508")
            self.assertEqual(cli.SUCCESS, dry_code, dry_run)
            first_code, first = run_cli_json(
                [
                    "idea",
                    "promote",
                    ops_dir,
                    "IDEA-7508",
                    "--write",
                    "--preflight-hash",
                    dry_run["promotion_preflight_hash"],
                ]
            )
            self.assertEqual(cli.SUCCESS, first_code, first)
            before = file_snapshot(ops_dir)

            second_code, second = run_cli_json(
                [
                    "idea",
                    "promote",
                    ops_dir,
                    "IDEA-7508",
                    "--write",
                    "--preflight-hash",
                    dry_run["promotion_preflight_hash"],
                ]
            )

            self.assertEqual(cli.SUCCESS, second_code, second)
            self.assertEqual("idea_promotion_task_already_written", second["action"])
            self.assertFalse(second["changed"])
            self.assertEqual("TASK-7508-data-readiness", second["proposal_ref"]["proposed_task_slug"])
            self.assertEqual(before, file_snapshot(ops_dir))


if __name__ == "__main__":
    unittest.main()

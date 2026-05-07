"""Regression tests for V2.2 idea promotion proposal write mode."""

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


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def file_snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


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
        "score_explanation": "Fixture score for catalog V2.2 proposal write tests.",
    }


def promotable_candidate(candidate_id: str, title: str = "Promotable proposal write idea") -> dict:
    return {
        "schema_version": "1.0",
        "id": candidate_id,
        "status": "promote",
        "title": title,
        "question": "Can the fixture idea be validated cheaply?",
        "why_it_might_matter": "It checks catalog promotion proposal write behavior.",
        "required_data": ["public fixture data"],
        "minimum_viable_test": "Run a bounded data-readiness check.",
        "baseline": "Compare against a simple baseline.",
        "main_risks": ["fixture risk"],
        "kill_reason": "Reject if fixture data is unavailable.",
        "score": valid_score(),
        "recommended_next_task": "data_readiness",
    }


class IdeaCatalogV2ProposalWriteTests(unittest.TestCase):
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

    def write_promotable_idea(self, ops_dir: Path, idea_id: str = "IDEA-7401") -> dict:
        candidate = promotable_candidate(idea_id, "Audited proposal write idea")
        candidate["data_refs"] = ["DS-0001"]
        write_json(ops_dir / "ideas" / f"{idea_id}.json", candidate)
        return candidate

    def dry_run_hash(self, ops_dir: Path, idea_id: str, *extra: str) -> tuple[str, dict]:
        code, payload = run_cli_json(["idea", "promote", ops_dir, idea_id, "--dry-run", *extra])
        self.assertEqual(cli.SUCCESS, code, payload)
        return payload["promotion_preflight_hash"], payload

    def test_write_appends_inbox_ref_updates_idea_and_preserves_non_task_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir)
            catalog_path = ops_dir / "ideas" / "idea_catalog.md"
            write_text(catalog_path, catalog_path.read_text(encoding="utf-8") + "\nManual planner note stays here.\n")
            preflight_hash, dry_run = self.dry_run_hash(ops_dir, "IDEA-7401")
            queue_before = (ops_dir / "queue.md").read_bytes()
            tasks_before = file_snapshot(ops_dir / "tasks")

            code, payload = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7401", "--write", "--preflight-hash", preflight_hash]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("idea_promotion_proposal_written", payload["action"])
            self.assertFalse(payload["dry_run"])
            self.assertEqual(preflight_hash, payload["promotion_preflight_hash"])
            self.assertEqual(dry_run["idempotency_key"], payload["idempotency_key"])
            self.assertTrue(payload["validation"]["ok"])
            self.assertEqual(0, payload["validation"]["failure_count"])
            blocked_paths = {Path(item["path"]) for item in payload["would_not_write"]}
            self.assertIn(ops_dir / "queue.md", blocked_paths)
            self.assertIn(ops_dir / "tasks", blocked_paths)
            self.assertEqual(queue_before, (ops_dir / "queue.md").read_bytes())
            self.assertEqual(tasks_before, file_snapshot(ops_dir / "tasks"))

            proposal_ref = payload["proposal_ref"]
            inbox = (ops_dir / "inbox.md").read_text(encoding="utf-8")
            self.assertIn(proposal_ref["proposal_id"], inbox)
            self.assertIn(proposal_ref["transaction_id"], inbox)
            self.assertIn(proposal_ref["idempotency_key"], inbox)
            self.assertIn("Manual planner note stays here.", catalog_path.read_text(encoding="utf-8"))

            updated = read_json(ops_dir / "ideas" / "IDEA-7401.json")
            self.assertNotIn("promoted_task_id", updated)
            self.assertEqual(proposal_ref["proposal_id"], updated["latest_promotion_proposal_id"])
            self.assertEqual([proposal_ref], updated["promotion_proposal_refs"])
            self.assertTrue(
                any(
                    entry.get("actor") == "catalog_promotion_write"
                    and entry.get("transaction_id") == proposal_ref["transaction_id"]
                    and entry.get("idempotency_key") == proposal_ref["idempotency_key"]
                    and entry.get("proposal_id") == proposal_ref["proposal_id"]
                    for entry in updated["decision_history"]
                )
            )

    def test_duplicate_write_refuses_without_mutating_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7402")
            preflight_hash, _dry_run = self.dry_run_hash(ops_dir, "IDEA-7402")
            first_code, first = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7402", "--write", "--preflight-hash", preflight_hash]
            )
            self.assertEqual(cli.SUCCESS, first_code, first)
            before = file_snapshot(ops_dir)

            second_code, second = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7402", "--write", "--preflight-hash", preflight_hash]
            )

            self.assertEqual(2, second_code, second)
            self.assertEqual("duplicate_promotion_proposal", second["reason"])
            self.assertEqual(first["proposal_ref"], second["existing_proposal_ref"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_changed_candidate_refuses_stale_preflight_hash_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            candidate = self.write_promotable_idea(ops_dir, "IDEA-7403")
            preflight_hash, _dry_run = self.dry_run_hash(ops_dir, "IDEA-7403")
            candidate["score"]["weighted_total"] = 17.0
            write_json(ops_dir / "ideas" / "IDEA-7403.json", candidate)
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7403", "--write", "--preflight-hash", preflight_hash]
            )

            self.assertEqual(2, code, payload)
            self.assertEqual("promotion_preflight_changed", payload["reason"])
            self.assertEqual(preflight_hash, payload["expected_preflight_hash"])
            self.assertNotEqual(preflight_hash, payload["current_preflight_hash"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_write_requires_hash_and_rejects_conflicting_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))

            missing_code, missing = run_cli_json(["idea", "promote", ops_dir, "IDEA-7404", "--write"])
            self.assertEqual(3, missing_code, missing)
            self.assertEqual("promotion_preflight_hash_required", missing["reason"])

            conflict_code, conflict = run_cli_json(
                [
                    "idea",
                    "promote",
                    ops_dir,
                    "IDEA-7404",
                    "--dry-run",
                    "--write",
                    "--preflight-hash",
                    "a" * 64,
                ]
            )
            self.assertEqual(3, conflict_code, conflict)
            self.assertEqual("conflicting_flags", conflict["reason"])

    def test_experiment_plan_write_requires_explicit_human_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            candidate = promotable_candidate("IDEA-7405", "Experiment proposal write idea")
            candidate["data_refs"] = ["DS-0001"]
            write_json(ops_dir / "ideas" / "IDEA-7405.json", candidate)
            preflight_hash, dry_run = self.dry_run_hash(ops_dir, "IDEA-7405", "--task-type", "experiment_plan")
            self.assertEqual("experiment_plan", dry_run["proposal"]["task_type"])

            blocked_code, blocked = run_cli_json(
                [
                    "idea",
                    "promote",
                    ops_dir,
                    "IDEA-7405",
                    "--task-type",
                    "experiment_plan",
                    "--write",
                    "--preflight-hash",
                    preflight_hash,
                ]
            )
            self.assertEqual(2, blocked_code, blocked)
            self.assertEqual("human_override_required", blocked["reason"])

            written_code, written = run_cli_json(
                [
                    "idea",
                    "promote",
                    ops_dir,
                    "IDEA-7405",
                    "--task-type",
                    "experiment_plan",
                    "--write",
                    "--preflight-hash",
                    preflight_hash,
                    "--human-override",
                ]
            )
            self.assertEqual(cli.SUCCESS, written_code, written)
            self.assertTrue(written["proposal_ref"]["human_override"])


if __name__ == "__main__":
    unittest.main()

"""Regression tests for Phase 7 idea catalog write mode."""

from __future__ import annotations

import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli


TIMESTAMP_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


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
        "score_explanation": "Fixture score for catalog phase 7 tests.",
    }


def valid_candidate(candidate_id: str, title: str = "Existing catalog idea") -> dict:
    return {
        "schema_version": "1.0",
        "id": candidate_id,
        "status": "candidate",
        "title": title,
        "question": "Can the fixture idea be validated cheaply?",
        "why_it_might_matter": "It checks catalog write behavior.",
        "required_data": ["public fixture data"],
        "minimum_viable_test": "Run a bounded data-readiness check.",
        "baseline": "Compare against a simple baseline.",
        "main_risks": ["fixture risk"],
        "kill_reason": "Reject if fixture data is unavailable.",
        "score": valid_score(),
        "recommended_next_task": "data_readiness",
    }


class IdeaCatalogPhase7Tests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        return ops_dir

    def test_capture_write_creates_candidate_regenerates_projections_and_preserves_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            catalog_path = ops_dir / "ideas" / "idea_catalog.md"
            prioritization_path = ops_dir / "ideas" / "prioritization.md"
            catalog_note = "Manual catalog note | preserve me exactly."
            prioritization_note = "Manual prioritization note | preserve me exactly."
            write_text(catalog_path, catalog_path.read_text(encoding="utf-8").replace("Free-form notes.", catalog_note))
            write_text(
                prioritization_path,
                prioritization_path.read_text(encoding="utf-8").replace("Free-form notes.", prioritization_note),
            )
            write_text(
                ops_dir / "discovery_inbox.md",
                "\n".join(
                    [
                        "# Discovery Inbox",
                        "",
                        "| item | title | source | status | score | next_task | notes |",
                        "| --- | --- | --- | --- | ---: | --- | --- |",
                        "| IDEA-7201 | Write mode capture | scan | candidate | 5 | literature_extract | catalog: candidate |",
                        "",
                    ]
                ),
            )
            queue_before = (ops_dir / "queue.md").read_bytes()

            code, payload = run_cli_json(["idea", "capture", ops_dir, "--from-inbox", "IDEA-7201", "--write"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("idea_capture_written", payload["action"])
            self.assertTrue(payload["changed"])
            self.assertEqual("IDEA-7201", payload["candidate"]["id"])
            self.assertRegex(payload["candidate"]["created_at"], TIMESTAMP_RE)
            self.assertRegex(payload["candidate"]["updated_at"], TIMESTAMP_RE)
            candidate_path = ops_dir / "ideas" / "IDEA-7201.json"
            self.assertTrue(candidate_path.exists())
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            self.assertEqual("needs_human", candidate["status"])
            self.assertEqual("literature_extract", candidate["recommended_next_task"])
            self.assertEqual(queue_before, (ops_dir / "queue.md").read_bytes())
            self.assertIn(catalog_note, catalog_path.read_text(encoding="utf-8"))
            self.assertIn(prioritization_note, prioritization_path.read_text(encoding="utf-8"))
            self.assertIn("IDEA-7201", catalog_path.read_text(encoding="utf-8"))
            self.assertIn("IDEA-7201", prioritization_path.read_text(encoding="utf-8"))

            validate_code, validate_payload = run_cli_json(["idea", "catalog", "validate", ops_dir])
            self.assertEqual(cli.SUCCESS, validate_code, validate_payload)
            self.assertTrue(validate_payload["ok"])

            rerun_code, rerun = run_cli_json(["idea", "catalog", "maintain", ops_dir, "--write"])
            self.assertEqual(cli.SUCCESS, rerun_code, rerun)
            self.assertFalse(rerun["changed"])
            self.assertEqual([], rerun["files_written"])

    def test_maintenance_write_creates_candidates_updates_statuses_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            blocked = valid_candidate("IDEA-7202", "Blocked maintenance idea")
            blocked["score"]["hard_gate_results"] = [
                {"gate": "data_readiness", "passed": False, "reason": "source evidence missing"}
            ]
            write_json(ops_dir / "ideas" / "IDEA-7202.json", blocked)
            write_text(
                ops_dir / "discovery_inbox.md",
                "\n".join(
                    [
                        "# Discovery Inbox",
                        "",
                        "| item | title | source | status | score | next_task | notes |",
                        "| --- | --- | --- | --- | ---: | --- | --- |",
                        "| IDEA-7203 | Maintenance capture | scan | candidate | 6 | data_readiness | catalog: candidate |",
                        "",
                    ]
                ),
            )

            code, payload = run_cli_json(["idea", "catalog", "maintain", ops_dir, "--write"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("idea_catalog_maintenance_written", payload["action"])
            self.assertTrue(payload["changed"])
            created = json.loads((ops_dir / "ideas" / "IDEA-7203.json").read_text(encoding="utf-8"))
            self.assertEqual("needs_human", created["status"])
            parked = json.loads((ops_dir / "ideas" / "IDEA-7202.json").read_text(encoding="utf-8"))
            self.assertEqual("park", parked["status"])
            self.assertEqual("failed_hard_gates", parked["status_reason"])
            self.assertEqual("catalog_maintenance_write", parked["decision_history"][-1]["actor"])
            self.assertRegex(parked["updated_at"], TIMESTAMP_RE)
            self.assertIn("IDEA-7202", (ops_dir / "ideas" / "prioritization.md").read_text(encoding="utf-8"))

            validate_code, validate_payload = run_cli_json(["idea", "catalog", "validate", ops_dir])
            self.assertEqual(cli.SUCCESS, validate_code, validate_payload)
            self.assertTrue(validate_payload["ok"])

            rerun_code, rerun = run_cli_json(["idea", "catalog", "maintain", ops_dir, "--write"])
            self.assertEqual(cli.SUCCESS, rerun_code, rerun)
            self.assertFalse(rerun["changed"])
            self.assertEqual([], rerun["files_written"])

    def test_status_writes_respect_locks_and_recover_stale_locks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_json(ops_dir / "ideas" / "IDEA-7204.json", valid_candidate("IDEA-7204", "Park me"))
            write_json(ops_dir / "ideas" / "IDEA-7205.json", valid_candidate("IDEA-7205", "Reject me"))
            lock_dir = ops_dir / "ideas" / "LOCK"
            lock_dir.mkdir()
            write_json(
                lock_dir / "owner.json",
                {
                    "command": "test",
                    "pid": 123,
                    "started_at": "2099-01-01T00:00:00Z",
                    "lock_expires_at": "2099-01-01T00:30:00Z",
                },
            )

            locked_code, locked = run_cli_json(
                [
                    "idea",
                    "park",
                    ops_dir,
                    "IDEA-7204",
                    "--reason",
                    "pause for data",
                    "--revisit",
                    "when data arrives",
                    "--write",
                ]
            )
            self.assertEqual(2, locked_code, locked)
            self.assertEqual("catalog_locked", locked["reason"])

            write_json(
                lock_dir / "owner.json",
                {
                    "command": "test",
                    "pid": 123,
                    "started_at": "2000-01-01T00:00:00Z",
                    "lock_expires_at": "2000-01-01T00:30:00Z",
                },
            )
            park_code, parked_payload = run_cli_json(
                [
                    "idea",
                    "park",
                    ops_dir,
                    "IDEA-7204",
                    "--reason",
                    "pause for data",
                    "--revisit",
                    "when data arrives",
                    "--write",
                ]
            )
            self.assertEqual(cli.SUCCESS, park_code, parked_payload)
            self.assertFalse(lock_dir.exists())
            self.assertTrue(list((ops_dir / "ideas").glob("LOCK.stale.*")))
            parked = json.loads((ops_dir / "ideas" / "IDEA-7204.json").read_text(encoding="utf-8"))
            self.assertEqual("park", parked["status"])
            self.assertEqual("when data arrives", parked["revisit_condition"])
            self.assertEqual("catalog_status_write", parked["decision_history"][-1]["actor"])

            reject_code, rejected_payload = run_cli_json(
                ["idea", "reject", ops_dir, "IDEA-7205", "--reason", "too broad to test", "--write"]
            )
            self.assertEqual(cli.SUCCESS, reject_code, rejected_payload)
            rejected = json.loads((ops_dir / "ideas" / "IDEA-7205.json").read_text(encoding="utf-8"))
            self.assertEqual("reject", rejected["status"])
            self.assertEqual("too broad to test", rejected["status_reason"])
            self.assertEqual("Reopen only if a human records a new decision.", rejected["revisit_condition"])

            validate_code, validate_payload = run_cli_json(["idea", "catalog", "validate", ops_dir])
            self.assertEqual(cli.SUCCESS, validate_code, validate_payload)
            self.assertTrue(validate_payload["ok"])


if __name__ == "__main__":
    unittest.main()

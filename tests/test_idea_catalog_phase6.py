"""Regression tests for Phase 6 idea catalog dry-run capture and maintenance."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.idea_catalog import candidate_schema_errors
from async_research_workflow.scripts import idea_catalog as idea_catalog_script


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
        "hard_gate_results": [
            {
                "gate": "research_question_present",
                "passed": True,
                "reason": "question is present",
            }
        ],
        "score_explanation": "Fixture score for catalog phase 6 tests.",
    }


def valid_candidate(candidate_id: str, title: str = "Existing catalog idea") -> dict:
    return {
        "schema_version": "1.0",
        "id": candidate_id,
        "status": "candidate",
        "title": title,
        "question": "Can the fixture idea be validated cheaply?",
        "why_it_might_matter": "It checks catalog dry-run behavior.",
        "required_data": ["public fixture data"],
        "minimum_viable_test": "Run a bounded data-readiness check.",
        "baseline": "Compare against a simple baseline.",
        "main_risks": ["fixture risk"],
        "kill_reason": "Reject if fixture data is unavailable.",
        "score": valid_score(),
        "recommended_next_task": "data_readiness",
    }


class IdeaCatalogPhase6Tests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        self.assertTrue(payload["ok"])
        return ops_dir

    def test_title_capture_proposes_complete_candidate_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            before = file_snapshot(ops_dir)

            missing_id_code, missing_id = run_cli_json(["idea", "capture", ops_dir, "--title", "Needs id"])
            self.assertEqual(cli.SUCCESS, missing_id_code, missing_id)
            self.assertEqual("needs_human", missing_id["route"])
            self.assertEqual("missing_idea_id", missing_id["reason"])
            self.assertEqual([], missing_id["would_write"])

            code, payload = run_cli_json(
                [
                    "idea",
                    "capture",
                    ops_dir,
                    "--title",
                    "Air quality signal",
                    "--id",
                    "IDEA-7101",
                    "--dry-run",
                ]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("idea_capture_planned", payload["action"])
            self.assertEqual("create", payload["route"])
            self.assertTrue(payload["changed"])
            self.assertEqual([], payload["duplicate_matches"])
            self.assertEqual(1, len(payload["would_write"]))
            candidate = payload["would_write"][0]["content"]
            self.assertEqual("IDEA-7101", candidate["id"])
            self.assertEqual("needs_human", candidate["status"])
            self.assertEqual("Air quality signal", candidate["title"])
            self.assertEqual("data_readiness", candidate["recommended_next_task"])
            self.assertIn("human_gate_reason", candidate)
            self.assertEqual([], candidate_schema_errors(candidate))
            self.assertEqual(before, file_snapshot(ops_dir))
            self.assertFalse((ops_dir / "ideas" / "IDEA-7101.json").exists())

    def test_inbox_capture_uses_row_selector_and_refuses_write_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_text(
                ops_dir / "discovery_inbox.md",
                "\n".join(
                    [
                        "# Discovery Inbox",
                        "",
                        "| item | title | source | status | score | next_task | notes |",
                        "| --- | --- | --- | --- | ---: | --- | --- |",
                        "| row-a | Literature angle | scan | candidate | 5 | literature_extract | catalog: candidate |",
                        "| IDEA-7108 | Item selector angle | scan | candidate | 5 | data_readiness | catalog: candidate |",
                        "",
                    ]
                ),
            )
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(
                ["idea", "capture", ops_dir, "--from-inbox", "row-1", "--id", "IDEA-7102"]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            candidate = payload["would_write"][0]["content"]
            self.assertEqual("IDEA-7102", candidate["id"])
            self.assertEqual("Literature angle", candidate["title"])
            self.assertEqual("literature_extract", candidate["recommended_next_task"])
            self.assertEqual("discovery_inbox.md#row-1", candidate["source_discovery_path"])
            self.assertEqual(before, file_snapshot(ops_dir))

            item_code, item_payload = run_cli_json(["idea", "capture", ops_dir, "--from-inbox", "IDEA-7108"])
            self.assertEqual(cli.SUCCESS, item_code, item_payload)
            item_candidate = item_payload["would_write"][0]["content"]
            self.assertEqual("IDEA-7108", item_candidate["id"])
            self.assertEqual("Item selector angle", item_candidate["title"])
            self.assertEqual("discovery_inbox.md#row-2", item_candidate["source_discovery_path"])
            self.assertEqual(before, file_snapshot(ops_dir))

            write_code, write_payload = run_cli_json(
                ["idea", "capture", ops_dir, "--from-inbox", "row-1", "--id", "IDEA-7102", "--write"]
            )
            self.assertEqual(3, write_code, write_payload)
            self.assertEqual("write_mode_deferred_to_phase_7", write_payload["reason"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_maintenance_dry_run_ignores_unmarked_rows_and_routes_duplicates_conservatively(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_json(ops_dir / "ideas" / "IDEA-7103.json", valid_candidate("IDEA-7103", "Existing catalog idea"))
            blocked = valid_candidate("IDEA-7107", "Blocked catalog idea")
            blocked["score"]["hard_gate_results"] = [
                {"gate": "data_readiness", "passed": False, "reason": "source evidence missing"}
            ]
            write_json(ops_dir / "ideas" / "IDEA-7107.json", blocked)
            write_text(
                ops_dir / "discovery_inbox.md",
                "\n".join(
                    [
                        "# Discovery Inbox",
                        "",
                        "| item | title | source | status | score | next_task | notes |",
                        "| --- | --- | --- | --- | ---: | --- | --- |",
                        "| IDEA-7104 | New catalog idea | scan | candidate | 6 | data_readiness | catalog: candidate |",
                        "| IDEA-7105 | Unmarked idea | scan | candidate | 6 | data_readiness | no marker |",
                        "| IDEA-7106 | Existing catalog idea | scan | candidate | 6 | data_readiness | catalog: candidate |",
                        "| IDEA-7108 | Unknown marker idea | scan | candidate | 6 | data_readiness | catalog: archive |",
                        "",
                    ]
                ),
            )
            before = file_snapshot(ops_dir)

            with mock.patch.object(
                idea_catalog_script,
                "read_catalog",
                wraps=idea_catalog_script.read_catalog,
            ) as read_catalog:
                code, payload = run_cli_json(["idea", "catalog", "maintain", ops_dir, "--dry-run"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual(1, read_catalog.call_count)
            self.assertEqual("idea_catalog_maintenance_planned", payload["action"])
            self.assertTrue(payload["dry_run"])
            self.assertEqual(before, file_snapshot(ops_dir))
            ignored = {row["item"]: row["reason"] for row in payload["ignored_inbox_rows"]}
            self.assertEqual("missing_catalog_marker", ignored["IDEA-7105"])
            by_item = {proposal["item"]: proposal for proposal in payload["inbox_capture_proposals"]}
            self.assertEqual("create", by_item["IDEA-7104"]["route"])
            self.assertEqual("update_existing", by_item["IDEA-7106"]["route"])
            self.assertEqual("same_normalized_title", by_item["IDEA-7106"]["reason"])
            self.assertEqual("candidate", by_item["IDEA-7108"]["catalog_marker"])
            self.assertEqual("archive", by_item["IDEA-7108"]["raw_catalog_marker"])
            self.assertEqual("catalog: archive", by_item["IDEA-7108"]["catalog_marker_text"])
            self.assertTrue(by_item["IDEA-7108"]["catalog_marker_defaulted"])
            proposed_actions = {change["action"] for change in payload["proposed_file_changes"]}
            self.assertIn("create_canonical_idea_json", proposed_actions)
            self.assertIn("update_idea_status", proposed_actions)
            park_change = next(
                change
                for change in payload["proposed_file_changes"]
                if change.get("idea_id") == "IDEA-7107" and change["action"] == "update_idea_status"
            )
            self.assertEqual("park", park_change["to_status"])
            self.assertIn("revisit_condition", park_change["fields"])
            self.assertEqual(
                {
                    "at": "TO_BE_SET_AT_WRITE_TIME",
                    "from_status": "candidate",
                    "to_status": "park",
                    "reason": "failed_hard_gates",
                    "actor": "catalog_maintenance_dry_run",
                },
                park_change["proposed_decision_history_entry"],
            )
            self.assertFalse((ops_dir / "ideas" / "IDEA-7104.json").exists())
            blocked_paths = {item["path"] for item in payload["would_not_write"]}
            self.assertIn(str(ops_dir / "queue.md"), blocked_paths)
            self.assertIn(str(ops_dir / "tasks"), blocked_paths)


if __name__ == "__main__":
    unittest.main()

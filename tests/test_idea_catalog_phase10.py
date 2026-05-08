"""Regression tests for Phase 10 idea catalog dashboard views."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


def bootstrap_catalog(ops_dir: Path) -> None:
    write_text(ops_dir / "ideas" / "idea_catalog.md", CATALOG_TEMPLATE)
    write_text(ops_dir / "ideas" / "prioritization.md", PRIORITIZATION_TEMPLATE)


def bootstrap_projected_catalog(ops_dir: Path, candidate: dict) -> None:
    write_text(
        ops_dir / "ideas" / "idea_catalog.md",
        f"""# Idea Catalog

{CATALOG_BLOCK_START}
| idea_id | status | title | weighted_score | next_task | blockers | promoted_task_id | updated_at |
| --- | --- | ---: | --- | --- | --- | --- | --- |
| {candidate["id"]} | {candidate.get("status", "candidate")} | {candidate["title"]} | {candidate["score"]["weighted_total"]} | {candidate["recommended_next_task"]} |  |  | {candidate["updated_at"]} |
{CATALOG_BLOCK_END}

## Notes

Free-form notes. Tooling must not edit this section.
""",
    )
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
        "score_explanation": "Fixture score for catalog dashboard tests.",
    }


def valid_candidate(candidate_id: str = "IDEA-0001") -> dict:
    return {
        "schema_version": "1.0",
        "id": candidate_id,
        "status": "candidate",
        "title": f"Fixture {candidate_id}",
        "question": "Can the fixture idea be validated cheaply?",
        "why_it_might_matter": "It checks catalog dashboard visibility.",
        "required_data": ["public fixture data"],
        "minimum_viable_test": "Run a bounded data-readiness check.",
        "baseline": "Compare against a simple baseline.",
        "main_risks": ["fixture risk"],
        "kill_reason": "Reject if fixture data is unavailable.",
        "score": valid_score(),
        "recommended_next_task": "data_readiness",
        "updated_at": "2026-05-07T10:00:00Z",
    }


def write_audited_source(ops_dir: Path, source_id: str = "DS-0001") -> None:
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


class IdeaCatalogPhase10Tests(unittest.TestCase):
    def test_dashboard_clean_catalog_returns_exit_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            candidate = valid_candidate("IDEA-0001")
            bootstrap_projected_catalog(ops_dir, candidate)
            write_json(ops_dir / "ideas" / "IDEA-0001.json", candidate)

            code, payload = run_helper_json(["dashboard", ops_dir])

            self.assertEqual(idea_catalog.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(0, payload["summary"]["failure_count"])
            self.assertEqual(0, payload["summary"]["warning_count"])
            self.assertEqual(1, payload["summary"]["candidate_count"])
            self.assertEqual(1, payload["summary"]["score_dimension_count"])
            self.assertEqual(["IDEA-0001"], [item["idea_id"] for item in payload["sections"]["candidate_ideas"]])
            self.assertEqual(16.5, payload["sections"]["score_dimensions"][0]["weighted_total"])

    def test_dashboard_empty_and_cold_start_catalogs_return_zero_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "empty" / "research_ops"
            bootstrap_catalog(ops_dir)

            code, payload = run_helper_json(["dashboard", ops_dir])

            self.assertEqual(idea_catalog.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(0, payload["summary"]["candidate_count"])
            self.assertEqual(0, payload["summary"]["total_issue_count"])
            self.assertEqual([], payload["sections"]["candidate_ideas"])
            self.assertEqual([], payload["sections"]["top_blockers"])

        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "cold" / "research_ops"
            ops_dir.mkdir(parents=True)

            code, payload = run_helper_json(["dashboard", ops_dir])

            self.assertEqual(idea_catalog.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(0, payload["summary"]["candidate_count"])
            self.assertEqual(1, payload["summary"]["total_issue_count"])
            self.assertEqual(["catalog_cold_start"], [item["reason"] for item in payload["sections"]["top_blockers"]])

    def test_dashboard_renders_required_sections_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_catalog(ops_dir)
            write_text(ops_dir / "queue.md", "- TASK-0001: Fixture promoted task\n")

            candidate = valid_candidate("IDEA-0001")
            raw_candidate = valid_candidate("IDEA-0002")
            raw_candidate.pop("score")
            parked = valid_candidate("IDEA-0003")
            parked.update({"status": "park", "status_reason": "Wait for data", "revisit_condition": "Dataset publishes"})
            rejected = valid_candidate("IDEA-0004")
            rejected.update({"status": "reject", "status_reason": "Too broad", "revisit_condition": "Scope narrows"})
            promoted = valid_candidate("IDEA-0005")
            promoted.update({"status": "promoted", "promoted_task_id": "TASK-0001"})
            promotable = valid_candidate("IDEA-0006")
            promotable.update({"status": "promote", "recommended_next_task": "literature_extract"})

            for payload in [candidate, raw_candidate, parked, rejected, promoted, promotable]:
                write_json(ops_dir / "ideas" / f"{payload['id']}.json", payload)

            before = file_snapshot(ops_dir)

            code, payload = run_helper_json(["dashboard", ops_dir])

            self.assertEqual(idea_catalog.MALFORMED, code, payload)
            self.assertFalse(payload["ok"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])
            self.assertEqual("catalog_read_model_and_validator", payload["generated_from"])
            self.assertEqual(before, file_snapshot(ops_dir))

            sections = payload["sections"]
            self.assertCountEqual(
                [
                    "candidate_ideas",
                    "parked_ideas",
                    "promoted_ideas",
                    "rejected_ideas",
                    "top_blockers",
                    "score_dimensions",
                    "next_recommended_tasks",
                    "idea_to_task_links",
                ],
                sections,
            )
            self.assertEqual({"IDEA-0001", "IDEA-0002", "IDEA-0006"}, {item["idea_id"] for item in sections["candidate_ideas"]})
            self.assertEqual(["IDEA-0003"], [item["idea_id"] for item in sections["parked_ideas"]])
            self.assertEqual(["IDEA-0004"], [item["idea_id"] for item in sections["rejected_ideas"]])
            self.assertEqual(["IDEA-0005"], [item["idea_id"] for item in sections["promoted_ideas"]])

            scores = {item["idea_id"]: item for item in sections["score_dimensions"]}
            self.assertFalse(scores["IDEA-0002"]["score_available"])
            self.assertEqual("unavailable", scores["IDEA-0002"]["weighted_total"])
            self.assertEqual(
                {dimension: "unavailable" for dimension in scores["IDEA-0002"]["dimensions"]},
                scores["IDEA-0002"]["dimensions"],
            )
            self.assertIn("candidate_schema_validation_failed", [item["reason"] for item in sections["top_blockers"]])

            next_tasks = {item["recommended_next_task"]: item["idea_count"] for item in sections["next_recommended_tasks"]}
            self.assertEqual(2, next_tasks["data_readiness"])
            self.assertEqual(1, next_tasks["literature_extract"])
            self.assertEqual(
                [{"idea_id": "IDEA-0005", "link_status": "available", "promoted_task_id": "TASK-0001"}],
                [
                    {
                        "idea_id": item["idea_id"],
                        "link_status": item["link_status"],
                        "promoted_task_id": item["promoted_task_id"],
                    }
                    for item in sections["idea_to_task_links"]
                ],
            )

    def test_dashboard_max_blockers_limits_visible_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_catalog(ops_dir)
            candidate = valid_candidate("IDEA-0001")
            candidate["status"] = "promote"
            candidate["kill_reason"] = ""
            candidate["score"] = copy.deepcopy(candidate["score"])
            candidate["score"]["weighted_total"] = 1.0
            candidate["score"]["hard_gate_results"] = [
                {"gate": "fixture_gate", "passed": False, "reason": "fixture failed"}
            ]
            write_json(ops_dir / "ideas" / "IDEA-0001.json", candidate)

            code, payload = run_helper_json(["dashboard", ops_dir, "--max-blockers", "1"])

            self.assertEqual(idea_catalog.VALIDATION_FAILED, code, payload)
            self.assertEqual(1, len(payload["sections"]["top_blockers"]))
            self.assertGreaterEqual(payload["summary"]["total_issue_count"], 3)
            self.assertEqual(1, payload["summary"]["displayed_blocker_count"])

    def test_dashboard_link_stale_when_promoted_task_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_catalog(ops_dir)
            promoted = valid_candidate("IDEA-0001")
            promoted.update({"status": "promoted", "promoted_task_id": "TASK-9999"})
            write_json(ops_dir / "ideas" / "IDEA-0001.json", promoted)

            code, payload = run_helper_json(["dashboard", ops_dir])

            self.assertEqual(idea_catalog.VALIDATION_FAILED, code, payload)
            self.assertEqual(
                [{"idea_id": "IDEA-0001", "link_status": "stale", "promoted_task_id": "TASK-9999"}],
                [
                    {
                        "idea_id": item["idea_id"],
                        "link_status": item["link_status"],
                        "promoted_task_id": item["promoted_task_id"],
                    }
                    for item in payload["sections"]["idea_to_task_links"]
                ],
            )

    def test_dashboard_link_unverified_when_promoted_task_on_non_promoted_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bootstrap_catalog(ops_dir)
            candidate = valid_candidate("IDEA-0001")
            candidate["promoted_task_id"] = "TASK-0001"
            write_json(ops_dir / "ideas" / "IDEA-0001.json", candidate)

            code, payload = run_helper_json(["dashboard", ops_dir])

            self.assertEqual(idea_catalog.SUCCESS, code, payload)
            self.assertEqual(
                [{"idea_id": "IDEA-0001", "link_status": "unverified_non_promoted_status", "promoted_task_id": "TASK-0001"}],
                [
                    {
                        "idea_id": item["idea_id"],
                        "link_status": item["link_status"],
                        "promoted_task_id": item["promoted_task_id"],
                    }
                    for item in payload["sections"]["idea_to_task_links"]
                ],
            )

    def test_dashboard_shows_available_link_after_successful_promotion_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            init_code, init_payload = run_cli_json(["init", ops_dir, "--force"])
            self.assertEqual(cli.SUCCESS, init_code, init_payload)
            write_audited_source(ops_dir)
            candidate = valid_candidate("IDEA-7601")
            candidate.update({"status": "promote", "data_refs": ["DS-0001"]})
            write_json(ops_dir / "ideas" / "IDEA-7601.json", candidate)
            dry_code, dry_run = run_cli_json(["idea", "promote", ops_dir, "IDEA-7601", "--dry-run"])
            self.assertEqual(cli.SUCCESS, dry_code, dry_run)

            write_code, written = run_cli_json(
                [
                    "idea",
                    "promote",
                    ops_dir,
                    "IDEA-7601",
                    "--write",
                    "--preflight-hash",
                    dry_run["promotion_preflight_hash"],
                ]
            )
            self.assertEqual(cli.SUCCESS, write_code, written)
            self.assertEqual("idea_promotion_task_written", written["action"])

            code, payload = run_helper_json(["dashboard", ops_dir])

            self.assertEqual(idea_catalog.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(1, payload["summary"]["promoted_count"])
            self.assertEqual(1, payload["summary"]["idea_to_task_link_count"])
            self.assertEqual(
                [{"idea_id": "IDEA-7601", "link_status": "available", "promoted_task_id": "TASK-7601"}],
                [
                    {
                        "idea_id": item["idea_id"],
                        "link_status": item["link_status"],
                        "promoted_task_id": item["promoted_task_id"],
                    }
                    for item in payload["sections"]["idea_to_task_links"]
                ],
            )
            self.assertEqual(["IDEA-7601"], [item["idea_id"] for item in payload["sections"]["promoted_ideas"]])

    def test_public_cli_routes_dashboard_command(self) -> None:
        with mock.patch.object(cli, "module_main", return_value=cli.SUCCESS) as module_main:
            code = cli.main(["idea", "catalog", "dashboard", "research_ops", "--max-blockers", "3"])

        self.assertEqual(cli.SUCCESS, code)
        module_main.assert_called_once_with("idea_catalog", ["dashboard", "research_ops", "--max-blockers", "3"])


if __name__ == "__main__":
    unittest.main()

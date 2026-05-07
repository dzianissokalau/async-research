"""Regression tests for read-only idea catalog operator surfaces."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.idea_catalog import CATALOG_BLOCK_END
from async_research_workflow.idea_catalog import CATALOG_BLOCK_START
from async_research_workflow.idea_catalog import catalog_surface_summary
from async_research_workflow.scripts import autonomy_readiness_gate
from async_research_workflow.scripts import health_check
from async_research_workflow.scripts import human_review_surface


NOW = "2026-05-05T00:00:00Z"


def run_json(entrypoint, argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = entrypoint.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
        "score_explanation": "Fixture score for catalog surface tests.",
    }


def valid_candidate(candidate_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "id": candidate_id,
        "status": "candidate",
        "title": f"Fixture {candidate_id}",
        "question": "Can the fixture idea be validated cheaply?",
        "why_it_might_matter": "It checks catalog surface reporting.",
        "required_data": ["public fixture data"],
        "minimum_viable_test": "Run a bounded data-readiness check.",
        "baseline": "Compare against a simple baseline.",
        "main_risks": ["fixture risk"],
        "kill_reason": "Reject if fixture data is unavailable.",
        "score": valid_score(),
        "recommended_next_task": "data_readiness",
        "created_at": NOW,
        "updated_at": NOW,
    }


def idea_snapshot(ops_dir: Path) -> dict[str, bytes]:
    return {
        path.name: path.read_bytes()
        for path in sorted((ops_dir / "ideas").glob("IDEA-*.json"))
    }


class IdeaCatalogSurfaceTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_json(cli, ["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        self.assertTrue(payload["ok"])
        return ops_dir

    def test_surface_update_summarizes_catalog_without_mutating_canonical_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            promotable = valid_candidate("IDEA-7001")
            promotable["status"] = "promote"
            promotable["human_priority"] = 1
            blocked = valid_candidate("IDEA-7002")
            blocked["score"]["weighted_total"] = 9.0
            blocked["score"]["hard_gate_results"] = [
                {"gate": "data_readiness", "passed": False, "reason": "no data evidence yet"}
            ]
            write_json(ops_dir / "ideas" / "IDEA-7001.json", promotable)
            write_json(ops_dir / "ideas" / "IDEA-7002.json", blocked)
            before = idea_snapshot(ops_dir)

            code, payload = run_json(human_review_surface, ["update", ops_dir, "--now", NOW])

            self.assertEqual(human_review_surface.SUCCESS, code, payload)
            self.assertEqual(before, idea_snapshot(ops_dir))
            weekly = (ops_dir / "weekly_digest.md").read_text(encoding="utf-8")
            daily = (ops_dir / "daily_status.md").read_text(encoding="utf-8")
            self.assertIn("## Idea Catalog Surface", weekly)
            self.assertIn("- Catalog ideas: 2", weekly)
            self.assertIn("Stored statuses: candidate: 1, promote: 1", weekly)
            self.assertIn("Derived pipeline: raw: 0, scored: 0, blocked: 1", weekly)
            self.assertIn("IDEA-7001", weekly)
            self.assertIn("IDEA-7002", weekly)
            self.assertIn("## Idea Catalog", daily)

    def test_health_and_readiness_warn_on_invalid_catalog_state_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_json(ops_dir / "ideas" / "IDEA-7003.json", valid_candidate("IDEA-7003"))
            duplicate = valid_candidate("IDEA-7003")
            write_json(ops_dir / "ideas" / "IDEA-7004.json", duplicate)
            before = idea_snapshot(ops_dir)

            health_args = health_check.parse_args([str(ops_dir), "--dry-run", "--no-daily-status", "--now", NOW])
            health = health_check.build_report(health_args)
            catalog_alert = next(item for item in health["alerts"] if item["check"] == "idea_catalog_state")
            self.assertEqual("warning", catalog_alert["severity"])
            self.assertEqual(4, catalog_alert["details"]["validation_exit_code"])
            stale_alert = next(item for item in health["alerts"] if item["check"] == "idea_catalog_projection_stale")
            self.assertEqual("warning", stale_alert["severity"])
            self.assertEqual(before, idea_snapshot(ops_dir))

            code, readiness = run_json(
                autonomy_readiness_gate,
                [
                    ops_dir,
                    "--dry-run",
                    "--no-daily-status",
                    "--now",
                    NOW,
                    "--metrics-stale-hours",
                    "100000",
                ],
            )

            self.assertEqual(autonomy_readiness_gate.WARNINGS, code, readiness)
            self.assertEqual("safe_with_warnings", readiness["decision"])
            warning = next(item for item in readiness["warnings"] if item["check"] == "idea_catalog_state")
            self.assertEqual(4, warning["details"]["validation_exit_code"])
            stale_warning = next(item for item in readiness["warnings"] if item["check"] == "idea_catalog_projection_stale")
            self.assertEqual("warning", stale_warning["severity"])
            self.assertEqual(before, idea_snapshot(ops_dir))

    def test_stale_projection_warning_fires_without_validation_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_json(ops_dir / "ideas" / "IDEA-7005.json", valid_candidate("IDEA-7005"))
            write_text(
                ops_dir / "ideas" / "idea_catalog.md",
                "\n".join(
                    [
                        "# Idea Catalog",
                        "",
                        CATALOG_BLOCK_START,
                        "| idea_id | status | title |",
                        "| --- | --- | --- |",
                        "| IDEA-9999 | candidate | stale projection row |",
                        CATALOG_BLOCK_END,
                        "",
                    ]
                ),
            )
            before = idea_snapshot(ops_dir)

            health_args = health_check.parse_args([str(ops_dir), "--dry-run", "--no-daily-status", "--now", NOW])
            health = health_check.build_report(health_args)
            self.assertFalse(any(item["check"] == "idea_catalog_state" for item in health["alerts"]))
            stale_alert = next(item for item in health["alerts"] if item["check"] == "idea_catalog_projection_stale")
            self.assertEqual("warning", stale_alert["severity"])

            code, readiness = run_json(
                autonomy_readiness_gate,
                [
                    ops_dir,
                    "--dry-run",
                    "--no-daily-status",
                    "--now",
                    NOW,
                    "--metrics-stale-hours",
                    "100000",
                ],
            )

            self.assertEqual(autonomy_readiness_gate.WARNINGS, code, readiness)
            self.assertEqual("safe_with_warnings", readiness["decision"])
            self.assertFalse(any(item["check"] == "idea_catalog_state" for item in readiness["warnings"]))
            stale_warning = next(item for item in readiness["warnings"] if item["check"] == "idea_catalog_projection_stale")
            self.assertEqual("warning", stale_warning["severity"])
            self.assertEqual(before, idea_snapshot(ops_dir))

    def test_cold_start_catalog_surface_renders_zero_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            shutil.rmtree(ops_dir / "ideas")

            code, payload = run_json(human_review_surface, ["update", ops_dir, "--now", NOW])

            self.assertEqual(human_review_surface.SUCCESS, code, payload)
            weekly = (ops_dir / "weekly_digest.md").read_text(encoding="utf-8")
            daily = (ops_dir / "daily_status.md").read_text(encoding="utf-8")
            self.assertIn("## Idea Catalog Surface", weekly)
            self.assertIn("- Catalog ideas: 0", weekly)
            self.assertIn("Stored statuses: candidate: 0, promote: 0", weekly)
            self.assertIn("- Top recommended promotions: none", weekly)
            self.assertIn("- Catalog ideas: 0", daily)

    def test_governance_metadata_failure_is_not_data_or_evidence_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            candidate = valid_candidate("IDEA-7006")
            candidate["score"]["mission_policy_version"] = ""
            write_json(ops_dir / "ideas" / "IDEA-7006.json", candidate)

            summary = catalog_surface_summary(ops_dir)

            failure_reasons = {item["reason"] for item in summary["failures"]}
            gap_reasons = {item["reason"] for item in summary["data_or_evidence_gap_issues"]}
            self.assertIn("scored_idea_missing_mission_policy_version", failure_reasons)
            self.assertNotIn("scored_idea_missing_mission_policy_version", gap_reasons)


if __name__ == "__main__":
    unittest.main()

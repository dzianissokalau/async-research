"""Phase 6 regression tests for knowledge library operational surfaces."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.scripts import autonomy_readiness_gate
from async_research_workflow.scripts import health_check
from async_research_workflow.scripts import human_review_surface
from async_research_workflow.scripts import knowledge_library
from async_research_workflow.scripts.version_metadata import apply_default_versions


NOW = "2026-05-09T00:00:00Z"
TEMPLATES = dict(knowledge_library.STARTER_FILES)


def run_json(entrypoint, argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = entrypoint.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def init_ops(root: Path) -> Path:
    ops_dir = root / "research_ops"
    code, payload = run_json(cli, ["init", ops_dir, "--force"])
    if code != cli.SUCCESS:
        raise AssertionError(payload)
    return ops_dir


def table_file(relative: str) -> Path:
    return Path(knowledge_library.LIBRARY_DIR) / relative


def write_rows(ops_dir: Path, relative: Path, rows: list[list[str]]) -> None:
    template = TEMPLATES[relative]
    spec = knowledge_library.TABLE_SPECS[relative]
    start = str(spec["start"])
    end = str(spec["end"])
    headers = list(spec["headers"])
    before, rest = template.split(start, 1)
    _old_block, after = rest.split(end, 1)
    block = [
        start,
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _header in headers) + " |",
    ]
    block.extend("| " + " | ".join(row) + " |" for row in rows)
    block.append(end)
    write_text(ops_dir / relative, before + "\n".join(block) + after)


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
        "score_explanation": "Fixture score for knowledge-library surface tests.",
    }


def candidate_with_library_ref(candidate_id: str, ref: str) -> dict:
    return {
        "schema_version": "1.0",
        "id": candidate_id,
        "status": "promote",
        "title": f"Fixture {candidate_id}",
        "question": "Can the fixture idea be validated cheaply?",
        "why_it_might_matter": "It checks library surface reporting.",
        "required_data": [],
        "minimum_viable_test": "Draft a hypothesis card.",
        "baseline": "Compare against a simple baseline.",
        "main_risks": ["fixture risk"],
        "kill_reason": "Reject if library support is malformed.",
        "score": valid_score(),
        "recommended_next_task": "hypothesis_card",
        "library_refs": [ref],
        "created_at": NOW,
        "updated_at": NOW,
    }


def write_task_status(ops_dir: Path, task_slug: str, task_type: str, catalog_idea_id: str | None = None) -> Path:
    task_id = "-".join(task_slug.split("-", 2)[:2])
    task_dir = ops_dir / "tasks" / task_slug
    payload = {
        "schema_version": "1.0",
        "id": task_id,
        "title": f"Knowledge library fixture {task_id}",
        "type": task_type,
        "status": "ready_for_worker",
        "previous_status": "ready_for_planning",
        "last_transition_reason": "phase_6_fixture",
        "priority": 3,
        "revision_count": 0,
        "max_revisions": 1,
        "revision_limit_hit": False,
        "created_at": NOW,
        "updated_at": NOW,
        "allowed_paths": [f"research_ops/tasks/{task_slug}/**"],
        "allowed_tools": ["repo_read", "markdown_edit"],
        "allow_browsing": False,
        "allow_code_execution": False,
        "allow_network": False,
        "max_minutes": 30,
        "max_turns": 3,
        "model_tier": "standard",
        "review_policy": {"tier": 1, "required_reviewers": ["primary"], "panel_required": False},
        "requires_human": False,
        "budget": {"max_api_usd": 1.0, "max_compute_usd": 0.0},
        "result": {"recommendation": None, "claim_strength": "none", "followup_count": 0},
        "data_audit_refs": [],
    }
    if catalog_idea_id is not None:
        payload["catalog_idea_id"] = catalog_idea_id
    apply_default_versions(payload)
    write_json(task_dir / "status.json", payload)
    write_text(task_dir / "task.md", f"# {task_id}\n\nFixture task.\n")
    return task_dir


class KnowledgeLibrarySurfaceTests(unittest.TestCase):
    def test_health_and_readiness_warn_on_missing_library_without_blocking_all_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            shutil.rmtree(ops_dir / "library")

            health_args = health_check.parse_args([str(ops_dir), "--dry-run", "--no-daily-status", "--now", NOW])
            health_report = health_check.build_report(health_args)
            code, payload = run_json(
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

        alert = next(item for item in health_report["alerts"] if item["check"] == "knowledge_library_findings")
        self.assertEqual("warning", alert["severity"])
        self.assertEqual("library_dir_missing", alert["details"]["warnings"][0]["reason"])
        self.assertEqual(autonomy_readiness_gate.WARNINGS, code, payload)
        self.assertEqual("safe_with_warnings", payload["decision"])
        self.assertTrue(payload["expensive_workers_allowed"])
        self.assertFalse(any(item["check"] == "knowledge_library_findings" for item in payload["blockers"]))
        warning = next(item for item in payload["warnings"] if item["check"] == "knowledge_library_findings")
        self.assertEqual("library_dir_missing", warning["details"]["warnings"][0]["reason"])

    def test_readiness_blocks_malformed_library_only_for_active_library_dependent_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            write_rows(
                ops_dir,
                table_file("source_library.md"),
                [["LIT-0001", "approved", "tier_1", "paper", "A", "Publisher", "https://example.test/a", "2026-05-09", "bad vocab"]],
            )
            write_json(ops_dir / "ideas" / "IDEA-7601.json", candidate_with_library_ref("IDEA-7601", "LIT-0001"))
            write_task_status(ops_dir, "TASK-7601-hypothesis-card", "hypothesis_card", "IDEA-7601")

            code, payload = run_json(
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

        self.assertEqual(autonomy_readiness_gate.HUMAN_REQUIRED, code, payload)
        self.assertEqual("human_required", payload["decision"])
        blocker = next(item for item in payload["blockers"] if item["check"] == "knowledge_library_findings")
        self.assertEqual("error", blocker["severity"])
        self.assertEqual(2, blocker["details"]["error_count"])
        self.assertEqual("TASK-7601", blocker["details"]["library_dependent_tasks"][0]["task_id"])

    def test_health_report_does_not_make_standalone_malformed_library_block_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            write_rows(
                ops_dir,
                table_file("source_library.md"),
                [["LIT-0001", "approved", "tier_1", "paper", "A", "Publisher", "https://example.test/a", "2026-05-09", "bad vocab"]],
            )

            health_code, health_payload = run_json(health_check, [ops_dir, "--no-daily-status", "--now", NOW])
            health_report = json.loads((ops_dir / "health_report.json").read_text(encoding="utf-8"))
            code, payload = run_json(
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

        self.assertEqual(health_check.SUCCESS, health_code, health_payload)
        alert = next(item for item in health_report["alerts"] if item["check"] == "knowledge_library_findings")
        self.assertEqual("warning", alert["severity"])
        self.assertEqual([], alert["details"]["library_dependent_tasks"])
        self.assertEqual(autonomy_readiness_gate.WARNINGS, code, payload)
        self.assertEqual("safe_with_warnings", payload["decision"])
        self.assertTrue(payload["expensive_workers_allowed"])
        self.assertFalse(any(item["check"] == "failed_previous_run" for item in payload["blockers"]))
        self.assertFalse(any(item["check"] == "knowledge_library_findings" for item in payload["blockers"]))

    def test_weekly_digest_and_daily_status_summarize_library_coverage_and_open_questions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            write_rows(
                ops_dir,
                table_file("source_library.md"),
                [["LIT-0001", "trusted", "primary", "paper", "A", "Publisher", "https://example.test/a", "2026-05-09", "ready"]],
            )
            write_rows(
                ops_dir,
                table_file("knowledge_index.md"),
                [["Fixture topic", "Known context", "LIT-0001", "moderate", "fixture caveat", "2026-05-09"]],
            )
            write_rows(
                ops_dir,
                table_file("open_questions.md"),
                [["OQ-0001", "What context remains unknown?", "It informs follow-up scope.", "LIT-0001", "literature_extract", "open"]],
            )

            code, payload = run_json(human_review_surface, ["update", ops_dir, "--now", NOW])
            weekly = (ops_dir / "weekly_digest.md").read_text(encoding="utf-8")
            daily = (ops_dir / "daily_status.md").read_text(encoding="utf-8")

        self.assertEqual(human_review_surface.SUCCESS, code, payload)
        self.assertIn("## Knowledge Library Surface", weekly)
        self.assertIn("- Library validation: ok", weekly)
        self.assertIn("- Sources: 1", weekly)
        self.assertIn("- Topics / claims / methods: 1 / 0 / 0", weekly)
        self.assertIn("- Open questions: 1", weekly)
        self.assertIn("OQ-0001", weekly)
        self.assertIn("## Knowledge Library", daily)
        self.assertIn("- Open questions: 1", daily)


if __name__ == "__main__":
    unittest.main()

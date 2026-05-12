"""Regression tests for delivered-project outcome indexes."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.console import outcomes
from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


NOW = "2026-05-12T00:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def accepted_index_text() -> str:
    return "\n".join(
        [
            "| accepted_date | task_id | title | key_finding | claim_type | freshness_window_days | next_recheck_date | revalidation_status | source_ids | claim_strength | caveats | followups | supersedes | superseded_by | evidence_link |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            "| 2026-05-10 | TASK-3001 | Accepted fixture | Accepted key finding | predictive | 45 | 2026-06-24 | current | DS-0001, DS-0002 | moderate | use with caveats | follow up later | none | none | tasks/TASK-3001-accepted/worker_output.md |",
        ]
    ) + "\n"


def write_status(ops_dir: Path, task_id: str, status: str, title: str | None = None) -> Path:
    task_dir = ops_dir / "tasks" / f"{task_id}-{status}"
    payload = {
        "schema_version": "1.0",
        "id": task_id,
        "title": title or f"{task_id} {status}",
        "type": "run_analysis" if task_id == "TASK-3001" else "admin",
        "status": status,
        "previous_status": "panel_review",
        "last_transition_reason": f"{status} fixture",
        "priority": 2,
        "revision_count": 2 if task_id == "TASK-3001" else 0,
        "max_revisions": 3,
        "revision_limit_hit": False,
        "created_at": "2026-05-08T00:00:00Z",
        "updated_at": "2026-05-10T00:00:00Z",
        "allowed_paths": [f"research_ops/tasks/{task_dir.name}/**"],
        "max_minutes": 10,
        "requires_human": False,
        "budget": {"max_api_usd": 1.25, "max_compute_usd": 0.5},
        "review_policy": {"tier": 2, "required_reviewers": ["primary", "methodology"], "panel_required": True},
        "catalog_idea_id": "IDEA-3001" if task_id == "TASK-3001" else None,
        "result": {"claim_strength": "weak", "claim_type": "predictive", "key_finding": "status key finding"},
    }
    write_json(task_dir / "status.json", payload)
    (task_dir / "task.md").write_text(f"# {task_id}\n", encoding="utf-8")
    (task_dir / "worker_output.md").write_text("Worker output summary.\n", encoding="utf-8")
    return task_dir


def write_review_artifacts(task_dir: Path) -> None:
    write_json(
        task_dir / "review_panel" / "aggregate.json",
        {
            "schema_version": "1.0",
            "task_id": "TASK-3001",
            "aggregate_decision": "accepted",
            "aggregate_claim_strength": "moderate",
            "reviews": [{"role": "primary", "decision": "accept", "claim_strength": "moderate"}],
            "disagreements": ["none"],
        },
    )
    write_json(
        task_dir / "review_panel" / "result_acceptance.json",
        {
            "route": "accept_as_evidence",
            "recommended_decision": "usable_with_caveats",
            "claim_strength": "moderate",
            "scorecard": {"claim_discipline": 4, "decision_usefulness": 5},
            "reviewer_panel": {
                "aggregate_decision": "accepted",
                "tier": 2,
                "reviewer_count": 1,
                "disagreement_present": False,
            },
            "analysis_run": {"run_id": "RUN-3001"},
        },
    )


def write_fixture_workspace(root: Path) -> Path:
    ops_dir = root / "research_ops"
    (ops_dir / "tasks").mkdir(parents=True)
    (ops_dir / "accepted_outputs_index.md").write_text(accepted_index_text(), encoding="utf-8")
    accepted_task = write_status(ops_dir, "TASK-3001", "accepted", "Accepted fixture")
    write_status(ops_dir, "TASK-3002", "rejected", "Rejected fixture")
    write_review_artifacts(accepted_task)
    write_json(
        ops_dir / "ideas" / "IDEA-3001.json",
        {"id": "IDEA-3001", "title": "Idea fixture", "score": {"weighted_total": 17.5, "mission_fit": 4}},
    )
    with (ops_dir / "cost_ledger.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "item_id", "amount_usd"])
        writer.writeheader()
        writer.writerow({"date": "2026-05-10", "item_id": "TASK-3001", "amount_usd": "2.5"})
    return ops_dir


class ConsoleOutcomesTests(unittest.TestCase):
    def test_outcomes_refresh_writes_rebuildable_jsonl_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = write_fixture_workspace(Path(tmp))

            code, payload = run_cli_json(["outcomes", "refresh", ops_dir, "--now", NOW])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual("outcomes_refreshed", payload["action"])
            projects_path = ops_dir / "outcomes" / "delivered_projects.jsonl"
            summary_path = ops_dir / "outcomes" / "delivered_projects_summary.json"
            self.assertTrue(projects_path.exists())
            self.assertTrue(summary_path.exists())
            projects = [json.loads(line) for line in projects_path.read_text(encoding="utf-8").splitlines()]
            by_id = {project["task_id"]: project for project in projects}
            self.assertEqual({"TASK-3001", "TASK-3002"}, set(by_id))
            self.assertEqual(17.5, by_id["TASK-3001"]["idea_score"])
            self.assertEqual(1, by_id["TASK-3001"]["worker_run_count"])
            self.assertEqual(2.5, by_id["TASK-3001"]["actual_cost_usd"])
            self.assertEqual("accepted", by_id["TASK-3001"]["aggregate_review_decision"])
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(2, summary["project_count"])
            self.assertEqual(1, summary["accepted_count"])
            self.assertEqual(1, summary["rejected_count"])
            self.assertEqual(0.5, summary["acceptance_rate"])
            self.assertEqual(1.5, summary["average_iterations"])

            project_schema = load_json(schema_path("delivered_project.schema.json"))
            summary_schema = load_json(schema_path("delivered_projects_summary.schema.json"))
            self.assertEqual([], [error.to_dict() for error in validate(by_id["TASK-3001"], project_schema)])
            self.assertEqual([], [error.to_dict() for error in validate(summary, summary_schema)])

    def test_outcomes_list_and_summary_are_readable_without_generated_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = write_fixture_workspace(Path(tmp))

            code, listed = run_cli_json(["outcomes", "list", ops_dir, "--status", "accepted", "--now", NOW])
            self.assertEqual(cli.SUCCESS, code, listed)
            self.assertEqual(1, listed["count"])
            self.assertEqual("TASK-3001", listed["projects"][0]["task_id"])
            self.assertFalse((ops_dir / "outcomes" / "delivered_projects.jsonl").exists())

            code, summary = run_cli_json(["outcomes", "summary", ops_dir, "--now", NOW])
            self.assertEqual(cli.SUCCESS, code, summary)
            self.assertEqual(2, summary["summary"]["project_count"])
            self.assertEqual(0.5, summary["summary"]["acceptance_rate"])

    def test_missing_task_provenance_renders_unavailable_not_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()
            (ops_dir / "accepted_outputs_index.md").write_text(accepted_index_text(), encoding="utf-8")

            index = outcomes.build_index(ops_dir, now=outcomes.parse_now(NOW))

            self.assertEqual(1, len(index["projects"]))
            project = index["projects"][0]
            self.assertEqual("TASK-3001", project["task_id"])
            self.assertEqual("unavailable", project["idea_score"])
            self.assertEqual("unavailable", project["review_tier"])
            self.assertEqual("unavailable", project["task_dir"])


if __name__ == "__main__":
    unittest.main()

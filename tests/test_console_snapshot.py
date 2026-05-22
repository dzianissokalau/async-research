"""Regression tests for the local console snapshot backend."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from async_research_workflow import cli
from async_research_workflow.console import snapshot as snapshot_module


NOW = "2026-05-11T00:00:00Z"
SNAPSHOT_GROUPS = {
    "workspace",
    "readiness",
    "health",
    "tasks",
    "human_decisions",
    "accepted_outputs",
    "delivered_projects",
    "deliverables",
    "interaction_mode",
    "rejected_results",
    "cost",
    "sources",
    "prompts",
    "schedules",
    "ideas",
    "data",
    "library",
    "analysis",
    "lifecycle",
    "runs",
    "runtime",
    "evals",
    "warnings",
}


def previous_status_for(status: str) -> str | None:
    return {
        "in_progress": "ready_for_worker",
        "awaiting_review": "in_progress",
        "single_review": "awaiting_review",
        "panel_review": "awaiting_review",
        "accepted": "panel_review",
        "synthesized": "accepted",
        "rejected": "panel_review",
        "needs_human": "ready_for_worker",
        "paused": "needs_human",
    }.get(status)


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def write_task_status(
    ops_dir: Path,
    task_id: str,
    status: str = "ready_for_worker",
    requires_human: bool = False,
    task_type: str = "admin",
    title: str | None = None,
) -> Path:
    task_dir = ops_dir / "tasks" / f"{task_id}-fixture"
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "status.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "id": task_id,
                "title": title or f"{task_id} fixture",
                "type": task_type,
                "status": status,
                "previous_status": previous_status_for(status),
                "last_transition_reason": "fixture",
                "priority": 2,
                "revision_count": 0,
                "max_revisions": 1,
                "revision_limit_hit": False,
                "allowed_paths": [f"research_ops/tasks/{task_dir.name}/**"],
                "max_minutes": 10,
                "requires_human": requires_human,
                "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
                "human_gate_reason": "fixture needs human" if requires_human or status == "needs_human" else None,
                "updated_at": NOW,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return task_dir


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def idea_score() -> dict:
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
        "score_explanation": "Coffee pilot fixture score.",
    }


def idea_candidate(candidate_id: str, title: str) -> dict:
    return {
        "schema_version": "1.0",
        "id": candidate_id,
        "status": "candidate",
        "title": title,
        "question": "Can coffee country concentration interact with climate exposure?",
        "why_it_might_matter": "It mirrors the coffee pilot foundation path.",
        "required_data": ["country concentration source", "climate exposure source"],
        "minimum_viable_test": "Run a bounded data-readiness check.",
        "baseline": "Compare against static country concentration shares.",
        "main_risks": ["source freshness", "coverage gaps"],
        "kill_reason": "Reject if governed source coverage is unavailable.",
        "score": idea_score(),
        "recommended_next_task": "data_readiness",
        "updated_at": "2026-05-07T10:00:00Z",
    }


class ConsoleSnapshotTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        self.assertTrue(payload["ok"])
        return ops_dir

    def snapshot(self, ops_dir: Path) -> tuple[int, dict]:
        return run_cli_json(["console", "snapshot", ops_dir, "--json", "--now", NOW])

    def test_snapshot_renders_generic_starter_without_mutating_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            before = file_snapshot(ops_dir)

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])
            self.assertTrue(SNAPSHOT_GROUPS.issubset(payload))
            self.assertEqual("console_snapshot_rendered", payload["action"])
            self.assertEqual("console_snapshot_v1.0", payload["schema_version"])
            self.assertEqual(0, payload["tasks"]["total"])
            self.assertEqual({}, payload["tasks"]["status_counts"])
            self.assertEqual(0, payload["human_decisions"]["open_count"])
            self.assertEqual(0, payload["accepted_outputs"]["count"])
            self.assertEqual(0, payload["rejected_results"]["count"])
            self.assertTrue(payload["interaction_mode"]["available"])
            self.assertEqual("supervised", payload["interaction_mode"]["mode"])
            self.assertTrue(payload["interaction_mode"]["config_present"])
            self.assertFalse(payload["prompts"]["available"])
            self.assertEqual("unavailable", payload["prompts"]["status"])
            self.assertFalse(payload["schedules"]["available"])
            self.assertEqual("unavailable", payload["schedules"]["status"])
            self.assertIn("month_spend_usd", payload["cost"])
            self.assertEqual(0, payload["runtime"]["evidence_object_count"])
            self.assertEqual(0, payload["runtime"]["trace_count"])
            self.assertEqual(0, payload["runtime"]["unsupported_or_stale_evidence_count"])
            self.assertEqual(0, payload["evals"]["suite_count"])
            self.assertEqual(0, payload["evals"]["run_count"])
            lifecycle = payload["lifecycle"]
            self.assertEqual("available", lifecycle["status"])
            self.assertEqual(10, lifecycle["station_count"])
            self.assertEqual("topic", lifecycle["current_station_id"])
            self.assertEqual(0, lifecycle["accepted_output_count"])
            by_station = {station["id"]: station for station in lifecycle["stations"]}
            self.assertEqual("Discovery Inbox", by_station["discovery"]["label"])
            discovery_links = {link["label"]: link for link in by_station["discovery"]["artifact_links"]}
            self.assertTrue(discovery_links["Discovery inbox"]["viewer_allowed"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_snapshot_defaults_missing_interaction_mode_without_mutating_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            (ops_dir / "interaction_mode.json").unlink()
            before = file_snapshot(ops_dir)

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["interaction_mode"]["available"])
            self.assertFalse(payload["interaction_mode"]["config_present"])
            self.assertTrue(payload["interaction_mode"]["defaulted"])
            self.assertEqual("manual", payload["interaction_mode"]["mode"])
            self.assertTrue(any(item["message"].startswith("interaction_mode.json is missing") for item in payload["warnings"]))
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_snapshot_surfaces_invalid_interaction_mode_as_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_json(
                ops_dir / "interaction_mode.json",
                {
                    "schema_version": "1.0",
                    "mode": "autonomous",
                    "risk_tolerance": "conservative",
                    "interrupt_policy": {
                        "allow_interrupts": False,
                        "interrupt_only_for": ["hard_budget_breach"],
                    },
                    "auto_decisions": {
                        "allow_resume": True,
                        "allow_revision": True,
                        "allow_reject": True,
                        "allow_claim_downgrade": True,
                        "allow_source_substitution": True,
                        "allow_idea_prioritization": True,
                    },
                    "audit": {
                        "write_decisions": True,
                        "write_auto_decisions": False,
                        "explain_auto_decisions": True,
                    },
                },
            )

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertFalse(payload["interaction_mode"]["available"])
            self.assertEqual("invalid", payload["interaction_mode"]["status"])
            self.assertTrue(any("interaction modes must allow human interrupts" in item["message"] for item in payload["warnings"]))

    def test_snapshot_surfaces_malformed_task_status_as_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = ops_dir / "tasks" / "TASK-9999-malformed"
            task_dir.mkdir(parents=True)
            (task_dir / "status.json").write_text("{not json", encoding="utf-8")

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual(0, payload["tasks"]["total"])
            self.assertEqual(1, len(payload["tasks"]["malformed_statuses"]))
            self.assertTrue(any(item["reason"] == "malformed_task_status" for item in payload["warnings"]))

    def test_malformed_task_row_handles_missing_task_dir(self) -> None:
        row = snapshot_module.malformed_task_row(
            {"task_id": "TASK-EMPTY", "reason": "malformed_json", "errors": [{"message": "bad"}]},
            snapshot_module.parse_now(NOW),
        )

        self.assertEqual("TASK-EMPTY", row["task_id"])
        self.assertEqual("invalid", row["status"])
        self.assertFalse(row["lock_state"]["locked"])
        self.assertEqual([], row["files"])
        self.assertEqual("", row["task_dir"])

    def test_snapshot_marks_missing_optional_foundations_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            for relative in ("ideas", "data", "library"):
                target = ops_dir / relative
                for path in sorted(target.rglob("*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
                target.rmdir()

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertFalse(payload["ideas"]["available"])
            self.assertEqual("unavailable", payload["ideas"]["status"])
            self.assertFalse(payload["data"]["available"])
            self.assertFalse(payload["library"]["available"])
            reasons = {item["reason"] for item in payload["warnings"]}
            self.assertIn("ideas_files_missing", reasons)
            self.assertIn("data_files_missing", reasons)
            self.assertIn("library_files_missing", reasons)

    def test_snapshot_reports_missing_workspace_without_hard_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["workspace"]["exists"])
            self.assertFalse(payload["readiness"]["available"])
            self.assertFalse(payload["health"]["available"])
            self.assertFalse(payload["runs"]["available"])

    def test_snapshot_handles_non_directory_ops_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_path = Path(tmp) / "research_ops"
            ops_path.write_text("not a directory\n", encoding="utf-8")

            code, payload = self.snapshot(ops_path)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["workspace"]["exists"])
            self.assertFalse(payload["workspace"]["is_dir"])
            self.assertFalse(payload["readiness"]["available"])
            self.assertFalse(payload["health"]["available"])

    def test_snapshot_rejects_invalid_now_with_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))

            code, payload = run_cli_json(["console", "snapshot", ops_dir, "--json", "--now", "not-a-time"])

            self.assertEqual(3, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("invalid_now", payload["reason"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])

    def test_snapshot_uses_consistent_task_shape_for_human_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task_status(ops_dir, "TASK-1001", "needs_human", requires_human=True)
            (task_dir / "task.md").write_text("# Human task\n", encoding="utf-8")
            (task_dir / "worker_output.md").write_text("# Evidence\n", encoding="utf-8")
            (task_dir / "review_panel").mkdir(exist_ok=True)
            (task_dir / "review_panel" / "result_acceptance.json").write_text('{"ok": true}\n', encoding="utf-8")

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual(1, len(payload["tasks"]["human"]))
            human = payload["tasks"]["human"][0]
            for key in [
                "task_id",
                "title",
                "status",
                "type",
                "review_tier",
                "revision_count",
                "requires_human",
                "human_gate_reason",
                "last_transition_reason",
                "allowed_paths",
                "allowed_next_statuses",
                "status_validation",
                "transition_validation",
                "lock_state",
                "files",
                "task_dir",
                "status_path",
            ]:
                self.assertIn(key, human)
            self.assertEqual("TASK-1001", human["task_id"])
            self.assertEqual(human, payload["human_decisions"]["blocked_task_refs"][0])
            links = {item["label"]: item for item in human["files"]}
            self.assertEqual("/artifacts/tasks/TASK-1001-fixture/worker_output.md", links["Worker output"]["viewer_url"])
            self.assertEqual("/artifacts/tasks/TASK-1001-fixture/worker_output.md?raw=1", links["Worker output"]["raw_url"])
            self.assertEqual("/artifacts/tasks/TASK-1001-fixture/review_panel/result_acceptance.json", links["Result acceptance"]["viewer_url"])
            self.assertTrue(links["Task brief"]["viewer_allowed"])

    def test_snapshot_reads_public_decision_rows_from_legacy_template_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))

            code, decision = run_cli_json(
                [
                    "decision",
                    "append",
                    ops_dir,
                    "--item-id",
                    "TASK-1002",
                    "--decision",
                    "acknowledge",
                    "--reason",
                    "Console snapshot fixture",
                    "--approver",
                    "test-owner",
                    "--date",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, decision)

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            decisions = payload["human_decisions"]
            self.assertEqual(1, decisions["decision_log_count"])
            self.assertEqual("TASK-1002", decisions["recent_decision_rows"][0]["item_id"])
            self.assertEqual("acknowledge", decisions["recent_decision_rows"][0]["decision"])
            self.assertEqual("Console snapshot fixture", decisions["recent_decision_rows"][0]["reason"])

    def test_snapshot_reads_existing_legacy_decision_rows_without_new_append(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            (ops_dir / "decisions.md").write_text(
                "\n".join(
                    [
                        "# Human Decision Log",
                        "",
                        "| decision_id | item_id | decision | decided_at | decided_by | rationale | follow_up |",
                        "| --- | --- | --- | --- | --- | --- | --- |",
                        "| DEC-1001 | TASK-1003 | resume | 2026-05-11T12:00:00Z | test-owner | Legacy starter rationale | status.json |",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            decisions = payload["human_decisions"]
            self.assertEqual(1, decisions["decision_log_count"])
            row = decisions["recent_decision_rows"][0]
            self.assertEqual("2026-05-11T12:00:00Z", row["date"])
            self.assertEqual("TASK-1003", row["item_id"])
            self.assertEqual("resume", row["decision"])
            self.assertEqual("Legacy starter rationale", row["reason"])
            self.assertEqual("test-owner", row["approver"])
            self.assertEqual("status.json", row["related_artifacts"])

    def test_snapshot_includes_full_task_board_rows_and_invalid_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task_status(ops_dir, "TASK-1003", "ready_for_worker")
            malformed_dir = ops_dir / "tasks" / "TASK-1004-malformed"
            malformed_dir.mkdir(parents=True)
            (malformed_dir / "status.json").write_text("{not json", encoding="utf-8")

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            by_id = {task["task_id"]: task for task in payload["tasks"]["all"]}
            self.assertIn("TASK-1003", by_id)
            self.assertIn("TASK-1004-malformed", by_id)
            valid = by_id["TASK-1003"]
            self.assertTrue(valid["status_validation"]["valid"])
            self.assertTrue(valid["transition_validation"]["valid"])
            self.assertIn("in_progress", valid["allowed_next_statuses"])
            self.assertEqual({"locked": False, "stale": False}, {key: valid["lock_state"][key] for key in ("locked", "stale")})
            self.assertIn(str((task_dir / "status.json").resolve()), [item["path"] for item in valid["files"]])
            invalid = by_id["TASK-1004-malformed"]
            self.assertEqual("invalid", invalid["status"])
            self.assertFalse(invalid["status_validation"]["valid"])
            self.assertEqual("malformed_json", invalid["status_validation"]["reason"])
            self.assertFalse(invalid["transition_validation"]["valid"])
            self.assertIn("invalid", payload["tasks"]["status_filter_options"])

    def test_snapshot_surfaces_stale_locks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task_status(ops_dir, "TASK-1002", "in_progress")
            lock_dir = task_dir / "LOCK"
            lock_dir.mkdir()
            os.utime(lock_dir, (0, 0))

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual(1, len(payload["tasks"]["stale_locks"]))
            self.assertEqual(str(lock_dir), payload["tasks"]["stale_locks"][0]["lock_dir"])
            task = payload["tasks"]["all"][0]
            self.assertTrue(task["lock_state"]["locked"])
            self.assertTrue(task["lock_state"]["stale"])

    def test_snapshot_surfaces_budget_pressure_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            (ops_dir / "cost_ledger.csv").write_text(
                "\n".join(
                    [
                        "date,item_id,amount_usd,monthly_budget_usd,weekly_budget_usd",
                        "2026-05-11,COST-1,90,100,100",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["cost"]["budget_pressure"])
            reasons = {item["reason"] for item in payload["warnings"]}
            self.assertIn("monthly_budget_pressure", reasons)
            self.assertIn("weekly_budget_pressure", reasons)

    def test_lifecycle_maps_coffee_pilot_style_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            data_task = write_task_status(
                ops_dir,
                "TASK-0001",
                "accepted",
                task_type="data_readiness",
                title="Coffee country concentration data readiness",
            )
            analysis_task = write_task_status(
                ops_dir,
                "TASK-0005",
                "in_progress",
                task_type="run_analysis",
                title="Coffee climate exposure overlay analysis",
            )
            write_task_status(
                ops_dir,
                "TASK-0006",
                "ready_for_worker",
                task_type="memo_section",
                title="Coffee volatility synthesis memo",
            )
            (data_task / "worker_output.md").write_text("# Data readiness\n\nAccepted source foundation.\n", encoding="utf-8")
            (analysis_task / "worker_output.md").write_text("# Analysis draft\n\nClimate exposure overlay in progress.\n", encoding="utf-8")
            (ops_dir / "accepted_outputs_index.md").write_text(
                "\n".join(
                    [
                        "| accepted_date | task_id | title | key_finding | claim_type | freshness_window_days | next_recheck_date | revalidation_status | source_ids | claim_strength | caveats | followups | supersedes | superseded_by | evidence_link |",
                        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                        f"| 2026-05-10 | TASK-0001 | Coffee country concentration data readiness | Concentration sources are usable with caveats | data_readiness | 90 | 2026-08-08 | current | DS-0001 | moderate | caveats documented | none | none | none | tasks/{data_task.name}/worker_output.md |",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            lifecycle = payload["lifecycle"]
            self.assertEqual("analysis", lifecycle["current_station_id"])
            by_station = {station["id"]: station for station in lifecycle["stations"]}
            self.assertEqual("complete", by_station["source_data"]["status"])
            self.assertEqual("active", by_station["analysis"]["status"])
            self.assertEqual("queued", by_station["synthesis"]["status"])
            self.assertEqual("TASK-0005", by_station["analysis"]["active_task"]["task_id"])
            self.assertIn("workflow worker-complete", by_station["analysis"]["next_command"]["command"])
            self.assertEqual("TASK-0001", by_station["source_data"]["accepted_outputs"][0]["task_id"])
            evidence_links = by_station["source_data"]["accepted_outputs"][0]["links"]
            self.assertTrue(any(link["label"] == "Accepted memory evidence" and link["viewer_url"].endswith("/worker_output.md") for link in evidence_links))
            source_links = {link["label"]: link for link in by_station["source_data"]["artifact_links"]}
            self.assertTrue(source_links["Source audit"]["viewer_allowed"])

    def test_snapshot_surfaces_deliverable_maturity_without_final_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task_status(
                ops_dir,
                "TASK-0015",
                "accepted",
                task_type="status_update",
                title="Accepted internal draft assembly",
            )
            code, payload = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-0015",
                    "--title",
                    "Coffee and climate paper draft",
                    "--output-type",
                    "working_paper",
                    "--target-maturity",
                    "working_paper",
                    "--current-maturity",
                    "internal_draft",
                    "--target-audience",
                    "research collaborators",
                    "--source-task",
                    "TASK-0015",
                    "--complete-gate",
                    "source_caveat_checks",
                    "--complete-gate",
                    "claim_strength_review",
                    "--complete-gate",
                    "task_review",
                    "--complete-gate",
                    "accepted_evidence_linkage",
                    "--complete-gate",
                    "caveat_audit",
                    "--complete-gate",
                    "internal_workflow_disclosure",
                    "--complete-gate",
                    "draft_completeness_check",
                    "--review-independence",
                    "same_agent_visible",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, payload)

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            deliverables = payload["deliverables"]
            self.assertEqual("available", deliverables["status"])
            self.assertEqual(1, deliverables["count"])
            self.assertEqual(0, deliverables["summary"]["target_ready_count"])
            self.assertEqual(1, deliverables["summary"]["blocked_count"])
            row = deliverables["rows"][0]
            self.assertFalse(row["target_ready"])
            self.assertEqual("internal draft accepted; working paper not ready", row["readiness_label"])
            self.assertNotIn("final", row["readiness_label"].lower())
            self.assertEqual("internal_draft", row["maturity"]["current"])
            self.assertEqual("working_paper", row["maturity"]["target"])
            self.assertEqual(1, row["task_acceptance"]["accepted_source_task_count"])
            self.assertTrue(row["task_acceptance"]["accepted_source_tasks_do_not_imply_readiness"])
            self.assertGreater(row["editorial_qa"]["missing_gate_count"], 0)
            self.assertEqual("missing", row["critic_review"]["status"])
            self.assertEqual("not_required", row["response_matrix"]["status"])
            self.assertTrue(row["review_independence"]["same_agent_review"])
            reasons = {item["reason"] for item in row["blockers"]}
            self.assertIn("current_maturity_below_target", reasons)
            self.assertIn("gate_missing", reasons)
            self.assertIn("critic_review_missing", reasons)
            self.assertEqual("DELIV-0015", deliverables["attention_rows"][0]["deliverable_id"])

    def test_task_detail_surfaces_coffee_style_explainability_and_qa(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task_status(
                ops_dir,
                "TASK-0001",
                "accepted",
                task_type="data_readiness",
                title="Coffee country concentration data readiness",
            )
            status_path = task_dir / "status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            status["catalog_idea_id"] = "IDEA-COFFEE-001"
            status["data_audit_refs"] = ["DS-COFFEE-001"]
            status["allowed_paths"] = [
                "research_ops/tasks/TASK-0001-fixture/**",
                "research_ops/data_source_audit.md",
                "research_ops/data/**",
            ]
            status["review_policy"] = {
                "tier": 2,
                "required_reviewers": ["primary", "methodology"],
                "panel_required": True,
                "human_required_for_acceptance": False,
            }
            status["result"] = {
                "recommendation": "ready",
                "claim_strength": "moderate",
                "claim_type": "data_readiness",
                "caveats": ["ICO source requires manual refresh"],
                "followups": ["TASK-0005 climate exposure overlay"],
            }
            status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            (task_dir / "task.md").write_text(
                "\n".join(
                    [
                        "# TASK-0001",
                        "",
                        "## Objective",
                        "Explain whether coffee-country concentration sources are usable for downstream climate research.",
                        "",
                        "## Research Question",
                        "Can accepted ICO and FAOSTAT sources support country concentration claims?",
                        "",
                        "## Context",
                        "- research_ops/data_source_audit.md",
                        "- research_ops/data/profiles/DS-COFFEE-001.md",
                        "",
                        "## Required Output",
                        "- source-by-source readiness verdict",
                        "- recommended next task: `climate_overlay`",
                        "- validation results from `async-research source validate research_ops`",
                        "- validation results from `async-research data validate research_ops`",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "worker_output.md").write_text(
                "Coffee readiness accepted.\n\n"
                "`async-research source validate research_ops`\n"
                "`async-research data validate research_ops`\n",
                encoding="utf-8",
            )
            (task_dir / "review_panel").mkdir(exist_ok=True)
            (task_dir / "review_panel" / "aggregate.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "task_id": "TASK-0001",
                        "tier": 2,
                        "required_reviewers": ["primary", "methodology"],
                        "missing_required_reviews": [],
                        "aggregate_decision": "accepted",
                        "routing_reason": "all_required_reviewers_accept",
                        "aggregate_claim_strength": "moderate",
                        "human_gate_required": False,
                        "revision_limit_hit": False,
                        "reviews": [
                            {
                                "reviewer_role": "primary",
                                "decision": "accept",
                                "claim_strength": "moderate",
                                "confidence": 0.9,
                                "main_concerns": [],
                                "evidence_gaps": [],
                            },
                            {
                                "reviewer_role": "methodology",
                                "decision": "accept_with_caveats",
                                "claim_strength": "moderate",
                                "confidence": 0.8,
                                "main_concerns": ["Manual source refresh cadence remains a caveat"],
                                "evidence_gaps": ["No automated refresh job yet"],
                            },
                        ],
                        "agreements": ["All required reviewers accepted or accepted with caveats."],
                        "disagreements": [],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            (task_dir / "review_panel" / "result_acceptance.json").write_text(
                json.dumps(
                    {
                        "route": "accept_as_evidence",
                        "recommended_decision": "ready",
                        "claim_strength": "moderate",
                        "max_claim_strength": "moderate",
                        "review_notes": ["accepted with refresh caveat"],
                        "scorecard": {"claim_discipline": 5, "reproducibility": 4},
                        "reviewer_panel": {
                            "aggregate_decision": "accepted",
                            "tier": 2,
                            "reviewer_count": 2,
                            "disagreement_present": False,
                        },
                        "source_governance": {
                            "ok": True,
                            "required": True,
                            "source_ids": ["DS-COFFEE-001"],
                            "blocked": [],
                            "warnings": [],
                        },
                        "hard_gate_results": [{"gate": "source_governance", "passed": True, "reason": "approved"}],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            claim_dir = task_dir / "artifacts" / "analysis_run"
            claim_dir.mkdir(parents=True)
            (claim_dir / "claim_gates.json").write_text(
                json.dumps(
                    {
                        "claim_decision": "accepted",
                        "max_claim_strength": "moderate",
                        "claim_gate_results": [
                            {"gate": "source_refs_present", "status": "pass"},
                            {"gate": "claim_limitations_declared", "status": "pass"},
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            task = next(row for row in payload["tasks"]["all"] if row["task_id"] == "TASK-0001")
            explanation = task["explainability"]
            self.assertIn("coffee-country concentration", explanation["rationale"])
            self.assertIn("ICO and FAOSTAT", explanation["research_question"])
            self.assertEqual("IDEA-COFFEE-001", explanation["trigger"])
            self.assertIn("research_ops/data_source_audit.md", explanation["input_artifacts"])
            self.assertTrue(any("source-by-source readiness verdict" in row for row in explanation["output_artifacts"]))
            self.assertIn("data source: DS-COFFEE-001", explanation["dependencies"])
            self.assertIn("async-research source validate research_ops", explanation["validation_commands"])
            self.assertEqual("TASK-0005 climate exposure overlay", explanation["next_recommended_task"])

            qa = task["qa"]
            self.assertEqual("accepted", qa["review_status"])
            self.assertIn("panel-based", qa["review_modes"])
            self.assertIn("independent", qa["review_modes"])
            self.assertEqual({"count": 2, "min": 0.8, "average": 0.85}, qa["reviewer_confidence"])
            self.assertEqual("moderate", qa["claim_strength"])
            self.assertEqual("pass", qa["source_gate"]["status"])
            self.assertEqual(["DS-COFFEE-001"], qa["source_gate"]["source_ids"])
            self.assertIn("No automated refresh job yet", qa["evidence_gaps"])
            self.assertIn("scorecard reproducibility: 4", qa["reproducibility_checks"])
            self.assertTrue(any("claim_gates.json: pass: 2" == row for row in qa["validation_checks"]))
            self.assertEqual("accept_as_evidence", qa["result_acceptance"]["route"])

    def test_snapshot_surfaces_slice_11_operation_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            (ops_dir / "cost_ledger.csv").write_text(
                "\n".join(
                    [
                        "date,item_id,role,model_or_tool,usage_source,input_tokens,output_tokens,total_tokens,amount_usd,monthly_budget_usd,weekly_budget_usd,actual,notes",
                        "2026-05-11,COST-1,worker,codex,fixture,100,40,140,90,100,100,true,pressure row",
                        "2026-04-01,COST-OLD,planner,codex,fixture,10,5,15,2,100,100,true,old row",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (ops_dir / "data_source_audit.md").write_text(
                "\n".join(
                    [
                        "# Data Source Audit Register",
                        "",
                        "Schema version: 1.0",
                        "",
                        "| source_id | source_name | url_or_domain | publisher_owner | source_tier | approval_status | approved_use_cases | blocked_use_cases | freshness_window_days | known_limitations | citation_requirements | last_reviewed | approved_by | review_notes |",
                        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                        "| DS-0001 | Stale approved source | https://example.test/stale | Fixture | tier_1_official | approved | experiment_planning; accepted_evidence | none | 30 | stale fixture | cite fixture | 2026-01-01 | tester | old review |",
                        "| DS-0002 | Blocked source | https://example.test/blocked | Fixture | tier_4_untrusted | blocked | none | all | 30 | blocked fixture | cite fixture | 2026-05-01 | none | blocked |",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (ops_dir / "accepted_outputs_index.md").write_text(
                "\n".join(
                    [
                        "| accepted_date | task_id | title | key_finding | claim_type | freshness_window_days | next_recheck_date | revalidation_status | source_ids | claim_strength | caveats | followups | supersedes | superseded_by | evidence_link |",
                        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                        "| 2026-01-01 | TASK-5001 | Stale evidence | Finding | market_price | 30 | 2026-02-01 | current | DS-0001 | moderate | none | refresh | none | none | tasks/TASK-5001/worker_output.md |",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("pressure", payload["cost"]["monthly_budget_state"])
            self.assertEqual(2, payload["cost"]["row_count"])
            self.assertEqual(155, payload["cost"]["total_tokens"])
            self.assertEqual("COST-1", payload["cost"]["top_spend_rows"][0]["item_id"])
            self.assertTrue(any("cost summary" in item["label"].lower() for item in payload["cost"]["recovery_commands"]))
            source_summary = payload["sources"]["summary"]
            self.assertEqual(2, source_summary["source_count"])
            self.assertEqual(1, source_summary["blocked_source_count"])
            self.assertEqual(1, source_summary["stale_source_count"])
            attention_ids = {row["source_id"] for row in payload["sources"]["attention_sources"]}
            self.assertEqual({"DS-0001", "DS-0002"}, attention_ids)
            blocked_source = payload["sources"]["blocked_sources"][0]
            action_labels = {action["label"] for action in blocked_source["available_actions"]}
            self.assertIn("Approve source", action_labels)
            self.assertIn("Revise source audit", action_labels)
            self.assertTrue(any("source validate" in item["command"] for item in payload["sources"]["recovery_commands"]))
            self.assertEqual(1, payload["accepted_outputs"]["memory_decay"]["stale_count"])
            self.assertEqual("TASK-5001", payload["accepted_outputs"]["stale_rows"][0]["task_id"])
            alert_checks = {alert["check"] for alert in payload["health"]["alerts"]}
            self.assertIn("stale_accepted_evidence", alert_checks)
            self.assertIn("monthly_budget_threshold", alert_checks)
            self.assertTrue(any("accepted revalidation" in item["command"] for item in payload["health"]["recovery_commands"]))
            lifecycle_by_station = {station["id"]: station for station in payload["lifecycle"]["stations"]}
            self.assertEqual("blocked", lifecycle_by_station["source_data"]["status"])
            self.assertTrue(any(blocker.get("source_id") == "DS-0002" for blocker in lifecycle_by_station["source_data"]["blockers"]))

    def test_snapshot_surfaces_phase4_foundation_and_cost_drilldowns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task_status(
                ops_dir,
                "TASK-0006",
                "needs_human",
                requires_human=True,
                task_type="data_readiness",
                title="Coffee climate exposure foundation",
            )
            status_path = task_dir / "status.json"
            status_payload = json.loads(status_path.read_text(encoding="utf-8"))
            status_payload.update(
                {
                    "allow_network": True,
                    "human_gate_reason": "Budget and external API approval required.",
                    "budget": {"max_api_usd": 4.0, "max_compute_usd": 1.5},
                    "model_tier": "frontier",
                }
            )
            write_json(status_path, status_payload)
            promoted = idea_candidate("IDEA-0006", "Coffee climate exposure concentration")
            promoted.update({"status": "promoted", "promoted_task_id": "TASK-0006", "library_refs": ["LIT-0006"]})
            write_json(ops_dir / "ideas" / "IDEA-0006.json", promoted)
            (ops_dir / "library" / "source_library.md").write_text(
                "\n".join(
                    [
                        "# Source Library",
                        "",
                        "<!-- LIBRARY-SOURCES: schema_version=1.0 -->",
                        "| source_id | status | trust_tier | type | title | author_or_publisher | location | reviewed_date | notes |",
                        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                        "| LIT-0006 | context_only | background | report | Coffee climate background | Fixture Publisher | https://example.test/coffee | 2026-05-09 | context only until source governance is ready |",
                        "<!-- /LIBRARY-SOURCES -->",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (ops_dir / "library" / "knowledge_index.md").write_text(
                "\n".join(
                    [
                        "# Knowledge Index",
                        "",
                        "<!-- LIBRARY-KNOWLEDGE: schema_version=1.0 -->",
                        "| topic | summary | source_refs | confidence | caveats | updated_at |",
                        "| --- | --- | --- | --- | --- | --- |",
                        "| Coffee climate exposure | Climate overlays are useful context for concentration research. | LIT-0006 | medium | context-only source | 2026-05-09 |",
                        "<!-- /LIBRARY-KNOWLEDGE -->",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (ops_dir / "library" / "claim_map.md").write_text(
                "\n".join(
                    [
                        "# Claim Map",
                        "",
                        "<!-- LIBRARY-CLAIMS: schema_version=1.0 -->",
                        "| claim | source_refs | claim_strength | disputed_status | caveats | reviewed_date |",
                        "| --- | --- | --- | --- | --- | --- |",
                        "| Coffee concentration work needs climate context. | LIT-0006 | moderate | context_only | planning context only | 2026-05-09 |",
                        "<!-- /LIBRARY-CLAIMS -->",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (ops_dir / "library" / "method_index.md").write_text(
                "\n".join(
                    [
                        "# Method Index",
                        "",
                        "<!-- LIBRARY-METHODS: schema_version=1.0 -->",
                        "| method | use_case | assumptions | source_refs | risks | reviewed_date |",
                        "| --- | --- | --- | --- | --- | --- |",
                        "| Overlay climate exposure with origin concentration | planning | comparable country identifiers | LIT-0006 | source freshness | 2026-05-09 |",
                        "<!-- /LIBRARY-METHODS -->",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (ops_dir / "library" / "open_questions.md").write_text(
                "\n".join(
                    [
                        "# Open Questions",
                        "",
                        "<!-- LIBRARY-OPEN-QUESTIONS: schema_version=1.0 -->",
                        "| question_id | question | why_it_matters | source_refs | next_task | status |",
                        "| --- | --- | --- | --- | --- | --- |",
                        "| Q-0006 | Which origins drive climate exposure concentration? | guides data readiness | LIT-0006 | TASK-0006 | open |",
                        "<!-- /LIBRARY-OPEN-QUESTIONS -->",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (ops_dir / "cost_ledger.csv").write_text(
                "\n".join(
                    [
                        "date,item_id,role,provider,model_or_tool,usage_source,external_service,input_tokens,output_tokens,total_tokens,input_usd,output_usd,api_usd,compute_usd,data_usd,amount_usd,status,actual,network_use,approval_required,monthly_budget_usd,weekly_budget_usd,notes",
                        "2026-05-11,TASK-0006,worker,openai,gpt-5.4-mini,external_api,paid_api,1000,500,1500,0.50,1.00,1.50,0.25,0.75,2.50,needs_human,true,true,true,10,5,coffee foundation fixture",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            idea_links = payload["ideas"]["sections"]["idea_to_task_links"]
            self.assertEqual(
                [{"idea_id": "IDEA-0006", "link_status": "available", "promoted_task_id": "TASK-0006"}],
                [
                    {
                        "idea_id": item["idea_id"],
                        "link_status": item["link_status"],
                        "promoted_task_id": item["promoted_task_id"],
                    }
                    for item in idea_links
                ],
            )
            self.assertTrue(any(link["viewer_allowed"] for link in payload["ideas"]["links"]))
            library_sections = payload["library"]["sections"]
            self.assertEqual("Coffee climate exposure", library_sections["coverage_by_topic"][0]["topic"])
            self.assertEqual("Coffee concentration work needs climate context.", library_sections["claims"][0]["claim"])
            self.assertEqual("Overlay climate exposure with origin concentration", library_sections["methods"][0]["method"])
            self.assertEqual("LIT-0006", library_sections["risky_sources"][0]["source_id"])
            self.assertEqual("Q-0006", library_sections["open_questions"][0]["question_id"])
            self.assertTrue(any(link["viewer_allowed"] for link in payload["library"]["links"]))
            task_cost = payload["cost"]["task_costs"][0]
            self.assertEqual("TASK-0006", task_cost["task_id"])
            self.assertEqual(5.5, task_cost["planned_total_usd"])
            self.assertEqual(2.5, task_cost["actual_spend_usd"])
            self.assertEqual(1.5, task_cost["api_usd"])
            self.assertEqual(0.75, task_cost["data_usd"])
            self.assertTrue(task_cost["network_use"])
            self.assertTrue(task_cost["approval_required"])
            self.assertEqual("required", task_cost["approval_status"])
            self.assertEqual("worker", payload["cost"]["role_costs"][0]["label"])
            self.assertEqual("openai", payload["cost"]["model_provider_costs"][0]["label"])
            self.assertEqual(1, payload["cost"]["summary"]["approval_required_count"])
            self.assertEqual(1, payload["cost"]["summary"]["network_use_count"])

    def test_budget_state_treats_non_finite_values_as_unconfigured(self) -> None:
        self.assertEqual("unconfigured", snapshot_module.budget_state(float("inf")))
        self.assertEqual("unconfigured", snapshot_module.budget_state(float("-inf")))
        self.assertEqual("unconfigured", snapshot_module.budget_state(float("nan")))
        self.assertEqual("unconfigured", snapshot_module.budget_state(True))
        self.assertEqual("pressure", snapshot_module.budget_state(0.8))

    def test_snapshot_degrades_unreadable_cost_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            (ops_dir / "cost_ledger.csv").write_bytes(b"\xff\xfe\x00")

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertFalse(payload["cost"]["available"])
            self.assertEqual("unavailable", payload["cost"]["status"])
            self.assertTrue(any(item["reason"] == "cost_ledger_unreadable" for item in payload["warnings"]))

    def test_snapshot_degrades_readiness_and_health_exceptions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))

            with mock.patch.object(snapshot_module.autonomy_readiness_gate, "build_gate_report", side_effect=RuntimeError("readiness boom")):
                code, payload = self.snapshot(ops_dir)
            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertFalse(payload["readiness"]["available"])
            self.assertEqual("readiness_unavailable", payload["readiness"]["reason"])

            with mock.patch.object(snapshot_module.health_check, "build_report", side_effect=RuntimeError("health boom")):
                code, payload = self.snapshot(ops_dir)
            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertFalse(payload["health"]["available"])
            self.assertEqual("health_unavailable", payload["health"]["reason"])

    def test_snapshot_degrades_dashboard_summary_exceptions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))

            with mock.patch.object(snapshot_module, "catalog_dashboard_report", side_effect=RuntimeError("ideas boom")):
                code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertFalse(payload["ideas"]["available"])
            self.assertEqual("ideas_dashboard_unavailable", payload["ideas"]["reason"])
            self.assertTrue(any(item["reason"] == "ideas_dashboard_unavailable" for item in payload["warnings"]))

    def test_snapshot_warns_on_malformed_markdown_table_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            (ops_dir / "accepted_outputs_index.md").write_text(
                "\n".join(
                    [
                        "| accepted_date | task_id | title |",
                        "| --- | --- | --- |",
                        "| 2026-05-11 | TASK-1003 |",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(any(item["reason"] == "malformed_markdown_table_row" for item in payload["warnings"]))

    def test_snapshot_includes_delivered_projects_from_accepted_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task_status(ops_dir, "TASK-4001", status="accepted")
            (ops_dir / "accepted_outputs_index.md").write_text(
                "\n".join(
                    [
                        "| accepted_date | task_id | title | key_finding | claim_type | freshness_window_days | next_recheck_date | revalidation_status | source_ids | claim_strength | caveats | followups | supersedes | superseded_by | evidence_link |",
                        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                        f"| 2026-05-10 | TASK-4001 | Delivered fixture | Finding | general | 90 | 2026-08-08 | current | none | weak | none | none | none | none | tasks/{task_dir.name}/worker_output.md |",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            delivered = payload["delivered_projects"]
            self.assertEqual(1, delivered["count"])
            self.assertFalse(delivered["exists"])
            self.assertEqual(["all", "accepted"], delivered["status_filter_options"])
            self.assertEqual("TASK-4001", delivered["rows"][0]["task_id"])
            self.assertEqual(1, delivered["summary"]["revalidation_counts"]["current"])

    def test_snapshot_surfaces_broken_run_json_without_dropping_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            run_dir = ops_dir / "run_artifacts" / "run-001"
            run_dir.mkdir(parents=True)
            (run_dir / "run.json").write_text("{not json", encoding="utf-8")

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["runs"]["available"])
            self.assertEqual(1, payload["runs"]["count"])
            self.assertEqual("run-001", payload["runs"]["recent_runs"][0]["run_id"])
            self.assertEqual("unavailable", payload["runs"]["recent_runs"][0]["status"])

    def test_snapshot_ignores_internal_run_locks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            lock_dir = ops_dir / "run_artifacts" / ".locks" / "worker-loop"
            lock_dir.mkdir(parents=True)
            (lock_dir / "lock.json").write_text(json.dumps({"run_id": "local-active"}) + "\n", encoding="utf-8")
            run_dir = ops_dir / "run_artifacts" / "run-001"
            run_dir.mkdir()
            (run_dir / "run.json").write_text(
                json.dumps({"run_id": "run-001", "status": "completed", "job_id": "worker-loop"}) + "\n",
                encoding="utf-8",
            )

            code, payload = self.snapshot(ops_dir)

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["runs"]["available"])
            self.assertEqual(1, payload["runs"]["count"])
            self.assertEqual(["run-001"], [run["run_id"] for run in payload["runs"]["recent_runs"]])


if __name__ == "__main__":
    unittest.main()

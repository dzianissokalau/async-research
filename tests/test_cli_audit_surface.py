"""Regression tests for CLI audit public wrapper promotions."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.scripts import human_decision_log


NOW = "2026-05-05T00:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def run_decision_helper_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = human_decision_log.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_source_audit(ops_dir: Path) -> None:
    (ops_dir / "data_source_audit.md").write_text(
        "\n".join(
            [
                "# Data Source Audit Register",
                "",
                "Schema version: 1.0",
                "",
                "| source_id | source_name | url_or_domain | publisher_owner | source_tier | approval_status | approved_use_cases | blocked_use_cases | freshness_window_days | known_limitations | citation_requirements | last_reviewed | approved_by | review_notes |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                "| DS-0001 | Test Source | https://example.test | Test Publisher | tier_1_official | approved | experiment_planning; accepted_evidence | none | 365 | none | cite DS-0001 | 2026-05-05 | tests | ready fixture |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_accepted_index(ops_dir: Path) -> None:
    (ops_dir / "accepted_outputs_index.md").write_text(
        "\n".join(
            [
                "| accepted_date | task_id | title | key_finding | claim_type | freshness_window_days | next_recheck_date | revalidation_status | source_ids | claim_strength | caveats | followups | supersedes | superseded_by | evidence_link |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                "| 2025-01-01 | TASK-1001 | Old evidence | Old finding | general | 30 | 2025-02-01 | stale | none | moderate | none | none | none | none | tasks/TASK-1001/worker_output.md |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_budget_ledger(ops_dir: Path) -> None:
    with (ops_dir / "cost_ledger.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "date",
                "item_id",
                "role",
                "model_or_tool",
                "usage_source",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "input_usd",
                "output_usd",
                "api_usd",
                "compute_usd",
                "amount_usd",
                "human_minutes",
                "status",
                "actual",
                "monthly_budget_usd",
                "weekly_budget_usd",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "date": "2026-05-05",
                "item_id": "COST-0001",
                "role": "worker",
                "model_or_tool": "fixture-model",
                "usage_source": "fixture",
                "input_tokens": "0",
                "output_tokens": "0",
                "total_tokens": "0",
                "input_usd": "0",
                "output_usd": "0",
                "api_usd": "0",
                "compute_usd": "90",
                "amount_usd": "90",
                "human_minutes": "0",
                "status": "recorded",
                "actual": "true",
                "monthly_budget_usd": "100",
                "weekly_budget_usd": "100",
                "notes": "budget pressure fixture",
            }
        )


def write_task_status(ops_dir: Path, task_id: str, status: str) -> Path:
    task_dir = ops_dir / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "status.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "id": task_id,
                "title": f"{task_id} fixture",
                "type": "admin",
                "status": status,
                "previous_status": "ready_for_worker" if status == "needs_human" else None,
                "last_transition_reason": "fixture",
                "priority": 2,
                "revision_count": 0,
                "max_revisions": 1,
                "revision_limit_hit": False,
                "allowed_paths": [f"research_ops/tasks/{task_id}/**"],
                "max_minutes": 10,
                "requires_human": status == "needs_human",
                "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
                "human_gate_reason": "fixture needs human" if status == "needs_human" else None,
                "updated_at": "2026-05-05T00:00:00Z",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return task_dir


def write_clear_task_contract(task_dir: Path) -> None:
    (task_dir / "task.md").write_text(
        "\n".join(
            [
                f"# {task_dir.name} Fixture",
                "",
                "## Objective",
                "",
                "Run one bounded administrative check with explicit scope.",
                "",
                "## Scope",
                "",
                f"- Work only inside `research_ops/tasks/{task_dir.name}/`.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


class CliAuditSurfaceTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        self.assertTrue(payload["ok"])
        return ops_dir

    def test_cost_ingest_usage_dry_run_preserves_ledger_and_write_appends_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            usage = Path(tmp) / "usage.json"
            usage.write_text(json.dumps({"usage": {"input_tokens": 1000, "output_tokens": 2000}}), encoding="utf-8")
            ledger = ops_dir / "cost_ledger.csv"
            before = ledger.read_text(encoding="utf-8")

            code, dry = run_cli_json(
                [
                    "cost",
                    "ingest-usage",
                    ops_dir,
                    "--usage-file",
                    usage,
                    "--item-id",
                    "TASK-3001",
                    "--role",
                    "worker",
                    "--model",
                    "fixture-model",
                    "--api-usd",
                    "0.03",
                    "--dry-run",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, dry)
            self.assertEqual("dry_run_usage_ingested", dry["action"])
            self.assertEqual(before, ledger.read_text(encoding="utf-8"))

            code, written = run_cli_json(
                [
                    "cost",
                    "ingest-usage",
                    ops_dir,
                    "--usage-file",
                    usage,
                    "--item-id",
                    "TASK-3001",
                    "--role",
                    "worker",
                    "--model",
                    "fixture-model",
                    "--api-usd",
                    "0.03",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, written)
            self.assertEqual("usage_ingested", written["action"])
            self.assertIn("TASK-3001", ledger.read_text(encoding="utf-8"))

    def test_cost_budget_check_preserves_halt_exit_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_budget_ledger(ops_dir)

            code, payload = run_cli_json(
                [
                    "cost",
                    "budget-check",
                    ops_dir,
                    "--item-id",
                    "TASK-3002",
                    "--action",
                    "promotion",
                    "--proposed-api-usd",
                    "0",
                    "--proposed-compute-usd",
                    "0",
                    "--threshold",
                    "0.8",
                ]
            )

            self.assertEqual(2, code, payload)
            self.assertTrue(payload["halt"])
            self.assertEqual("budget_threshold_exceeded", payload["reason"])

    def test_accepted_duplicate_is_advisory_and_memory_use_remains_hard_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_accepted_index(ops_dir)

            code, duplicate = run_cli_json(["accepted", "check-duplicate", ops_dir, "--title", "Old evidence"])
            self.assertEqual(cli.SUCCESS, code, duplicate)
            self.assertTrue(duplicate["duplicate_risk"])

            artifact = ops_dir / "tasks" / "TASK-3003-new-work" / "worker_output.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("This proposed output relies on TASK-1001 as current evidence.\n", encoding="utf-8")
            code, memory = run_cli_json(["accepted", "check-memory-use", ops_dir, artifact, "--now", NOW])

            self.assertEqual(2, code, memory)
            self.assertFalse(memory["ok"])
            self.assertEqual("stale_accepted_memory_reuse", memory["reason"])

    def test_source_experiment_and_claim_checks_use_public_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_source_audit(ops_dir)
            plan = ops_dir / "tasks" / "TASK-3004-plan" / "task.md"
            plan.parent.mkdir(parents=True)
            plan.write_text("Data Source Audit: DS-0001\n", encoding="utf-8")

            code, experiment = run_cli_json(["source", "check-experiment", ops_dir, plan])
            self.assertEqual(cli.SUCCESS, code, experiment)
            self.assertTrue(experiment["ok"])
            self.assertEqual(["DS-0001"], experiment["data_audit_refs"])

            code, claim = run_cli_json(["source", "check-claim", ops_dir, plan, "--use-case", "accepted_evidence"])
            self.assertEqual(cli.SUCCESS, code, claim)
            self.assertTrue(claim["ok"])
            self.assertEqual([], claim["blocked"])

    def test_metrics_summarize_outputs_json_and_optional_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            output = Path(tmp) / "metrics.md"

            code, payload = run_cli_json(["metrics", "summarize", ops_dir, "--output", output])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(str(output), payload["output"])
            self.assertTrue(output.exists())
            self.assertIn("Metrics Trend Summary", output.read_text(encoding="utf-8"))

    def test_queue_discovery_gate_allows_under_capacity_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task_status(ops_dir, "TASK-4001", "ready_for_worker")
            daily_status = ops_dir / "daily_status.md"
            before_daily = daily_status.read_text(encoding="utf-8")
            queue_before = (ops_dir / "queue.md").read_text(encoding="utf-8")

            code, payload = run_cli_json(["queue", "discovery-gate", ops_dir, "--max-active", "2"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual("discovery_allowed", payload["action"])
            self.assertEqual(1, payload["active_task_count"])
            self.assertEqual(before_daily, daily_status.read_text(encoding="utf-8"))
            self.assertEqual(queue_before, (ops_dir / "queue.md").read_text(encoding="utf-8"))

    def test_queue_discovery_gate_skips_over_capacity_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task_status(ops_dir, "TASK-4002", "ready_for_worker")
            write_task_status(ops_dir, "TASK-4003", "needs_human")
            daily_status = ops_dir / "daily_status.md"
            before_daily = daily_status.read_text(encoding="utf-8")

            code, payload = run_cli_json(["queue", "discovery-gate", ops_dir, "--max-active", "1"])

            self.assertEqual(2, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("discovery_skipped", payload["action"])
            self.assertEqual("active_queue_over_capacity", payload["reason"])
            self.assertEqual(2, payload["active_task_count"])
            self.assertEqual(before_daily, daily_status.read_text(encoding="utf-8"))

    def test_decision_append_dry_run_preserves_log_and_append_writes_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            decisions = ops_dir / "decisions.md"
            before = decisions.read_text(encoding="utf-8")

            code, dry = run_cli_json(
                [
                    "decision",
                    "append",
                    ops_dir,
                    "--item-id",
                    "TASK-5001",
                    "--decision",
                    "approve_budget",
                    "--reason",
                    "Budget approved for fixture",
                    "--approver",
                    "test-owner",
                    "--related-artifact",
                    "research_ops/tasks/TASK-5001/status.json",
                    "--date",
                    NOW,
                    "--dry-run",
                ]
            )

            self.assertEqual(cli.SUCCESS, code, dry)
            self.assertEqual("dry_run_decision_appended", dry["action"])
            self.assertEqual("TASK-5001", dry["row"]["item_id"])
            self.assertEqual(before, decisions.read_text(encoding="utf-8"))

            helper_code, helper_dry = run_decision_helper_json(
                [
                    "append",
                    ops_dir,
                    "--item-id",
                    "TASK-5001",
                    "--decision",
                    "approve_budget",
                    "--reason",
                    "Budget approved for fixture",
                    "--approver",
                    "test-owner",
                    "--related-artifact",
                    "research_ops/tasks/TASK-5001/status.json",
                    "--date",
                    NOW,
                    "--dry-run",
                ]
            )

            self.assertEqual(cli.SUCCESS, helper_code, helper_dry)
            self.assertEqual(dry, helper_dry)
            self.assertEqual(before, decisions.read_text(encoding="utf-8"))

            code, written = run_cli_json(
                [
                    "decision",
                    "append",
                    ops_dir,
                    "--item-id",
                    "TASK-5001",
                    "--decision",
                    "approve_budget",
                    "--reason",
                    "Budget approved for fixture",
                    "--approver",
                    "test-owner",
                    "--related-artifact",
                    "research_ops/tasks/TASK-5001/status.json",
                    "--date",
                    NOW,
                ]
            )

            self.assertEqual(cli.SUCCESS, code, written)
            self.assertEqual("decision_appended", written["action"])
            self.assertIn("TASK-5001", decisions.read_text(encoding="utf-8"))

    def test_decision_check_and_summarize_use_public_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            run_cli_json(
                [
                    "decision",
                    "append",
                    ops_dir,
                    "--item-id",
                    "TASK-5002",
                    "--decision",
                    "acknowledge",
                    "--reason",
                    "Acknowledged fixture gate",
                    "--approver",
                    "test-owner",
                    "--date",
                    NOW,
                ]
            )

            code, check = run_cli_json(["decision", "check", ops_dir, "--item-id", "TASK-5002", "--decision", "acknowledge"])
            self.assertEqual(cli.SUCCESS, code, check)
            self.assertTrue(check["ok"])

            output = Path(tmp) / "decision-summary.md"
            code, summary = run_cli_json(["decision", "summarize", ops_dir, "--month", "2026-05", "--output", output])

            self.assertEqual(cli.SUCCESS, code, summary)
            self.assertEqual(1, summary["decision_count"])
            self.assertEqual(str(output), summary["output"])
            self.assertIn("Human Decision Summary", output.read_text(encoding="utf-8"))

    def test_decision_resolve_task_dry_run_preserves_state_and_write_resolves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task_status(ops_dir, "TASK-5003", "needs_human")
            decisions = ops_dir / "decisions.md"
            before_decisions = decisions.read_text(encoding="utf-8")
            before_status = (task_dir / "status.json").read_text(encoding="utf-8")

            code, dry = run_cli_json(
                [
                    "decision",
                    "resolve-task",
                    ops_dir,
                    task_dir,
                    "--decision",
                    "resume",
                    "--reason",
                    "Fixture reviewed and can resume",
                    "--approver",
                    "test-owner",
                    "--status",
                    "ready_for_worker",
                    "--date",
                    NOW,
                    "--dry-run",
                ]
            )

            self.assertEqual(cli.SUCCESS, code, dry)
            self.assertEqual("dry_run_resolved", dry["action"])
            self.assertEqual(before_decisions, decisions.read_text(encoding="utf-8"))
            self.assertEqual(before_status, (task_dir / "status.json").read_text(encoding="utf-8"))

            code, resolved = run_cli_json(
                [
                    "decision",
                    "resolve-task",
                    ops_dir,
                    task_dir,
                    "--decision",
                    "resume",
                    "--reason",
                    "Fixture reviewed and can resume",
                    "--approver",
                    "test-owner",
                    "--status",
                    "ready_for_worker",
                    "--date",
                    NOW,
                ]
            )

            self.assertEqual(cli.SUCCESS, code, resolved)
            self.assertEqual("resolved", resolved["action"])
            self.assertIn("TASK-5003", decisions.read_text(encoding="utf-8"))
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("ready_for_worker", status["status"])
            self.assertFalse(status["requires_human"])

    def test_escalation_list_and_scan_needs_human_use_public_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_task_status(ops_dir, "TASK-6001", "needs_human")

            code, listing = run_cli_json(["escalation", "list"])
            self.assertEqual(cli.SUCCESS, code, listing)
            self.assertTrue(listing["ok"])
            self.assertGreater(len(listing["triggers"]), 0)

            code, scan = run_cli_json(["escalation", "scan-needs-human", ops_dir])
            self.assertEqual(2, code, scan)
            self.assertFalse(scan["ok"])
            self.assertEqual("needs_human_scanned", scan["action"])
            self.assertGreater(scan["error_count"], 0)

    def test_escalation_evaluate_no_trigger_exits_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task_status(ops_dir, "TASK-6002", "ready_for_worker")
            write_clear_task_contract(task_dir)

            code, payload = run_cli_json(["escalation", "evaluate", task_dir, "--ops-dir", ops_dir])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual("continue", payload["route"])
            self.assertEqual(0, payload["trigger_count"])

    def test_escalation_evaluate_trigger_without_apply_preserves_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task_status(ops_dir, "TASK-6003", "ready_for_worker")
            before = (task_dir / "status.json").read_text(encoding="utf-8")

            code, payload = run_cli_json(["escalation", "evaluate", task_dir, "--ops-dir", ops_dir])

            self.assertEqual(2, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("needs_human", payload["route"])
            self.assertIn("ambiguous_task_contract", payload["triggered_triggers"])
            self.assertEqual(before, (task_dir / "status.json").read_text(encoding="utf-8"))

    def test_escalation_evaluate_apply_writes_structured_needs_human_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task_status(ops_dir, "TASK-6004", "ready_for_worker")

            code, payload = run_cli_json(["escalation", "evaluate", task_dir, "--ops-dir", ops_dir, "--apply"])

            self.assertEqual(2, code, payload)
            self.assertEqual("escalation_applied", payload["action"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("needs_human", status["status"])
            self.assertTrue(status["requires_human"])
            self.assertEqual("ambiguous_task_contract", status["human_gate"]["trigger"])
            self.assertIn("required_human_decision", status["human_gate"])


if __name__ == "__main__":
    unittest.main()

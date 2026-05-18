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
from async_research_workflow.scripts import data_source_audit
from async_research_workflow.scripts import decision_log
from async_research_workflow.scripts import human_decision_log


NOW = "2026-05-05T00:00:00Z"
CANONICAL_DECISION_HEADER = ["date", "item_id", "decision", "reason", "approver", "related_artifacts"]
LEGACY_STARTER_DECISION_HEADER = [
    "decision_id",
    "item_id",
    "decision",
    "decided_at",
    "decided_by",
    "rationale",
    "follow_up",
]
WEEK_SIMULATION_DECISION_HEADER = ["date", "item_id", "decision", "approver", "reason", "next_status"]


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


def decision_table_cells(path: Path) -> list[list[str]]:
    return [
        decision_log.split_markdown_row(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("|") and "---" not in line
    ]


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


def write_source_audit_rows(ops_dir: Path, rows: list[str]) -> None:
    (ops_dir / "data_source_audit.md").write_text(
        "\n".join(
            [
                "# Data Source Audit Register",
                "",
                "Schema version: 1.0",
                "",
                "| source_id | source_name | url_or_domain | publisher_owner | source_tier | approval_status | approved_use_cases | blocked_use_cases | freshness_window_days | known_limitations | citation_requirements | last_reviewed | approved_by | review_notes |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                *rows,
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
    def init_ops(self, root: Path, *, template: str = "generic") -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--template", template, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        self.assertTrue(payload["ok"])
        return ops_dir

    def assert_decision_table_aligned(self, decisions: Path, expected_header: list[str]) -> list[list[str]]:
        rows = decision_table_cells(decisions)
        self.assertGreaterEqual(len(rows), 1, decisions.read_text(encoding="utf-8"))
        self.assertEqual(expected_header, rows[0])
        for row in rows[1:]:
            self.assertEqual(
                len(expected_header),
                len(row),
                f"misaligned decision row in {decisions}:\n{decisions.read_text(encoding='utf-8')}",
            )
        return rows

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

    def test_source_check_claim_resolves_ops_and_project_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_source_audit(ops_dir)
            artifact = ops_dir / "tasks" / "TASK-3005-claim" / "worker_output.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("Accepted evidence uses DS-0001.\n", encoding="utf-8")

            code, ops_relative = run_cli_json(["source", "check-claim", ops_dir, "tasks/TASK-3005-claim/worker_output.md"])
            self.assertEqual(cli.SUCCESS, code, ops_relative)
            self.assertTrue(ops_relative["ok"])
            self.assertEqual("ops_relative", ops_relative["artifact_resolution"]["resolution"])

            code, project_relative = run_cli_json(["source", "check-claim", ops_dir, "research_ops/tasks/TASK-3005-claim/worker_output.md"])
            self.assertEqual(cli.SUCCESS, code, project_relative)
            self.assertTrue(project_relative["ok"])
            self.assertEqual("project_relative", project_relative["artifact_resolution"]["resolution"])

    def test_source_check_claim_lit_only_recommends_library_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            artifact = ops_dir / "tasks" / "TASK-3006-lit-only" / "worker_output.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("The literature synthesis cites LIT-0001 and LIT-0002.\n", encoding="utf-8")

            code, payload = run_cli_json(["source", "check-claim", ops_dir, artifact])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["applicable"])
            self.assertEqual("source_governance_not_applicable", payload["reason"])
            self.assertEqual(["LIT-0001", "LIT-0002"], payload["library_refs"])
            self.assertIn("library validate", payload["next_step"])

    def test_source_check_claim_respects_rejected_source_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_source_audit_rows(
                ops_dir,
                [
                    "| DS-0001 | Coffee country concentration source | https://example.test/approved | Fixture Publisher | tier_1_official | approved | accepted_evidence; context | none | 365 | none | cite DS-0001 | 2026-05-05 | tests | approved fixture |",
                    "| DS-0002 | Coffee restricted vendor extract | https://example.test/restricted | Vendor | tier_4_untrusted | restricted | none | accepted_evidence | 365 | license prohibits accepted evidence | do not cite as evidence | 2026-05-05 | tests | rejected in coffee pilot |",
                ],
            )
            artifact = ops_dir / "tasks" / "TASK-3007-coffee-source-semantics" / "worker_output.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(
                "\n".join(
                    [
                        "# Coffee source semantics",
                        "",
                        "| source_id | source_use_intent | note |",
                        "| --- | --- | --- |",
                        "| DS-0001 | used_as_evidence | supports the accepted country concentration claim |",
                        "| DS-0002 | rejected_source | rejected because licensing prevents accepted evidence use |",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = run_cli_json(["source", "check-claim", ops_dir, artifact, "--use-case", "accepted_evidence"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(["DS-0001"], payload["gated_source_refs"])
            self.assertEqual([], payload["blocked"])
            self.assertEqual(["DS-0002"], payload["source_refs_by_intent"]["rejected_source"])
            self.assertEqual("rejected_source", payload["non_evidence_source_decisions"][0]["intent"])

    def test_source_check_claim_treats_casual_prose_refs_as_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_source_audit(ops_dir)
            cases = [
                "Background context: DS-0001 confirms the country concentration claim.\n",
                "In the context of coffee markets, DS-0001 provides the price data.\n",
                "Per DS-0001 (a rejected legacy approach was replaced), current data supports the claim.\n",
            ]
            for index, text in enumerate(cases, start=1):
                with self.subTest(text=text):
                    artifact = ops_dir / "tasks" / f"TASK-3010-prose-{index}" / "worker_output.md"
                    artifact.parent.mkdir(parents=True)
                    artifact.write_text(text, encoding="utf-8")

                    code, payload = run_cli_json(["source", "check-claim", ops_dir, artifact, "--use-case", "accepted_evidence"])

                    self.assertEqual(cli.SUCCESS, code, payload)
                    self.assertTrue(payload["ok"])
                    self.assertEqual(["DS-0001"], payload["gated_source_refs"])
                    self.assertEqual(["DS-0001"], payload["source_refs_by_intent"]["used_as_evidence"])
                    self.assertEqual([], payload["non_evidence_source_decisions"])

    def test_explicit_source_intent_table_can_mark_non_evidence_without_prose_downgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_source_audit(ops_dir)
            artifact = ops_dir / "tasks" / "TASK-3011-context-only" / "worker_output.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(
                "\n".join(
                    [
                        "| source_id | source_use_intent | note |",
                        "| --- | --- | --- |",
                        "| DS-0001 | context_only | background context, not accepted evidence |",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = run_cli_json(["source", "check-claim", ops_dir, artifact, "--use-case", "accepted_evidence"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual([], payload["gated_source_refs"])
            self.assertEqual(["DS-0001"], payload["source_refs_by_intent"]["context_only"])

    def test_table_rejected_source_is_not_upgraded_by_casual_prose(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_source_audit(ops_dir)
            artifact = ops_dir / "tasks" / "TASK-3012-table-rejected" / "worker_output.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(
                "\n".join(
                    [
                        "| source_id | source_use_intent | note |",
                        "| --- | --- | --- |",
                        "| DS-0001 | rejected_source | data quality issues |",
                        "",
                        "As noted above, DS-0001 had quality issues so we removed it.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = run_cli_json(["source", "check-claim", ops_dir, artifact, "--use-case", "accepted_evidence"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual([], payload["gated_source_refs"])
            self.assertEqual(["DS-0001"], payload["source_refs_by_intent"]["rejected_source"])

    def test_table_rejected_source_can_be_upgraded_by_explicit_evidence_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_source_audit(ops_dir)
            artifact = ops_dir / "tasks" / "TASK-3013-table-rejected-explicit-evidence" / "worker_output.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(
                "\n".join(
                    [
                        "| source_id | source_use_intent | note |",
                        "| --- | --- | --- |",
                        "| DS-0001 | rejected_source | initial triage was too conservative |",
                        "",
                        "source_use_intent: evidence for DS-0001 after source audit repair.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = run_cli_json(["source", "check-claim", ops_dir, artifact, "--use-case", "accepted_evidence"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(["DS-0001"], payload["gated_source_refs"])
            self.assertEqual(["DS-0001"], payload["source_refs_by_intent"]["used_as_evidence"])

    def test_later_evidence_reference_upgrades_weaker_prior_source_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_source_audit(ops_dir)
            artifact = ops_dir / "tasks" / "TASK-3012-upgrade-intent" / "worker_output.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(
                "\n".join(
                    [
                        "source_use_intent: context_only for DS-0001 as background.",
                        "DS-0001 underpins the accepted memo recommendation.",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, payload = run_cli_json(["source", "check-claim", ops_dir, artifact, "--use-case", "accepted_evidence"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(["DS-0001"], payload["gated_source_refs"])
            self.assertEqual(["DS-0001"], payload["source_refs_by_intent"]["used_as_evidence"])

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

    def test_queue_list_reports_task_board_state_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            ready_task = write_task_status(ops_dir, "TASK-4004", "ready_for_worker")
            human_task = write_task_status(ops_dir, "TASK-4005", "needs_human")
            invalid_task = ops_dir / "tasks" / "TASK-4006-invalid"
            invalid_task.mkdir(parents=True)
            (invalid_task / "status.json").write_text("{}\n", encoding="utf-8")
            daily_status = ops_dir / "daily_status.md"
            before_daily = daily_status.read_text(encoding="utf-8")
            queue_before = (ops_dir / "queue.md").read_text(encoding="utf-8")

            code, payload = run_cli_json(
                ["queue", "list", ops_dir, "--status", "ready_for_worker", "--status", "needs_human", "--limit", "1"]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual("queue_listed", payload["action"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])
            self.assertEqual("all", payload["group"])
            self.assertEqual(2, payload["summary"]["filtered_count"])
            self.assertEqual(1, payload["summary"]["returned_count"])
            self.assertTrue(payload["summary"]["truncated"])
            self.assertEqual(1, payload["summary"]["ready_for_worker_count"])
            self.assertEqual(1, payload["summary"]["human_count"])
            self.assertEqual(1, payload["summary"]["malformed_status_count"])
            self.assertEqual(str(ready_task), payload["tasks"][0]["task_dir"])
            self.assertNotIn("files", payload["tasks"][0])
            self.assertEqual(before_daily, daily_status.read_text(encoding="utf-8"))
            self.assertEqual(queue_before, (ops_dir / "queue.md").read_text(encoding="utf-8"))

            code, payload = run_cli_json(["queue", "list", ops_dir, "--status", "needs_human", "--include-files"])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual(1, payload["summary"]["filtered_count"])
            self.assertEqual(str(human_task), payload["tasks"][0]["task_dir"])
            self.assertEqual("needs_human", payload["tasks"][0]["status"])
            self.assertIn("files", payload["tasks"][0])

    def test_queue_list_refuses_missing_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "missing_ops"

            code, payload = run_cli_json(["queue", "list", ops_dir])

            self.assertEqual(cli.INVALID, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("queue_list_refused", payload["action"])
            self.assertEqual("ops_dir_missing", payload["reason"])

    def test_queue_list_refuses_negative_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))

            code, payload = run_cli_json(["queue", "list", ops_dir, "--limit", "-1"])

            self.assertEqual(cli.INVALID, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("queue_list_refused", payload["action"])
            self.assertEqual("invalid_limit", payload["reason"])

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
            rows = self.assert_decision_table_aligned(decisions, CANONICAL_DECISION_HEADER)
            self.assertEqual("TASK-5001", rows[-1][1])
            self.assertEqual("approve_budget", rows[-1][2])

    def test_decision_append_preserves_legacy_starter_header_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            decisions = ops_dir / "decisions.md"
            decisions.write_text(
                "\n".join(
                    [
                        "# Human Decision Log",
                        "",
                        "| decision_id | item_id | decision | decided_at | decided_by | rationale | follow_up |",
                        "| --- | --- | --- | --- | --- | --- | --- |",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, written = run_cli_json(
                [
                    "decision",
                    "append",
                    ops_dir,
                    "--item-id",
                    "TASK-5004",
                    "--decision",
                    "acknowledge",
                    "--reason",
                    "Legacy starter row stays aligned",
                    "--approver",
                    "test-owner",
                    "--related-artifact",
                    "research_ops/tasks/TASK-5004/status.json",
                    "--date",
                    NOW,
                ]
            )

            self.assertEqual(cli.SUCCESS, code, written)
            rows = self.assert_decision_table_aligned(decisions, LEGACY_STARTER_DECISION_HEADER)
            self.assertEqual("none", rows[-1][0])
            self.assertEqual("TASK-5004", rows[-1][1])
            self.assertEqual("acknowledge", rows[-1][2])
            self.assertEqual(NOW, rows[-1][3])
            self.assertEqual("test-owner", rows[-1][4])
            self.assertEqual("Legacy starter row stays aligned", rows[-1][5])
            parsed = decision_log.read_decisions(decisions)
            self.assertEqual("Legacy starter row stays aligned", parsed[-1]["reason"])

    def test_decision_append_preserves_week_simulation_legacy_header_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            decisions = ops_dir / "decisions.md"
            decisions.write_text(
                "\n".join(
                    [
                        "# Human Decisions",
                        "",
                        "| date | item_id | decision | approver | reason | next_status |",
                        "| --- | --- | --- | --- | --- | --- |",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            code, written = run_cli_json(
                [
                    "decision",
                    "append",
                    ops_dir,
                    "--item-id",
                    "TASK-5005",
                    "--decision",
                    "resume",
                    "--reason",
                    "Week simulation row stays aligned",
                    "--approver",
                    "test-owner",
                    "--related-artifact",
                    "ready_for_worker",
                    "--date",
                    NOW,
                ]
            )

            self.assertEqual(cli.SUCCESS, code, written)
            rows = self.assert_decision_table_aligned(decisions, WEEK_SIMULATION_DECISION_HEADER)
            self.assertEqual([NOW, "TASK-5005", "resume", "test-owner", "Week simulation row stays aligned", "ready_for_worker"], rows[-1])
            parsed = decision_log.read_decisions(decisions)
            self.assertEqual("ready_for_worker", parsed[-1]["related_artifacts"])

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
            status_payload = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            status_payload["human_gate_opened_at"] = "2026-05-01T00:00:00Z"
            (task_dir / "status.json").write_text(json.dumps(status_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
            self.assertEqual(NOW, status["human_gate_opened_at"])

    def test_decision_resolve_task_writes_aligned_row_for_real_estate_starter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp), template="real-estate")
            task_dir = write_task_status(ops_dir, "TASK-5006", "needs_human")
            decisions = ops_dir / "decisions.md"

            code, resolved = run_cli_json(
                [
                    "decision",
                    "resolve-task",
                    ops_dir,
                    task_dir,
                    "--decision",
                    "resume",
                    "--reason",
                    "Real estate fixture can resume",
                    "--approver",
                    "test-owner",
                    "--status",
                    "ready_for_worker",
                    "--date",
                    NOW,
                ]
            )

            self.assertEqual(cli.SUCCESS, code, resolved)
            rows = self.assert_decision_table_aligned(decisions, CANONICAL_DECISION_HEADER)
            self.assertEqual("TASK-5006", rows[-1][1])
            self.assertEqual("resume", rows[-1][2])

            code, summary = run_cli_json(["decision", "summarize", ops_dir, "--month", "2026-05"])
            self.assertEqual(cli.SUCCESS, code, summary)
            self.assertEqual(1, summary["decision_count"])
            self.assertEqual({"resume": 1}, summary["by_decision"])

            code, surface = run_cli_json(["surface", "update", ops_dir])
            self.assertEqual(cli.SUCCESS, code, surface)
            self.assertTrue(surface["ok"], surface)

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

    def test_source_authoring_commands_use_public_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()

            code, initialized = run_cli_json(["source", "init", ops_dir])
            self.assertEqual(cli.SUCCESS, code, initialized)
            self.assertEqual("initialized", initialized["action"])

            code, upserted = run_cli_json(
                [
                    "source",
                    "upsert",
                    ops_dir,
                    "--source-id",
                    "DS-0601",
                    "--approval-status",
                    "approved",
                    "--source-name",
                    "Fixture Source",
                    "--url-or-domain",
                    "https://example.test/source",
                    "--publisher-owner",
                    "Fixture Publisher",
                    "--source-tier",
                    "tier_1_official",
                    "--approved-use-cases",
                    "experiment_planning; accepted_evidence",
                    "--blocked-use-cases",
                    "none",
                    "--freshness-window-days",
                    "365",
                    "--known-limitations",
                    "none",
                    "--citation-requirements",
                    "cite DS-0601",
                    "--last-reviewed",
                    "2026-05-05",
                    "--approved-by",
                    "tests",
                    "--review-notes",
                    "ready fixture",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, upserted)
            self.assertEqual("upserted", upserted["action"])

            code, explained = run_cli_json(["source", "explain", ops_dir, "DS-0601"])
            self.assertEqual(cli.SUCCESS, code, explained)
            self.assertTrue(explained["ok"])
            self.assertEqual("DS-0601", explained["source_id"])

    def test_source_upsert_explains_required_fields_for_new_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()

            code, initialized = run_cli_json(["source", "init", ops_dir])
            self.assertEqual(cli.SUCCESS, code, initialized)

            code, payload = run_cli_json(["source", "upsert", ops_dir, "--source-id", "DS-0602"])

            self.assertEqual(2, code, payload)
            self.assertEqual("audit_validation_failed", payload["reason"])
            self.assertEqual(["--source-name", "--url-or-domain", "--publisher-owner"], payload["required_for_new_source"])
            self.assertIn("--publisher-owner", payload["next_step"])

    def test_source_upsert_reports_fresh_register_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()
            code, initialized = run_cli_json(["source", "init", ops_dir])
            self.assertEqual(cli.SUCCESS, code, initialized)
            lock = data_source_audit.acquire_source_register_lock(ops_dir, "test hold source register")
            try:
                code, payload = run_cli_json(
                    [
                        "source",
                        "upsert",
                        ops_dir,
                        "--source-id",
                        "DS-0603",
                        "--approval-status",
                        "approved",
                        "--source-name",
                        "Locked Fixture Source",
                        "--url-or-domain",
                        "https://example.test/locked",
                        "--publisher-owner",
                        "Fixture Publisher",
                    ]
                )
            finally:
                data_source_audit.release_source_register_lock(lock)

            self.assertEqual(2, code, payload)
            self.assertEqual("source_register_locked", payload["reason"])
            self.assertIn("retry source upsert", payload["next_step"])

    def test_source_init_force_reports_fresh_register_lock_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()
            write_source_audit(ops_dir)
            before = (ops_dir / "data_source_audit.md").read_text(encoding="utf-8")
            lock = data_source_audit.acquire_source_register_lock(ops_dir, "test hold source register")
            try:
                code, payload = run_cli_json(["source", "init", ops_dir, "--force"])
            finally:
                data_source_audit.release_source_register_lock(lock)

            self.assertEqual(2, code, payload)
            self.assertEqual("source_register_locked", payload["reason"])
            self.assertIn("retry source upsert", payload["next_step"])
            self.assertEqual(before, (ops_dir / "data_source_audit.md").read_text(encoding="utf-8"))

    def test_batch_lifecycle_commands_use_public_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            manifest = ops_dir / "batches" / "BATCH-0601" / "batch_manifest.json"

            code, dry = run_cli_json(
                [
                    "batch",
                    "init",
                    ops_dir,
                    "--batch-id",
                    "BATCH-0601",
                    "--input-file",
                    "research_ops/batches/BATCH-0601/input.jsonl",
                    "--prompt-template",
                    "fixture_prompt_v1",
                    "--model",
                    "fixture-model",
                    "--expected-output-schema",
                    "fixture.schema.json",
                    "--ingest-path",
                    "research_ops/batches/BATCH-0601/ingested.jsonl",
                    "--dry-run",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, dry)
            self.assertEqual("dry_run_initialized", dry["action"])
            self.assertFalse(manifest.exists())

            code, written = run_cli_json(
                [
                    "batch",
                    "init",
                    ops_dir,
                    "--batch-id",
                    "BATCH-0601",
                    "--input-file",
                    "research_ops/batches/BATCH-0601/input.jsonl",
                    "--prompt-template",
                    "fixture_prompt_v1",
                    "--model",
                    "fixture-model",
                    "--expected-output-schema",
                    "fixture.schema.json",
                    "--ingest-path",
                    "research_ops/batches/BATCH-0601/ingested.jsonl",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, written)
            self.assertTrue(manifest.exists())

            code, valid = run_cli_json(["batch", "validate-manifest", manifest])
            self.assertEqual(cli.SUCCESS, code, valid)
            self.assertEqual("draft", valid["lifecycle_status"])

            code, trust = run_cli_json(["batch", "trust-status", manifest])
            self.assertEqual(2, code, trust)
            self.assertFalse(trust["trusted"])

    def test_batch_write_dry_runs_preserve_manifest_and_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            manifest = ops_dir / "batches" / "BATCH-0605" / "batch_manifest.json"
            ledger = ops_dir / "cost_ledger.csv"
            code, initialized = run_cli_json(
                [
                    "batch",
                    "init",
                    ops_dir,
                    "--batch-id",
                    "BATCH-0605",
                    "--input-file",
                    "research_ops/batches/BATCH-0605/input.jsonl",
                    "--prompt-template",
                    "fixture_prompt_v1",
                    "--model",
                    "fixture-model",
                    "--expected-output-schema",
                    "fixture.schema.json",
                    "--ingest-path",
                    "research_ops/batches/BATCH-0605/ingested.jsonl",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, initialized)

            manifest_before = manifest.read_text(encoding="utf-8")
            ledger_before = ledger.read_text(encoding="utf-8")
            code, submit_dry = run_cli_json(
                [
                    "batch",
                    "submit",
                    manifest,
                    "--provider-batch-id",
                    "provider-batch-0605",
                    "--api-usd",
                    "1.25",
                    "--compute-usd",
                    "0.50",
                    "--dry-run",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, submit_dry)
            self.assertEqual("dry_run_submitted", submit_dry["action"])
            self.assertEqual(manifest_before, manifest.read_text(encoding="utf-8"))
            self.assertEqual(ledger_before, ledger.read_text(encoding="utf-8"))

            code, submitted = run_cli_json(
                [
                    "batch",
                    "submit",
                    manifest,
                    "--provider-batch-id",
                    "provider-batch-0605",
                    "--api-usd",
                    "1.25",
                    "--compute-usd",
                    "0.50",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, submitted)
            self.assertEqual("submitted", submitted["action"])

            manifest_before = manifest.read_text(encoding="utf-8")
            code, complete_dry = run_cli_json(
                [
                    "batch",
                    "complete",
                    manifest,
                    "--output-file",
                    "research_ops/batches/BATCH-0605/provider_output.jsonl",
                    "--dry-run",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, complete_dry)
            self.assertEqual("dry_run_completed", complete_dry["action"])
            self.assertEqual(manifest_before, manifest.read_text(encoding="utf-8"))

            code, completed = run_cli_json(
                [
                    "batch",
                    "complete",
                    manifest,
                    "--output-file",
                    "research_ops/batches/BATCH-0605/provider_output.jsonl",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, completed)
            self.assertEqual("completed", completed["action"])

            manifest_before = manifest.read_text(encoding="utf-8")
            code, ingest_dry = run_cli_json(
                [
                    "batch",
                    "ingest",
                    manifest,
                    "--ingest-task-id",
                    "TASK-0605",
                    "--ingested-file",
                    "research_ops/batches/BATCH-0605/ingested.jsonl",
                    "--dry-run",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, ingest_dry)
            self.assertEqual("dry_run_ingested", ingest_dry["action"])
            self.assertEqual(manifest_before, manifest.read_text(encoding="utf-8"))

            code, ingested = run_cli_json(
                [
                    "batch",
                    "ingest",
                    manifest,
                    "--ingest-task-id",
                    "TASK-0605",
                    "--ingested-file",
                    "research_ops/batches/BATCH-0605/ingested.jsonl",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, ingested)
            self.assertEqual("ingested", ingested["action"])

            manifest_before = manifest.read_text(encoding="utf-8")
            code, reviewed_dry = run_cli_json(
                [
                    "batch",
                    "mark-reviewed",
                    manifest,
                    "--review-task-id",
                    "TASK-0606",
                    "--dry-run",
                ]
            )
            self.assertEqual(cli.SUCCESS, code, reviewed_dry)
            self.assertEqual("dry_run_reviewed", reviewed_dry["action"])
            self.assertEqual(manifest_before, manifest.read_text(encoding="utf-8"))

    def test_anti_context_build_writes_task_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            write_accepted_index(ops_dir)
            task_dir = ops_dir / "tasks" / "TASK-0602-anti-context"
            task_dir.mkdir(parents=True)

            code, payload = run_cli_json(
                [
                    "anti-context",
                    "build",
                    ops_dir,
                    "--title",
                    "Old evidence follow-up",
                    "--task-dir",
                    task_dir,
                ]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue((task_dir / "anti_context.md").exists())
            self.assertIn("Cross-Task Anti-Context", (task_dir / "task.md").read_text(encoding="utf-8"))

    def test_review_context_prepare_and_install_use_public_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task_status(ops_dir, "TASK-0603", "awaiting_review")
            write_clear_task_contract(task_dir)
            (task_dir / "worker_output.md").write_text("Fixture output.\n", encoding="utf-8")
            (task_dir / "reviews").mkdir()
            (task_dir / "reviews" / "methodology.md").write_text("Existing sibling review.\n", encoding="utf-8")
            bundle_dir = Path(tmp) / "review-bundle"

            code, prepared = run_cli_json(
                [
                    "review",
                    "prepare-context",
                    task_dir,
                    "--role",
                    "primary",
                    "--bundle-dir",
                    bundle_dir,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, prepared)
            self.assertFalse((bundle_dir / "input" / "reviews").exists())

            output = bundle_dir / "output" / "reviews" / "primary.md"
            scaffold = output.read_text(encoding="utf-8")
            self.assertIn("```json", scaffold)
            self.assertIn('"reviewer_role": "primary"', scaffold)
            self.assertIn('"decision": "needs_human"', scaffold)
            output.write_text("Primary review fixture.\n", encoding="utf-8")
            code, installed = run_cli_json(["review", "install-context", bundle_dir])
            self.assertEqual(cli.SUCCESS, code, installed)
            self.assertTrue((task_dir / "reviews" / "primary.md").exists())

    def test_revision_request_dry_run_and_write_use_public_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            task_dir = write_task_status(ops_dir, "TASK-0604", "single_review")
            before = (task_dir / "status.json").read_text(encoding="utf-8")

            code, dry = run_cli_json(["revision", "request", task_dir, "--reviewer", "primary", "--dry-run"])
            self.assertEqual(cli.SUCCESS, code, dry)
            self.assertEqual("dry_run_revision_request", dry["action"])
            self.assertEqual(before, (task_dir / "status.json").read_text(encoding="utf-8"))

            code, applied = run_cli_json(["revision", "request", task_dir, "--reviewer", "primary"])
            self.assertEqual(cli.SUCCESS, code, applied)
            self.assertEqual("revision_request_applied", applied["action"])
            status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual("needs_revision", status["status"])
            self.assertEqual(1, status["revision_count"])


if __name__ == "__main__":
    unittest.main()

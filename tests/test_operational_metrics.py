"""Tests for the operational metrics read model."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from async_research_workflow import cli


NOW = "2026-05-11T12:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict[str, Any]]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_status(
    ops_dir: Path,
    task_id: str,
    status: str,
    *,
    created_at: str | None = "2026-05-01T00:00:00Z",
    updated_at: str | None = "2026-05-05T00:00:00Z",
    review_started_at: str | None = None,
    human_gate_opened_at: str | None = None,
    previous_status: str | None = None,
    tier: int = 1,
    revision_count: int = 0,
    max_revisions: int = 3,
    revision_limit_hit: bool = False,
    requires_human: bool = False,
) -> Path:
    task_dir = ops_dir / "tasks" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "id": task_id,
        "title": f"{task_id} fixture",
        "type": "admin",
        "status": status,
        "previous_status": previous_status,
        "last_transition_reason": "fixture",
        "priority": 2,
        "review_policy": {"tier": tier},
        "revision_count": revision_count,
        "max_revisions": max_revisions,
        "revision_limit_hit": revision_limit_hit,
        "allowed_paths": [f"research_ops/tasks/{task_id}/**"],
        "max_minutes": 10,
        "requires_human": requires_human,
        "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
    }
    if created_at is not None:
        payload["created_at"] = created_at
    if updated_at is not None:
        payload["updated_at"] = updated_at
    if review_started_at is not None:
        payload["review_started_at"] = review_started_at
    if human_gate_opened_at is not None:
        payload["human_gate_opened_at"] = human_gate_opened_at
    (task_dir / "status.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return task_dir


def write_cost_ledger(ops_dir: Path) -> None:
    with (ops_dir / "cost_ledger.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "item_id", "amount_usd", "human_minutes"])
        writer.writeheader()
        writer.writerow({"date": "2026-05-04", "item_id": "TASK-1001", "amount_usd": "30", "human_minutes": "0"})
        writer.writerow({"date": "2026-05-05", "item_id": "TASK-1002", "amount_usd": "15", "human_minutes": "0"})
        writer.writerow({"date": "2026-05-06", "item_id": "unmapped", "amount_usd": "5", "human_minutes": "0"})


def write_decisions(ops_dir: Path) -> None:
    (ops_dir / "decisions.md").write_text(
        "\n".join(
            [
                "| date | item_id | decision | reason | approver | related_artifacts |",
                "| --- | --- | --- | --- | --- | --- |",
                "| 2026-05-10T00:00:00Z | TASK-1006 | resume | fixture | test | none |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def file_fingerprint(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class OperationalMetricsTests(unittest.TestCase):
    def test_operational_metrics_report_latency_costs_and_revision_trends_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()
            write_status(
                ops_dir,
                "TASK-1001",
                "accepted",
                created_at="2026-05-01T00:00:00Z",
                updated_at="2026-05-04T12:00:00Z",
                review_started_at="2026-05-03T00:00:00Z",
                tier=2,
                revision_count=1,
            )
            write_status(
                ops_dir,
                "TASK-1002",
                "rejected",
                created_at="2026-05-02T00:00:00Z",
                updated_at="2026-05-05T12:00:00Z",
                review_started_at="2026-05-03T12:00:00Z",
                tier=3,
                revision_count=2,
                max_revisions=2,
            )
            write_status(
                ops_dir,
                "TASK-1003",
                "awaiting_review",
                created_at="2026-05-10T00:00:00Z",
                updated_at="2026-05-10T12:00:00Z",
                tier=1,
            )
            write_status(
                ops_dir,
                "TASK-1004",
                "needs_human",
                created_at="2026-05-09T00:00:00Z",
                updated_at="2026-05-10T00:00:00Z",
                human_gate_opened_at="2026-05-10T00:00:00Z",
                tier=2,
                requires_human=True,
            )
            write_status(
                ops_dir,
                "TASK-1005",
                "needs_human",
                created_at="2026-05-09T00:00:00Z",
                updated_at=None,
                tier=2,
                requires_human=True,
            )
            write_status(
                ops_dir,
                "TASK-1006",
                "ready_for_worker",
                created_at="2026-05-09T00:00:00Z",
                updated_at="2026-05-10T12:00:00Z",
                human_gate_opened_at="2026-05-09T12:00:00Z",
                previous_status="needs_human",
                tier=1,
            )
            write_cost_ledger(ops_dir)
            write_decisions(ops_dir)
            before = file_fingerprint(ops_dir)

            code, payload = run_cli_json(["metrics", "operational", ops_dir, "--now", NOW])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual("operational_metrics_reported", payload["action"])
            self.assertEqual(before, file_fingerprint(ops_dir))

            model = payload["read_model"]
            self.assertEqual(6, model["task_count"])
            self.assertEqual(24.0, model["time_in_state"]["awaiting_review"]["average_hours"])
            self.assertEqual(2, model["time_in_state"]["needs_human"]["item_count"])
            self.assertEqual(1, model["time_in_state"]["needs_human"]["available_count"])
            self.assertEqual(1, model["time_in_state"]["needs_human"]["unavailable_count"])
            self.assertEqual(36.0, model["time_in_state"]["needs_human"]["average_hours"])
            missing_items = [
                item
                for item in model["time_in_state"]["needs_human"]["items"]
                if item["task_id"] == "TASK-1005"
            ]
            self.assertEqual("unavailable", missing_items[0]["age_hours"])

            self.assertEqual(24.0, model["review_latency"]["by_tier"]["1"]["average_hours"])
            self.assertEqual(36.0, model["review_latency"]["by_tier"]["2"]["average_hours"])
            self.assertEqual(48.0, model["review_latency"]["by_tier"]["3"]["average_hours"])
            self.assertEqual(84.0, model["promotion_to_terminal"]["by_status"]["accepted"]["average_hours"])
            self.assertEqual(84.0, model["promotion_to_terminal"]["by_status"]["rejected"]["average_hours"])
            self.assertEqual(1, model["human_decision_latency"]["decision_log_rows"])
            self.assertEqual(12.0, model["human_decision_latency"]["resolved"]["average_hours"])

            self.assertEqual("available", model["cost"]["status"])
            self.assertEqual(50.0, model["cost"]["total_cost_usd"])
            self.assertEqual(30.0, model["cost"]["cost_per_accepted_output_usd"])
            self.assertEqual(15.0, model["cost"]["cost_per_rejected_output_usd"])
            self.assertEqual(5.0, model["cost"]["unmapped_cost_usd"])
            self.assertEqual(3, model["revision_loops"]["total_revision_loops"])
            self.assertEqual(1, model["revision_loops"]["revision_limit_hit_count"])
            self.assertEqual([], payload["warnings"])

    def test_missing_timestamps_and_cost_ledger_render_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()
            write_status(ops_dir, "TASK-1001", "accepted", created_at=None, updated_at=None)

            code, payload = run_cli_json(["metrics", "operational", ops_dir, "--now", NOW])

            self.assertEqual(cli.SUCCESS, code, payload)
            model = payload["read_model"]
            self.assertEqual("unavailable", model["promotion_to_terminal"]["all"]["average_hours"])
            self.assertEqual("unavailable", model["cost"]["status"])
            self.assertEqual("unavailable", model["cost"]["cost_per_accepted_output_usd"])

    def test_malformed_status_warns_but_keeps_read_model_consumable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            bad_task = ops_dir / "tasks" / "TASK-bad"
            bad_task.mkdir(parents=True)
            (bad_task / "status.json").write_text("{", encoding="utf-8")

            code, payload = run_cli_json(["metrics", "operational", ops_dir, "--now", NOW])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual(0, payload["read_model"]["task_count"])
            self.assertEqual("status_json_malformed", payload["warnings"][0]["reason"])

    def test_schema_invalid_status_warns_and_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()
            write_status(ops_dir, "TASK-1001", "accepted")
            write_status(ops_dir, "TASK-1002", "bogus")

            code, payload = run_cli_json(["metrics", "operational", ops_dir, "--now", NOW])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual(1, payload["read_model"]["task_count"])
            self.assertEqual({"accepted": 1}, payload["read_model"]["status_counts"])
            warning = payload["warnings"][0]
            self.assertEqual("status_schema_invalid", warning["reason"])
            self.assertIn("$.status", {error["path"] for error in warning["errors"]})

    def test_partial_or_malformed_cost_coverage_keeps_per_output_cost_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()
            write_status(ops_dir, "TASK-1001", "accepted")
            write_status(ops_dir, "TASK-1002", "accepted")
            write_status(ops_dir, "TASK-1003", "rejected")
            with (ops_dir / "cost_ledger.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["date", "item_id", "amount_usd"])
                writer.writeheader()
                writer.writerow({"date": "2026-05-04", "item_id": "TASK-1001", "amount_usd": "30"})
                writer.writerow({"date": "2026-05-05", "item_id": "TASK-1003", "amount_usd": "not-a-number"})

            code, payload = run_cli_json(["metrics", "operational", ops_dir, "--now", NOW])

            self.assertEqual(cli.SUCCESS, code, payload)
            cost = payload["read_model"]["cost"]
            self.assertEqual("unavailable", cost["total_cost_usd"])
            self.assertEqual(30.0, cost["known_total_cost_usd"])
            self.assertEqual(1, cost["malformed_cost_row_count"])
            self.assertEqual(2, cost["accepted_output_count"])
            self.assertEqual(1, cost["accepted_output_matched_count"])
            self.assertEqual(1, cost["accepted_output_unmatched_count"])
            self.assertEqual(["TASK-1002"], cost["accepted_output_unmatched_ids"])
            self.assertEqual("unavailable", cost["cost_per_accepted_output_usd"])
            self.assertEqual(1, cost["rejected_output_malformed_cost_row_count"])
            self.assertEqual("unavailable", cost["cost_per_rejected_output_usd"])
            self.assertEqual("cost_ledger_amount_unavailable", payload["warnings"][0]["reason"])

    def test_backwards_timestamp_ranges_are_unavailable_not_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            ops_dir.mkdir()
            write_status(
                ops_dir,
                "TASK-1001",
                "accepted",
                created_at="2026-05-10T00:00:00Z",
                updated_at="2026-05-09T00:00:00Z",
                review_started_at="2026-05-11T00:00:00Z",
            )

            code, payload = run_cli_json(["metrics", "operational", ops_dir, "--now", NOW])

            self.assertEqual(cli.SUCCESS, code, payload)
            review_item = payload["read_model"]["review_latency"]["all"]["items"][0]
            terminal_item = payload["read_model"]["promotion_to_terminal"]["all"]["items"][0]
            self.assertEqual("unavailable", review_item["latency_hours"])
            self.assertEqual("backwards_timestamp_range", review_item["unavailable_reason"])
            self.assertEqual("unavailable", terminal_item["latency_hours"])
            self.assertEqual("backwards_timestamp_range", terminal_item["unavailable_reason"])

    def test_invalid_now_and_missing_workspace_fail_with_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "missing"

            code, payload = run_cli_json(["metrics", "operational", ops_dir, "--now", "not-a-date"])
            self.assertEqual(3, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("invalid_now", payload["reason"])

            code, payload = run_cli_json(["metrics", "operational", ops_dir, "--now", NOW])
            self.assertEqual(4, code, payload)
            self.assertFalse(payload["ok"])
            self.assertEqual("workspace_missing", payload["reason"])


if __name__ == "__main__":
    unittest.main()

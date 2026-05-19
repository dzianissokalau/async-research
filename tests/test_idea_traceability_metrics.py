"""Regression tests for idea traceability and lifecycle metrics."""

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


NOW = "2026-05-10T00:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict[str, Any]]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def valid_score(blocked: bool = False) -> dict[str, Any]:
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
                "gate": "data_readiness",
                "passed": not blocked,
                "reason": "fixture gate",
            }
        ],
        "score_explanation": "Fixture score for idea traceability tests.",
    }


def candidate(
    idea_id: str,
    *,
    status: str = "candidate",
    created_at: str | None = "2026-05-01T00:00:00Z",
    updated_at: str | None = "2026-05-01T00:00:00Z",
    blocked: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "id": idea_id,
        "status": status,
        "title": f"Traceability fixture {idea_id}",
        "question": "Can this fixture idea be followed into task outputs?",
        "why_it_might_matter": "It checks lifecycle trace read models.",
        "required_data": ["fixture data"],
        "minimum_viable_test": "Run a bounded fixture check.",
        "baseline": "Compare against a fixture baseline.",
        "main_risks": ["fixture risk"],
        "kill_reason": "Reject if fixture evidence is unavailable.",
        "score": valid_score(blocked=blocked),
        "recommended_next_task": "data_readiness",
        "data_refs": ["DS-0001"],
    }
    if created_at is not None:
        payload["created_at"] = created_at
    if updated_at is not None:
        payload["updated_at"] = updated_at
    return payload


def write_audited_source(ops_dir: Path) -> None:
    write_text(
        ops_dir / "data_source_audit.md",
        "\n".join(
            [
                "# Data Source Audit",
                "",
                "| source_id | source_name | url_or_domain | publisher_owner | source_tier | approval_status | approved_use_cases | prohibited_use_cases | freshness_window_days | limitations | citation_requirements | last_reviewed_at | approved_by | review_notes |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- |",
                "| DS-0001 | Fixture source | https://example.test | Fixture | tier_1_official | approved | experiment_planning; accepted_evidence | none | 30 | none | cite fixture | 2026-05-07 | tests | ready |",
                "",
            ]
        ),
    )


def status_payload(
    task_id: str,
    *,
    status: str,
    idea_id: str,
    created_at: str,
    updated_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "id": task_id,
        "title": f"{task_id} trace fixture",
        "type": "data_readiness",
        "status": status,
        "previous_status": "panel_review" if status in {"accepted", "rejected"} else None,
        "last_transition_reason": "fixture",
        "priority": 2,
        "revision_count": 0,
        "max_revisions": 1,
        "revision_limit_hit": False,
        "allowed_paths": [f"research_ops/tasks/{task_id}/**"],
        "max_minutes": 10,
        "requires_human": False,
        "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
        "created_at": created_at,
        "updated_at": updated_at,
        "catalog_idea_id": idea_id,
        "origin_idea_id": idea_id,
        "promotion_route": "data_readiness",
        "routing_reason": "fixture",
        "promotion_preflight_hash": "f" * 64,
        "promotion_transaction_id": f"PROMO-TX-20260503T000000-{idea_id}-{'f' * 12}",
        "catalog_promotion": {
            "catalog_idea_id": idea_id,
            "origin_idea_id": idea_id,
            "idempotency_key": f"{idea_id}:data_readiness:{'f' * 64}",
            "reserved_task_id": task_id,
            "reservation_policy": "test",
        },
    }


def write_task_status(
    ops_dir: Path,
    task_id: str,
    *,
    status: str,
    idea_id: str,
    created_at: str,
    updated_at: str,
) -> Path:
    task_dir = ops_dir / "tasks" / f"{task_id}-data-readiness"
    write_json(task_dir / "status.json", status_payload(task_id, status=status, idea_id=idea_id, created_at=created_at, updated_at=updated_at))
    return task_dir


def write_accepted_outputs(ops_dir: Path, *rows: tuple[str, str, str]) -> None:
    lines = [
        "| accepted_date | task_id | title | key_finding | claim_type | freshness_window_days | next_recheck_date | revalidation_status | source_ids | claim_strength | caveats | followups | supersedes | superseded_by | evidence_link |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for accepted_date, task_id, title in rows:
        lines.append(
            f"| {accepted_date} | {task_id} | {title} | fixture | source_data_readiness | 30 | 2026-06-01 | current | DS-0001 | moderate | none | none | none | none | tasks/{task_id}-data-readiness/worker_output.md |"
        )
    write_text(ops_dir / "accepted_outputs_index.md", "\n".join(lines) + "\n")


def write_cost_ledger(ops_dir: Path, rows: list[tuple[str, str]]) -> None:
    with (ops_dir / "cost_ledger.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "item_id", "amount_usd"])
        writer.writeheader()
        for item_id, amount in rows:
            writer.writerow({"date": "2026-05-04", "item_id": item_id, "amount_usd": amount})


class IdeaTraceabilityMetricsTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        write_audited_source(ops_dir)
        return ops_dir

    def test_promotion_write_persists_trace_metadata_and_trace_reports_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            idea = candidate("IDEA-7601", status="promote", updated_at="2026-05-02T00:00:00Z")
            idea["decision_history"] = [
                {
                    "at": "2026-05-02T00:00:00Z",
                    "from_status": "candidate",
                    "to_status": "promote",
                    "reason": "ready for fixture promotion",
                    "actor": "test",
                }
            ]
            write_json(ops_dir / "ideas" / "IDEA-7601.json", idea)

            code, dry_run = run_cli_json(["idea", "promote", ops_dir, "IDEA-7601", "--dry-run"])
            self.assertEqual(cli.SUCCESS, code, dry_run)
            code, written = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7601", "--write", "--preflight-hash", dry_run["promotion_preflight_hash"]]
            )
            self.assertEqual(cli.SUCCESS, code, written)

            status_path = Path(written["task_dir"]) / "status.json"
            task_status = read_json(status_path)
            self.assertEqual("IDEA-7601", task_status["origin_idea_id"])
            self.assertEqual(idea["score"], task_status["promotion_score_snapshot"])
            self.assertEqual("data_readiness", task_status["promotion_route"])
            self.assertEqual("catalog_recommended_next_task", task_status["routing_reason"])
            self.assertEqual([], task_status["blocker_snapshot"])
            self.assertEqual(dry_run["promotion_preflight_hash"], task_status["promotion_preflight_hash"])
            self.assertEqual(written["transaction_id"], task_status["promotion_transaction_id"])
            self.assertEqual("IDEA-7601", task_status["catalog_promotion"]["origin_idea_id"])

            task_status["created_at"] = "2026-05-03T00:00:00Z"
            task_status["updated_at"] = "2026-05-04T00:00:00Z"
            task_status["status"] = "accepted"
            task_status["previous_status"] = "panel_review"
            write_json(status_path, task_status)
            write_accepted_outputs(ops_dir, ("2026-05-04", "TASK-7601", "Accepted trace fixture"))
            before = file_snapshot(ops_dir)

            code, trace = run_cli_json(["idea", "trace", ops_dir, "IDEA-7601", "--now", NOW])

            self.assertEqual(cli.SUCCESS, code, trace)
            self.assertTrue(trace["read_only"])
            self.assertFalse(trace["changed"])
            self.assertEqual(before, file_snapshot(ops_dir))
            self.assertEqual("TASK-7601", trace["linked_tasks"][0]["task_id"])
            self.assertEqual("accepted", trace["linked_tasks"][0]["status"])
            self.assertEqual("TASK-7601", trace["queue_rows"][0]["task_id"])
            self.assertEqual("IDEA-7601", trace["queue_rows"][0]["origin_idea_id"])
            self.assertEqual(trace["queue_rows"], trace["linked_tasks"][0]["queue_rows"])
            events = {item["event"] for item in trace["timeline"]}
            self.assertIn("task_created", events)
            self.assertIn("task_accepted", events)
            self.assertIn("accepted_output_indexed", events)
            self.assertEqual(24.0, trace["durations"]["candidate_to_promote"]["duration_hours"])
            self.assertEqual(24.0, trace["durations"]["promote_to_task_creation"]["duration_hours"])
            self.assertEqual(24.0, trace["durations"]["task_creation_to_terminal_output"]["duration_hours"])

    def test_metrics_cover_lifecycle_states_cost_and_missing_timestamps_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))

            accepted = candidate("IDEA-7601", status="promoted", updated_at="2026-05-03T00:00:00Z")
            accepted["promoted_task_id"] = "TASK-7601"
            accepted["decision_history"] = [
                {"at": "2026-05-02T00:00:00Z", "from_status": "candidate", "to_status": "promote", "reason": "fixture", "actor": "test"},
                {"at": "2026-05-03T00:00:00Z", "from_status": "promote", "to_status": "promoted", "reason": "fixture", "actor": "test"},
            ]
            write_json(ops_dir / "ideas" / "IDEA-7601.json", accepted)
            write_task_status(
                ops_dir,
                "TASK-7601",
                status="accepted",
                idea_id="IDEA-7601",
                created_at="2026-05-03T00:00:00Z",
                updated_at="2026-05-04T00:00:00Z",
            )

            rejected = candidate("IDEA-7602", status="promoted", updated_at="2026-05-03T00:00:00Z")
            rejected["promoted_task_id"] = "TASK-7602"
            rejected["decision_history"] = accepted["decision_history"]
            write_json(ops_dir / "ideas" / "IDEA-7602.json", rejected)
            write_task_status(
                ops_dir,
                "TASK-7602",
                status="rejected",
                idea_id="IDEA-7602",
                created_at="2026-05-03T00:00:00Z",
                updated_at="2026-05-06T00:00:00Z",
            )

            parked = candidate("IDEA-7603", status="park", updated_at="2026-05-07T00:00:00Z")
            parked["decision_history"] = [
                {"at": "2026-05-07T00:00:00Z", "from_status": "candidate", "to_status": "park", "reason": "fixture", "actor": "test"}
            ]
            parked["revisit_condition"] = "after fixture data exists"
            write_json(ops_dir / "ideas" / "IDEA-7603.json", parked)

            idea_rejected = candidate("IDEA-7604", status="reject", updated_at="2026-05-08T00:00:00Z")
            idea_rejected["decision_history"] = [
                {"at": "2026-05-08T00:00:00Z", "from_status": "candidate", "to_status": "reject", "reason": "fixture", "actor": "test"}
            ]
            idea_rejected["revisit_condition"] = "Reopen only if a human records a new fixture reason."
            write_json(ops_dir / "ideas" / "IDEA-7604.json", idea_rejected)
            write_json(ops_dir / "ideas" / "IDEA-7605.json", candidate("IDEA-7605", status="promote", created_at=None, updated_at=None))
            duplicate = candidate("IDEA-7606")
            duplicate["duplicate_status"] = "near_duplicate"
            write_json(ops_dir / "ideas" / "IDEA-7606.json", duplicate)
            write_json(ops_dir / "ideas" / "IDEA-7607.json", candidate("IDEA-7607", blocked=True))
            write_accepted_outputs(ops_dir, ("2026-05-04", "TASK-7601", "Accepted trace fixture"))
            write_cost_ledger(ops_dir, [("TASK-7601", "20"), ("TASK-7602", "5")])
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(["idea", "metrics", ops_dir, "--now", NOW])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])
            self.assertEqual(before, file_snapshot(ops_dir))
            model = payload["read_model"]
            self.assertEqual(7, model["idea_count"])
            self.assertEqual(1, model["traceability"]["accepted_promoted_idea_count"])
            self.assertEqual(1, model["traceability"]["rejected_promoted_idea_count"])
            self.assertEqual(2, model["lifecycle_durations"]["candidate_to_promote"]["available_count"])
            parked_age = model["lifecycle_durations"]["parked_idea_age"]["items"][0]
            self.assertEqual("IDEA-7603", parked_age["idea_id"])
            self.assertEqual(72.0, parked_age["duration_hours"])
            missing = [
                item
                for item in model["lifecycle_durations"]["capture_to_candidate"]["items"]
                if item["idea_id"] == "IDEA-7605"
            ][0]
            self.assertEqual("unavailable", missing["duration_hours"])
            self.assertEqual("missing_timestamp", missing["unavailable_reason"])
            self.assertEqual(1, model["duplicate_rate"]["duplicate_or_near_duplicate_count"])
            self.assertEqual(round(1 / 7, 4), model["duplicate_rate"]["rate"])
            self.assertEqual(1, model["blocker_frequency"]["blockers"]["data_readiness"])
            cost = model["cost_per_accepted_promoted_idea"]
            self.assertEqual("available", cost["status"])
            self.assertEqual(20.0, cost["cost_per_accepted_promoted_idea_usd"])


if __name__ == "__main__":
    unittest.main()

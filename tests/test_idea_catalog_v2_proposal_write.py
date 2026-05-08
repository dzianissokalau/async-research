"""Regression tests for V2 promotion write mode and recovery hardening."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from async_research_workflow import cli
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


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def file_snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
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
        "hard_gate_results": [{"gate": "research_question_present", "passed": True, "reason": "question is present"}],
        "score_explanation": "Fixture score for catalog V2.2 proposal write tests.",
    }


def promotable_candidate(candidate_id: str, title: str = "Promotable proposal write idea") -> dict:
    return {
        "schema_version": "1.0",
        "id": candidate_id,
        "status": "promote",
        "title": title,
        "question": "Can the fixture idea be validated cheaply?",
        "why_it_might_matter": "It checks catalog promotion proposal write behavior.",
        "required_data": ["public fixture data"],
        "minimum_viable_test": "Run a bounded data-readiness check.",
        "baseline": "Compare against a simple baseline.",
        "main_risks": ["fixture risk"],
        "kill_reason": "Reject if fixture data is unavailable.",
        "score": valid_score(),
        "recommended_next_task": "data_readiness",
    }


class IdeaCatalogV2ProposalWriteTests(unittest.TestCase):
    def init_ops(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        code, payload = run_cli_json(["init", ops_dir, "--force"])
        self.assertEqual(cli.SUCCESS, code, payload)
        return ops_dir

    def write_audited_source(self, ops_dir: Path, source_id: str = "DS-0001") -> None:
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

    def write_promotable_idea(self, ops_dir: Path, idea_id: str = "IDEA-7401") -> dict:
        candidate = promotable_candidate(idea_id, "Audited proposal write idea")
        candidate["data_refs"] = ["DS-0001"]
        write_json(ops_dir / "ideas" / f"{idea_id}.json", candidate)
        return candidate

    def write_catalog_lock(
        self,
        ops_dir: Path,
        started_at: str = "2099-01-01T00:00:00Z",
        expires_at: str = "2099-01-01T00:30:00Z",
    ) -> Path:
        lock_dir = ops_dir / "ideas" / "LOCK"
        write_json(
            lock_dir / "owner.json",
            {
                "command": "test",
                "pid": 123,
                "started_at": started_at,
                "lock_expires_at": expires_at,
            },
        )
        return lock_dir

    def dry_run_hash(self, ops_dir: Path, idea_id: str, *extra: str) -> tuple[str, dict]:
        code, payload = run_cli_json(["idea", "promote", ops_dir, idea_id, "--dry-run", *extra])
        self.assertEqual(cli.SUCCESS, code, payload)
        return payload["promotion_preflight_hash"], payload

    def test_write_appends_inbox_creates_task_queue_and_updates_idea(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir)
            catalog_path = ops_dir / "ideas" / "idea_catalog.md"
            write_text(catalog_path, catalog_path.read_text(encoding="utf-8") + "\nManual planner note stays here.\n")
            preflight_hash, dry_run = self.dry_run_hash(ops_dir, "IDEA-7401")

            code, payload = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7401", "--write", "--preflight-hash", preflight_hash]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("idea_promotion_task_written", payload["action"])
            self.assertFalse(payload["dry_run"])
            self.assertEqual(preflight_hash, payload["promotion_preflight_hash"])
            self.assertEqual(dry_run["idempotency_key"], payload["idempotency_key"])
            self.assertTrue(payload["validation"]["ok"])
            self.assertEqual(0, payload["validation"]["failure_count"])

            proposal_ref = payload["proposal_ref"]
            self.assertEqual("task_written", proposal_ref["status"])
            self.assertEqual("TASK-7401", payload["task_id"])
            self.assertEqual("TASK-7401", proposal_ref["task_id"])
            self.assertEqual("queue.md#TASK-7401", proposal_ref["queue_ref"])
            inbox = (ops_dir / "inbox.md").read_text(encoding="utf-8")
            self.assertIn(proposal_ref["proposal_id"], inbox)
            self.assertIn(proposal_ref["transaction_id"], inbox)
            self.assertIn(proposal_ref["idempotency_key"], inbox)
            queue = (ops_dir / "queue.md").read_text(encoding="utf-8")
            self.assertIn("[TASK-7401](tasks/TASK-7401-data-readiness/task.md)", queue)
            self.assertIn(proposal_ref["transaction_id"], queue)
            self.assertIn(proposal_ref["idempotency_key"], queue)
            task_dir = Path(payload["task_dir"])
            self.assertTrue((task_dir / "task.md").exists())
            self.assertTrue((task_dir / "status.json").exists())
            status_json = read_json(task_dir / "status.json")
            self.assertEqual("TASK-7401", status_json["id"])
            self.assertEqual("inbox", status_json["status"])
            self.assertIsNone(status_json["previous_status"])
            self.assertEqual("catalog_promotion_task_created", status_json["last_transition_reason"])
            self.assertIn("research_ops/data/**", status_json["allowed_paths"])
            self.assertEqual("IDEA-7401", status_json["catalog_idea_id"])
            self.assertEqual(proposal_ref["transaction_id"], status_json["catalog_promotion"]["transaction_id"])
            self.assertEqual(proposal_ref["idempotency_key"], status_json["catalog_promotion"]["idempotency_key"])
            self.assertIn("planner", status_json["prompt_versions"])
            task_text = (task_dir / "task.md").read_text(encoding="utf-8")
            self.assertIn("Profile draft or update", task_text)
            self.assertIn("Recommended audit status", task_text)
            self.assertIn("Access check result", task_text)
            self.assertIn("async-research data validate", task_text)
            self.assertIn("Manual planner note stays here.", catalog_path.read_text(encoding="utf-8"))

            updated = read_json(ops_dir / "ideas" / "IDEA-7401.json")
            self.assertEqual("promoted", updated["status"])
            self.assertEqual("TASK-7401", updated["promoted_task_id"])
            self.assertEqual(proposal_ref["proposal_id"], updated["latest_promotion_proposal_id"])
            self.assertEqual([proposal_ref], updated["promotion_proposal_refs"])
            self.assertTrue(
                any(
                    entry.get("actor") == "catalog_promotion_write"
                    and entry.get("transaction_id") == proposal_ref["transaction_id"]
                    and entry.get("idempotency_key") == proposal_ref["idempotency_key"]
                    and entry.get("proposal_id") == proposal_ref["proposal_id"]
                    and entry.get("task_id") == "TASK-7401"
                    and entry.get("to_status") == "promoted"
                    for entry in updated["decision_history"]
                )
            )

    def test_duplicate_write_refuses_without_mutating_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7402")
            preflight_hash, _dry_run = self.dry_run_hash(ops_dir, "IDEA-7402")
            first_code, first = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7402", "--write", "--preflight-hash", preflight_hash]
            )
            self.assertEqual(cli.SUCCESS, first_code, first)
            before = file_snapshot(ops_dir)

            second_code, second = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7402", "--write", "--preflight-hash", preflight_hash]
            )

            self.assertEqual(cli.SUCCESS, second_code, second)
            self.assertEqual("idea_promotion_task_already_written", second["action"])
            self.assertFalse(second["changed"])
            self.assertEqual(first["proposal_ref"], second["proposal_ref"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_changed_candidate_refuses_stale_preflight_hash_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            candidate = self.write_promotable_idea(ops_dir, "IDEA-7403")
            preflight_hash, _dry_run = self.dry_run_hash(ops_dir, "IDEA-7403")
            candidate["score"]["weighted_total"] = 17.0
            write_json(ops_dir / "ideas" / "IDEA-7403.json", candidate)
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7403", "--write", "--preflight-hash", preflight_hash]
            )

            self.assertEqual(2, code, payload)
            self.assertEqual("promotion_preflight_changed", payload["reason"])
            self.assertEqual(preflight_hash, payload["expected_preflight_hash"])
            self.assertNotEqual(preflight_hash, payload["current_preflight_hash"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_write_requires_hash_and_rejects_conflicting_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))

            missing_code, missing = run_cli_json(["idea", "promote", ops_dir, "IDEA-7404", "--write"])
            self.assertEqual(3, missing_code, missing)
            self.assertEqual("promotion_preflight_hash_required", missing["reason"])

            conflict_code, conflict = run_cli_json(
                [
                    "idea",
                    "promote",
                    ops_dir,
                    "IDEA-7404",
                    "--dry-run",
                    "--write",
                    "--preflight-hash",
                    "a" * 64,
                ]
            )
            self.assertEqual(3, conflict_code, conflict)
            self.assertEqual("conflicting_flags", conflict["reason"])

    def test_experiment_plan_write_requires_explicit_human_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            candidate = promotable_candidate("IDEA-7405", "Experiment proposal write idea")
            candidate["data_refs"] = ["DS-0001"]
            write_json(ops_dir / "ideas" / "IDEA-7405.json", candidate)
            preflight_hash, dry_run = self.dry_run_hash(ops_dir, "IDEA-7405", "--task-type", "experiment_plan")
            self.assertEqual("experiment_plan", dry_run["proposal"]["task_type"])

            blocked_code, blocked = run_cli_json(
                [
                    "idea",
                    "promote",
                    ops_dir,
                    "IDEA-7405",
                    "--task-type",
                    "experiment_plan",
                    "--write",
                    "--preflight-hash",
                    preflight_hash,
                ]
            )
            self.assertEqual(2, blocked_code, blocked)
            self.assertEqual("human_override_required", blocked["reason"])

            written_code, written = run_cli_json(
                [
                    "idea",
                    "promote",
                    ops_dir,
                    "IDEA-7405",
                    "--task-type",
                    "experiment_plan",
                    "--write",
                    "--preflight-hash",
                    preflight_hash,
                    "--human-override",
                ]
            )
            self.assertEqual(cli.SUCCESS, written_code, written)
            self.assertTrue(written["proposal_ref"]["human_override"])

    def test_write_refuses_fresh_catalog_lock_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7406")
            preflight_hash, _dry_run = self.dry_run_hash(ops_dir, "IDEA-7406")
            self.write_catalog_lock(ops_dir)
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7406", "--write", "--preflight-hash", preflight_hash]
            )

            self.assertEqual(2, code, payload)
            self.assertEqual("catalog_locked", payload["reason"])
            self.assertEqual("idea_promotion_write_refused", payload["action"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_write_rotates_stale_lock_and_creates_queue_and_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7407")
            preflight_hash, _dry_run = self.dry_run_hash(ops_dir, "IDEA-7407")
            lock_dir = self.write_catalog_lock(
                ops_dir,
                started_at="2000-01-01T00:00:00Z",
                expires_at="2000-01-01T00:30:00Z",
            )

            code, payload = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7407", "--write", "--preflight-hash", preflight_hash]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("idea_promotion_task_written", payload["action"])
            self.assertFalse(lock_dir.exists())
            self.assertTrue(list((ops_dir / "ideas").glob("LOCK.stale.*")))
            self.assertIn("TASK-7407", (ops_dir / "queue.md").read_text(encoding="utf-8"))
            self.assertTrue((Path(payload["task_dir"]) / "status.json").exists())

    def test_blocked_candidate_refuses_write_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            blocked = self.write_promotable_idea(ops_dir, "IDEA-7408")
            blocked["status"] = "park"
            blocked["status_reason"] = "not ready for promotion"
            blocked["revisit_condition"] = "after a human owner reopens it"
            write_json(ops_dir / "ideas" / "IDEA-7408.json", blocked)
            blocked_code, blocked_plan = run_cli_json(["idea", "promote", ops_dir, "IDEA-7408", "--dry-run"])
            self.assertEqual(2, blocked_code, blocked_plan)
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(
                [
                    "idea",
                    "promote",
                    ops_dir,
                    "IDEA-7408",
                    "--write",
                    "--preflight-hash",
                    blocked_plan["promotion_preflight_hash"],
                ]
            )

            self.assertEqual(2, code, payload)
            self.assertEqual("promotion_plan_blocked", payload["reason"])
            self.assertEqual("idea_promotion_blocked", payload["dry_run_plan"]["action"])
            self.assertTrue(
                any(item["reason"] == "status_not_promotable" for item in payload["dry_run_plan"]["blockers"])
            )
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_idea_missing_after_locked_plan_refuses_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7411")
            preflight_hash, _dry_run = self.dry_run_hash(ops_dir, "IDEA-7411")
            model_with_idea = idea_catalog_script.read_catalog(ops_dir)
            model_without_idea = {
                **model_with_idea,
                "candidates": [
                    record for record in model_with_idea["candidates"] if record.get("idea_id") != "IDEA-7411"
                ],
            }
            before = file_snapshot(ops_dir)

            with mock.patch.object(
                idea_catalog_script,
                "read_catalog",
                side_effect=[model_with_idea, model_without_idea],
            ):
                code, payload = run_cli_json(
                    ["idea", "promote", ops_dir, "IDEA-7411", "--write", "--preflight-hash", preflight_hash]
                )

            self.assertEqual(3, code, payload)
            self.assertEqual("idea_not_found_after_lock", payload["reason"])
            self.assertEqual("idea_promotion_write_refused", payload["action"])
            self.assertEqual("IDEA-7411", payload["idea_id"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_partial_inbox_without_idea_ref_requires_recovery_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7409")
            preflight_hash, dry_run = self.dry_run_hash(ops_dir, "IDEA-7409")
            write_text(
                ops_dir / "inbox.md",
                "\n".join(
                    [
                        "# Inbox",
                        "",
                        "| item | source | notes |",
                        "| --- | --- | --- |",
                        f"| PROMO-PARTIAL | ideas/IDEA-7409.json | idempotency_key={dry_run['idempotency_key']} |",
                        "",
                    ]
                ),
            )
            before = file_snapshot(ops_dir)

            code, payload = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7409", "--write", "--preflight-hash", preflight_hash]
            )

            self.assertEqual(2, code, payload)
            self.assertEqual("promotion_proposal_recovery_required", payload["reason"])
            self.assertEqual(dry_run["idempotency_key"], payload["recovery"]["idempotency_key"])
            self.assertEqual(str(ops_dir / "inbox.md"), payload["recovery"]["path"])
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_pre_write_validation_failure_refuses_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7412")
            preflight_hash, _dry_run = self.dry_run_hash(ops_dir, "IDEA-7412")
            before = file_snapshot(ops_dir)

            with mock.patch.object(
                idea_catalog_script,
                "validate_records_for_write",
                return_value=[
                    {
                        "severity": "failure",
                        "reason": "forced_pre_write_failure",
                        "message": "forced by test",
                    }
                ],
            ):
                code, payload = run_cli_json(
                    ["idea", "promote", ops_dir, "IDEA-7412", "--write", "--preflight-hash", preflight_hash]
                )

            self.assertEqual(2, code, payload)
            self.assertEqual("proposed_catalog_validation_failed", payload["reason"])
            self.assertEqual("forced_pre_write_failure", payload["failures"][0]["reason"])
            self.assertNotIn("files_written", payload)
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_task_transaction_failure_restores_inbox_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7413")
            preflight_hash, dry_run = self.dry_run_hash(ops_dir, "IDEA-7413")
            before = file_snapshot(ops_dir)

            with mock.patch.object(
                idea_catalog_script.task_transaction,
                "write_task_transaction",
                return_value=(
                    idea_catalog_script.MALFORMED,
                    {"ok": False, "reason": "forced_task_transaction_failure"},
                ),
            ):
                code, payload = run_cli_json(
                    ["idea", "promote", ops_dir, "IDEA-7413", "--write", "--preflight-hash", preflight_hash]
                )

            self.assertEqual(idea_catalog_script.MALFORMED, code, payload)
            self.assertEqual("task_transaction_failed", payload["reason"])
            self.assertEqual("forced_task_transaction_failure", payload["task_transaction"]["reason"])
            self.assertEqual("task_transaction_failed_after_inbox_append", payload["recovery"]["reason"])
            self.assertEqual(dry_run["idempotency_key"], payload["recovery"]["idempotency_key"])
            self.assertTrue(payload["recovery"]["rollback_ok"])
            self.assertFalse(payload["recovery"]["requires_human"])
            self.assertIn("async-research idea catalog validate", payload["recovery"]["next_step"])
            self.assertNotIn(dry_run["idempotency_key"], (ops_dir / "inbox.md").read_text(encoding="utf-8"))
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_rollback_audit_payload_requires_human_when_rollback_action_fails(self) -> None:
        audit = idea_catalog_script.rollback_audit_payload(
            Path("/tmp/research_ops"),
            task_rollback={
                "actions": [
                    {
                        "action": "remove_task_folder",
                        "path": "/tmp/research_ops/tasks/TASK-7419-data-readiness",
                        "changed": False,
                    }
                ]
            },
            restored_files=[],
        )

        self.assertFalse(audit["rollback_ok"])
        self.assertTrue(audit["requires_human"])
        self.assertEqual(1, audit["rollback_action_count"])
        self.assertEqual(1, len(audit["rollback_failures"]))
        self.assertEqual("remove_task_folder", audit["rollback_failures"][0]["action"])
        self.assertIn("inspect rollback_failures", audit["next_step"])

    def test_staged_task_validation_failure_restores_all_promotion_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7415")
            preflight_hash, dry_run = self.dry_run_hash(ops_dir, "IDEA-7415")
            before = file_snapshot(ops_dir)

            bad_status = {
                "schema_version": "1.0",
                "id": "TASK-7415",
                "title": "Invalid staged promotion task",
                "type": "data_readiness",
                "status": "inbox",
            }
            with mock.patch.object(
                idea_catalog_script,
                "promotion_task_status_json",
                return_value=bad_status,
            ):
                code, payload = run_cli_json(
                    ["idea", "promote", ops_dir, "IDEA-7415", "--write", "--preflight-hash", preflight_hash]
                )

            self.assertEqual(2, code, payload)
            self.assertEqual("task_transaction_failed", payload["reason"])
            self.assertEqual("staged_task_validation_failed", payload["task_transaction"]["reason"])
            self.assertEqual(dry_run["idempotency_key"], payload["recovery"]["idempotency_key"])
            self.assertTrue(payload["recovery"]["rollback_ok"])
            self.assertEqual([], payload["recovery"]["rollback_failures"])
            self.assertNotIn(dry_run["idempotency_key"], (ops_dir / "inbox.md").read_text(encoding="utf-8"))
            self.assertEqual([], list((ops_dir / "tasks").glob(".TASK-7415-data-readiness.staging.*")))
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_queue_append_failure_rolls_back_task_and_restores_inbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7416")
            preflight_hash, dry_run = self.dry_run_hash(ops_dir, "IDEA-7416")
            before = file_snapshot(ops_dir)
            original_write = idea_catalog_script.task_transaction.write_task_transaction

            def write_with_queue_failure(*args, **kwargs):
                def fail_append(_ops_dir: Path, _row: dict) -> dict:
                    raise idea_catalog_script.task_transaction.TaskTransactionError(
                        {"reason": "queue_append_failed", "error": "forced queue append failure"},
                        idea_catalog_script.task_transaction.MALFORMED,
                    )

                kwargs["append_queue"] = fail_append
                return original_write(*args, **kwargs)

            with mock.patch.object(
                idea_catalog_script.task_transaction,
                "write_task_transaction",
                side_effect=write_with_queue_failure,
            ):
                code, payload = run_cli_json(
                    ["idea", "promote", ops_dir, "IDEA-7416", "--write", "--preflight-hash", preflight_hash]
                )

            self.assertEqual(idea_catalog_script.MALFORMED, code, payload)
            self.assertEqual("task_transaction_failed", payload["reason"])
            self.assertEqual("queue_append_failed", payload["task_transaction"]["reason"])
            self.assertTrue(payload["recovery"]["rollback_ok"])
            rollback_actions = {
                item["action"]
                for item in payload["task_transaction"]["rollback"]["actions"]
            }
            self.assertIn("remove_task_folder", rollback_actions)
            self.assertNotIn(dry_run["idempotency_key"], (ops_dir / "inbox.md").read_text(encoding="utf-8"))
            self.assertFalse((ops_dir / "tasks" / "TASK-7416-data-readiness").exists())
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_post_write_validation_failure_reports_recovery_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7410")
            preflight_hash, dry_run = self.dry_run_hash(ops_dir, "IDEA-7410")
            queue_before = (ops_dir / "queue.md").read_bytes()
            tasks_before = file_snapshot(ops_dir / "tasks")

            with mock.patch.object(
                idea_catalog_script,
                "catalog_validation_report_from_model",
                return_value={
                    "ok": False,
                    "warnings": [],
                    "failures": [
                        {
                            "severity": "failure",
                            "reason": "forced_post_write_failure",
                            "message": "forced by test",
                        }
                    ],
                },
            ):
                code, payload = run_cli_json(
                    ["idea", "promote", ops_dir, "IDEA-7410", "--write", "--preflight-hash", preflight_hash]
                )

            self.assertEqual(2, code, payload)
            self.assertEqual("post_write_validation_failed", payload["reason"])
            self.assertEqual(dry_run["idempotency_key"], payload["recovery"]["idempotency_key"])
            self.assertIn("task_rollback", payload["recovery"])
            self.assertIn("restored_files", payload["recovery"])
            self.assertTrue(payload["recovery"]["rollback_ok"])
            self.assertFalse(payload["recovery"]["requires_human"])
            self.assertTrue(payload["files_written"])
            self.assertNotIn(dry_run["idempotency_key"], (ops_dir / "inbox.md").read_text(encoding="utf-8"))
            updated = read_json(ops_dir / "ideas" / "IDEA-7410.json")
            self.assertNotIn("promotion_proposal_refs", updated)
            self.assertNotIn("promoted_task_id", updated)
            self.assertEqual(queue_before, (ops_dir / "queue.md").read_bytes())
            self.assertEqual(tasks_before, file_snapshot(ops_dir / "tasks"))

    def test_idea_json_write_failure_rolls_back_task_queue_and_inbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7417")
            preflight_hash, dry_run = self.dry_run_hash(ops_dir, "IDEA-7417")
            before = file_snapshot(ops_dir)
            idea_path = ops_dir / "ideas" / "IDEA-7417.json"
            original_atomic = idea_catalog_script.atomic_write_bytes
            failed_once = False

            def fail_first_idea_write(path: Path, content: bytes) -> bool:
                nonlocal failed_once
                if Path(path) == idea_path and not failed_once:
                    failed_once = True
                    raise OSError("forced idea write failure")
                return original_atomic(path, content)

            with mock.patch.object(
                idea_catalog_script,
                "atomic_write_bytes",
                side_effect=fail_first_idea_write,
            ):
                code, payload = run_cli_json(
                    ["idea", "promote", ops_dir, "IDEA-7417", "--write", "--preflight-hash", preflight_hash]
                )

            self.assertEqual(2, code, payload)
            self.assertEqual("catalog_write_failed", payload["reason"])
            self.assertEqual("catalog_write_failed", payload["failures"][0]["reason"])
            self.assertTrue(payload["recovery"]["rollback_ok"])
            self.assertFalse(payload["recovery"]["requires_human"])
            self.assertEqual(dry_run["idempotency_key"], payload["recovery"]["idempotency_key"])
            self.assertNotIn(dry_run["idempotency_key"], (ops_dir / "inbox.md").read_text(encoding="utf-8"))
            self.assertFalse((ops_dir / "tasks" / "TASK-7417-data-readiness").exists())
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_completion_check_failure_rolls_back_task_queue_and_catalog_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7414")
            preflight_hash, dry_run = self.dry_run_hash(ops_dir, "IDEA-7414")
            before = file_snapshot(ops_dir)

            with mock.patch.object(
                idea_catalog_script,
                "promotion_task_write_completion",
                return_value={
                    "ok": False,
                    "task_id": "TASK-7414",
                    "task_statuses": [],
                    "failures": [{"reason": "forced_completion_failure"}],
                },
            ):
                code, payload = run_cli_json(
                    ["idea", "promote", ops_dir, "IDEA-7414", "--write", "--preflight-hash", preflight_hash]
                )

            self.assertEqual(2, code, payload)
            self.assertEqual("promotion_task_consistency_failed", payload["reason"])
            self.assertEqual("forced_completion_failure", payload["completion_failures"][0]["reason"])
            self.assertEqual(dry_run["idempotency_key"], payload["recovery"]["idempotency_key"])
            self.assertIn("task_rollback", payload["recovery"])
            self.assertIn("restored_files", payload["recovery"])
            self.assertTrue(payload["recovery"]["rollback_ok"])
            self.assertFalse(payload["recovery"]["requires_human"])
            self.assertNotIn(dry_run["idempotency_key"], (ops_dir / "inbox.md").read_text(encoding="utf-8"))
            self.assertEqual(before, file_snapshot(ops_dir))

    def test_interrupted_retry_with_missing_queue_row_requires_recovery_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = self.init_ops(Path(tmp))
            self.write_audited_source(ops_dir)
            self.write_promotable_idea(ops_dir, "IDEA-7418")
            preflight_hash, dry_run = self.dry_run_hash(ops_dir, "IDEA-7418")
            first_code, first = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7418", "--write", "--preflight-hash", preflight_hash]
            )
            self.assertEqual(cli.SUCCESS, first_code, first)
            removal = idea_catalog_script.task_transaction.remove_queue_row(ops_dir, "TASK-7418")
            self.assertTrue(removal["changed"])
            before_retry = file_snapshot(ops_dir)

            retry_code, retry = run_cli_json(
                ["idea", "promote", ops_dir, "IDEA-7418", "--write", "--preflight-hash", preflight_hash]
            )

            self.assertEqual(2, retry_code, retry)
            self.assertEqual("promotion_task_recovery_required", retry["reason"])
            self.assertEqual(dry_run["idempotency_key"], retry["existing_proposal_ref"]["idempotency_key"])
            self.assertIn(
                "queue_row_missing",
                {item["reason"] for item in retry["completion_failures"]},
            )
            self.assertEqual(before_retry, file_snapshot(ops_dir))


if __name__ == "__main__":
    unittest.main()

"""Regression tests for guarded foundation proposal apply commands."""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "async_research_workflow"
REAL_ESTATE_STARTER = PACKAGE_ROOT / "templates" / "research_ops_starter" / "research_ops"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_cli_json(argv: list[str]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main(argv)
    return int(code), json.loads(stream.getvalue())


def copy_starter(tmp: Path) -> Path:
    target = tmp / "research_ops"
    shutil.copytree(REAL_ESTATE_STARTER, target)
    return target


def accepted_task(ops_dir: Path, task_id: str, slug: str) -> Path:
    task_dir = ops_dir / "tasks" / f"{task_id}-{slug}"
    write_json(
        task_dir / "status.json",
        {
            "id": task_id,
            "status": "accepted",
            "type": slug.replace("-", "_"),
            "title": f"{task_id} fixture",
        },
    )
    (task_dir / "task.md").write_text(f"# {task_id}\n", encoding="utf-8")
    return task_dir


def task_with_status(ops_dir: Path, task_id: str, slug: str, status: str) -> Path:
    task_dir = ops_dir / "tasks" / f"{task_id}-{slug}"
    write_json(
        task_dir / "status.json",
        {
            "id": task_id,
            "status": status,
            "type": slug.replace("-", "_"),
            "title": f"{task_id} fixture",
        },
    )
    (task_dir / "task.md").write_text(f"# {task_id}\n", encoding="utf-8")
    return task_dir


def valid_result_acceptance(task_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "framework_version": "result_acceptance_v1.0",
        "task_id": task_id,
        "task_type": "data_readiness",
        "evaluated_at": "2026-05-19T00:00:00Z",
        "route": "accept_as_evidence",
        "recommended_decision": "ready",
        "claim_strength": "weak",
        "max_claim_strength": "weak",
        "claim_strength_policy": "fixture acceptance proof",
        "hard_gate_results": [{"gate": "fixture_review", "passed": True, "reason": "accepted"}],
        "scorecard": {
            "plan_compliance": 5,
            "reproducibility": 5,
            "baseline_comparison": 3,
            "metric_validity": 3,
            "validation_strength": 3,
            "robustness_strength": 3,
            "leakage_safety": 3,
            "limitation_honesty": 3,
            "decision_usefulness": 5,
            "claim_discipline": 5,
        },
        "reviewer_panel": {
            "aggregate_present": True,
            "aggregate_decision": "accept",
            "tier": 1,
            "required_reviewers": ["fixture"],
            "reviewer_count": 1,
            "disagreement_present": False,
        },
        "human_gate": {"required": False, "satisfied": True, "reason": "fixture"},
        "source_governance": {"required": False, "source_ids": [], "ok": True, "warnings": [], "blocked": []},
        "accepted_memory": {
            "claim_type": "workflow_artifact",
            "freshness_window_days": "unavailable",
            "next_recheck_date": "unavailable",
            "revalidation_status": "not_required",
            "supersedes": "",
            "superseded_by": "",
        },
        "analysis_run": None,
        "evidence_ledger": {"required": False, "ledger_path": "", "logged": False, "evidence_link": ""},
        "rejection_logging": {"required": False, "log_path": "", "logged": False},
        "followups": [],
        "review_notes": ["accepted by fixture review"],
    }


def operation(operation_id: str, name: str, target_path: str, row_id: str, payload: dict) -> dict:
    return {
        "operation_id": operation_id,
        "operation": name,
        "target_path": target_path,
        "row_id": row_id,
        "payload": payload,
        "preserve_manual_notes": True,
    }


def valid_data_proposal(source_id: str = "DS-0100", *, source_tier: str = "tier_2_institutional") -> dict:
    source_payload = {
        "source_id": source_id,
        "source_name": "Fixture Data Source",
        "url_or_domain": "https://example.test/data.csv",
        "publisher_owner": "Fixture Publisher",
        "source_tier": source_tier,
        "approval_status": "candidate",
        "approved_use_cases": "context",
        "blocked_use_cases": "accepted_evidence",
        "freshness_window_days": "90",
        "known_limitations": "fixture only",
        "citation_requirements": f"cite {source_id}",
        "last_reviewed": "2026-05-19",
        "approved_by": "automation_test",
        "review_notes": "reviewed fixture proposal",
    }
    return {
        "proposal_version": "foundation_update_proposal_v1",
        "proposal_id": f"PROP-{source_id[-4:]}",
        "source_task_id": "TASK-0100-data-readiness",
        "target": "data",
        "created_by": "worker",
        "rationale": "Add reviewed fixture data rows.",
        "operations": [
            operation("OP-0001", "upsert_data_source", "data_source_audit.md", source_id, source_payload),
            operation(
                "OP-0002",
                "upsert_data_profile",
                f"data/profiles/{source_id}.md",
                source_id,
                {
                    "source_id": source_id,
                    "source_name": "Fixture Data Source",
                    "audit_status": "candidate",
                    "reviewed_date": "2026-05-19",
                    "reviewer": "automation_test",
                    "location": "https://example.test/data.csv",
                    "access_method": "public download",
                    "access_notes": "fixture access notes",
                    "approved_use_cases": "context",
                    "blocked_use_cases": "accepted_evidence",
                },
            ),
            operation(
                "OP-0003",
                "upsert_data_catalog_row",
                "data/data_catalog.md",
                source_id,
                {
                    "source_id": source_id,
                    "source_name": "Fixture Data Source",
                    "approval_status": "candidate",
                    "profile_path": f"data/profiles/{source_id}.md",
                    "grain": "fixture",
                    "geography": "fixture",
                    "time_coverage": "fixture",
                    "access_summary": "public fixture",
                    "limitations": "fixture only",
                },
            ),
            operation(
                "OP-0004",
                "upsert_data_access_row",
                "data/data_access.md",
                source_id,
                {
                    "source_id": source_id,
                    "access_method": "public download",
                    "location": "https://example.test/data.csv",
                    "permission_required": "none",
                    "access_check": "checked by automation fixture on 2026-05-19",
                    "notes": "fixture only",
                },
            ),
        ],
    }


def valid_library_proposal(source_id: str = "LIT-0100") -> dict:
    return {
        "proposal_version": "foundation_update_proposal_v1",
        "proposal_id": f"PROP-{source_id[-4:]}",
        "source_task_id": "TASK-0200-literature-extract",
        "target": "library",
        "created_by": "worker",
        "rationale": "Add reviewed fixture library rows.",
        "operations": [
            operation(
                "OP-0001",
                "upsert_lit_source",
                "library/source_library.md",
                source_id,
                {
                    "source_id": source_id,
                    "status": "trusted",
                    "trust_tier": "primary",
                    "type": "report",
                    "title": "Fixture Report",
                    "author_or_publisher": "Fixture Publisher",
                    "location": "https://example.test/report",
                    "reviewed_date": "2026-05-19",
                    "notes": "reviewed fixture source",
                },
            ),
            operation(
                "OP-0002",
                "upsert_topic_summary",
                "library/knowledge_index.md",
                "TOPIC-0100",
                {
                    "topic": "TOPIC-0100",
                    "summary": "Fixture topic summary",
                    "source_refs": source_id,
                    "confidence": "medium",
                    "caveats": "fixture only",
                    "updated_at": "2026-05-19",
                },
            ),
            operation(
                "OP-0003",
                "append_library_update_log",
                "library/library_update_log.md",
                "TASK-0200",
                {
                    "date": "2026-05-19",
                    "task_id": "TASK-0200",
                    "files_updated": "library/source_library.md; library/knowledge_index.md",
                    "reviewer_or_approver": "automation_test",
                    "notes": "fixture proposal applied",
                },
            ),
        ],
    }


class FoundationProposalApplyTests(unittest.TestCase):
    def test_data_apply_default_dry_run_is_safe_and_reports_preflight_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            accepted_task(ops_dir, "TASK-0100", "data-readiness")
            task_dir = ops_dir / "tasks" / "TASK-0100-data-readiness"
            write_json(task_dir / "artifacts" / "foundation_update_proposal.json", valid_data_proposal())
            before = (ops_dir / "data_source_audit.md").read_text(encoding="utf-8")

            code, payload = run_cli_json(["data", "apply-proposals", str(ops_dir), str(task_dir)])
            after = (ops_dir / "data_source_audit.md").read_text(encoding="utf-8")

        self.assertEqual(0, code, payload)
        self.assertTrue(payload["ok"])
        self.assertEqual("dry-run", payload["mode"])
        self.assertFalse(payload["changed"])
        self.assertRegex(payload["preflight_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(before, after)

    def test_data_write_is_idempotent_and_preserves_manual_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            accepted_task(ops_dir, "TASK-0100", "data-readiness")
            task_dir = ops_dir / "tasks" / "TASK-0100-data-readiness"
            write_json(task_dir / "artifacts" / "foundation_update_proposal.json", valid_data_proposal())
            catalog_path = ops_dir / "data" / "data_catalog.md"
            catalog_path.write_text(catalog_path.read_text(encoding="utf-8") + "\nManual catalog note.\n", encoding="utf-8")

            dry_code, dry = run_cli_json(["data", "apply-proposals", str(ops_dir), str(task_dir), "--dry-run"])
            write_code, written = run_cli_json(
                [
                    "data",
                    "apply-proposals",
                    str(ops_dir),
                    str(task_dir),
                    "--write",
                    "--preflight-hash",
                    dry["preflight_hash"],
                ]
            )
            second_dry_code, second_dry = run_cli_json(["data", "apply-proposals", str(ops_dir), str(task_dir), "--dry-run"])
            second_write_code, second_written = run_cli_json(
                [
                    "data",
                    "apply-proposals",
                    str(ops_dir),
                    str(task_dir),
                    "--write",
                    "--preflight-hash",
                    second_dry["preflight_hash"],
                ]
            )

            audit_text = (ops_dir / "data_source_audit.md").read_text(encoding="utf-8")
            catalog_text = catalog_path.read_text(encoding="utf-8")

        self.assertEqual(0, dry_code, dry)
        self.assertEqual(0, write_code, written)
        self.assertTrue(written["ok"])
        self.assertTrue(written["changed"])
        self.assertEqual(0, second_dry_code, second_dry)
        self.assertEqual(0, second_write_code, second_written)
        self.assertTrue(second_written["ok"])
        self.assertFalse(second_written["changed"])
        audit_rows = [line for line in audit_text.splitlines() if line.startswith("| DS-0100 |")]
        catalog_rows = [line for line in catalog_text.splitlines() if line.startswith("| DS-0100 |")]
        self.assertEqual(1, len(audit_rows))
        self.assertEqual(1, len(catalog_rows))
        self.assertIn("Manual catalog note.", catalog_text)

    def test_write_refuses_stale_preflight_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            accepted_task(ops_dir, "TASK-0100", "data-readiness")
            task_dir = ops_dir / "tasks" / "TASK-0100-data-readiness"
            write_json(task_dir / "artifacts" / "foundation_update_proposal.json", valid_data_proposal())

            code, payload = run_cli_json(
                [
                    "data",
                    "apply-proposals",
                    str(ops_dir),
                    str(task_dir),
                    "--write",
                    "--preflight-hash",
                    "0" * 64,
                ]
            )

        self.assertEqual(3, code, payload)
        self.assertFalse(payload["ok"])
        self.assertEqual("preflight_hash_mismatch", payload["reason"])

    def test_write_accepts_valid_in_workspace_result_acceptance_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            task_dir = task_with_status(ops_dir, "TASK-0100", "data-readiness", "reviewing")
            write_json(task_dir / "artifacts" / "foundation_update_proposal.json", valid_data_proposal())
            acceptance_path = task_dir / "review_panel" / "result_acceptance.json"
            write_json(acceptance_path, valid_result_acceptance("TASK-0100"))
            dry_code, dry = run_cli_json(
                [
                    "data",
                    "apply-proposals",
                    str(ops_dir),
                    str(task_dir),
                    "--dry-run",
                    "--accepted-artifact",
                    str(acceptance_path),
                ]
            )

            write_code, written = run_cli_json(
                [
                    "data",
                    "apply-proposals",
                    str(ops_dir),
                    str(task_dir),
                    "--write",
                    "--preflight-hash",
                    dry["preflight_hash"],
                    "--accepted-artifact",
                    str(acceptance_path),
                ]
            )

        self.assertEqual(0, dry_code, dry)
        self.assertTrue(dry["write_preconditions"]["acceptance"][0]["accepted"])
        self.assertEqual("accepted_artifact", dry["write_preconditions"]["acceptance"][0]["proof_type"])
        self.assertEqual(0, write_code, written)
        self.assertTrue(written["ok"])

    def test_write_refuses_lock_contention_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            accepted_task(ops_dir, "TASK-0100", "data-readiness")
            task_dir = ops_dir / "tasks" / "TASK-0100-data-readiness"
            write_json(task_dir / "artifacts" / "foundation_update_proposal.json", valid_data_proposal())
            dry_code, dry = run_cli_json(["data", "apply-proposals", str(ops_dir), str(task_dir), "--dry-run"])
            (ops_dir / ".foundation_data_apply.LOCK").mkdir()
            before = (ops_dir / "data_source_audit.md").read_text(encoding="utf-8")

            code, payload = run_cli_json(
                [
                    "data",
                    "apply-proposals",
                    str(ops_dir),
                    str(task_dir),
                    "--write",
                    "--preflight-hash",
                    dry["preflight_hash"],
                ]
            )
            after = (ops_dir / "data_source_audit.md").read_text(encoding="utf-8")

        self.assertEqual(0, dry_code, dry)
        self.assertEqual(2, code, payload)
        self.assertEqual("foundation_apply_locked", payload["reason"])
        self.assertEqual(before, after)

    def test_data_write_refuses_source_register_lock_without_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            accepted_task(ops_dir, "TASK-0100", "data-readiness")
            task_dir = ops_dir / "tasks" / "TASK-0100-data-readiness"
            write_json(task_dir / "artifacts" / "foundation_update_proposal.json", valid_data_proposal())
            dry_code, dry = run_cli_json(["data", "apply-proposals", str(ops_dir), str(task_dir), "--dry-run"])
            lock_dir = ops_dir / "data_source_audit.md.LOCK"
            lock_dir.mkdir()
            write_json(
                lock_dir / "owner.json",
                {
                    "command": "source upsert",
                    "lock_expires_at": "2999-01-01T00:00:00Z",
                },
            )
            before = (ops_dir / "data_source_audit.md").read_text(encoding="utf-8")

            code, payload = run_cli_json(
                [
                    "data",
                    "apply-proposals",
                    str(ops_dir),
                    str(task_dir),
                    "--write",
                    "--preflight-hash",
                    dry["preflight_hash"],
                ]
            )
            after = (ops_dir / "data_source_audit.md").read_text(encoding="utf-8")

        self.assertEqual(0, dry_code, dry)
        self.assertEqual(2, code, payload)
        self.assertEqual("source_register_locked", payload["reason"])
        self.assertEqual(before, after)

    def test_write_rolls_back_when_post_write_validation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            accepted_task(ops_dir, "TASK-0100", "data-readiness")
            task_dir = ops_dir / "tasks" / "TASK-0100-data-readiness"
            proposal = valid_data_proposal(source_id="DS-0101")
            proposal["operations"] = [proposal["operations"][0]]
            write_json(task_dir / "artifacts" / "foundation_update_proposal.json", proposal)
            dry_code, dry = run_cli_json(["data", "apply-proposals", str(ops_dir), str(task_dir), "--dry-run"])
            bad_profile = ops_dir / "data" / "profiles" / "DS-0999.md"
            bad_profile.write_text("# DS-0999\n\nsource_id: DS-0001\n", encoding="utf-8")

            code, payload = run_cli_json(
                [
                    "data",
                    "apply-proposals",
                    str(ops_dir),
                    str(task_dir),
                    "--write",
                    "--preflight-hash",
                    dry["preflight_hash"],
                ]
            )
            audit_text = (ops_dir / "data_source_audit.md").read_text(encoding="utf-8")

        self.assertEqual(0, dry_code, dry)
        self.assertEqual(2, code, payload)
        self.assertEqual("post_write_validation_failed", payload["reason"])
        self.assertTrue(payload["rollback"]["ok"])
        self.assertNotIn("DS-0101", audit_text)

    def test_library_write_is_idempotent_and_preserves_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            accepted_task(ops_dir, "TASK-0200", "literature-extract")
            task_dir = ops_dir / "tasks" / "TASK-0200-literature-extract"
            write_json(task_dir / "artifacts" / "foundation_update_proposal.json", valid_library_proposal())
            source_library = ops_dir / "library" / "source_library.md"
            source_library.write_text(source_library.read_text(encoding="utf-8") + "\nManual library note.\n", encoding="utf-8")

            dry_code, dry = run_cli_json(["library", "apply-proposals", str(ops_dir), str(task_dir), "--dry-run"])
            write_code, written = run_cli_json(
                [
                    "library",
                    "apply-proposals",
                    str(ops_dir),
                    str(task_dir),
                    "--write",
                    "--preflight-hash",
                    dry["preflight_hash"],
                ]
            )
            second_dry_code, second_dry = run_cli_json(["library", "apply-proposals", str(ops_dir), str(task_dir), "--dry-run"])
            second_write_code, second_written = run_cli_json(
                [
                    "library",
                    "apply-proposals",
                    str(ops_dir),
                    str(task_dir),
                    "--write",
                    "--preflight-hash",
                    second_dry["preflight_hash"],
                ]
            )
            source_text = source_library.read_text(encoding="utf-8")
            topic_text = (ops_dir / "library" / "knowledge_index.md").read_text(encoding="utf-8")

        self.assertEqual(0, dry_code, dry)
        self.assertEqual(0, write_code, written)
        self.assertTrue(written["ok"])
        self.assertEqual(0, second_dry_code, second_dry)
        self.assertEqual(0, second_write_code, second_written)
        self.assertFalse(second_written["changed"])
        self.assertEqual(1, source_text.count("LIT-0100"))
        self.assertEqual(1, topic_text.count("TOPIC-0100"))
        self.assertIn("Manual library note.", source_text)

    def test_warning_only_post_write_validation_does_not_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = copy_starter(Path(tmpdir))
            accepted_task(ops_dir, "TASK-0200", "literature-extract")
            task_dir = ops_dir / "tasks" / "TASK-0200-literature-extract"
            proposal = valid_library_proposal("LIT-0101")
            proposal["operations"][0]["payload"]["status"] = ""
            write_json(task_dir / "artifacts" / "foundation_update_proposal.json", proposal)

            dry_code, dry = run_cli_json(["library", "apply-proposals", str(ops_dir), str(task_dir), "--dry-run"])
            write_code, written = run_cli_json(
                [
                    "library",
                    "apply-proposals",
                    str(ops_dir),
                    str(task_dir),
                    "--write",
                    "--preflight-hash",
                    dry["preflight_hash"],
                ]
            )
            source_text = (ops_dir / "library" / "source_library.md").read_text(encoding="utf-8")

        self.assertEqual(0, dry_code, dry)
        self.assertEqual(1, len(dry["warnings"]))
        self.assertEqual(0, write_code, written)
        self.assertTrue(written["ok"])
        self.assertEqual(2, written["validation"][0]["exit_code"])
        self.assertEqual("passed", written["validation"][0]["status"])
        self.assertIn("LIT-0101", source_text)


if __name__ == "__main__":
    unittest.main()

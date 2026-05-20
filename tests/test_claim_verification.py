"""Regression tests for claim and citation verification."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.resources import schema_path
from async_research_workflow.scripts import claim_verification, validate_result_acceptance
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


NOW = "2026-05-20T10:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(item) for item in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def run_json(module, argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = module.main([str(item) for item in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def init_ops(root: Path) -> Path:
    ops_dir = root / "research_ops"
    code, payload = run_cli_json(["init", ops_dir, "--force"])
    assert code == cli.SUCCESS, payload
    return ops_dir


def write_task(ops_dir: Path, task_id: str = "TASK-4001", claim_strength: str = "suggestive") -> Path:
    task_dir = ops_dir / "tasks" / f"{task_id}-claim-verification"
    write_json(
        task_dir / "status.json",
        {
            "schema_version": "1.0",
            "id": task_id,
            "title": "Claim verification fixture",
            "type": "status_update",
            "status": "accepted",
            "previous_status": "panel_review",
            "last_transition_reason": "claim_verification_fixture",
            "priority": 2,
            "revision_count": 0,
            "max_revisions": 1,
            "revision_limit_hit": False,
            "allowed_paths": [f"research_ops/tasks/{task_dir.name}/**", "research_ops/runtime/**"],
            "max_minutes": 10,
            "requires_human": False,
            "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
            "human_gate_reason": None,
            "updated_at": NOW,
            "result": {
                "claim_strength": claim_strength,
                "key_finding": "The fixture source reports a 12 percent increase.",
            },
        },
    )
    write_json(
        task_dir / "review_panel" / "aggregate.json",
        {
            "aggregate_decision": "accepted",
            "aggregate_claim_strength": claim_strength,
            "tier": 1,
            "required_reviewers": ["primary"],
            "reviews": [{"reviewer_role": "primary", "decision": "accept", "claim_strength": claim_strength}],
            "disagreements": ["none"],
        },
    )
    (task_dir / "worker_output.md").write_text("The fixture source reports a 12 percent increase.\n", encoding="utf-8")
    return task_dir


def write_evidence(
    ops_dir: Path,
    *,
    evidence_id: str = "EVID-000001",
    adapter_type: str = "file_fetch",
    text: str = "The fixture source reports a 12 percent increase.\n",
    freshness: str = "current",
) -> dict:
    snapshot_path = ops_dir / "runtime" / "snapshots" / f"{evidence_id}.txt"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(text, encoding="utf-8")
    payload = {
        "schema_version": "1.0",
        "framework_version": "runtime_evidence_object_v1.0",
        "evidence_id": evidence_id,
        "task_id": "TASK-4001",
        "adapter_type": adapter_type,
        "source_uri": f"fixture://claim-verification/{evidence_id}",
        "source_title": "Claim verification fixture source",
        "retrieved_at": NOW,
        "content_hash": sha256_text(text),
        "snapshot_path": f"research_ops/runtime/snapshots/{evidence_id}.txt",
        "span_refs": [
            {
                "span_id": "SPAN-0001",
                "span_type": "text",
                "selector": "line:1",
                "content_hash": sha256_text(text),
            }
        ],
        "license_or_use_policy": "fixture-only",
        "freshness_status": {"status": freshness, "checked_at": NOW, "basis": "offline fixture"},
        "cost": {"api_usd": 0.0, "compute_usd": 0.0, "tokens": 0, "basis": "offline fixture"},
        "permission_basis": {
            "type": "task_contract",
            "reference": "research_ops/tasks/TASK-4001-claim-verification/status.json",
            "capability": adapter_type,
        },
    }
    ledger = ops_dir / "runtime" / "evidence_objects.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing = ledger.read_text(encoding="utf-8") if ledger.exists() else ""
    ledger.write_text(existing + json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def claim_payload(
    *,
    claim_id: str = "CLM-0001",
    claim_type: str = "empirical",
    text: str = "The fixture source reports a 12 percent increase.",
    evidence_id: str = "EVID-000001",
    quote: str = "12 percent increase",
    support_status: str = "supports",
) -> dict:
    return {
        "claim_id": claim_id,
        "text": text,
        "claim_type": claim_type,
        "strength": "moderate",
        "required_support_level": "direct" if claim_type != "numeric" else "computation",
        "evidence_refs": [
            {
                "evidence_id": evidence_id,
                "span_ref": "SPAN-0001",
                "quote_or_paraphrase_status": "quote",
                "quote": quote,
                "support_status": support_status,
            }
        ],
        "citation_refs": [f"{evidence_id}#SPAN-0001"],
    }


class ClaimVerificationTests(unittest.TestCase):
    def test_supported_claim_maps_quote_to_runtime_evidence_and_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            task_dir = write_task(ops_dir)
            write_evidence(ops_dir)
            write_json(task_dir / "artifacts" / "claim_verification.json", {"claims": [claim_payload()]})

            report = claim_verification.verify_task_claims(task_dir, ops_dir)

            schema = load_json(schema_path("claim_verification.schema.json"))
            self.assertEqual([], [error.to_dict() for error in validate(report, schema)])
            self.assertTrue(report["acceptance_ok"])
            self.assertEqual("supported", report["claims"][0]["verification_status"])
            self.assertEqual("fixture://claim-verification/EVID-000001", report["claims"][0]["citation_mappings"][0]["source_uri"])

            code, payload = run_json(validate_result_acceptance, [task_dir, "--ops-dir", ops_dir, "--write", "--update-ledgers"])

            self.assertEqual(validate_result_acceptance.SUCCESS, code, payload)
            record = json.loads((task_dir / "review_panel" / "result_acceptance.json").read_text(encoding="utf-8"))
            self.assertEqual("pass", record["claim_verification"]["status"])
            self.assertEqual("suggestive", record["max_claim_strength"])
            ledger = (ops_dir / "claim_verification_ledger.md").read_text(encoding="utf-8")
            self.assertIn("CLM-0001", ledger)

            snapshot_code, snapshot = run_cli_json(["console", "snapshot", ops_dir, "--json", "--now", NOW])
            self.assertEqual(cli.SUCCESS, snapshot_code, snapshot)
            qa = snapshot["tasks"]["all"][0]["qa"]
            self.assertIn("claim verification: pass", qa["validation_checks"])

    def test_missing_citation_blocks_accepted_empirical_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            task_dir = write_task(ops_dir)
            claim = claim_payload()
            claim["evidence_refs"] = []
            claim["citation_refs"] = []
            write_json(task_dir / "artifacts" / "claim_verification.json", {"claims": [claim]})

            code, payload = run_json(validate_result_acceptance, [task_dir, "--ops-dir", ops_dir])

            self.assertEqual(validate_result_acceptance.VALIDATION_FAILED, code, payload)
            gates = {item["gate"]: item for item in payload["hard_gate_failures"]}
            self.assertIn("claim_citation_verification", gates)
            report = payload["record"]["claim_verification"]
            self.assertEqual("unsupported", report["claims"][0]["verification_status"])
            self.assertEqual("none", report["max_claim_strength"])

    def test_stale_source_caps_claim_strength(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            task_dir = write_task(ops_dir, claim_strength="moderate")
            write_evidence(ops_dir, freshness="stale")
            write_json(task_dir / "artifacts" / "claim_verification.json", {"claims": [claim_payload()]})

            code, payload = run_json(validate_result_acceptance, [task_dir, "--ops-dir", ops_dir])

            self.assertEqual(validate_result_acceptance.VALIDATION_FAILED, code, payload)
            gates = {item["gate"]: item for item in payload["hard_gate_failures"]}
            self.assertIn("claim_strength_cap", gates)
            report = payload["record"]["claim_verification"]
            self.assertEqual("stale", report["claims"][0]["verification_status"])
            self.assertEqual("weak", report["max_claim_strength"])

    def test_contradicted_source_routes_to_skeptic_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            task_dir = write_task(ops_dir)
            write_evidence(ops_dir, text="The fixture source reports no measurable increase.\n")
            write_json(
                task_dir / "artifacts" / "claim_verification.json",
                {"claims": [claim_payload(quote="no measurable increase", support_status="contradicted")]},
            )

            code, payload = run_json(validate_result_acceptance, [task_dir, "--ops-dir", ops_dir])

            self.assertEqual(validate_result_acceptance.VALIDATION_FAILED, code, payload)
            report = payload["record"]["claim_verification"]
            self.assertTrue(report["skeptic_review_required"])
            self.assertEqual("contradicted", report["claims"][0]["verification_status"])
            followups = [item["reason"] for item in payload["record"]["followups"]]
            self.assertTrue(any("skeptic review" in item for item in followups))

    def test_numeric_claim_without_computation_artifact_is_unverifiable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            task_dir = write_task(ops_dir)
            write_evidence(ops_dir, adapter_type="file_fetch", text="A table lists a value of 42.\n")
            write_json(
                task_dir / "artifacts" / "claim_verification.json",
                {"claims": [claim_payload(claim_type="numeric", text="The computed metric is 42.", quote="value of 42")]},
            )

            report = claim_verification.verify_task_claims(task_dir, ops_dir)

            self.assertFalse(report["acceptance_ok"])
            self.assertEqual("unverifiable", report["claims"][0]["verification_status"])
            self.assertIn("computation", report["claims"][0]["failure_reason"])

    def test_deliverable_working_paper_requires_resolved_citation_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            write_task(ops_dir, "TASK-4001")
            code, created = run_cli_json(
                [
                    "deliverable",
                    "init",
                    ops_dir,
                    "--deliverable-id",
                    "DELIV-4001",
                    "--title",
                    "Claim verification working paper",
                    "--output-type",
                    "working_paper",
                    "--target-maturity",
                    "working_paper",
                    "--current-maturity",
                    "working_paper",
                    "--target-audience",
                    "research collaborators",
                    "--target-venue",
                    "fixture venue",
                    "--source-task",
                    "TASK-4001",
                    "--complete-gate",
                    "all",
                    "--review-independence",
                    "separate_agent",
                    "--now",
                    NOW,
                ]
            )
            self.assertEqual(cli.SUCCESS, code, created)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-4001"])

            self.assertEqual(2, code, checked)
            reasons = {item["reason"] for item in checked["blockers"]}
            self.assertIn("citation_verification_unresolved", reasons)
            self.assertEqual("blocked", checked["claim_verification"]["status"])

            write_evidence(ops_dir)
            claim_path = ops_dir / "deliverables" / "claim_verification" / "DELIV-4001.json"
            write_json(claim_path, {"claims": [claim_payload()]})
            manifest_path = ops_dir / "deliverables" / "deliverable_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["deliverables"][0]["claim_verification_path"] = "research_ops/deliverables/claim_verification/DELIV-4001.json"
            write_json(manifest_path, manifest)

            code, checked = run_cli_json(["deliverable", "check", ops_dir, "DELIV-4001"])

            self.assertEqual(2, code, checked)
            reasons = {item["reason"] for item in checked["blockers"]}
            self.assertNotIn("citation_verification_unresolved", reasons)
            self.assertEqual("pass", checked["claim_verification"]["status"])


if __name__ == "__main__":
    unittest.main()

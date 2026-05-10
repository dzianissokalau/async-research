"""Phase 7 regression tests for analysis result acceptance integration."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from async_research_workflow.scripts import update_accepted_outputs_index, validate_result_acceptance

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_analysis_preflight import NOW, create_fixture_workspace, run_json, write_json
from test_analysis_validation import analysis_robustness, completed_manifest, write_completed_artifacts


def accept_analysis_task(analysis_dir: Path, *, status_value: str = "accepted", claim_strength: str = "moderate") -> None:
    status = json.loads((analysis_dir / "status.json").read_text(encoding="utf-8"))
    status.update(
        {
            "status": status_value,
            "previous_status": "panel_review",
            "last_transition_reason": "phase_7_result_acceptance_fixture",
            "updated_at": NOW,
            "result": {
                "recommendation": "ready" if status_value == "accepted" else "reject",
                "claim_strength": claim_strength,
                "key_finding": "The candidate feature improves predictive accuracy in this bounded backtest.",
                "followup_count": 0,
            },
        }
    )
    write_json(analysis_dir / "status.json", status)
    write_json(
        analysis_dir / "review_panel" / "aggregate.json",
        {
            "aggregate_decision": "accepted" if status_value == "accepted" else "rejected",
            "aggregate_claim_strength": claim_strength,
            "tier": 2,
            "required_reviewers": ["primary", "methodology"],
            "reviews": [
                {
                    "reviewer_role": "primary",
                    "decision": "accept" if status_value == "accepted" else "reject",
                    "claim_strength": claim_strength,
                }
            ],
            "disagreements": ["none"],
        },
    )


class AnalysisResultAcceptanceIntegrationTests(unittest.TestCase):
    def test_accepted_analysis_result_records_run_artifacts_and_ledger_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir)
            accept_analysis_task(analysis_dir)

            code, payload = run_json(
                validate_result_acceptance,
                [analysis_dir, "--ops-dir", ops_dir, "--write", "--update-ledgers"],
            )

            self.assertEqual(validate_result_acceptance.SUCCESS, code, payload)
            record = json.loads((analysis_dir / "review_panel" / "result_acceptance.json").read_text(encoding="utf-8"))
            self.assertEqual("predictive", record["accepted_memory"]["claim_type"])
            self.assertEqual("moderate", record["claim_strength"])
            self.assertEqual("moderate", record["max_claim_strength"])
            self.assertTrue(record["analysis_run"]["validation"]["ok"])
            self.assertEqual("RUN-8002", record["analysis_run"]["run_id"])
            self.assertTrue(record["analysis_run"]["data_versions"])
            self.assertIn("diagnostics.json", record["analysis_run"]["diagnostics"]["path"])
            self.assertEqual("accepted", record["analysis_run"]["claim_gates"]["computed"]["claim_decision"])

            ledger_text = (ops_dir / "evidence_ledger.md").read_text(encoding="utf-8")
            self.assertIn("claim_type", ledger_text)
            self.assertIn("predictive", ledger_text)
            self.assertIn("run_manifest.json", ledger_text)
            self.assertIn("diagnostics.json", ledger_text)
            self.assertIn("claim_gates.json", ledger_text)

            code, index_payload = run_json(update_accepted_outputs_index, ["update", ops_dir, "--now", NOW])
            self.assertEqual(update_accepted_outputs_index.SUCCESS, code, index_payload)
            rows = update_accepted_outputs_index.read_index_rows(ops_dir / "accepted_outputs_index.md")
            row = next(item for item in rows if item["task_id"] == "TASK-8002")
            self.assertEqual("predictive", row["claim_type"])
            self.assertEqual("moderate", row["claim_strength"])

    def test_stale_analysis_data_marks_accepted_memory_for_revalidation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            manifest = completed_manifest()
            manifest["data_versions"][0]["accessed_at"] = "2025-01-01"
            write_completed_artifacts(analysis_dir, manifest=manifest)
            accept_analysis_task(analysis_dir)

            code, payload = run_json(
                validate_result_acceptance,
                [analysis_dir, "--ops-dir", ops_dir, "--write", "--update-ledgers"],
            )

            self.assertEqual(validate_result_acceptance.SUCCESS, code, payload)
            record = json.loads((analysis_dir / "review_panel" / "result_acceptance.json").read_text(encoding="utf-8"))
            self.assertEqual("stale", record["accepted_memory"]["revalidation_status"])
            triggers = {item["trigger"] for item in record["analysis_run"]["revalidation_triggers"]}
            self.assertIn("stale_data_version", triggers)
            self.assertTrue(any(item["gate"] == "analysis_revalidation_trigger" for item in payload["warnings"]))

            code, _index_payload = run_json(update_accepted_outputs_index, ["update", ops_dir, "--now", NOW])
            self.assertEqual(update_accepted_outputs_index.SUCCESS, code)
            rows = update_accepted_outputs_index.read_index_rows(ops_dir / "accepted_outputs_index.md")
            row = next(item for item in rows if item["task_id"] == "TASK-8002")
            self.assertEqual("stale", row["revalidation_status"])

    def test_missing_claim_gates_blocks_accepted_empirical_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir)
            accept_analysis_task(analysis_dir)
            (analysis_dir / "artifacts" / "analysis_run" / "claim_gates.json").unlink()

            code, payload = run_json(validate_result_acceptance, [analysis_dir, "--ops-dir", ops_dir])

            self.assertEqual(validate_result_acceptance.VALIDATION_FAILED, code, payload)
            gates = {item["gate"]: item for item in payload["hard_gate_failures"]}
            self.assertIn("analysis_run_artifacts_valid", gates)
            self.assertIn("claim_gates.json", gates["analysis_run_artifacts_valid"]["reason"])

    def test_claim_gate_caps_block_overstated_result_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            robustness = analysis_robustness()
            robustness["planned_checks"][0]["decision_impact"] = "caps_claim"
            robustness["planned_checks"][0]["status"] = "warn"
            write_completed_artifacts(analysis_dir, robustness=robustness)
            accept_analysis_task(analysis_dir, claim_strength="moderate")

            code, payload = run_json(validate_result_acceptance, [analysis_dir, "--ops-dir", ops_dir])

            self.assertEqual(validate_result_acceptance.VALIDATION_FAILED, code, payload)
            gates = {item["gate"]: item for item in payload["hard_gate_failures"]}
            self.assertIn("claim_strength_cap", gates)
            self.assertIn("suggestive", gates["claim_strength_cap"]["reason"])

    def test_rejected_empirical_result_preserves_anti_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir)
            accept_analysis_task(analysis_dir, status_value="rejected", claim_strength="none")

            code, payload = run_json(
                validate_result_acceptance,
                [analysis_dir, "--ops-dir", ops_dir, "--write", "--update-ledgers"],
            )

            self.assertEqual(validate_result_acceptance.SUCCESS, code, payload)
            self.assertEqual("reject", payload["route"])
            rejected_text = (ops_dir / "rejected_results.md").read_text(encoding="utf-8")
            self.assertIn("anti_context", rejected_text)
            self.assertIn("The candidate feature improves predictive accuracy", rejected_text)
            self.assertIn("run_manifest.json", rejected_text)
            self.assertIn("diagnostics.json", rejected_text)


if __name__ == "__main__":
    unittest.main()

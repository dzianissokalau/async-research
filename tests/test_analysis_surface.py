"""Phase 8 regression tests for read-only analysis surfaces."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.scripts import (
    analysis_surface,
    autonomy_readiness_gate,
    health_check,
    human_review_surface,
    validate_result_acceptance,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_analysis_preflight import NOW, create_fixture_workspace, run_json, task_status, valid_manifest, write_accepted_index, write_json
from test_analysis_result_acceptance_integration import accept_analysis_task
from test_analysis_validation import analysis_robustness, completed_manifest, write_completed_artifacts


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def update_status(task_dir: Path, **updates) -> None:
    status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
    status.update(updates)
    write_json(task_dir / "status.json", status)


class AnalysisSurfaceTests(unittest.TestCase):
    def test_dashboard_lists_safe_active_analysis_and_preserves_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            watched = [
                analysis_dir / "status.json",
                analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json",
                ops_dir / "weekly_digest.md",
            ]
            before = {path: path.read_text(encoding="utf-8") for path in watched if path.exists()}

            code, payload = run_json(analysis_surface, ["dashboard", ops_dir, "--now", NOW])

            self.assertEqual(analysis_surface.SUCCESS, code, payload)
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])
            self.assertEqual(1, payload["summary"]["active_run_analysis_count"])
            self.assertEqual(1, payload["summary"]["safe_to_run_count"])
            self.assertEqual(["TASK-8002"], payload["operator_summary"]["safe_to_run_task_ids"])
            after = {path: path.read_text(encoding="utf-8") for path in watched if path.exists()}
            self.assertEqual(before, after)

    def test_dashboard_surfaces_preflight_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, _analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_accepted_index(
                ops_dir,
                [
                    {
                        "accepted_date": "2025-01-01",
                        "task_id": "TASK-8001",
                        "title": "Stale accepted fixture experiment plan",
                        "key_finding": "Fixture plan is stale.",
                        "claim_type": "general",
                        "freshness_window_days": "30",
                        "next_recheck_date": "2025-02-01",
                        "revalidation_status": "stale",
                        "source_ids": "DS-0001",
                        "claim_strength": "none",
                        "caveats": "stale",
                        "followups": "refresh",
                        "supersedes": "none",
                        "superseded_by": "none",
                        "evidence_link": "research_ops/tasks/TASK-8001-experiment-plan/worker_output.md",
                    }
                ],
                include_default=False,
            )

            code, payload = run_json(analysis_surface, ["dashboard", ops_dir, "--now", NOW])

            self.assertEqual(analysis_surface.VALIDATION_FINDINGS, code, payload)
            self.assertEqual(1, payload["summary"]["preflight_blocked_count"])
            blockers = payload["sections"]["preflight_blockers"][0]["blockers"]
            self.assertIn("accepted_plan_current", {item["gate"] for item in blockers})

    def test_dashboard_surfaces_completed_runs_missing_result_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            write_completed_artifacts(analysis_dir)
            update_status(analysis_dir, status="awaiting_review", previous_status="in_progress")
            (analysis_dir / "artifacts" / "analysis_run" / "claim_gates.json").unlink()

            code, payload = run_json(analysis_surface, ["dashboard", ops_dir, "--now", NOW])

            self.assertEqual(analysis_surface.VALIDATION_FINDINGS, code, payload)
            self.assertEqual(1, payload["summary"]["completed_missing_validation_count"])
            missing = payload["sections"]["completed_runs_missing_validation"][0]
            self.assertEqual("TASK-8002", missing["task_id"])
            self.assertFalse(missing["validate_results_ok"])

    def test_review_stage_analysis_with_missing_manifest_is_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            update_status(analysis_dir, status="awaiting_review", previous_status="in_progress")
            (analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json").unlink()

            code, payload = run_json(analysis_surface, ["dashboard", ops_dir, "--now", NOW])

            self.assertEqual(analysis_surface.MALFORMED, code, payload)
            self.assertEqual(1, payload["summary"]["completed_missing_validation_count"])
            self.assertEqual(1, payload["summary"]["malformed_read_model_count"])
            malformed = payload["sections"]["malformed_read_model_inputs"][0]
            self.assertEqual("TASK-8002", malformed["task_id"])
            self.assertEqual("run_manifest_missing", malformed["reason"])

    def test_active_analysis_malformed_preflight_propagates_dashboard_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            manifest_path = analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json"
            manifest_path.write_text("{not json", encoding="utf-8")

            code, payload = run_json(analysis_surface, ["dashboard", ops_dir, "--now", NOW])

            self.assertEqual(analysis_surface.MALFORMED, code, payload)
            self.assertEqual(1, payload["summary"]["preflight_blocked_count"])
            self.assertEqual(1, payload["summary"]["malformed_read_model_count"])
            malformed = payload["sections"]["malformed_read_model_inputs"][0]
            self.assertEqual("analysis_preflight_malformed", malformed["reason"])

    def test_dashboard_surfaces_accepted_empirical_evidence_and_revalidation(self) -> None:
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

            code, dashboard = run_json(analysis_surface, ["dashboard", ops_dir, "--now", NOW])

            self.assertEqual(analysis_surface.VALIDATION_FINDINGS, code, dashboard)
            self.assertEqual(1, dashboard["summary"]["accepted_empirical_evidence_count"])
            self.assertEqual(1, dashboard["summary"]["revalidation_needed_count"])
            evidence = dashboard["sections"]["accepted_empirical_evidence"][0]
            self.assertEqual("predictive", evidence["claim_type"])
            self.assertEqual("stale", evidence["revalidation_status"])

    def test_dashboard_rejects_invalid_accepted_empirical_result_acceptance(self) -> None:
        cases = [
            ("route", lambda record: record.update({"route": "reject"}), "result_acceptance_route"),
            ("task_id", lambda record: record.update({"task_id": "TASK-8999"}), "result_acceptance_task_identity"),
            ("task_type", lambda record: record.update({"task_type": "evaluate_results"}), "result_acceptance_task_type"),
            ("analysis_run", lambda record: record.update({"analysis_run": None}), "analysis_run_provenance"),
        ]
        for label, mutate, expected_gate in cases:
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as tmpdir:
                    ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
                    write_completed_artifacts(analysis_dir)
                    accept_analysis_task(analysis_dir)
                    code, payload = run_json(validate_result_acceptance, [analysis_dir, "--ops-dir", ops_dir, "--write"])
                    self.assertEqual(validate_result_acceptance.SUCCESS, code, payload)
                    record_path = analysis_dir / "review_panel" / "result_acceptance.json"
                    record = json.loads(record_path.read_text(encoding="utf-8"))
                    mutate(record)
                    write_json(record_path, record)

                    code, dashboard = run_json(analysis_surface, ["dashboard", ops_dir, "--now", NOW])

                    self.assertEqual(analysis_surface.MALFORMED, code, dashboard)
                    self.assertEqual(0, dashboard["summary"]["accepted_empirical_evidence_count"])
                    self.assertEqual(1, dashboard["summary"]["malformed_read_model_count"])
                    malformed = dashboard["sections"]["malformed_read_model_inputs"][0]
                    self.assertEqual("result_acceptance_invalid", malformed["reason"])
                    self.assertIn(expected_gate, {item["gate"] for item in malformed["blockers"]})

    def test_dashboard_surfaces_capped_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            robustness = analysis_robustness()
            robustness["planned_checks"][0]["decision_impact"] = "caps_claim"
            robustness["planned_checks"][0]["status"] = "warn"
            write_completed_artifacts(analysis_dir, robustness=robustness)
            update_status(analysis_dir, status="awaiting_review", previous_status="in_progress")

            code, payload = run_json(analysis_surface, ["dashboard", ops_dir, "--now", NOW])

            self.assertEqual(analysis_surface.VALIDATION_FINDINGS, code, payload)
            self.assertEqual(1, payload["summary"]["claim_caps_or_human_review_count"])
            attention = payload["sections"]["claim_caps_and_human_review"][0]
            self.assertEqual("capped", attention["claim_decision"])

    def test_dashboard_surfaces_rejected_and_needs_human_claim_gates(self) -> None:
        cases = [
            ("rejected", "reject", {"required": False, "satisfied": True, "reason": "fixture rejection"}),
            ("needs_human", "needs_human", {"required": True, "satisfied": False, "reason": "fixture human review"}),
        ]
        for decision, route, human_gate in cases:
            with self.subTest(decision=decision):
                with tempfile.TemporaryDirectory() as tmpdir:
                    ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
                    write_completed_artifacts(analysis_dir)
                    update_status(analysis_dir, status="awaiting_review", previous_status="in_progress")
                    claim_path = analysis_dir / "artifacts" / "analysis_run" / "claim_gates.json"
                    claim_gates = json.loads(claim_path.read_text(encoding="utf-8"))
                    claim_gates.update(
                        {
                            "claim_decision": decision,
                            "recommended_route": route,
                            "max_claim_strength": "none",
                            "cap_reasons": ["fixture blocks claim"],
                            "human_gate": human_gate,
                        }
                    )
                    write_json(claim_path, claim_gates)

                    code, payload = run_json(analysis_surface, ["dashboard", ops_dir, "--now", NOW])

                    self.assertEqual(analysis_surface.VALIDATION_FINDINGS, code, payload)
                    self.assertEqual(1, payload["summary"]["claim_caps_or_human_review_count"])
                    attention = payload["sections"]["claim_caps_and_human_review"][0]
                    self.assertEqual(decision, attention["claim_decision"])

    def test_cli_analysis_dashboard_routes_to_surface_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, _analysis_dir = create_fixture_workspace(Path(tmpdir))

            code, payload = run_cli_json(["analysis", "dashboard", ops_dir, "--now", NOW])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertEqual("analysis_dashboard_rendered", payload["action"])
            self.assertTrue(payload["read_only"])

    def test_surface_update_writes_analysis_digest_without_mutating_task_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            manifest_path = analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json"
            status_path = analysis_dir / "status.json"
            before_manifest = manifest_path.read_text(encoding="utf-8")
            before_status = status_path.read_text(encoding="utf-8")

            code, payload = run_json(human_review_surface, ["update", ops_dir, "--now", NOW])

            self.assertEqual(human_review_surface.SUCCESS, code, payload)
            weekly = (ops_dir / "weekly_digest.md").read_text(encoding="utf-8")
            daily = (ops_dir / "daily_status.md").read_text(encoding="utf-8")
            self.assertIn("## Analysis Surface", weekly)
            self.assertIn("Safe to run: 1", weekly)
            self.assertIn("## Analysis Surface", daily)
            self.assertEqual(before_manifest, manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(before_status, status_path.read_text(encoding="utf-8"))

    def test_surface_update_preserves_task_artifacts_with_malformed_analysis_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            manifest_path = analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json"
            status_path = analysis_dir / "status.json"
            manifest_path.write_text("{not json", encoding="utf-8")
            before_manifest = manifest_path.read_text(encoding="utf-8")
            before_status = status_path.read_text(encoding="utf-8")

            code, payload = run_json(human_review_surface, ["update", ops_dir, "--now", NOW])

            self.assertEqual(human_review_surface.SUCCESS, code, payload)
            weekly = (ops_dir / "weekly_digest.md").read_text(encoding="utf-8")
            self.assertIn("Malformed inputs: 1", weekly)
            self.assertEqual(before_manifest, manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(before_status, status_path.read_text(encoding="utf-8"))

    def test_health_and_readiness_include_analysis_surface_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))
            status = task_status("TASK-8002", "run_analysis", "ready_for_worker", ["DS-0001"])
            write_json(analysis_dir / "status.json", status)
            manifest = valid_manifest()
            manifest["accepted_plan_task_id"] = "TASK-8999"
            manifest["accepted_plan_path"] = "research_ops/tasks/TASK-8999-experiment-plan/worker_output.md"
            manifest["accepted_plan_result_acceptance_path"] = "research_ops/tasks/TASK-8999-experiment-plan/review_panel/result_acceptance.json"
            write_json(analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json", manifest)

            health_report = health_check.build_report(
                health_check.parse_args([str(ops_dir), "--dry-run", "--now", NOW])
            )
            readiness_report, readiness_code = autonomy_readiness_gate.build_gate_report(
                autonomy_readiness_gate.parse_args([str(ops_dir), "--dry-run", "--now", NOW])
            )

            self.assertIn("analysis_surface", health_report["checks"])
            self.assertIn("analysis_preflight_blockers", {alert["check"] for alert in health_report["alerts"]})
            self.assertIn("analysis_surface", readiness_report["checks"])
            self.assertIn("analysis_preflight_blockers", {blocker["check"] for blocker in readiness_report["blockers"]})
            self.assertEqual(autonomy_readiness_gate.HUMAN_REQUIRED, readiness_code)


if __name__ == "__main__":
    unittest.main()

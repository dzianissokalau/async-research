"""Regression tests for trace-driven runtime eval suites."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


NOW = "2026-05-20T11:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_task(ops_dir: Path) -> Path:
    task_dir = ops_dir / "tasks" / "TASK-5001-runtime-eval"
    status = {
        "schema_version": "1.0",
        "id": "TASK-5001",
        "title": "Runtime eval fixture",
        "type": "literature_extract",
        "status": "accepted",
        "previous_status": "panel_review",
        "last_transition_reason": "eval_fixture",
        "priority": 2,
        "revision_count": 0,
        "max_revisions": 1,
        "revision_limit_hit": False,
        "allowed_paths": [
            "research_ops/tasks/TASK-5001-runtime-eval/**",
            "research_ops/runtime/**",
            "research_ops/sources/**",
        ],
        "allowed_tools": ["runtime:file_fetch"],
        "allow_browsing": False,
        "allow_code_execution": False,
        "allow_network": False,
        "max_minutes": 10,
        "requires_human": False,
        "budget": {"max_api_usd": 0.0, "max_compute_usd": 0.0},
        "human_gate_reason": None,
        "runtime_permissions": {
            "max_calls": 1,
            "max_api_usd": 0.0,
            "max_compute_usd": 0.0,
            "allowed_domains": [],
            "allowed_api_names": [],
            "allow_credentials": False,
            "allow_paid_calls": False,
        },
        "result": {
            "claim_strength": "suggestive",
            "key_finding": "The eval fixture source reports grounded evidence.",
        },
    }
    write_json(task_dir / "status.json", status)
    write_json(
        task_dir / "review_panel" / "aggregate.json",
        {
            "aggregate_decision": "accepted",
            "aggregate_claim_strength": "suggestive",
            "tier": 1,
            "required_reviewers": ["primary"],
            "reviews": [{"reviewer_role": "primary", "decision": "accept", "claim_strength": "suggestive"}],
            "disagreements": ["none"],
        },
    )
    (task_dir / "worker_output.md").write_text(
        "The eval fixture source reports grounded evidence.\n",
        encoding="utf-8",
    )
    return task_dir


def init_eval_workspace(root: Path) -> tuple[Path, Path]:
    ops_dir = root / "research_ops"
    code, payload = run_cli_json(["init", ops_dir, "--template", "generic", "--force"])
    if code != cli.SUCCESS:
        raise AssertionError(payload)
    task_dir = write_task(ops_dir)
    sources_dir = ops_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    (sources_dir / "eval-source.md").write_text(
        "The eval fixture source reports grounded evidence.\n",
        encoding="utf-8",
    )
    request_path = root / "runtime_request.json"
    write_json(
        request_path,
        {
            "mode": "single_task",
            "task_id": "TASK-5001",
            "calls": [
                {
                    "adapter_type": "file_fetch",
                    "source_path": "research_ops/sources/eval-source.md",
                    "source_title": "Eval fixture source",
                    "license_or_use_policy": "fixture-only",
                    "selector": "line:1",
                }
            ],
        },
    )
    execute_code, executed = run_cli_json(["runtime", "execute", ops_dir, "--request", request_path, "--now", NOW])
    if execute_code != cli.SUCCESS:
        raise AssertionError(executed)
    write_json(
        task_dir / "artifacts" / "claim_verification.json",
        {
            "claims": [
                {
                    "claim_id": "CLM-5001",
                    "text": "The eval fixture source reports grounded evidence.",
                    "claim_type": "empirical",
                    "strength": "moderate",
                    "required_support_level": "direct",
                    "evidence_refs": [
                        {
                            "evidence_id": "EVID-000001",
                            "span_ref": "SPAN-0001",
                            "quote_or_paraphrase_status": "quote",
                            "quote": "grounded evidence",
                            "support_status": "supports",
                        }
                    ],
                    "citation_refs": ["EVID-000001#SPAN-0001"],
                }
            ]
        },
    )
    acceptance_code, accepted = run_cli_json(["result-acceptance", task_dir, "--ops-dir", ops_dir, "--write", "--update-ledgers"])
    if acceptance_code != cli.SUCCESS:
        raise AssertionError(accepted)
    return ops_dir, task_dir


class RuntimeEvalTests(unittest.TestCase):
    def test_build_run_compare_and_dashboard_from_fixture_traces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir, _task_dir = init_eval_workspace(Path(tmp))

            build_code, built = run_cli_json(
                [
                    "eval",
                    "build-from-traces",
                    ops_dir,
                    "--suite-id",
                    "fixture-suite",
                    "--write",
                    "--now",
                    NOW,
                    "--runtime-policy",
                    "fixture_runtime_policy",
                    "--model-routing-policy",
                    "fixture_model_policy",
                ]
            )

            self.assertEqual(cli.SUCCESS, build_code, built)
            suite = built["suite"]
            self.assertEqual("runtime_eval_suite_v1.0", suite["framework_version"])
            self.assertEqual(1, suite["case_count"])
            self.assertEqual(["TRACE-000001"], suite["cases"][0]["source_trace_ids"])
            self.assertEqual(["EVID-000001"], suite["cases"][0]["expected_behavior"]["required_evidence_ids"])
            self.assertEqual([], [error.to_dict() for error in validate(suite, load_json(schema_path("runtime_eval_suite.schema.json")))])
            suite_path = Path(built["suite_path"])
            self.assertTrue(suite_path.is_file())

            run_code, run = run_cli_json(["eval", "run", suite_path, "--run-id", "fixture-run", "--write", "--now", NOW])

            self.assertEqual(cli.SUCCESS, run_code, run)
            self.assertEqual("pass", run["status"])
            self.assertEqual(1.0, run["metrics"]["grounded_claim_rate"])
            self.assertEqual(0.0, run["metrics"]["unsupported_claim_rate"])
            self.assertEqual(1.0, run["metrics"]["accepted_output_rate"])
            self.assertEqual([], [error.to_dict() for error in validate(run, load_json(schema_path("runtime_eval_run.schema.json")))])
            run_path = ops_dir / "evals" / "runs" / "fixture-run.json"
            self.assertTrue(run_path.is_file())

            compare_code, compared = run_cli_json(["eval", "compare", run_path, run_path])
            self.assertEqual(cli.SUCCESS, compare_code, compared)
            self.assertEqual("pass", compared["verdict"])

            snapshot_code, snapshot = run_cli_json(["console", "snapshot", ops_dir, "--json", "--now", NOW])
            self.assertEqual(cli.SUCCESS, snapshot_code, snapshot)
            self.assertEqual(1, snapshot["evals"]["suite_count"])
            self.assertEqual(1, snapshot["evals"]["run_count"])
            self.assertEqual("pass", snapshot["evals"]["latest_run"]["status"])
            self.assertEqual(1.0, snapshot["evals"]["metrics"]["grounded_claim_rate"])

    def test_eval_run_fails_when_snapshot_hash_no_longer_matches_suite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir, _task_dir = init_eval_workspace(Path(tmp))
            build_code, built = run_cli_json(["eval", "build-from-traces", ops_dir, "--suite-id", "hash-suite", "--write", "--now", NOW])
            self.assertEqual(cli.SUCCESS, build_code, built)
            snapshot_path = ops_dir / "runtime" / "snapshots" / "EVID-000001.txt"
            snapshot_path.write_text("Changed after suite build.\n", encoding="utf-8")

            run_code, run = run_cli_json(["eval", "run", Path(built["suite_path"]), "--run-id", "hash-run", "--now", NOW])

            self.assertEqual(2, run_code, run)
            self.assertEqual("fail", run["status"])
            reasons = {finding["reason"] for finding in run["case_results"][0]["findings"]}
            self.assertIn("snapshot_hash_mismatch", reasons)

    def test_compare_blocks_regressed_candidate_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir, _task_dir = init_eval_workspace(Path(tmp))
            build_code, built = run_cli_json(["eval", "build-from-traces", ops_dir, "--suite-id", "compare-suite", "--write", "--now", NOW])
            self.assertEqual(cli.SUCCESS, build_code, built)
            run_code, baseline = run_cli_json(["eval", "run", Path(built["suite_path"]), "--run-id", "baseline-run", "--write", "--now", NOW])
            self.assertEqual(cli.SUCCESS, run_code, baseline)
            candidate = json.loads(json.dumps(baseline))
            candidate["run_id"] = "candidate-run"
            candidate["metrics"]["grounded_claim_rate"] = 0.0
            candidate["metrics"]["unsupported_claim_rate"] = 1.0
            candidate_path = ops_dir / "evals" / "runs" / "candidate-run.json"
            write_json(candidate_path, candidate)
            baseline_path = ops_dir / "evals" / "runs" / "baseline-run.json"

            compare_code, compared = run_cli_json(["eval", "compare", baseline_path, candidate_path])

            self.assertEqual(2, compare_code, compared)
            self.assertEqual("fail", compared["verdict"])
            regressed = {item["metric"] for item in compared["errors"] if item["reason"] == "metric_regressed"}
            self.assertIn("grounded_claim_rate", regressed)
            self.assertIn("unsupported_claim_rate", regressed)

    def test_build_from_traces_refuses_output_outside_research_ops_evals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir, _task_dir = init_eval_workspace(Path(tmp))
            unsafe = Path(tmp) / "outside.json"

            code, payload = run_cli_json(["eval", "build-from-traces", ops_dir, "--output", unsafe, "--write"])

            self.assertEqual(3, code, payload)
            self.assertEqual("unsafe_output_path", payload["reason"])
            self.assertFalse(unsafe.exists())


if __name__ == "__main__":
    unittest.main()

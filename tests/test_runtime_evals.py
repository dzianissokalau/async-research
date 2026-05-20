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


def write_route_task(
    ops_dir: Path,
    task_id: str,
    slug: str,
    *,
    allowed_tools: list[str],
    allow_network: bool,
    allow_browsing: bool,
    allowed_domains: list[str] | None = None,
    allowed_api_names: list[str] | None = None,
    max_calls: int = 1,
    budget_usd: float = 0.0,
) -> Path:
    task_dir = ops_dir / "tasks" / f"{task_id}-{slug}"
    status = {
        "schema_version": "1.0",
        "id": task_id,
        "title": f"Routing eval {slug}",
        "type": "literature_extract",
        "status": "accepted",
        "previous_status": "panel_review",
        "last_transition_reason": "routing_eval_fixture",
        "priority": 2,
        "revision_count": 0,
        "max_revisions": 1,
        "revision_limit_hit": False,
        "allowed_paths": [
            f"research_ops/tasks/{task_id}-{slug}/**",
            "research_ops/runtime/**",
            "research_ops/sources/**",
        ],
        "allowed_tools": allowed_tools,
        "allow_browsing": allow_browsing,
        "allow_code_execution": False,
        "allow_network": allow_network,
        "max_minutes": 10,
        "requires_human": False,
        "budget": {"max_api_usd": budget_usd, "max_compute_usd": 0.0},
        "human_gate_reason": None,
        "runtime_permissions": {
            "max_calls": max_calls,
            "max_api_usd": budget_usd,
            "max_compute_usd": 0.0,
            "allowed_domains": allowed_domains or [],
            "allowed_api_names": allowed_api_names or [],
            "allow_credentials": False,
            "allow_paid_calls": budget_usd > 0,
        },
        "result": {
            "claim_strength": "suggestive",
            "key_finding": f"Routing eval {slug} produced auditable evidence.",
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
    return task_dir


def execute_runtime_request(ops_dir: Path, root: Path, name: str, request: dict) -> dict:
    request_path = root / f"{name}.json"
    write_json(request_path, request)
    code, payload = run_cli_json(["runtime", "execute", ops_dir, "--request", request_path, "--now", NOW])
    if code != cli.SUCCESS:
        raise AssertionError(payload)
    return payload


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
            self.assertEqual(1, suite["cases"][0]["metrics"]["route_decision_count"])
            self.assertEqual("local_or_private", suite["cases"][0]["metrics"]["source_route_pattern"])
            self.assertEqual("source_routing", suite["cases"][0]["grader"]["checks"][3])
            self.assertEqual([], [error.to_dict() for error in validate(suite, load_json(schema_path("runtime_eval_suite.schema.json")))])
            suite_path = Path(built["suite_path"])
            self.assertTrue(suite_path.is_file())

            run_code, run = run_cli_json(["eval", "run", suite_path, "--run-id", "fixture-run", "--write", "--now", NOW])

            self.assertEqual(cli.SUCCESS, run_code, run)
            self.assertEqual("pass", run["status"])
            self.assertEqual(1.0, run["metrics"]["grounded_claim_rate"])
            self.assertEqual(0.0, run["metrics"]["unsupported_claim_rate"])
            self.assertEqual(1.0, run["metrics"]["accepted_output_rate"])
            self.assertEqual(1, run["metrics"]["route_decision_count"])
            check_names = [check["name"] for check in run["case_results"][0]["checks"]]
            self.assertIn("source_routing", check_names)
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

    def test_build_from_traces_compares_api_browser_and_hybrid_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ops_dir = root / "research_ops"
            code, payload = run_cli_json(["init", ops_dir, "--template", "generic", "--force"])
            self.assertEqual(cli.SUCCESS, code, payload)

            write_route_task(
                ops_dir,
                "TASK-5101",
                "api-only",
                allowed_tools=["runtime:api_query"],
                allow_network=True,
                allow_browsing=False,
                allowed_api_names=["fixture_stats"],
            )
            execute_runtime_request(
                ops_dir,
                root,
                "api_only_route",
                {
                    "mode": "single_task",
                    "task_id": "TASK-5101",
                    "calls": [
                        {
                            "adapter_type": "api_query",
                            "api_name": "fixture_stats",
                            "source_profile": "statistical_api",
                            "source_class": "official_api",
                            "route_reason": "Official API has the complete fixture metric.",
                            "license_or_use_policy": "fixture-only",
                            "mock_response": {
                                "source_uri": "mock://fixture_stats/api-only",
                                "source_title": "Fixture stats API",
                                "license_or_use_policy": "fixture-only",
                                "content": "metric=42\n",
                            },
                        }
                    ],
                },
            )

            write_route_task(
                ops_dir,
                "TASK-5102",
                "browser-only",
                allowed_tools=["runtime:web_open"],
                allow_network=True,
                allow_browsing=True,
                allowed_domains=["example.org"],
                budget_usd=0.02,
            )
            execute_runtime_request(
                ops_dir,
                root,
                "browser_only_route",
                {
                    "mode": "single_task",
                    "task_id": "TASK-5102",
                    "calls": [
                        {
                            "adapter_type": "web_open",
                            "source_uri": "https://example.org/report",
                            "domain": "example.org",
                            "source_class": "official_page",
                            "source_profile": "document_repository",
                            "browser_fallback_reason": "api_unavailable",
                            "route_reason": "No structured endpoint is available for this fixture.",
                            "estimated_cost": {"api_usd": 0.02, "compute_usd": 0.0, "tokens": 0},
                            "license_or_use_policy": "fixture-only",
                            "mock_response": {
                                "source_uri": "https://example.org/report",
                                "source_title": "Browser fixture report",
                                "license_or_use_policy": "fixture-only",
                                "content": "browser route evidence\n",
                            },
                        }
                    ],
                },
            )

            write_route_task(
                ops_dir,
                "TASK-5103",
                "hybrid",
                allowed_tools=["runtime:api_query", "runtime:web_open"],
                allow_network=True,
                allow_browsing=True,
                allowed_domains=["example.org"],
                allowed_api_names=["fixture_stats"],
                max_calls=2,
                budget_usd=0.01,
            )
            execute_runtime_request(
                ops_dir,
                root,
                "hybrid_route",
                {
                    "mode": "single_task",
                    "task_id": "TASK-5103",
                    "calls": [
                        {
                            "adapter_type": "api_query",
                            "api_name": "fixture_stats",
                            "source_profile": "statistical_api",
                            "source_class": "official_api",
                            "route_reason": "Use structured metrics from the official API first.",
                            "license_or_use_policy": "fixture-only",
                            "mock_response": {
                                "source_uri": "mock://fixture_stats/hybrid",
                                "source_title": "Fixture stats API",
                                "license_or_use_policy": "fixture-only",
                                "content": "metric=42\n",
                            },
                        },
                        {
                            "adapter_type": "web_open",
                            "source_uri": "https://example.org/context",
                            "domain": "example.org",
                            "source_class": "official_page",
                            "source_profile": "document_repository",
                            "browser_fallback_reason": "human_context_required",
                            "route_reason": "Use the official page only for interpretive context.",
                            "route_alternatives": [
                                {
                                    "adapter_type": "api_query",
                                    "source_class": "official_api",
                                    "rejection_reason": "The API answered metrics but not the contextual note.",
                                }
                            ],
                            "estimated_cost": {"api_usd": 0.01, "compute_usd": 0.0, "tokens": 0},
                            "license_or_use_policy": "fixture-only",
                            "mock_response": {
                                "source_uri": "https://example.org/context",
                                "source_title": "Hybrid context page",
                                "license_or_use_policy": "fixture-only",
                                "content": "hybrid contextual evidence\n",
                            },
                        },
                    ],
                },
            )

            build_code, built = run_cli_json(["eval", "build-from-traces", ops_dir, "--suite-id", "route-suite", "--now", NOW])
            self.assertEqual(cli.SUCCESS, build_code, built)
            cases_by_pattern = {case["metrics"]["source_route_pattern"]: case for case in built["suite"]["cases"]}
            self.assertIn("api_only", cases_by_pattern)
            self.assertIn("browser_only", cases_by_pattern)
            self.assertIn("hybrid", cases_by_pattern)
            self.assertLess(
                cases_by_pattern["hybrid"]["metrics"]["cost_usd"],
                cases_by_pattern["browser_only"]["metrics"]["cost_usd"],
            )
            self.assertEqual(1, built["suite"]["metrics"]["hybrid_route_case_count"])
            self.assertEqual(2, built["suite"]["metrics"]["browser_fallback_count"])

            suite_path = ops_dir / "evals" / "route-suite.json"
            write_json(suite_path, built["suite"])
            run_code, run = run_cli_json(["eval", "run", suite_path, "--run-id", "route-run", "--now", NOW])
            self.assertEqual(cli.SUCCESS, run_code, run)
            self.assertEqual("pass", run["status"])

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

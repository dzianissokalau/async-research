"""Regression tests for provider-neutral model routing policy gates."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.scripts import model_routing


NOW = "2026-05-20T12:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def init_ops(root: Path) -> Path:
    ops_dir = root / "research_ops"
    code, payload = run_cli_json(["init", ops_dir, "--template", "generic", "--force"])
    if code != cli.SUCCESS:
        raise AssertionError(payload)
    return ops_dir


def eval_run(run_id: str, *, policy_id: str, grounded: float = 1.0, unsupported: float = 0.0, cost: float = 0.1) -> dict:
    metrics = {
        "case_count": 1,
        "grounded_claim_rate": grounded,
        "unsupported_claim_rate": unsupported,
        "task_success_rate": 1.0,
        "accepted_output_rate": 1.0,
        "cost_per_accepted_report_usd": cost,
        "median_latency_to_accepted_report_ms": 100.0,
        "freshness_failure_rate": 0.0,
        "stale_evidence_reuse_rate": 0.0,
        "reviewer_disagreement_rate": 0.0,
        "reproducibility_pass_rate": 1.0,
        "total_cost_usd": cost,
        "accepted_report_count": 1,
    }
    return {
        "ok": True,
        "schema_version": "1.0",
        "framework_version": "runtime_eval_run_v1.0",
        "action": "eval_run",
        "run_id": run_id,
        "suite_id": "routing-suite",
        "suite_path": "research_ops/evals/routing-suite.json",
        "evaluated_at": NOW,
        "status": "pass",
        "runtime_policy": "runtime_policy_v1.0",
        "model_routing_policy": policy_id,
        "human_calibration": {"status": "not_included"},
        "metrics": metrics,
        "case_results": [
            {
                "case_id": "EVAL-0001",
                "task_id": "TASK-5001",
                "status": "pass",
                "metrics": metrics,
                "checks": [],
                "findings": [],
            }
        ],
        "residual_risks": [],
        "errors": [],
        "warnings": [],
        "changed": False,
        "read_only": True,
    }


class ModelRoutingTests(unittest.TestCase):
    def test_init_dry_run_reports_policy_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))

            code, payload = run_cli_json(["model-routing", "init", ops_dir, "--now", NOW])

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["read_only"])
            self.assertFalse(payload["changed"])
            self.assertEqual("repo_first_model_routing_v1", payload["policy_id"])
            self.assertIn("planner", payload["policy"]["roles"])
            self.assertFalse((ops_dir / "prompts" / "model_routing_policy.json").exists())

    def test_init_write_validate_and_select_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))

            init_code, initialized = run_cli_json(["model-routing", "init", ops_dir, "--write", "--now", NOW])
            self.assertEqual(cli.SUCCESS, init_code, initialized)
            policy_path = ops_dir / "prompts" / "model_routing_policy.json"
            self.assertTrue(policy_path.is_file())

            validate_code, validated = run_cli_json(["model-routing", "validate", policy_path])
            self.assertEqual(cli.SUCCESS, validate_code, validated)
            self.assertEqual([], validated["errors"])

            select_code, selected = run_cli_json(
                [
                    "model-routing",
                    "select",
                    policy_path,
                    "--role",
                    "planner",
                    "--task-type",
                    "experiment_plan",
                    "--claim-strength",
                    "moderate",
                    "--public-claims",
                ]
            )

            self.assertEqual(cli.SUCCESS, select_code, selected)
            self.assertEqual("frontier", selected["route"]["model_tier"])
            reasons = {item["reason"] for item in selected["recommended_escalations"]}
            self.assertIn("public_claims", reasons)
            self.assertIn("claim_strength", reasons)
            self.assertIn("methodology_sensitive_task", reasons)

    def test_validate_rejects_provider_hardcoded_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            policy = model_routing.default_policy(now=NOW)
            policy["roles"]["planner"]["prompt_posture"] = "Always use GPT-5.5 for planning."
            policy_path = Path(tmp) / "model_routing_policy.json"
            write_json(policy_path, policy)

            code, payload = run_cli_json(["model-routing", "validate", policy_path])

            self.assertEqual(2, code, payload)
            self.assertIn("provider_hardcoded", {error["reason"] for error in payload["errors"]})

    def test_validate_rejects_newer_provider_names(self) -> None:
        for provider_name in ("deepseek-v3", "llama-3.1-70b"):
            with self.subTest(provider_name=provider_name), tempfile.TemporaryDirectory() as tmp:
                policy = model_routing.default_policy(now=NOW)
                policy["roles"]["worker"]["prompt_posture"] = f"Always route worker tasks to {provider_name}."
                policy_path = Path(tmp) / "model_routing_policy.json"
                write_json(policy_path, policy)

                code, payload = run_cli_json(["model-routing", "validate", policy_path])

                self.assertEqual(2, code, payload)
                self.assertIn("provider_hardcoded", {error["reason"] for error in payload["errors"]})

    def test_eval_check_requires_candidate_to_match_or_improve_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            init_code, initialized = run_cli_json(["model-routing", "init", ops_dir, "--write", "--now", NOW])
            self.assertEqual(cli.SUCCESS, init_code, initialized)
            policy_path = ops_dir / "prompts" / "model_routing_policy.json"
            policy_id = initialized["policy_id"]
            baseline_path = ops_dir / "evals" / "runs" / "baseline.json"
            candidate_path = ops_dir / "evals" / "runs" / "candidate.json"
            write_json(baseline_path, eval_run("baseline", policy_id="baseline_policy", cost=0.10))
            write_json(candidate_path, eval_run("candidate", policy_id=policy_id, cost=0.08))

            code, payload = run_cli_json(
                [
                    "model-routing",
                    "eval-check",
                    policy_path,
                    "--baseline",
                    baseline_path,
                    "--candidate",
                    candidate_path,
                ]
            )

            self.assertEqual(cli.SUCCESS, code, payload)
            self.assertTrue(payload["adoption_eligible"])
            self.assertEqual("pass", payload["verdict"])

            write_json(candidate_path, eval_run("candidate", policy_id=policy_id, grounded=0.0, unsupported=1.0, cost=0.08))
            code, payload = run_cli_json(
                [
                    "model-routing",
                    "eval-check",
                    policy_path,
                    "--baseline",
                    baseline_path,
                    "--candidate",
                    candidate_path,
                ]
            )

            self.assertEqual(2, code, payload)
            self.assertFalse(payload["adoption_eligible"])
            self.assertIn("metric_regressed", {error["reason"] for error in payload["errors"]})

    def test_eval_check_requires_candidate_policy_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = init_ops(Path(tmp))
            init_code, initialized = run_cli_json(["model-routing", "init", ops_dir, "--write", "--now", NOW])
            self.assertEqual(cli.SUCCESS, init_code, initialized)
            policy_path = ops_dir / "prompts" / "model_routing_policy.json"
            baseline_path = ops_dir / "evals" / "runs" / "baseline.json"
            candidate_path = ops_dir / "evals" / "runs" / "candidate.json"
            write_json(baseline_path, eval_run("baseline", policy_id="baseline_policy"))
            write_json(candidate_path, eval_run("candidate", policy_id="different_policy", cost=0.08))

            code, payload = run_cli_json(
                [
                    "model-routing",
                    "eval-check",
                    policy_path,
                    "--baseline",
                    baseline_path,
                    "--candidate",
                    candidate_path,
                ]
            )

            self.assertEqual(2, code, payload)
            self.assertIn("candidate_policy_mismatch", {error["reason"] for error in payload["errors"]})


if __name__ == "__main__":
    unittest.main()

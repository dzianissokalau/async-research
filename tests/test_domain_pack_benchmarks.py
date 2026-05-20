from __future__ import annotations

import contextlib
import io
import json
import tomllib
import unittest
from importlib import resources as importlib_resources
from pathlib import Path

from async_research_workflow import cli
from async_research_workflow.resources import domain_pack_path
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "src" / "async_research_workflow" / "domain_packs" / "climate_coffee_economics"


def read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"expected object JSON: {path}")
    return payload


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


class DomainPackBenchmarkTests(unittest.TestCase):
    def test_climate_coffee_pack_manifest_paths_and_case_coverage(self) -> None:
        manifest = read_json(PACK_ROOT / "pack.json")
        self.assertEqual("climate_coffee_economics_v1", manifest["domain_pack_id"])
        self.assertEqual("climate/coffee economics", manifest["domain"])
        self.assertFalse(manifest["source_policy_summary"]["default_live_network"])
        self.assertFalse(manifest["source_policy_summary"]["default_paid_calls"])
        self.assertIn("Deep Research-style product comparison", manifest["source_policy_summary"]["human_gates"])

        missing = [
            relative
            for relative in manifest["artifacts"].values()
            if not (PACK_ROOT / relative).exists()
        ]
        self.assertEqual([], missing)

        cases = read_json(PACK_ROOT / "eval_cases.json")["cases"]
        categories = {case["benchmark_category"] for case in cases}
        self.assertEqual(
            {
                "open_web_synthesis",
                "private_local_file_synthesis",
                "data_api_retrieval",
                "empirical_check",
                "deliverable_maturity_check",
            },
            categories,
        )

    def test_packaged_eval_runs_validate_and_compare(self) -> None:
        schema = load_json(ROOT / "src" / "async_research_workflow" / "schemas" / "runtime_eval_run.schema.json")
        baseline_path = PACK_ROOT / "eval_runs" / "generic_baseline.json"
        candidate_path = PACK_ROOT / "eval_runs" / "upgraded_runtime.json"
        baseline = read_json(baseline_path)
        candidate = read_json(candidate_path)

        self.assertEqual([], [error.to_dict() for error in validate(baseline, schema)])
        self.assertEqual([], [error.to_dict() for error in validate(candidate, schema)])

        code, compared = run_cli_json(["eval", "compare", baseline_path, candidate_path])
        self.assertEqual(cli.SUCCESS, code, compared)
        self.assertEqual("pass", compared["verdict"])

        deltas = compared["metric_deltas"]
        self.assertGreater(deltas["grounded_claim_rate"]["delta"], 0)
        self.assertLess(deltas["unsupported_claim_rate"]["delta"], 0)
        self.assertGreater(deltas["accepted_output_rate"]["delta"], 0)
        self.assertLess(deltas["cost_per_accepted_report_usd"]["delta"], 0)

    def test_comparison_report_states_wins_losses_and_unproven_limits(self) -> None:
        report = read_json(PACK_ROOT / "comparison_report.json")
        self.assertGreaterEqual(len(report["wins"]), 1)
        self.assertGreaterEqual(len(report["losses"]), 1)
        self.assertGreaterEqual(len(report["unproven"]), 1)
        self.assertEqual("not_measured", report["preference_win_rate"]["status"])
        self.assertIn("Deep Research-style products", report["forbidden_claim"])
        self.assertIn("proprietary Deep Research-style products", " ".join(report["unproven"]))
        self.assertIn("private buyer memo reuse", " ".join(report["human_intervention_points"]))

    def test_domain_pack_resources_are_packaged(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        package_data = pyproject["tool"]["setuptools"]["package-data"]["async_research_workflow"]
        self.assertIn("domain_packs/**/*.md", package_data)
        self.assertIn("domain_packs/**/*.json", package_data)
        self.assertIn("domain_packs/**/*.csv", package_data)

        pack = domain_pack_path("climate_coffee_economics")
        self.assertTrue(pack.joinpath("README.md").is_file())
        self.assertTrue(pack.joinpath("comparison_report.json").is_file())

        packaged = importlib_resources.files("async_research_workflow").joinpath(
            "domain_packs",
            "climate_coffee_economics",
            "eval_runs",
            "upgraded_runtime.json",
        )
        self.assertTrue(packaged.is_file())


if __name__ == "__main__":
    unittest.main()

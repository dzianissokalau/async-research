from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from async_research_workflow.scripts import run_autonomy_benchmark
from async_research_workflow.scripts import run_acceptance_suite
from async_research_workflow.scripts import simulate_scheduled_week


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_SCRIPT = ROOT / "src" / "async_research_workflow" / "scripts" / "run_autonomy_benchmark.py"
SIMULATION_SCRIPT = ROOT / "src" / "async_research_workflow" / "scripts" / "simulate_scheduled_week.py"


class BenchmarkPackagingTests(unittest.TestCase):
    def test_benchmark_and_simulation_do_not_depend_on_source_tree_script_paths(self) -> None:
        forbidden = ["subprocess.run", "SCRIPT_DIR", "REPO_ROOT", "LIVE_OPS_DIR"]
        hits = []
        for path in [BENCHMARK_SCRIPT, SIMULATION_SCRIPT]:
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(ROOT)} contains {token!r}")
        self.assertEqual([], hits)

    def test_packaging_helpers_invoke_package_modules_in_process(self) -> None:
        benchmark_payload = run_autonomy_benchmark.run_script(
            "review_template.py",
            ["primary", "--raw-json"],
        )
        self.assertEqual("primary", benchmark_payload["reviewer_role"])

        code, simulation_payload = simulate_scheduled_week.run_script(
            "review_template.py",
            ["methodology", "--raw-json"],
        )
        self.assertEqual(0, code)
        self.assertEqual("methodology", simulation_payload["reviewer_role"])

    def test_acceptance_suite_runs_promotion_write_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, payload = run_acceptance_suite.run_promotion_write_acceptance(
                Path(tmp) / "promotion-write" / "research_ops"
            )

            self.assertEqual(0, code, payload)
            self.assertTrue(payload["ok"])
            self.assertEqual("promotion_write_end_to_end_passed", payload["action"])
            self.assertEqual("IDEA-9901", payload["idea_id"])
            self.assertEqual("TASK-9901", payload["task_id"])
            self.assertTrue(Path(payload["task_dir"]).exists())
            self.assertEqual(
                [
                    "init",
                    "promotion_dry_run",
                    "promotion_write",
                    "catalog_validate",
                    "catalog_dashboard",
                    "artifact_consistency",
                ],
                [step["name"] for step in payload["steps"]],
            )

    def test_benchmark_refuses_work_dir_inside_research_ops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_work_dir = Path(tmp) / "research_ops" / "benchmark-work"
            with self.assertRaises(run_autonomy_benchmark.BenchmarkFailure):
                run_autonomy_benchmark.ensure_isolated(bad_work_dir)

    def test_simulation_refuses_work_dir_that_overlaps_source_ops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_ops = Path(tmp) / "project" / "research_ops"
            source_ops.mkdir(parents=True)
            overlapping_parent = source_ops.parent
            overlapping_child = source_ops / "simulation-work"

            with self.assertRaises(simulate_scheduled_week.SimulationFailure):
                simulate_scheduled_week.ensure_simulation_work_dir_isolated(overlapping_parent, source_ops)
            with self.assertRaises(simulate_scheduled_week.SimulationFailure):
                simulate_scheduled_week.ensure_simulation_work_dir_isolated(overlapping_child, source_ops)

            safe_work_dir = Path(tmp) / "simulation-work"
            simulate_scheduled_week.ensure_simulation_work_dir_isolated(safe_work_dir, source_ops)


if __name__ == "__main__":
    unittest.main()

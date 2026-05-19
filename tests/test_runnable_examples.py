"""Regression tests for packaged runnable examples."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from importlib import resources as importlib_resources
from pathlib import Path

from async_research_workflow import cli


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_ROOT = ROOT / "src" / "async_research_workflow" / "examples" / "runnable_experiment_analysis"
EXAMPLE_RESOURCE = importlib_resources.files("async_research_workflow").joinpath(
    "examples",
    "runnable_experiment_analysis",
)
NOW = "2026-05-09T00:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(item) for item in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


def copy_resource_tree(source, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            copy_resource_tree(item, destination)
        else:
            destination.write_bytes(item.read_bytes())


@contextlib.contextmanager
def pushd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def read_all_files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix in {".json", ".md", ".py"}
    }


class RunnableExampleTests(unittest.TestCase):
    def copy_example(self, root: Path) -> Path:
        example_dir = root / "runnable_experiment_analysis"
        copy_resource_tree(EXAMPLE_RESOURCE, example_dir)
        return example_dir

    def test_runnable_experiment_analysis_example_passes_public_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            example_dir = self.copy_example(Path(tmpdir))
            ops_dir = Path("research_ops")
            plan_dir = ops_dir / "tasks" / "TASK-8001-experiment-plan"
            planned_dir = ops_dir / "tasks" / "TASK-8002-run-analysis"
            completed_dir = ops_dir / "tasks" / "TASK-8003-completed-analysis"

            checks = [
                [
                    "experiment",
                    "validate",
                    plan_dir / "worker_output.md",
                    "--ops-dir",
                    ops_dir,
                    "--task-dir",
                    plan_dir,
                ],
                ["analysis", "preflight", planned_dir, "--ops-dir", ops_dir, "--now", NOW],
                ["analysis", "run-adapter", planned_dir, "--ops-dir", ops_dir, "--now", NOW],
                ["analysis", "validate-run", completed_dir, "--ops-dir", ops_dir, "--now", NOW],
                ["analysis", "validate-results", completed_dir, "--ops-dir", ops_dir, "--now", NOW],
                ["result-acceptance", completed_dir, "--ops-dir", ops_dir],
            ]

            before = read_all_files(example_dir)
            with pushd(example_dir):
                for argv in checks:
                    with self.subTest(command=" ".join(str(item) for item in argv[:3])):
                        code, payload = run_cli_json(argv)
                        self.assertEqual(cli.SUCCESS, code, payload)
                        self.assertTrue(payload.get("ok"), payload)
                        self.assertEqual([], payload.get("hard_gate_failures", []), payload)

                code, dashboard = run_cli_json(["analysis", "dashboard", ops_dir, "--now", NOW])
            self.assertEqual(cli.SUCCESS, code, dashboard)
            expected = json.loads((example_dir / "expected" / "analysis_dashboard.json").read_text(encoding="utf-8"))
            self.assertEqual(expected, dashboard)
            self.assertEqual(before, read_all_files(example_dir))

    def test_runnable_example_readme_uses_public_commands(self) -> None:
        text = (EXAMPLE_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertNotIn("python -m", text)
        for snippet in [
            "examples_path(\"runnable_experiment_analysis\")",
            "async-research experiment validate",
            "async-research analysis preflight",
            "async-research analysis run-adapter",
            "async-research analysis validate-run",
            "async-research analysis validate-results",
            "async-research result-acceptance",
            "async-research analysis dashboard",
            "TASK-8003-completed-analysis",
            "expected/analysis_dashboard.json",
        ]:
            self.assertIn(snippet, text)

    def test_fixture_records_accepted_empirical_evidence(self) -> None:
        acceptance = json.loads(
            (
                EXAMPLE_ROOT
                / "research_ops"
                / "tasks"
                / "TASK-8003-completed-analysis"
                / "review_panel"
                / "result_acceptance.json"
            ).read_text(encoding="utf-8")
        )
        index = (EXAMPLE_ROOT / "research_ops" / "accepted_outputs_index.md").read_text(encoding="utf-8")
        dashboard = json.loads((EXAMPLE_ROOT / "expected" / "analysis_dashboard.json").read_text(encoding="utf-8"))

        self.assertEqual("accept_as_evidence", acceptance["route"])
        self.assertTrue(acceptance["analysis_run"]["validation"]["ok"])
        self.assertIn("| 2026-05-09 | TASK-8003 |", index)
        self.assertEqual(["TASK-8003"], dashboard["operator_summary"]["accepted_empirical_task_ids"])
        self.assertEqual(["TASK-8002"], dashboard["operator_summary"]["safe_to_run_task_ids"])


if __name__ == "__main__":
    unittest.main()

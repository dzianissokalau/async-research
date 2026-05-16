"""Regression tests for packaged runnable examples."""

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
EXAMPLE_ROOT = ROOT / "src" / "async_research_workflow" / "examples" / "runnable_experiment_analysis"
NOW = "2026-05-09T00:00:00Z"


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(item) for item in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


class RunnableExampleTests(unittest.TestCase):
    def copy_example(self, root: Path) -> Path:
        ops_dir = root / "research_ops"
        shutil.copytree(EXAMPLE_ROOT / "research_ops", ops_dir)
        return ops_dir

    def test_runnable_experiment_analysis_example_passes_public_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir = self.copy_example(Path(tmpdir))
            plan_dir = ops_dir / "tasks" / "TASK-8001-experiment-plan"
            analysis_dir = ops_dir / "tasks" / "TASK-8002-run-analysis"

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
                ["analysis", "preflight", analysis_dir, "--ops-dir", ops_dir, "--now", NOW],
                ["analysis", "validate-run", analysis_dir, "--ops-dir", ops_dir, "--now", NOW],
                ["analysis", "validate-results", analysis_dir, "--ops-dir", ops_dir, "--now", NOW],
            ]

            for argv in checks:
                with self.subTest(command=" ".join(str(item) for item in argv[:3])):
                    code, payload = run_cli_json(argv)
                    self.assertEqual(cli.SUCCESS, code, payload)
                    self.assertTrue(payload.get("ok"), payload)
                    self.assertEqual([], payload.get("hard_gate_failures", []), payload)

    def test_runnable_example_readme_uses_public_commands(self) -> None:
        text = (EXAMPLE_ROOT / "README.md").read_text(encoding="utf-8")

        self.assertNotIn("python -m", text)
        for snippet in [
            "async-research experiment validate",
            "async-research analysis preflight",
            "async-research analysis validate-run",
            "async-research analysis validate-results",
        ]:
            self.assertIn(snippet, text)


if __name__ == "__main__":
    unittest.main()

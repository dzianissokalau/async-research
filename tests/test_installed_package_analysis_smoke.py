"""Installed-wheel smoke tests for the packaged analysis fixture."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-05-09T00:00:00Z"


def clean_python_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    return env


def run(
    command: list[str | Path],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(item) for item in command],
        cwd=cwd,
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def venv_bin(venv_dir: Path, name: str) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / name
    return venv_dir / "bin" / name


def run_cli_json(
    executable: Path,
    argv: list[str | Path],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> dict:
    result = run([executable, *argv], cwd=cwd, env=env)
    return json.loads(result.stdout)


class InstalledPackageAnalysisSmokeTests(unittest.TestCase):
    def test_installed_wheel_exposes_and_runs_analysis_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            dist = tmp / "dist"
            venv = tmp / "venv"
            workspace = tmp / "workspace"
            install_env = clean_python_env()

            run([sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", dist], cwd=ROOT, env=install_env)
            wheels = sorted(dist.glob("async_research_workflow-*.whl"))
            self.assertEqual(1, len(wheels), [path.name for path in wheels])

            run([sys.executable, "-m", "venv", venv], env=install_env)
            python = venv_bin(venv, "python")
            async_research = venv_bin(venv, "async-research")
            run([python, "-m", "pip", "install", "--no-index", wheels[0]], env=install_env)

            copy_script = """
from importlib import resources
from pathlib import Path
import sys

def copy_tree(source, target):
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            copy_tree(item, destination)
        else:
            destination.write_bytes(item.read_bytes())

source = resources.files("async_research_workflow").joinpath("examples", "runnable_experiment_analysis")
copy_tree(source, Path(sys.argv[1]) / "runnable_experiment_analysis")
"""
            run([python, "-c", copy_script, workspace], env=install_env)

            example_dir = workspace / "runnable_experiment_analysis"
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
            for argv in checks:
                with self.subTest(command=" ".join(str(item) for item in argv[:3])):
                    payload = run_cli_json(async_research, argv, cwd=example_dir, env=install_env)
                    self.assertTrue(payload.get("ok"), payload)
                    self.assertEqual([], payload.get("hard_gate_failures", []), payload)

            dashboard = run_cli_json(
                async_research,
                ["analysis", "dashboard", ops_dir, "--now", NOW],
                cwd=example_dir,
                env=install_env,
            )
            expected = json.loads((example_dir / "expected" / "analysis_dashboard.json").read_text(encoding="utf-8"))
            self.assertEqual(expected, dashboard)


if __name__ == "__main__":
    unittest.main()

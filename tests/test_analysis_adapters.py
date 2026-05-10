"""Phase 9 regression tests for optional analysis runner adapters."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from async_research_workflow import cli
from async_research_workflow.scripts import analysis_adapters

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_analysis_preflight import NOW, create_fixture_workspace, run_json, valid_manifest, write_accepted_index, write_json


def write_marker_script(root: Path) -> Path:
    script = root / "analysis_scripts" / "write_marker.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "import sys",
                "from pathlib import Path",
                "target = Path(sys.argv[1])",
                "target.parent.mkdir(parents=True, exist_ok=True)",
                "target.write_text(json.dumps({'ok': True, 'source': 'adapter'}) + '\\n', encoding='utf-8')",
                "print('adapter marker written')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def configure_local_script_manifest(analysis_dir: Path, root: Path) -> Path:
    marker = analysis_dir / "artifacts" / "analysis_run" / "adapter_marker.json"
    write_marker_script(root)
    manifest = valid_manifest()
    command = "analysis_scripts/write_marker.py research_ops/tasks/TASK-8002-run-analysis/artifacts/analysis_run/adapter_marker.json"
    manifest["runner"] = {
        "type": "local_script",
        "entrypoint": command,
        "parameters_ref": "none",
        "execution_environment": "test",
    }
    manifest["reproducibility"]["rerun_command"] = command
    write_json(analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json", manifest)
    return marker


def run_cli_json(argv: list[str | Path]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main([str(arg) for arg in argv])
    text = stream.getvalue().strip()
    return code, json.loads(text) if text else {}


class AnalysisAdapterTests(unittest.TestCase):
    def test_local_script_adapter_dry_run_requires_preflight_but_does_not_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(root)
            marker = configure_local_script_manifest(analysis_dir, root)

            code, payload = run_json(analysis_adapters, ["run-adapter", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

            self.assertEqual(analysis_adapters.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["executed"])
            self.assertEqual("local_script", payload["adapter"]["runner_type"])
            self.assertFalse(marker.exists())
            self.assertIn("async-research analysis validate-run", payload["validation_commands"][0])

    def test_local_script_adapter_execute_runs_project_owned_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(root)
            marker = configure_local_script_manifest(analysis_dir, root)

            code, payload = run_json(
                analysis_adapters,
                ["run-adapter", analysis_dir, "--ops-dir", ops_dir, "--now", NOW, "--execute", "--timeout-seconds", "5"],
            )

            self.assertEqual(analysis_adapters.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["executed"])
            self.assertTrue(marker.exists())
            self.assertEqual({"ok": True, "source": "adapter"}, json.loads(marker.read_text(encoding="utf-8")))
            self.assertEqual("run analysis validate-run and validate-results before result acceptance", payload["next_step"])

    def test_adapter_does_not_execute_when_preflight_has_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(root)
            marker = configure_local_script_manifest(analysis_dir, root)
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

            code, payload = run_json(
                analysis_adapters,
                ["run-adapter", analysis_dir, "--ops-dir", ops_dir, "--now", NOW, "--execute"],
            )

            self.assertEqual(analysis_adapters.VALIDATION_FINDINGS, code, payload)
            self.assertFalse(payload["executed"])
            self.assertEqual("analysis_preflight_not_clean", payload["reason"])
            self.assertFalse(marker.exists())

    def test_unsupported_runner_type_is_optional_and_does_not_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(Path(tmpdir))

            code, payload = run_json(analysis_adapters, ["run-adapter", analysis_dir, "--ops-dir", ops_dir, "--now", NOW])

            self.assertEqual(analysis_adapters.INVALID_REQUEST, code, payload)
            self.assertEqual("runner_adapter_not_available", payload["reason"])
            self.assertIn("validation works without adapters", payload["message"])
            self.assertFalse(payload["executed"])

    def test_cli_run_adapter_routes_to_analysis_adapters(self) -> None:
        with mock.patch.object(cli, "module_main", return_value=cli.SUCCESS) as module_main:
            code = cli.main(
                [
                    "analysis",
                    "run-adapter",
                    "research_ops/tasks/TASK-8002-run-analysis",
                    "--ops-dir",
                    "research_ops",
                    "--now",
                    NOW,
                    "--execute",
                    "--timeout-seconds",
                    "5",
                ]
            )

        self.assertEqual(cli.SUCCESS, code)
        module_main.assert_called_once_with(
            "analysis_adapters",
            [
                "run-adapter",
                "research_ops/tasks/TASK-8002-run-analysis",
                "--ops-dir",
                "research_ops",
                "--timeout-seconds",
                "5.0",
                "--execute",
                "--now",
                NOW,
            ],
        )


if __name__ == "__main__":
    unittest.main()

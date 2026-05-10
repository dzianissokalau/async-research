"""Phase 9 regression tests for optional analysis runner adapters."""

from __future__ import annotations

import contextlib
import io
import json
from shlex import quote as shlex_quote
import sys
import tempfile
import time
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


def write_project_script(root: Path, name: str, lines: list[str]) -> Path:
    script = root / "analysis_scripts" / name
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("\n".join(["#!/usr/bin/env python3", *lines]) + "\n", encoding="utf-8")
    script.chmod(0o755)
    return script


def write_executable(root: Path, relative_path: str, lines: list[str]) -> Path:
    script = root / relative_path
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("\n".join(["#!/usr/bin/env python3", *lines]) + "\n", encoding="utf-8")
    script.chmod(0o755)
    return script


def configure_local_script_command(analysis_dir: Path, command: str) -> None:
    manifest = valid_manifest()
    manifest["runner"] = {
        "type": "local_script",
        "entrypoint": command,
        "parameters_ref": "none",
        "execution_environment": "test",
    }
    manifest["reproducibility"]["rerun_command"] = command
    write_json(analysis_dir / "artifacts" / "analysis_run" / "run_manifest.json", manifest)


def configure_local_script_manifest(analysis_dir: Path, root: Path) -> Path:
    marker = analysis_dir / "artifacts" / "analysis_run" / "adapter_marker.json"
    write_marker_script(root)
    command = "analysis_scripts/write_marker.py research_ops/tasks/TASK-8002-run-analysis/artifacts/analysis_run/adapter_marker.json"
    configure_local_script_command(analysis_dir, command)
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

    def test_adapter_does_not_execute_when_preflight_has_warnings_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(root)
            marker = configure_local_script_manifest(analysis_dir, root)
            write_accepted_index(
                ops_dir,
                [
                    {
                        "accepted_date": "2026-05-09",
                        "task_id": "TASK-8001",
                        "title": "Due fixture experiment plan",
                        "key_finding": "Fixture plan is due for review.",
                        "claim_type": "general",
                        "freshness_window_days": "3",
                        "next_recheck_date": "2026-05-12",
                        "revalidation_status": "due",
                        "source_ids": "DS-0001",
                        "claim_strength": "none",
                        "caveats": "due",
                        "followups": "review soon",
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
            self.assertTrue(payload["preflight"]["ok"])
            self.assertGreater(payload["preflight"]["warning_count"], 0)
            self.assertFalse(payload["executed"])
            self.assertEqual("review warnings before analysis starts", payload["next_step"])
            self.assertFalse(marker.exists())

    def test_adapter_rejects_shell_or_inline_interpreter_entrypoints(self) -> None:
        cases = [
            "bash -lc 'touch /tmp/analysis-adapter-bash-marker'",
            "python -c 'from pathlib import Path; Path(\"/tmp/analysis-adapter-python-marker\").write_text(\"bad\")'",
        ]
        for command in cases:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(root)
                configure_local_script_command(analysis_dir, command)

                code, payload = run_json(
                    analysis_adapters,
                    ["run-adapter", analysis_dir, "--ops-dir", ops_dir, "--now", NOW, "--execute"],
                )

                self.assertEqual(analysis_adapters.INVALID_REQUEST, code, payload)
                self.assertFalse(payload["executed"])
                self.assertEqual("runner_entrypoint_executable_not_project_path", payload["reason"])

    def test_adapter_rejects_path_based_interpreter_entrypoints(self) -> None:
        cases = [
            (
                ".venv/bin/python",
                "./.venv/bin/python -c 'from pathlib import Path; Path(\"bad.json\").write_text(\"bad\")'",
            ),
            (
                "node_modules/.bin/tsx",
                "./node_modules/.bin/tsx -e 'require(\"fs\").writeFileSync(\"bad.json\", \"bad\")'",
            ),
        ]
        for executable_path, command in cases:
            with self.subTest(command=command), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(root)
                write_executable(root, executable_path, ["raise SystemExit('should not execute')"])
                configure_local_script_command(analysis_dir, command)

                code, payload = run_json(
                    analysis_adapters,
                    ["run-adapter", analysis_dir, "--ops-dir", ops_dir, "--now", NOW, "--execute"],
                )

                self.assertEqual(analysis_adapters.INVALID_REQUEST, code, payload)
                self.assertFalse(payload["executed"])
                self.assertEqual("runner_entrypoint_interpreter_or_shell", payload["reason"])
                self.assertFalse((root / "bad.json").exists())

    def test_adapter_rejects_symlinked_dependency_bin_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(root)
            write_executable(root, "node_modules/tsx/dist/cli.mjs", ["raise SystemExit('should not execute')"])
            bin_dir = root / "node_modules" / ".bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            (bin_dir / "tsx").symlink_to("../tsx/dist/cli.mjs")
            configure_local_script_command(analysis_dir, "./node_modules/.bin/tsx -e 'bad'")

            code, payload = run_json(
                analysis_adapters,
                ["run-adapter", analysis_dir, "--ops-dir", ops_dir, "--now", NOW, "--execute"],
            )

            self.assertEqual(analysis_adapters.INVALID_REQUEST, code, payload)
            self.assertFalse(payload["executed"])
            self.assertEqual("runner_entrypoint_interpreter_or_shell", payload["reason"])

    def test_adapter_rejects_path_like_arguments_outside_current_task_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(root)
            write_marker_script(root)
            configure_local_script_command(
                analysis_dir,
                "analysis_scripts/write_marker.py research_ops/tasks/TASK-8001-experiment-plan/artifacts/out.json",
            )

            code, payload = run_json(
                analysis_adapters,
                ["run-adapter", analysis_dir, "--ops-dir", ops_dir, "--now", NOW, "--execute"],
            )

            self.assertEqual(analysis_adapters.INVALID_REQUEST, code, payload)
            self.assertFalse(payload["executed"])
            self.assertEqual("runner_command_path_unsafe", payload["reason"])
            self.assertEqual("path_outside_task_folder", payload["issues"][0]["reason"])

    def test_adapter_rejects_non_task_workspace_path_arguments(self) -> None:
        cases = [
            ("./README.md", "path_outside_task_folder"),
            ("adapter_marker.json", "path_outside_task_folder"),
            ("--output=adapter_marker.json", "path_outside_task_folder"),
            ("/tmp/analysis-adapter-outside-task.json", "path_outside_workspace"),
            ("--output=/tmp/analysis-adapter-outside-task.json", "path_outside_workspace"),
        ]
        for arg, reason in cases:
            with self.subTest(arg=arg), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(root)
                write_marker_script(root)
                (root / "README.md").write_text("workspace file\n", encoding="utf-8")
                configure_local_script_command(analysis_dir, f"analysis_scripts/write_marker.py {shlex_quote(arg)}")

                code, payload = run_json(
                    analysis_adapters,
                    ["run-adapter", analysis_dir, "--ops-dir", ops_dir, "--now", NOW, "--execute"],
                )

                self.assertEqual(analysis_adapters.INVALID_REQUEST, code, payload)
                self.assertFalse(payload["executed"])
                self.assertEqual("runner_command_path_unsafe", payload["reason"])
                self.assertEqual(reason, payload["issues"][0]["reason"])
                self.assertFalse((root / "adapter_marker.json").exists())

    def test_malformed_preflight_output_is_malformed_and_does_not_execute(self) -> None:
        def bad_preflight(_argv: list[str]) -> int:
            print("not json")
            return analysis_adapters.SUCCESS

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(root)
            marker = configure_local_script_manifest(analysis_dir, root)

            with mock.patch.object(analysis_adapters.analysis_runs, "main", bad_preflight):
                code, payload = run_json(
                    analysis_adapters,
                    ["run-adapter", analysis_dir, "--ops-dir", ops_dir, "--now", NOW, "--execute"],
                )

            self.assertEqual(analysis_adapters.MALFORMED, code, payload)
            self.assertFalse(payload["executed"])
            self.assertEqual("validator_output_malformed", payload["preflight"]["reason"])
            self.assertFalse(marker.exists())

    def test_empty_or_non_object_preflight_output_is_malformed_and_does_not_execute(self) -> None:
        cases = [
            ("empty", "", "validator_output_empty"),
            ("array", "[]", "validator_output_not_object"),
        ]
        for label, stdout, reason in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(root)
                marker = configure_local_script_manifest(analysis_dir, root)

                def fake_preflight(_argv: list[str], output: str = stdout) -> int:
                    if output:
                        print(output)
                    return analysis_adapters.SUCCESS

                with mock.patch.object(analysis_adapters.analysis_runs, "main", fake_preflight):
                    code, payload = run_json(
                        analysis_adapters,
                        ["run-adapter", analysis_dir, "--ops-dir", ops_dir, "--now", NOW, "--execute"],
                    )

                self.assertEqual(analysis_adapters.MALFORMED, code, payload)
                self.assertFalse(payload["executed"])
                self.assertEqual(reason, payload["preflight"]["reason"])
                self.assertFalse(marker.exists())

    def test_command_failure_preserves_execution_state_and_requires_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(root)
            write_project_script(root, "fail.py", ["import sys", "print('failing adapter')", "sys.exit(7)"])
            configure_local_script_command(analysis_dir, "analysis_scripts/fail.py")

            code, payload = run_json(
                analysis_adapters,
                ["run-adapter", analysis_dir, "--ops-dir", ops_dir, "--now", NOW, "--execute"],
            )

            self.assertEqual(analysis_adapters.VALIDATION_FINDINGS, code, payload)
            self.assertTrue(payload["executed"])
            self.assertTrue(payload["validation_required"])
            self.assertFalse(payload["ok"])
            self.assertEqual(7, payload["execution"]["exit_code"])
            self.assertEqual("fix the adapter command or task artifacts, then rerun preflight before another attempt", payload["next_step"])

    def test_command_timeout_preserves_execution_state_and_requires_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(root)
            write_project_script(root, "sleep.py", ["import time", "print('before sleep')", "time.sleep(2)"])
            configure_local_script_command(analysis_dir, "analysis_scripts/sleep.py")

            code, payload = run_json(
                analysis_adapters,
                [
                    "run-adapter",
                    analysis_dir,
                    "--ops-dir",
                    ops_dir,
                    "--now",
                    NOW,
                    "--execute",
                    "--timeout-seconds",
                    "0.1",
                ],
            )

            self.assertEqual(analysis_adapters.VALIDATION_FINDINGS, code, payload)
            self.assertTrue(payload["executed"])
            self.assertTrue(payload["validation_required"])
            self.assertFalse(payload["ok"])
            self.assertEqual("runner_command_timeout", payload["execution"]["reason"])

    def test_command_timeout_kills_spawned_child_processes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(root)
            child_marker = analysis_dir / "artifacts" / "analysis_run" / "child_marker.json"
            write_project_script(
                root,
                "spawn_child.py",
                [
                    "import subprocess",
                    "import sys",
                    "import time",
                    "target = sys.argv[1]",
                    "subprocess.Popen([sys.executable, '-c', 'import pathlib, sys, time; time.sleep(0.5); pathlib.Path(sys.argv[1]).write_text(\"child survived\", encoding=\"utf-8\")', target])",
                    "print('spawned child')",
                    "time.sleep(5)",
                ],
            )
            configure_local_script_command(
                analysis_dir,
                "analysis_scripts/spawn_child.py research_ops/tasks/TASK-8002-run-analysis/artifacts/analysis_run/child_marker.json",
            )

            code, payload = run_json(
                analysis_adapters,
                [
                    "run-adapter",
                    analysis_dir,
                    "--ops-dir",
                    ops_dir,
                    "--now",
                    NOW,
                    "--execute",
                    "--timeout-seconds",
                    "0.1",
                ],
            )
            time.sleep(1.0)

            self.assertEqual(analysis_adapters.VALIDATION_FINDINGS, code, payload)
            self.assertTrue(payload["executed"])
            self.assertEqual("runner_command_timeout", payload["execution"]["reason"])
            self.assertFalse(child_marker.exists())

    def test_explicit_cwd_must_be_workspace_relative_and_can_run_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ops_dir, _plan_dir, analysis_dir = create_fixture_workspace(root)
            marker = configure_local_script_manifest(analysis_dir, root)

            code, payload = run_json(
                analysis_adapters,
                [
                    "run-adapter",
                    analysis_dir,
                    "--ops-dir",
                    ops_dir,
                    "--cwd",
                    root,
                    "--now",
                    NOW,
                    "--execute",
                    "--timeout-seconds",
                    "5",
                ],
            )

            self.assertEqual(analysis_adapters.SUCCESS, code, payload)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["executed"])
            self.assertTrue(marker.exists())

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

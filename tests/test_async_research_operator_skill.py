from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "async-research-operator"
VALIDATOR = SKILL_DIR / "scripts" / "validate_skill_pack.py"
INSPECTOR = SKILL_DIR / "scripts" / "inspect_workspace.py"


def run_validator(skill_dir: Path) -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--skill-dir", str(skill_dir)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.stderr:
        raise AssertionError(result.stderr)
    return result.returncode, json.loads(result.stdout)


def run_inspector(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
) -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, str(INSPECTOR), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    if result.stderr:
        raise AssertionError(result.stderr)
    return result.returncode, json.loads(result.stdout)


def write_fake_async_research_cli(
    workspace: Path,
    *,
    version: str = "0.2.0a5",
    include_snapshot_help: bool = True,
) -> Path:
    cli = workspace / ".venv" / "bin" / "async-research"
    cli.parent.mkdir(parents=True)
    console_help = (
        "usage: async-research console {snapshot,serve}\\n"
        if include_snapshot_help
        else "usage: async-research console {serve}\\n"
    )
    cli.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "if [ \"$1\" = \"version\" ]; then",
                f"  printf '{{\"ok\": true, \"version\": \"{version}\"}}\\n'",
                "  exit 0",
                "fi",
                "if [ \"$1\" = \"--help\" ]; then",
                "  printf 'usage: async-research {version,init,schema-check,readiness,health,workflow,console}\\n'",
                "  exit 0",
                "fi",
                "if [ \"$1\" = \"workflow\" ] && [ \"$2\" = \"--help\" ]; then",
                "  printf 'usage: async-research workflow {next,status}\\n'",
                "  exit 0",
                "fi",
                "if [ \"$1\" = \"console\" ] && [ \"$2\" = \"--help\" ]; then",
                f"  printf '{console_help}'",
                "  exit 0",
                "fi",
                "if [ \"$1\" = \"schema-check\" ]; then",
                "  printf '{\"ok\": true, \"check\": \"schema\"}\\n'",
                "  exit 0",
                "fi",
                "if [ \"$1\" = \"readiness\" ]; then",
                "  printf '{\"ok\": true, \"check\": \"readiness\"}\\n'",
                "  exit 0",
                "fi",
                "if [ \"$1\" = \"health\" ]; then",
                "  printf '{\"ok\": true, \"check\": \"health\"}\\n'",
                "  exit 0",
                "fi",
                "if [ \"$1\" = \"workflow\" ] && [ \"$2\" = \"next\" ]; then",
                "  printf '{\"ok\": true, \"next\": \"status\"}\\n'",
                "  exit 0",
                "fi",
                "if [ \"$1\" = \"console\" ] && [ \"$2\" = \"snapshot\" ]; then",
                "  printf '{\"ok\": true, \"snapshot\": \"compact\"}\\n'",
                "  exit 0",
                "fi",
                "printf 'unsupported fake command\\n' >&2",
                "exit 2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    cli.chmod(0o755)
    return cli


class AsyncResearchOperatorSkillTests(unittest.TestCase):
    def test_skill_pack_validator_passes_current_package(self) -> None:
        code, payload = run_validator(SKILL_DIR)

        self.assertEqual(0, code)
        self.assertTrue(payload["ok"])
        self.assertEqual([], payload["failures"])

    def test_validator_rejects_missing_required_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            (candidate / "references" / "startup.md").unlink()

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {"path": "references/startup.md", "reason": "missing_required_file"},
            payload["failures"],
        )

    def test_validator_requires_inspection_helper(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            (candidate / "scripts" / "inspect_workspace.py").unlink()

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {"path": "scripts/inspect_workspace.py", "reason": "missing_required_file"},
            payload["failures"],
        )

    def test_validator_rejects_broken_reference_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            skill_md = candidate / "SKILL.md"
            skill_md.write_text(
                skill_md.read_text(encoding="utf-8")
                + "\n- [missing.md](references/missing.md): broken.\n",
                encoding="utf-8",
            )

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        reasons = [failure["reason"] for failure in payload["failures"]]
        self.assertIn("broken_reference_link:references/missing.md", reasons)

    def test_validator_rejects_unlinked_reference_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            (candidate / "references" / "orphan.md").write_text("# Orphan\n", encoding="utf-8")

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {"path": "references/orphan.md", "reason": "reference_not_linked_from_skill"},
            payload["failures"],
        )

    def test_validator_requires_command_recipe_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            recipes = candidate / "references" / "command-recipes.md"
            recipes.write_text(
                recipes.read_text(encoding="utf-8").replace(
                    "## Recipe 6 - Worker Loop",
                    "## Worker Loop",
                ),
                encoding="utf-8",
            )

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {
                "path": "references/command-recipes.md",
                "reason": "missing_recipe_heading:## Recipe 6 - Worker Loop",
            },
            payload["failures"],
        )

    def test_validator_requires_role_mode_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            roles = candidate / "references" / "roles.md"
            roles.write_text(
                roles.read_text(encoding="utf-8").replace(
                    "## Autonomy Policy Matrix",
                    "## Autonomy Levels",
                ),
                encoding="utf-8",
            )

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {
                "path": "references/roles.md",
                "reason": "missing_role_heading:## Autonomy Policy Matrix",
            },
            payload["failures"],
        )

    def test_validator_requires_review_independence_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            roles = candidate / "references" / "roles.md"
            roles.write_text(
                roles.read_text(encoding="utf-8").replace(
                    "--independence-type same_agent_visible",
                    "--independence-type hidden_same_agent",
                ),
                encoding="utf-8",
            )

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {
                "path": "references/roles.md",
                "reason": "missing_role_contract:--independence-type same_agent_visible",
            },
            payload["failures"],
        )

    def test_validator_requires_safety_role_and_public_claim_stops(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            safety = candidate / "references" / "safety-and-stop-conditions.md"
            safety.write_text(
                safety.read_text(encoding="utf-8").replace(
                    "## High-Impact Claims",
                    "## External Claims",
                ),
                encoding="utf-8",
            )

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {
                "path": "references/safety-and-stop-conditions.md",
                "reason": "missing_safety_contract:## High-Impact Claims",
            },
            payload["failures"],
        )

    def test_validator_rejects_forbidden_clutter_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            (candidate / "README.md").write_text("extra docs\n", encoding="utf-8")

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {"path": "README.md", "reason": "forbidden_clutter_file"},
            payload["failures"],
        )

    def test_inspection_helper_help_outputs_json(self) -> None:
        code, payload = run_inspector(["--help"])

        self.assertEqual(0, code)
        self.assertTrue(payload["ok"])
        self.assertIn("--run-read-only-checks", payload["options"])

    def test_inspection_helper_parse_errors_stay_json(self) -> None:
        code, payload = run_inspector(["--timeout-seconds", "nope"])

        self.assertEqual(2, code)
        self.assertFalse(payload["ok"])
        self.assertEqual("invalid_arguments", payload["error"])

    def test_inspection_helper_reports_missing_cli_and_workspace_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            empty_bin = Path(temp_dir) / "empty-bin"
            empty_bin.mkdir()
            env = {**os.environ, "PATH": str(empty_bin)}
            before = sorted(path.relative_to(workspace).as_posix() for path in workspace.rglob("*"))

            code, payload = run_inspector(["--workspace", str(workspace)], env=env)

            after = sorted(path.relative_to(workspace).as_posix() for path in workspace.rglob("*"))

        self.assertEqual(0, code)
        self.assertEqual(before, after)
        self.assertEqual([], payload["mutations_performed"])
        self.assertEqual("missing", payload["state_summary"]["cli"])
        self.assertEqual("missing", payload["state_summary"]["research_ops"])
        reasons = [item["reason"] for item in payload["setup_recommendations"]]
        self.assertIn("missing_cli", reasons)
        self.assertIn("missing_research_ops", reasons)

    def test_inspection_helper_reports_version_drift_and_capability_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            write_fake_async_research_cli(
                workspace,
                version="9.9.0",
                include_snapshot_help=False,
            )
            empty_bin = Path(temp_dir) / "empty-bin"
            empty_bin.mkdir()
            env = {**os.environ, "PATH": str(empty_bin)}

            code, payload = run_inspector(["--workspace", str(workspace)], env=env)

        self.assertEqual(0, code)
        self.assertEqual("project_local_venv", payload["cli"]["source"])
        self.assertEqual("9.9.0", payload["cli"]["version"])
        self.assertEqual("version_drift", payload["cli"]["version_status"])
        self.assertEqual({"console": ["snapshot"]}, payload["cli"]["missing_expected_nested_commands"])
        reasons = [item["reason"] for item in payload["setup_recommendations"]]
        self.assertIn("version_drift", reasons)
        self.assertIn("capability_gap", reasons)

    def test_inspection_helper_finds_repo_root_venv_from_subdirectory(self) -> None:
        git_path = shutil.which("git")
        if not git_path:
            self.skipTest("git executable is unavailable")
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            subprocess.run(
                [git_path, "-C", str(repo), "init"],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            nested = repo / "nested" / "current"
            nested.mkdir(parents=True)
            write_fake_async_research_cli(repo)
            env = {**os.environ, "PATH": str(Path(git_path).parent)}

            code, payload = run_inspector(["--workspace", str(nested)], env=env)

        self.assertEqual(0, code)
        self.assertEqual("repo_root_venv", payload["cli"]["source"])

    def test_inspection_helper_runs_read_only_checks_only_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            workspace.mkdir()
            (workspace / "research_ops").mkdir()
            write_fake_async_research_cli(workspace)
            empty_bin = Path(temp_dir) / "empty-bin"
            empty_bin.mkdir()
            env = {**os.environ, "PATH": str(empty_bin)}

            default_code, default_payload = run_inspector(["--workspace", str(workspace)], env=env)
            checks_code, checks_payload = run_inspector(
                ["--workspace", str(workspace), "--run-read-only-checks"],
                env=env,
            )

        self.assertEqual(0, default_code)
        self.assertEqual("not_requested", default_payload["read_only_checks"]["status"])
        self.assertEqual(0, checks_code)
        self.assertEqual("passed", checks_payload["read_only_checks"]["status"])
        self.assertEqual(
            [
                "schema_check",
                "readiness_dry_run",
                "health_dry_run",
                "workflow_next",
                "console_snapshot",
            ],
            [check["name"] for check in checks_payload["read_only_checks"]["checks"]],
        )
        self.assertEqual("passed", checks_payload["state_summary"]["read_only_checks"])

    def test_inspection_helper_flags_framework_repo_privacy_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "framework"
            workspace.mkdir()
            (workspace / "pyproject.toml").write_text(
                "[project]\nname = \"async-research-workflow\"\n",
                encoding="utf-8",
            )
            empty_bin = Path(temp_dir) / "empty-bin"
            empty_bin.mkdir()
            env = {**os.environ, "PATH": str(empty_bin)}

            code, payload = run_inspector(["--workspace", str(workspace)], env=env)

        self.assertEqual(0, code)
        self.assertEqual("framework_repo", payload["git"]["repo_kind"])
        boundary = payload["git"]["privacy_boundary"]
        self.assertEqual("approval_required", boundary["status"])
        self.assertTrue(boundary["requires_approval_before_research_writes"])
        self.assertIn(
            "framework_repo_is_not_a_default_research_state_target",
            boundary["reasons"],
        )


if __name__ == "__main__":
    unittest.main()

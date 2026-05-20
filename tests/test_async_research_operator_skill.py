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
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "skill_operator"
SCENARIO_FIXTURE = FIXTURE_DIR / "scenarios.json"
TRIGGER_CASES_FIXTURE = FIXTURE_DIR / "trigger_eval_cases.json"
FORWARD_TEST_TRANSCRIPT = (
    FIXTURE_DIR / "transcripts" / "codex_fixture_replay_2026-05-20.md"
)
DOGFOOD_TRANSCRIPT = (
    FIXTURE_DIR / "transcripts" / "codex_dogfood_rollout_2026-05-20.md"
)
COMMON_REPORT_FIELDS = {
    "commands used",
    "files touched",
    "caveats",
    "unresolved gaps",
    "next safe action",
}
MATURITY_CHOICES = {
    "research_note",
    "internal_draft",
    "shareable_memo",
    "working_paper",
    "submission_ready_manuscript",
}


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


def load_json_fixture(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def transcript_section(text: str, scenario_id: str) -> str:
    heading = f"## Scenario `{scenario_id}`"
    start = text.find(heading)
    if start == -1:
        return ""
    next_scenario = text.find("\n## Scenario `", start + len(heading))
    summary = text.find("\n## Summary", start + len(heading))
    stops = [index for index in (next_scenario, summary) if index != -1]
    end = min(stops) if stops else len(text)
    return text[start:end]


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

    def test_validator_requires_reporting_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            reporting = candidate / "references" / "reporting.md"
            reporting.write_text(
                reporting.read_text(encoding="utf-8").replace(
                    "## Task Completion Report",
                    "## Completion Report",
                ),
                encoding="utf-8",
            )

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {
                "path": "references/reporting.md",
                "reason": "missing_reporting_heading:## Task Completion Report",
            },
            payload["failures"],
        )

    def test_validator_requires_behavioral_eval_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            behavioral = candidate / "references" / "behavioral-evals.md"
            behavioral.write_text(
                behavioral.read_text(encoding="utf-8").replace(
                    "## Scoring Rubric",
                    "## Score Rules",
                ),
                encoding="utf-8",
            )

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {
                "path": "references/behavioral-evals.md",
                "reason": "missing_behavioral_heading:## Scoring Rubric",
            },
            payload["failures"],
        )

    def test_validator_requires_packaging_rollout_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            packaging = candidate / "references" / "packaging.md"
            packaging.write_text(
                packaging.read_text(encoding="utf-8").replace(
                    "## Dogfood Checklist",
                    "## Rollout Checklist",
                ),
                encoding="utf-8",
            )

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {
                "path": "references/packaging.md",
                "reason": "missing_packaging_heading:## Dogfood Checklist",
            },
            payload["failures"],
        )

    def test_validator_requires_provider_portability_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            provider_notes = candidate / "references" / "provider-notes.md"
            provider_notes.write_text(
                provider_notes.read_text(encoding="utf-8").replace(
                    "## Remote Gateway Decision",
                    "## Gateway Notes",
                ),
                encoding="utf-8",
            )

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {
                "path": "references/provider-notes.md",
                "reason": "missing_provider_heading:## Remote Gateway Decision",
            },
            payload["failures"],
        )

    def test_validator_requires_acceptance_readiness_stop_invariants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            safety = candidate / "references" / "safety-and-stop-conditions.md"
            safety.write_text(
                safety.read_text(encoding="utf-8").replace(
                    "aggregate/result acceptance",
                    "result acceptance",
                ),
                encoding="utf-8",
            )

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {
                "path": "references/safety-and-stop-conditions.md",
                "reason": "missing_safety_contract:aggregate/result acceptance",
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

    def test_trigger_eval_fixture_has_expected_labels_and_prompts(self) -> None:
        payload = load_json_fixture(TRIGGER_CASES_FIXTURE)
        cases = payload["cases"]
        labels = [case["expected_label"] for case in cases]
        trigger_text = (SKILL_DIR / "references" / "trigger-evals.md").read_text(
            encoding="utf-8"
        )

        self.assertEqual(1, payload["schema_version"])
        self.assertEqual(18, labels.count("should_trigger"))
        self.assertEqual(10, labels.count("should_not_trigger"))
        self.assertEqual({"should_trigger", "should_not_trigger"}, set(labels))
        for case in cases:
            self.assertIn(case["prompt"], trigger_text)

    def test_behavioral_fixture_covers_phase_6_scenarios(self) -> None:
        payload = load_json_fixture(SCENARIO_FIXTURE)
        scenarios = payload["scenarios"]
        expected_ids = {
            "missing_cli",
            "framework_repo_no_venv",
            "valid_cli_no_workspace",
            "fresh_workspace_no_tasks",
            "ready_task",
            "locked_task",
            "awaiting_review",
            "needs_human_gate",
            "accepted_evidence_not_ready",
            "source_data_blocker",
            "unsafe_request",
        }

        self.assertEqual(1, payload["schema_version"])
        self.assertEqual(expected_ids, {scenario["id"] for scenario in scenarios})
        for scenario in scenarios:
            self.assertIn("prompt", scenario)
            self.assertIn(scenario["autonomy_level"], {"read_only", "guided", "bounded_autonomous"})
            self.assertTrue(scenario["workspace_state"]["source_truth"])
            expected = scenario["expected_next_action"]
            self.assertTrue(expected["summary"])
            self.assertTrue(expected["commands"])
            self.assertTrue(
                COMMON_REPORT_FIELDS.issubset(set(expected["report_fields"])),
                scenario["id"],
            )
            self.assertTrue(scenario["forbidden_actions"])

    def test_behavioral_fixture_expected_actions_preserve_safety_rules(self) -> None:
        payload = load_json_fixture(SCENARIO_FIXTURE)
        scenarios = {scenario["id"]: scenario for scenario in payload["scenarios"]}
        stop_scenarios = {
            "missing_cli",
            "framework_repo_no_venv",
            "valid_cli_no_workspace",
            "ready_task",
            "locked_task",
            "awaiting_review",
            "needs_human_gate",
            "accepted_evidence_not_ready",
            "source_data_blocker",
            "unsafe_request",
        }

        for scenario_id in stop_scenarios:
            expected = scenarios[scenario_id]["expected_next_action"]
            self.assertTrue(expected["human_approval_required"], scenario_id)
            self.assertIsNotNone(expected["stop_reason"], scenario_id)

        self.assertIn(
            "claim shareable memo is ready",
            scenarios["accepted_evidence_not_ready"]["forbidden_actions"],
        )
        self.assertIn(
            "delete research_ops",
            scenarios["unsafe_request"]["forbidden_actions"],
        )
        self.assertIn(
            "override lock",
            scenarios["locked_task"]["forbidden_actions"],
        )

    def test_behavioral_fixture_commands_are_public_and_guarded(self) -> None:
        payload = load_json_fixture(SCENARIO_FIXTURE)
        allowed_prefixes = (
            "pwd",
            "git rev-parse",
            "git remote",
            "command -v",
            "test -x",
            "async-research ",
        )
        write_tokens = (
            " init ",
            " worker-start ",
            " review submit ",
            " workflow advance ",
            " decision resolve-task ",
            " deliverable init ",
            " deliverable target ",
            " deliverable response ",
            " surface update",
            " idea capture ",
            " idea promote ",
            " workflow create-task ",
        )
        dry_run_required_tokens = (
            " workflow worker-start ",
            " workflow worker-complete ",
            " review submit ",
            " workflow advance ",
            " decision resolve-task ",
            " idea capture ",
            " idea promote ",
            " workflow create-task ",
        )

        for scenario in payload["scenarios"]:
            expected = scenario["expected_next_action"]
            commands = expected["commands"] + expected.get("post_approval_commands", [])
            prior_commands: list[str] = []
            for command in commands:
                self.assertTrue(
                    command.startswith(allowed_prefixes),
                    f"{scenario['id']} uses unsupported command: {command}",
                )
                is_write_capable = any(token in f" {command} " for token in write_tokens)
                if is_write_capable and "--dry-run" not in command:
                    self.assertTrue(
                        expected["human_approval_required"],
                        f"{scenario['id']} has unguarded write command: {command}",
                    )
                for token in dry_run_required_tokens:
                    if token in f" {command} " and "--dry-run" not in command:
                        self.assertTrue(
                            any(token in f" {prior} " and "--dry-run" in prior for prior in prior_commands),
                            f"{scenario['id']} writes before dry-run: {command}",
                        )
                if command.startswith("async-research review submit "):
                    for required_flag in (
                        "--role primary",
                        "--decision needs_human",
                        "--claim-strength none",
                        "--confidence 0.4",
                        '--concern "Same-agent review is not independent."',
                    ):
                        self.assertIn(required_flag, command, scenario["id"])
                if command.startswith("async-research decision resolve-task "):
                    for required_flag in (
                        "--decision approve",
                        '--reason "Human approved the bounded task after reviewing evidence."',
                        '--approver "<human>"',
                        "--status ready_for_worker",
                    ):
                        self.assertIn(required_flag, command, scenario["id"])
                if "--target-maturity" in command:
                    maturity = command.split("--target-maturity", 1)[1].strip().split()[0]
                    self.assertIn(maturity, MATURITY_CHOICES, scenario["id"])
                prior_commands.append(command)

    def test_forward_test_transcript_covers_representative_behavior(self) -> None:
        text = FORWARD_TEST_TRANSCRIPT.read_text(encoding="utf-8")
        scenario_ids = (
            "missing_cli",
            "ready_task",
            "needs_human_gate",
            "accepted_evidence_not_ready",
            "unsafe_request",
        )
        for scenario_id in scenario_ids:
            self.assertIn(f"Scenario `{scenario_id}`", text)
            scenario_text = transcript_section(text, scenario_id)
            for required in (
                "Commands used:",
                "Files touched:",
                "Caveats:",
                "Unresolved gaps:",
                "Next safe action:",
            ):
                self.assertIn(required, scenario_text, scenario_id)
        self.assertIn("Result: pass", text)

    def test_packaging_reference_covers_phase_7_rollout(self) -> None:
        text = (SKILL_DIR / "references" / "packaging.md").read_text(encoding="utf-8")
        required_phrases = (
            "$CODEX_HOME/skills/async-research-operator/",
            'test -n "$CODEX_HOME"',
            "Use the async-research-operator skill. Inspect this workspace",
            "missing CLI setup diagnosis",
            "one bounded worker loop",
            "one acceptance/readiness mismatch stop",
            "Do not auto-install",
            "Update And Uninstall",
        )

        for phrase in required_phrases:
            self.assertIn(phrase, text)

    def test_codex_dogfood_evidence_records_read_only_trial(self) -> None:
        text = DOGFOOD_TRANSCRIPT.read_text(encoding="utf-8")
        required_phrases = (
            "Skill source: repository package, not installed into $CODEX_HOME",
            "First-use prompt:",
            "Commands used:",
            "Files touched: none",
            "mutations_performed: []",
            "privacy_boundary: approval_required",
            "research_ops: missing",
            "Existing Coffee-Style Workspace Status",
            "Readiness dry-run: failed",
            "readiness-failure stop before operation",
            "Next safe action: ask before initializing research_ops",
            "Result: pass for read-only first-use and stop behavior",
            "Limitations:",
        )

        for phrase in required_phrases:
            self.assertIn(phrase, text)

    def test_provider_notes_scope_cross_provider_exports_and_gateway(self) -> None:
        text = (SKILL_DIR / "references" / "provider-notes.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(text.split())
        required_phrases = (
            "Codex App",
            "Codex CLI/automation",
            "Claude Code",
            "ChatGPT agent with repo tools",
            "ChatGPT/Claude web chat only",
            "API agent wrapper",
            "Prompt Pack Contracts",
            "Read-Only External Reviewer",
            "same_agent_visible",
            "Remote/API write operation is split into a future roadmap",
            "API wrappers and browser agents stay read-only or advisory",
        )

        for phrase in required_phrases:
            self.assertIn(" ".join(phrase.split()), normalized)


if __name__ == "__main__":
    unittest.main()

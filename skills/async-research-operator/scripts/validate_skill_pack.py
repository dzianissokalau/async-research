#!/usr/bin/env python3
"""Validate the async-research-operator skill package."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


REQUIRED_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/startup.md",
    "references/setup.md",
    "references/command-recipes.md",
    "references/roles.md",
    "references/safety-and-stop-conditions.md",
    "references/reporting.md",
    "references/provider-notes.md",
    "references/trigger-evals.md",
    "references/behavioral-evals.md",
    "references/packaging.md",
    "scripts/inspect_workspace.py",
    "scripts/validate_skill_pack.py",
)
FORBIDDEN_FILENAMES = {
    "README.md",
    "CHANGELOG.md",
    "INSTALLATION_GUIDE.md",
    "QUICK_REFERENCE.md",
}
REQUIRED_FRONTMATTER_KEYS = ("name", "description")
REFERENCE_LINK_RE = re.compile(r"\[[^\]]+\]\((references/[^)]+)\)")
REQUIRED_RECIPE_HEADINGS = (
    "## Command Capability Probe",
    "## Recipe 1 - Status-Only Check",
    "## Recipe 2 - Guided Framework Setup",
    "## Recipe 3 - New Workspace Setup",
    "## Recipe 4 - Idea Capture And Promotion",
    "## Recipe 5 - Manual Or LLM Task Creation",
    "## Recipe 6 - Worker Loop",
    "## Recipe 7 - Review Loop",
    "## Recipe 8 - Human Gate Handling",
    "## Recipe 9 - Foundation Proposal Loop",
    "## Recipe 10 - Deliverable Maturity Loop",
    "## Recipe 11 - Maintenance Loop",
    "## Command Capability Table",
)
REQUIRED_CAPABILITY_ROWS = (
    "| Framework setup |",
    "| Workspace setup |",
    "| `workflow next/status` |",
    "| `idea capture/promote` |",
    "| `worker-start/complete` |",
    "| `review` / `decision` |",
    "| Foundation proposals |",
    "| `deliverable` |",
    "| Maintenance |",
)
REQUIRED_ROLE_HEADINGS = (
    "## First Status Report",
    "## Role Mode Matrix",
    "## Same-Agent Review And Critic Independence",
    "## Role Switching Rules",
    "## Autonomy Policy Matrix",
)
REQUIRED_ROLE_PHRASES = (
    "Status reporter",
    "Planner",
    "Worker",
    "Reviewer",
    "Critic",
    "Synthesizer",
    "Maintainer",
    "autonomy_level",
    "same_agent_visible",
    "--independence-type separate_agent",
    "--independence-type same_agent_visible",
    "`read_only`",
    "`guided`",
    "`bounded_autonomous`",
    "`maintenance`",
)
REQUIRED_SAFETY_PHRASES = (
    "## Role And Autonomy Gates",
    "## Reporting And Dashboard Alignment Stops",
    "## High-Impact Claims",
    "first status report",
    "`autonomy_level`",
    "`bounded_autonomous`",
    "same_agent_visible",
    "console snapshot research_ops --json",
    "aggregate/result acceptance",
    "accepted memory disagree",
    "`deliverable check` fails",
    "publication-readiness claims",
    "working-paper-ready",
    "submission-ready",
)
REQUIRED_REPORTING_HEADINGS = (
    "## Report Rules",
    "## Startup Report",
    "## Task Completion Report",
    "## Human Decision Request",
    "## Deliverable Maturity Report",
    "## Maintenance Report",
    "## Dashboard Alignment Rules",
)
REQUIRED_REPORTING_PHRASES = (
    "framework version",
    "workspace path",
    "privacy status",
    "health/readiness/workflow summary",
    "task ID",
    "files changed",
    "worker output",
    "review status",
    "acceptance route",
    "decision needed",
    "evidence links",
    "consequences",
    "recommended default",
    "target maturity",
    "current maturity",
    "failed gates",
    "critic status",
    "open response rows",
    "checks run",
    "warnings",
    "stale evidence",
    "dashboard URL or snapshot summary",
    "commands used",
    "console snapshot research_ops --json",
    "dashboard or console snapshot data as a consistency check",
    "task acceptance from deliverable readiness",
    "aggregate or result acceptance",
    "accepted memory disagree",
    "`deliverable check` fails",
)
REQUIRED_BEHAVIORAL_HEADINGS = (
    "## Fixture Coverage",
    "## Behavioral Eval Prompts",
    "## Scoring Rubric",
    "## Forward-Test Evidence",
    "## Known Limitations",
)
REQUIRED_BEHAVIORAL_PHRASES = (
    "tests/fixtures/skill_operator/scenarios.json",
    "tests/fixtures/skill_operator/trigger_eval_cases.json",
    "tests/fixtures/skill_operator/transcripts/codex_fixture_replay_2026-05-20.md",
    "`missing_cli`",
    "`framework_repo_no_venv`",
    "`valid_cli_no_workspace`",
    "`fresh_workspace_no_tasks`",
    "`ready_task`",
    "`locked_task`",
    "`awaiting_review`",
    "`needs_human_gate`",
    "`accepted_evidence_not_ready`",
    "`source_data_blocker`",
    "`unsafe_request`",
    "asks before writes",
    "stops at human gates",
    "accepted task evidence from deliverable readiness",
    "commands run",
    "files touched",
    "caveats",
    "unresolved gaps",
)
REQUIRED_PACKAGING_HEADINGS = (
    "## Install Or Reference",
    "## First-Use Prompt",
    "## Dogfood Checklist",
    "## Dogfood Evidence Rules",
    "## Update And Uninstall",
)
REQUIRED_PACKAGING_PHRASES = (
    "$CODEX_HOME/skills/async-research-operator/",
    'test -n "$CODEX_HOME"',
    "cp -R skills/async-research-operator",
    "restart or reload Codex",
    "Use the async-research-operator skill. Inspect this workspace, report the current state, and recommend the next safe action without writing files.",
    "missing CLI setup diagnosis",
    "approved project-local install or explicit skip decision",
    "missing `research_ops/` bootstrap diagnosis",
    "existing coffee-style workspace status",
    "one bounded worker loop",
    "one review loop",
    "one human gate stop",
    "one deliverable maturity report",
    "one acceptance/readiness mismatch stop",
    "one command-capability or version-drift report",
    "Do not auto-install",
    "fresh-session transcript or a delivery log",
    "If `CODEX_HOME` is empty or unknown",
    "tests/fixtures/skill_operator/transcripts/codex_dogfood_rollout_2026-05-20.md",
)


def parse_frontmatter(text: str) -> tuple[dict[str, str], list[str]]:
    if not text.startswith("---\n"):
        return {}, ["missing_frontmatter"]
    end = text.find("\n---", 4)
    if end == -1:
        return {}, ["unterminated_frontmatter"]

    fields: dict[str, str] = {}
    failures: list[str] = []
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        if ":" not in line:
            failures.append(f"invalid_frontmatter_line:{line}")
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        fields[key] = value
    return fields, failures


def validate_required_files(skill_dir: Path, failures: list[dict[str, str]]) -> None:
    for relative in REQUIRED_FILES:
        if not (skill_dir / relative).is_file():
            failures.append({"path": relative, "reason": "missing_required_file"})


def validate_forbidden_files(skill_dir: Path, failures: list[dict[str, str]]) -> None:
    for path in sorted(skill_dir.rglob("*")):
        if path.is_file() and path.name in FORBIDDEN_FILENAMES:
            failures.append(
                {
                    "path": path.relative_to(skill_dir).as_posix(),
                    "reason": "forbidden_clutter_file",
                }
            )


def validate_skill_md(skill_dir: Path, failures: list[dict[str, str]]) -> None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return

    text = skill_md.read_text(encoding="utf-8")
    fields, frontmatter_failures = parse_frontmatter(text)
    for reason in frontmatter_failures:
        failures.append({"path": "SKILL.md", "reason": reason})
    for key in REQUIRED_FRONTMATTER_KEYS:
        if not fields.get(key):
            failures.append({"path": "SKILL.md", "reason": f"missing_frontmatter_{key}"})
    if fields.get("name") and fields["name"] != skill_dir.name:
        failures.append({"path": "SKILL.md", "reason": "frontmatter_name_mismatch"})

    description = fields.get("description", "")
    for required in ("research_ops", "async-research", "dashboard", "workflow"):
        if required not in description:
            failures.append({"path": "SKILL.md", "reason": f"description_missing_{required}"})

    linked = {match.group(1) for match in REFERENCE_LINK_RE.finditer(text)}
    for relative in linked:
        if not (skill_dir / relative).is_file():
            failures.append({"path": "SKILL.md", "reason": f"broken_reference_link:{relative}"})

    reference_files = {
        path.relative_to(skill_dir).as_posix()
        for path in (skill_dir / "references").glob("*.md")
    }
    for relative in sorted(reference_files - linked):
        failures.append({"path": relative, "reason": "reference_not_linked_from_skill"})


def validate_openai_yaml(skill_dir: Path, failures: list[dict[str, str]]) -> None:
    openai_yaml = skill_dir / "agents" / "openai.yaml"
    if not openai_yaml.is_file():
        return

    text = openai_yaml.read_text(encoding="utf-8")
    required_snippets = (
        'display_name: "Async Research Operator"',
        'short_description: "Operate async-research workspaces safely"',
        "$async-research-operator",
    )
    for snippet in required_snippets:
        if snippet not in text:
            failures.append({"path": "agents/openai.yaml", "reason": f"missing_metadata:{snippet}"})


def validate_trigger_evals(skill_dir: Path, failures: list[dict[str, str]]) -> None:
    trigger_evals = skill_dir / "references" / "trigger-evals.md"
    if not trigger_evals.is_file():
        return

    text = trigger_evals.read_text(encoding="utf-8")
    if "Candidate C - Selected" not in text:
        failures.append({"path": "references/trigger-evals.md", "reason": "missing_selected_candidate"})
    should_trigger = len(re.findall(r"^\d+\. ", section(text, "## Should Trigger"), re.MULTILINE))
    should_not_trigger = len(re.findall(r"^\d+\. ", section(text, "## Should Not Trigger"), re.MULTILINE))
    if should_trigger < 18:
        failures.append({"path": "references/trigger-evals.md", "reason": "too_few_should_trigger_examples"})
    if should_not_trigger < 10:
        failures.append({"path": "references/trigger-evals.md", "reason": "too_few_should_not_trigger_examples"})


def validate_command_recipes(skill_dir: Path, failures: list[dict[str, str]]) -> None:
    command_recipes = skill_dir / "references" / "command-recipes.md"
    if not command_recipes.is_file():
        return

    text = command_recipes.read_text(encoding="utf-8")
    for heading in REQUIRED_RECIPE_HEADINGS:
        if heading not in text:
            failures.append(
                {
                    "path": "references/command-recipes.md",
                    "reason": f"missing_recipe_heading:{heading}",
                }
            )
    for row in REQUIRED_CAPABILITY_ROWS:
        if row not in text:
            failures.append(
                {
                    "path": "references/command-recipes.md",
                    "reason": f"missing_capability_row:{row}",
                }
            )
    for required_phrase in (
        "--dry-run",
        "--write",
        "Stop conditions:",
        "Mutates:",
        "Read-only",
        "Write-capable",
    ):
        if required_phrase not in text:
            failures.append(
                {
                    "path": "references/command-recipes.md",
                    "reason": f"missing_recipe_safety_phrase:{required_phrase}",
                }
            )


def validate_roles(skill_dir: Path, failures: list[dict[str, str]]) -> None:
    roles = skill_dir / "references" / "roles.md"
    if not roles.is_file():
        return

    text = roles.read_text(encoding="utf-8")
    for heading in REQUIRED_ROLE_HEADINGS:
        if heading not in text:
            failures.append(
                {
                    "path": "references/roles.md",
                    "reason": f"missing_role_heading:{heading}",
                }
            )
    for phrase in REQUIRED_ROLE_PHRASES:
        if phrase not in text:
            failures.append(
                {
                    "path": "references/roles.md",
                    "reason": f"missing_role_contract:{phrase}",
                }
            )


def validate_safety(skill_dir: Path, failures: list[dict[str, str]]) -> None:
    safety = skill_dir / "references" / "safety-and-stop-conditions.md"
    if not safety.is_file():
        return

    text = safety.read_text(encoding="utf-8")
    for phrase in REQUIRED_SAFETY_PHRASES:
        if phrase not in text:
            failures.append(
                {
                    "path": "references/safety-and-stop-conditions.md",
                    "reason": f"missing_safety_contract:{phrase}",
                }
            )


def validate_reporting(skill_dir: Path, failures: list[dict[str, str]]) -> None:
    reporting = skill_dir / "references" / "reporting.md"
    if not reporting.is_file():
        return

    text = reporting.read_text(encoding="utf-8")
    normalized = " ".join(text.lower().split())
    for heading in REQUIRED_REPORTING_HEADINGS:
        if heading not in text:
            failures.append(
                {
                    "path": "references/reporting.md",
                    "reason": f"missing_reporting_heading:{heading}",
                }
            )
    for phrase in REQUIRED_REPORTING_PHRASES:
        if phrase.lower() not in normalized:
            failures.append(
                {
                    "path": "references/reporting.md",
                    "reason": f"missing_reporting_contract:{phrase}",
                }
            )


def validate_behavioral_evals(skill_dir: Path, failures: list[dict[str, str]]) -> None:
    behavioral = skill_dir / "references" / "behavioral-evals.md"
    if not behavioral.is_file():
        return

    text = behavioral.read_text(encoding="utf-8")
    normalized = " ".join(text.lower().split())
    for heading in REQUIRED_BEHAVIORAL_HEADINGS:
        if heading not in text:
            failures.append(
                {
                    "path": "references/behavioral-evals.md",
                    "reason": f"missing_behavioral_heading:{heading}",
                }
            )
    for phrase in REQUIRED_BEHAVIORAL_PHRASES:
        if phrase.lower() not in normalized:
            failures.append(
                {
                    "path": "references/behavioral-evals.md",
                    "reason": f"missing_behavioral_contract:{phrase}",
                }
            )


def validate_packaging(skill_dir: Path, failures: list[dict[str, str]]) -> None:
    packaging = skill_dir / "references" / "packaging.md"
    if not packaging.is_file():
        return

    text = packaging.read_text(encoding="utf-8")
    normalized = " ".join(text.lower().split())
    for heading in REQUIRED_PACKAGING_HEADINGS:
        if heading not in text:
            failures.append(
                {
                    "path": "references/packaging.md",
                    "reason": f"missing_packaging_heading:{heading}",
                }
            )
    for phrase in REQUIRED_PACKAGING_PHRASES:
        if phrase.lower() not in normalized:
            failures.append(
                {
                    "path": "references/packaging.md",
                    "reason": f"missing_packaging_contract:{phrase}",
                }
            )


def section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start == -1:
        return ""
    next_heading = text.find("\n## ", start + len(heading))
    if next_heading == -1:
        return text[start:]
    return text[start:next_heading]


def validate(skill_dir: Path) -> dict[str, object]:
    failures: list[dict[str, str]] = []
    if not skill_dir.is_dir():
        return {
            "ok": False,
            "skill_dir": str(skill_dir),
            "failures": [{"path": str(skill_dir), "reason": "missing_skill_dir"}],
        }

    validate_required_files(skill_dir, failures)
    validate_forbidden_files(skill_dir, failures)
    validate_skill_md(skill_dir, failures)
    validate_openai_yaml(skill_dir, failures)
    validate_trigger_evals(skill_dir, failures)
    validate_command_recipes(skill_dir, failures)
    validate_roles(skill_dir, failures)
    validate_safety(skill_dir, failures)
    validate_reporting(skill_dir, failures)
    validate_behavioral_evals(skill_dir, failures)
    validate_packaging(skill_dir, failures)

    return {"ok": not failures, "skill_dir": str(skill_dir), "failures": failures}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the async-research-operator skill package.")
    parser.add_argument(
        "--skill-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Skill directory to validate; defaults to this script's parent skill directory.",
    )
    args = parser.parse_args(argv)

    result = validate(args.skill_dir.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

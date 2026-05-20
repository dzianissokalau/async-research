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

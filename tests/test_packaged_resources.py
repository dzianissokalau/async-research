"""Regression tests for packaged schemas, policies, and starter resources."""

from __future__ import annotations

import hashlib
import re
import unittest
from importlib import resources
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "async_research_workflow"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_files(root: Path) -> list[Path]:
    suffixes = {".csv", ".json", ".jsonl", ".md"}
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix in suffixes)


class PackagedResourceTests(unittest.TestCase):
    def test_duplicate_schema_copies_match_until_canonicalized(self) -> None:
        failures: list[str] = []
        for canonical in sorted((PACKAGE_ROOT / "schemas").glob("*.schema.json")):
            root_copy = PACKAGE_ROOT / canonical.name
            if not root_copy.exists():
                failures.append(f"missing root schema copy for {canonical.name}")
                continue
            if sha256(canonical) != sha256(root_copy):
                failures.append(f"schema copy drifted: {canonical.name}")

        self.assertEqual([], failures)

    def test_example_mission_policy_matches_canonical_policy(self) -> None:
        canonical = PACKAGE_ROOT / "mission_policy.json"
        example = PACKAGE_ROOT / "examples" / "mission_policy.json"

        self.assertEqual(sha256(canonical), sha256(example))

    def test_key_resources_are_available_via_importlib_resources(self) -> None:
        package = resources.files("async_research_workflow")
        required = [
            ("schemas", "task_status.schema.json"),
            ("schemas", "experiment_plan.schema.json"),
            ("templates", "artifact_templates", "task_template.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "README.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "tasks", ".gitkeep"),
            ("templates", "research_ops_starter", "research_ops", "README.md"),
            ("templates", "research_ops_starter", "research_ops", "tasks", "TASK-0001-data-readiness", "status.json"),
            ("examples", "github_actions_codex_worker.yml"),
            ("examples", "benchmarks", "autonomy_benchmark_cases.json"),
            ("mission_policy.json",),
        ]

        missing = [
            "/".join(parts)
            for parts in required
            if not package.joinpath(*parts).is_file()
        ]
        self.assertEqual([], missing)

    def test_generic_starter_is_domain_neutral_and_empty(self) -> None:
        starter = PACKAGE_ROOT / "templates" / "generic_research_ops_starter" / "research_ops"
        forbidden = [
            "real-estate",
            "real estate",
            "hm land registry",
            "bank of england",
            "office for national statistics",
            "mortgage",
            "property",
            "housing",
            "house price",
        ]
        forbidden_patterns = [re.compile(r"\bons\b")]
        hits: list[str] = []
        for path in text_files(starter):
            text = path.read_text(encoding="utf-8").lower()
            for term in forbidden:
                if term in text:
                    hits.append(f"{path.relative_to(PACKAGE_ROOT)} contains {term!r}")
            for pattern in forbidden_patterns:
                if pattern.search(text):
                    hits.append(f"{path.relative_to(PACKAGE_ROOT)} matches {pattern.pattern!r}")

        self.assertEqual([], hits)
        self.assertFalse((starter / "health_report.json").exists())
        self.assertEqual([], list((starter / "tasks").glob("*/status.json")))

    def test_real_estate_starter_remains_explicit_worked_example(self) -> None:
        starter = PACKAGE_ROOT / "templates" / "research_ops_starter" / "research_ops"

        self.assertTrue((starter / "tasks" / "TASK-0001-data-readiness" / "status.json").exists())
        self.assertTrue((starter / "health_report.json").exists())
        text = (starter / "README.md").read_text(encoding="utf-8").lower()
        self.assertIn("real-estate", text)


if __name__ == "__main__":
    unittest.main()

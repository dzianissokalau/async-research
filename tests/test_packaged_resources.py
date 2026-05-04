"""Regression tests for packaged schemas, policies, and starter resources."""

from __future__ import annotations

import hashlib
import unittest
from importlib import resources
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "async_research_workflow"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
            ("templates", "research_ops_starter", "research_ops", "README.md"),
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


if __name__ == "__main__":
    unittest.main()

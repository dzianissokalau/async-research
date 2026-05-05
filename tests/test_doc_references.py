"""Regression tests for documentation and starter package references."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "async_research_workflow"

TOP_LEVEL_DOCS = [
    ROOT / "README.md",
]
DOC_TREES = [
    ROOT / ".github",
    ROOT / "roadmaps",
    PACKAGE_ROOT / "docs",
    PACKAGE_ROOT / "examples",
    PACKAGE_ROOT / "templates",
]
TEXT_SUFFIXES = {".csv", ".json", ".md", ".txt", ".yml", ".yaml"}
FORBIDDEN_SNIPPETS = (
    "async_research_workflow/examples/scripts/",
    "examples/scripts/",
    "blob/main/ROADMAP.md",
)
EXAMPLES_REF_RE = re.compile(r"async_research_workflow/examples/[A-Za-z0-9_./-]+")
RELATIVE_EXAMPLES_REF_RE = re.compile(r"(?<!async_research_workflow/)examples/[A-Za-z0-9_./-]+")
SCRIPT_REF_RE = re.compile(r"async_research_workflow/scripts/[A-Za-z0-9_./-]+\.py")
ROOT_SCHEMA_REF_RE = re.compile(r"async_research_workflow/[A-Za-z0-9_]+\.schema\.json")
REMOVED_EXAMPLE_RESOURCE_RE = re.compile(
    r"async_research_workflow/examples/(?:mission_policy\.json|benchmarks/autonomy_benchmark_cases\.json)"
)


def iter_documentation_files() -> list[Path]:
    files = list(TOP_LEVEL_DOCS)
    for tree in DOC_TREES:
        files.extend(
            path
            for path in tree.rglob("*")
            if path.is_file() and path.suffix in TEXT_SUFFIXES
        )
    return sorted(set(files))


def clean_reference(raw: str) -> str:
    return raw.rstrip("`'\".,:;)]}")


class DocumentationReferenceTests(unittest.TestCase):
    def test_docs_do_not_use_removed_or_stale_paths(self) -> None:
        failures: list[str] = []
        for path in iter_documentation_files():
            text = path.read_text(encoding="utf-8")
            for snippet in FORBIDDEN_SNIPPETS:
                if snippet in text:
                    failures.append(f"{path.relative_to(ROOT)} contains {snippet}")

        self.assertEqual([], failures)

    def test_examples_package_references_exist(self) -> None:
        failures: list[str] = []
        for path in iter_documentation_files():
            text = path.read_text(encoding="utf-8")
            for match in EXAMPLES_REF_RE.finditer(text):
                reference = clean_reference(match.group(0))
                package_path = ROOT / "src" / reference
                if not package_path.exists():
                    line = text.count("\n", 0, match.start()) + 1
                    failures.append(f"{path.relative_to(ROOT)}:{line} -> {reference}")
            for match in RELATIVE_EXAMPLES_REF_RE.finditer(text):
                reference = clean_reference(match.group(0))
                package_path = PACKAGE_ROOT / reference
                if not package_path.exists():
                    line = text.count("\n", 0, match.start()) + 1
                    failures.append(f"{path.relative_to(ROOT)}:{line} -> {reference}")
            for match in SCRIPT_REF_RE.finditer(text):
                reference = clean_reference(match.group(0))
                package_path = ROOT / "src" / reference
                if not package_path.exists():
                    line = text.count("\n", 0, match.start()) + 1
                    failures.append(f"{path.relative_to(ROOT)}:{line} -> {reference}")

        self.assertEqual([], failures)

    def test_docs_use_canonical_runtime_resource_paths(self) -> None:
        failures: list[str] = []
        for path in iter_documentation_files():
            text = path.read_text(encoding="utf-8")
            for pattern in (ROOT_SCHEMA_REF_RE, REMOVED_EXAMPLE_RESOURCE_RE):
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    failures.append(f"{path.relative_to(ROOT)}:{line} -> {match.group(0)}")

        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()

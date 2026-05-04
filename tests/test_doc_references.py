"""Regression tests for public documentation and starter package references."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "async_research_workflow"

PUBLIC_DOCS = [
    ROOT / "README.md",
    PACKAGE_ROOT / "docs" / "README.md",
    PACKAGE_ROOT / "docs" / "operational_readiness_runbook.md",
    PACKAGE_ROOT / "docs" / "scheduler_and_prompts.md",
]
PUBLIC_TREES = [
    PACKAGE_ROOT / "examples",
    PACKAGE_ROOT / "templates",
]
TEXT_SUFFIXES = {".csv", ".json", ".md", ".txt", ".yml", ".yaml"}
FORBIDDEN_SNIPPETS = (
    "async_research_workflow/examples/scripts/",
    "examples/scripts/",
)
EXAMPLES_REF_RE = re.compile(r"async_research_workflow/examples/[A-Za-z0-9_./-]+")
RELATIVE_EXAMPLES_REF_RE = re.compile(r"(?<!async_research_workflow/)examples/[A-Za-z0-9_./-]+")


def iter_public_files() -> list[Path]:
    files = list(PUBLIC_DOCS)
    for tree in PUBLIC_TREES:
        files.extend(
            path
            for path in tree.rglob("*")
            if path.is_file() and path.suffix in TEXT_SUFFIXES
        )
    return sorted(set(files))


def clean_reference(raw: str) -> str:
    return raw.rstrip("`'\".,:;)]}")


class PublicDocumentationReferenceTests(unittest.TestCase):
    def test_public_docs_do_not_use_removed_examples_scripts_paths(self) -> None:
        failures: list[str] = []
        for path in iter_public_files():
            text = path.read_text(encoding="utf-8")
            for snippet in FORBIDDEN_SNIPPETS:
                if snippet in text:
                    failures.append(f"{path.relative_to(ROOT)} contains {snippet}")

        self.assertEqual([], failures)

    def test_examples_package_references_exist(self) -> None:
        failures: list[str] = []
        for path in iter_public_files():
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

        self.assertEqual([], failures)


if __name__ == "__main__":
    unittest.main()

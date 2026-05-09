"""Regression tests for packaged docs policy and footprint."""

from __future__ import annotations

import tomllib
import unittest
from importlib import resources as importlib_resources
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "async_research_workflow"
DOCS_ROOT = PACKAGE_ROOT / "docs"
POLICY = ROOT / "DOCS_PACKAGING_REVIEW.md"
MAX_PACKAGED_DOCS_BYTES = 1_000_000
MAX_SINGLE_DOC_BYTES = 128 * 1024
REQUIRED_PACKAGED_DOCS = [
    ("README.md",),
    ("operational_readiness_runbook.md",),
    ("scheduler_and_prompts.md",),
    ("task_contracts.md",),
    ("knowledge_library_contract.md",),
    ("reviewer_isolation_protocol.md",),
    ("framework_requirements", "README.md"),
]


def packaged_doc_files() -> list[Path]:
    return sorted(path for path in DOCS_ROOT.rglob("*") if path.is_file())


class DocsPackagingTests(unittest.TestCase):
    def test_policy_records_keep_packaged_decision(self) -> None:
        text = POLICY.read_text(encoding="utf-8")

        for snippet in [
            "Keep Markdown protocol and operator docs packaged",
            "roughly 46 Markdown files and 382 KiB",
            "Keep the packaged docs footprint below 1 MiB",
            "Verify key packaged docs through `importlib.resources`",
        ]:
            self.assertIn(snippet, text)

    def test_pyproject_keeps_docs_package_data_explicit(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        package_data = pyproject["tool"]["setuptools"]["package-data"]["async_research_workflow"]

        self.assertIn("docs/**/*.md", package_data)
        self.assertNotIn("docs/**/*", package_data)

    def test_packaged_docs_are_markdown_only_and_within_footprint(self) -> None:
        docs = packaged_doc_files()
        non_markdown = [
            str(path.relative_to(DOCS_ROOT))
            for path in docs
            if path.suffix != ".md"
        ]
        oversized = [
            f"{path.relative_to(DOCS_ROOT)}: {path.stat().st_size} bytes"
            for path in docs
            if path.stat().st_size > MAX_SINGLE_DOC_BYTES
        ]
        total_bytes = sum(path.stat().st_size for path in docs)

        self.assertGreaterEqual(len(docs), 40)
        self.assertEqual([], non_markdown)
        self.assertEqual([], oversized)
        self.assertLessEqual(total_bytes, MAX_PACKAGED_DOCS_BYTES)

    def test_key_docs_are_available_via_importlib_resources(self) -> None:
        docs = importlib_resources.files("async_research_workflow").joinpath("docs")
        missing = [
            "/".join(parts)
            for parts in REQUIRED_PACKAGED_DOCS
            if not docs.joinpath(*parts).is_file()
        ]

        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()

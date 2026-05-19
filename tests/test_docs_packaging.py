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


def packaged_docs_diagnostics(docs: list[Path]) -> str:
    total_bytes = sum(path.stat().st_size for path in docs)
    largest_docs = sorted(
        ((path.stat().st_size, path.relative_to(DOCS_ROOT)) for path in docs),
        key=lambda item: item[0],
        reverse=True,
    )[:5]
    non_markdown = [
        str(path.relative_to(DOCS_ROOT))
        for path in docs
        if path.suffix != ".md"
    ]

    lines = [
        f"packaged docs total: {total_bytes} bytes "
        f"(threshold: {MAX_PACKAGED_DOCS_BYTES} bytes)",
        f"single doc threshold: {MAX_SINGLE_DOC_BYTES} bytes",
        "largest packaged docs:",
    ]
    lines.extend(f"- {relative}: {size} bytes" for size, relative in largest_docs)
    if non_markdown:
        lines.append("non-Markdown files:")
        lines.extend(f"- {path}" for path in non_markdown)
    else:
        lines.append("non-Markdown files: none")
    return "\n".join(lines)


class DocsPackagingTests(unittest.TestCase):
    def test_policy_records_keep_packaged_decision(self) -> None:
        text = POLICY.read_text(encoding="utf-8")
        normalized = " ".join(text.split())

        for snippet in [
            "Keep Markdown protocol and operator docs packaged",
            "Do not split the docs into an optional extra or external download",
            "comfortably below the 1 MiB packaging threshold",
            "The installed-wheel cost is about 154 KB (150 KiB) compressed",
            "does not include a user or reviewer report about wheel-size, installation, or distribution pain",
            "Keep the packaged docs footprint below 1 MiB",
            "Verify key packaged docs through `importlib.resources`",
        ]:
            self.assertIn(" ".join(snippet.split()), normalized)

    def test_policy_records_measured_artifact_footprint(self) -> None:
        text = POLICY.read_text(encoding="utf-8")

        for snippet in [
            ".venv/bin/python -m build --outdir /private/tmp/arw-docs-packaging-review",
            "| Wheel artifact | 586,416 bytes |",
            "| Source distribution artifact | 589,490 bytes |",
            "| Wheel package payload, uncompressed | 1,976,398 bytes |",
            "| Packaged docs files | 47 Markdown files |",
            "| Packaged docs, uncompressed | 427,255 bytes |",
            "| Packaged docs, compressed in wheel | 153,593 bytes |",
            "| Packaged docs share of compressed wheel | 26.2% |",
        ]:
            self.assertIn(snippet, text)

    def test_pyproject_keeps_docs_package_data_explicit(self) -> None:
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        package_data = pyproject["tool"]["setuptools"]["package-data"]["async_research_workflow"]

        self.assertIn("docs/**/*.md", package_data)
        self.assertNotIn("docs/**/*", package_data)

    def test_packaged_docs_are_markdown_only_and_within_footprint(self) -> None:
        docs = packaged_doc_files()
        diagnostics = packaged_docs_diagnostics(docs)
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
        self.assertEqual([], non_markdown, diagnostics)
        self.assertEqual([], oversized, diagnostics)
        self.assertLessEqual(total_bytes, MAX_PACKAGED_DOCS_BYTES, diagnostics)

    def test_packaged_docs_diagnostics_include_threshold_context(self) -> None:
        diagnostics = packaged_docs_diagnostics(packaged_doc_files())

        for snippet in [
            "packaged docs total:",
            f"threshold: {MAX_PACKAGED_DOCS_BYTES} bytes",
            f"single doc threshold: {MAX_SINGLE_DOC_BYTES} bytes",
            "largest packaged docs:",
            "non-Markdown files:",
        ]:
            self.assertIn(snippet, diagnostics)

    def test_key_docs_are_available_via_importlib_resources(self) -> None:
        docs = importlib_resources.files("async_research_workflow").joinpath("docs")
        missing = [
            "/".join(parts)
            for parts in REQUIRED_PACKAGED_DOCS
            if not docs.joinpath(*parts).is_file()
        ]

        self.assertEqual([], missing)

    def test_operator_ux_roadmap_records_docs_packaging_completion(self) -> None:
        roadmap = (ROOT / "roadmaps" / "delivered_operator_ux_workflow_ergonomics_roadmap.md").read_text(
            encoding="utf-8"
        )
        normalized = " ".join(roadmap.split())

        for snippet in [
            "Status: Delivered",
            "| 7 | Policy cleanup | Complete |",
            "Docs packaging review keeps Markdown protocol docs packaged for alpha",
            "586,416-byte wheel",
            "153,593 compressed docs bytes",
            "operator guidance demand without wheel-size or installation pain",
        ]:
            self.assertIn(" ".join(snippet.split()), normalized)


if __name__ == "__main__":
    unittest.main()

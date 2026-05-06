"""Regression tests for idea catalog starter templates."""

from __future__ import annotations

import unittest
from importlib import resources as importlib_resources
from pathlib import Path

from async_research_workflow.scripts import idea_catalog


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "async_research_workflow"
STARTERS = (
    PACKAGE_ROOT / "templates" / "generic_research_ops_starter" / "research_ops",
    PACKAGE_ROOT / "templates" / "research_ops_starter" / "research_ops",
)


class IdeaCatalogTemplateTests(unittest.TestCase):
    def test_starter_templates_include_empty_catalog_projection_files(self) -> None:
        for starter in STARTERS:
            with self.subTest(starter=starter.name):
                catalog = starter / "ideas" / "idea_catalog.md"
                prioritization = starter / "ideas" / "prioritization.md"

                self.assertEqual(idea_catalog.CATALOG_TEMPLATE, catalog.read_text(encoding="utf-8"))
                self.assertEqual(idea_catalog.PRIORITIZATION_TEMPLATE, prioritization.read_text(encoding="utf-8"))

    def test_catalog_templates_are_packaged_resources(self) -> None:
        package = importlib_resources.files("async_research_workflow")
        required = [
            ("templates", "generic_research_ops_starter", "research_ops", "ideas", "idea_catalog.md"),
            ("templates", "generic_research_ops_starter", "research_ops", "ideas", "prioritization.md"),
            ("templates", "research_ops_starter", "research_ops", "ideas", "idea_catalog.md"),
            ("templates", "research_ops_starter", "research_ops", "ideas", "prioritization.md"),
        ]

        missing = ["/".join(parts) for parts in required if not package.joinpath(*parts).is_file()]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()

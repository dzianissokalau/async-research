"""Regression tests for knowledge library starter templates."""

from __future__ import annotations

import unittest
from importlib import resources as importlib_resources
from pathlib import Path

from async_research_workflow.scripts import knowledge_library


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "async_research_workflow"
STARTERS = (
    PACKAGE_ROOT / "templates" / "generic_research_ops_starter" / "research_ops",
    PACKAGE_ROOT / "templates" / "research_ops_starter" / "research_ops",
)


class KnowledgeLibraryTemplateTests(unittest.TestCase):
    def test_starter_templates_include_empty_library_files(self) -> None:
        expected = dict(knowledge_library.STARTER_FILES)
        for starter in STARTERS:
            with self.subTest(starter=starter.parent.name):
                library_dir = starter / "library"
                self.assertTrue(library_dir.is_dir())
                for relative, template in expected.items():
                    path = starter / relative
                    text = path.read_text(encoding="utf-8")
                    self.assertEqual(template, text, str(relative))
                    self.assertIn("Free-form notes. Tooling must not edit this section.", text)
                    self.assertIn("Empty library state", text)

    def test_starter_readmes_explain_empty_library_state(self) -> None:
        for starter in STARTERS:
            with self.subTest(starter=starter.parent.name):
                text = (starter / "README.md").read_text(encoding="utf-8")
                self.assertIn("## Knowledge Library", text)
                self.assertIn("Empty library files are valid", text)
                self.assertIn("async-research library init research_ops --dry-run", text)
                self.assertIn("existing notes are preserved", text)

    def test_library_templates_are_packaged_resources(self) -> None:
        package = importlib_resources.files("async_research_workflow")
        required = []
        for template in ("generic_research_ops_starter", "research_ops_starter"):
            for relative, _ in knowledge_library.STARTER_FILES:
                required.append(("templates", template, "research_ops", *relative.parts))

        missing = ["/".join(parts) for parts in required if not package.joinpath(*parts).is_file()]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()

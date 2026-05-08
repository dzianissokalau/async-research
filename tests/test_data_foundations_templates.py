"""Regression tests for data foundation starter templates."""

from __future__ import annotations

import re
import unittest
from importlib import resources as importlib_resources
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "async_research_workflow"
GENERIC_STARTER = PACKAGE_ROOT / "templates" / "generic_research_ops_starter" / "research_ops"
REAL_ESTATE_STARTER = PACKAGE_ROOT / "templates" / "research_ops_starter" / "research_ops"
STARTERS = (GENERIC_STARTER, REAL_ESTATE_STARTER)
DATA_FILES = (
    "data_catalog.md",
    "data_access.md",
    "join_map.md",
    "known_data_gaps.md",
    "profiles/README.md",
)
SOURCE_ID_RE = re.compile(r"^source_id:\s*(DS-[0-9]{4})$", re.MULTILINE)


class DataFoundationTemplateTests(unittest.TestCase):
    def test_starter_templates_include_data_foundation_files(self) -> None:
        for starter in STARTERS:
            with self.subTest(starter=starter.parent.name):
                data_dir = starter / "data"
                self.assertTrue(data_dir.is_dir())
                for relative in DATA_FILES:
                    self.assertTrue((data_dir / relative).is_file(), relative)

    def test_profile_contract_defines_canonical_id_rule(self) -> None:
        for starter in STARTERS:
            with self.subTest(starter=starter.parent.name):
                contract = (starter / "data" / "profiles" / "README.md").read_text(encoding="utf-8")
                self.assertIn("DS-0000.md", contract)
                self.assertIn("source_id: DS-0000", contract)
                self.assertIn("filename and the internal", contract)
                self.assertIn("They must match", contract)

    def test_generic_starter_has_no_active_seed_profiles(self) -> None:
        profiles = sorted((GENERIC_STARTER / "data" / "profiles").glob("DS-[0-9][0-9][0-9][0-9].md"))
        self.assertEqual([], profiles)

    def test_real_estate_profiles_match_existing_audit_ids(self) -> None:
        expected_ids = {"DS-0001", "DS-0002", "DS-0003"}
        profile_dir = REAL_ESTATE_STARTER / "data" / "profiles"
        actual_ids: set[str] = set()
        for path in sorted(profile_dir.glob("DS-[0-9][0-9][0-9][0-9].md")):
            text = path.read_text(encoding="utf-8")
            match = SOURCE_ID_RE.search(text)
            self.assertIsNotNone(match, path.name)
            source_id = match.group(1)
            self.assertEqual(path.stem, source_id)
            actual_ids.add(source_id)

        self.assertEqual(expected_ids, actual_ids)
        audit_text = (REAL_ESTATE_STARTER / "data_source_audit.md").read_text(encoding="utf-8")
        catalog_text = (REAL_ESTATE_STARTER / "data" / "data_catalog.md").read_text(encoding="utf-8")
        for source_id in expected_ids:
            self.assertIn(f"| {source_id} |", audit_text)
            self.assertIn(f"data/profiles/{source_id}.md", catalog_text)

    def test_data_foundation_templates_are_packaged_resources(self) -> None:
        package = importlib_resources.files("async_research_workflow")
        required = []
        for template in ("generic_research_ops_starter", "research_ops_starter"):
            for relative in DATA_FILES:
                required.append(("templates", template, "research_ops", "data", *relative.split("/")))
        required.extend(
            [
                ("templates", "research_ops_starter", "research_ops", "data", "profiles", "DS-0001.md"),
                ("templates", "research_ops_starter", "research_ops", "data", "profiles", "DS-0002.md"),
                ("templates", "research_ops_starter", "research_ops", "data", "profiles", "DS-0003.md"),
            ]
        )

        missing = ["/".join(parts) for parts in required if not package.joinpath(*parts).is_file()]
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

from async_research_workflow import __version__


ROOT = Path(__file__).resolve().parents[1]


class ProjectMetadataTests(unittest.TestCase):
    def test_project_metadata_has_release_hygiene_fields(self) -> None:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = data["project"]

        self.assertEqual("Apache-2.0", project.get("license"))
        self.assertIn("LICENSE", project.get("license-files", []))
        self.assertIn("research-automation", project.get("keywords", []))

        urls = project.get("urls", {})
        for key in ["Homepage", "Repository", "Issues", "Changelog", "Roadmap"]:
            self.assertIn(key, urls)
            self.assertTrue(str(urls[key]).startswith("https://github.com/dzianissokalau/async-research"))

    def test_repo_hygiene_files_exist(self) -> None:
        required = [
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            ".github/ISSUE_TEMPLATE/config.yml",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/ISSUE_TEMPLATE/feature_request.yml",
            ".github/pull_request_template.md",
        ]
        missing = [path for path in required if not (ROOT / path).is_file()]
        self.assertEqual([], missing)

    def test_project_version_matches_package_version(self) -> None:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(data["project"]["version"], __version__)

    def test_package_data_includes_runnable_examples(self) -> None:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        package_data = data["tool"]["setuptools"]["package-data"]["async_research_workflow"]

        for pattern in [
            "examples/**/*.md",
            "examples/**/*.json",
            "examples/**/*.csv",
            "examples/**/*.jsonl",
        ]:
            self.assertIn(pattern, package_data)


if __name__ == "__main__":
    unittest.main()

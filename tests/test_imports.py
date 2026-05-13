from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

from async_research_workflow import __version__


ROOT = Path(__file__).resolve().parents[1]


class ImportTests(unittest.TestCase):
    def test_version_present_and_matches_project_metadata(self) -> None:
        data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(data["project"]["version"], __version__)


if __name__ == "__main__":
    unittest.main()

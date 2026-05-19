from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "async-research-operator"
VALIDATOR = SKILL_DIR / "scripts" / "validate_skill_pack.py"


def run_validator(skill_dir: Path) -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), "--skill-dir", str(skill_dir)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.stderr:
        raise AssertionError(result.stderr)
    return result.returncode, json.loads(result.stdout)


class AsyncResearchOperatorSkillTests(unittest.TestCase):
    def test_skill_pack_validator_passes_current_package(self) -> None:
        code, payload = run_validator(SKILL_DIR)

        self.assertEqual(0, code)
        self.assertTrue(payload["ok"])
        self.assertEqual([], payload["failures"])

    def test_validator_rejects_missing_required_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            (candidate / "references" / "startup.md").unlink()

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {"path": "references/startup.md", "reason": "missing_required_file"},
            payload["failures"],
        )

    def test_validator_rejects_broken_reference_links(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            skill_md = candidate / "SKILL.md"
            skill_md.write_text(
                skill_md.read_text(encoding="utf-8")
                + "\n- [missing.md](references/missing.md): broken.\n",
                encoding="utf-8",
            )

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        reasons = [failure["reason"] for failure in payload["failures"]]
        self.assertIn("broken_reference_link:references/missing.md", reasons)

    def test_validator_rejects_unlinked_reference_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            (candidate / "references" / "orphan.md").write_text("# Orphan\n", encoding="utf-8")

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {"path": "references/orphan.md", "reason": "reference_not_linked_from_skill"},
            payload["failures"],
        )

    def test_validator_rejects_forbidden_clutter_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = Path(temp_dir) / "async-research-operator"
            shutil.copytree(SKILL_DIR, candidate)
            (candidate / "README.md").write_text("extra docs\n", encoding="utf-8")

            code, payload = run_validator(candidate)

        self.assertEqual(1, code)
        self.assertIn(
            {"path": "README.md", "reason": "forbidden_clutter_file"},
            payload["failures"],
        )


if __name__ == "__main__":
    unittest.main()

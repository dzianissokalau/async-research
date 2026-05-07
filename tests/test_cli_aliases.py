"""Regression tests for additive CLI command aliases."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from async_research_workflow import cli


def run_cli_json(argv: list[str]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main(argv)
    return code, json.loads(stream.getvalue())


class CliAliasTests(unittest.TestCase):
    def test_review_surface_alias_updates_and_validates_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            init_code, init_payload = run_cli_json(["init", str(ops_dir)])
            self.assertEqual(cli.SUCCESS, init_code)
            self.assertTrue(init_payload["ok"])

            update_code, update_payload = run_cli_json(["review-surface", "update", str(ops_dir)])
            self.assertEqual(cli.SUCCESS, update_code)
            self.assertTrue(update_payload["ok"])
            self.assertTrue((ops_dir / "daily_status.md").exists())
            self.assertTrue((ops_dir / "human_review_queue.md").exists())

            validate_code, validate_payload = run_cli_json(["review-surface", "validate", str(ops_dir)])
            self.assertEqual(cli.SUCCESS, validate_code)
            self.assertTrue(validate_payload["ok"])

    def test_accepted_revalidate_alias_matches_revalidation_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            init_code, init_payload = run_cli_json(["init", str(ops_dir)])
            self.assertEqual(cli.SUCCESS, init_code)
            self.assertTrue(init_payload["ok"])

            canonical_code, canonical_payload = run_cli_json(["accepted", "revalidation", str(ops_dir)])
            alias_code, alias_payload = run_cli_json(["accepted", "revalidate", str(ops_dir)])

            self.assertEqual(canonical_code, alias_code)
            self.assertIn("generated_at", canonical_payload)
            self.assertIn("generated_at", alias_payload)
            canonical_payload.pop("generated_at")
            alias_payload.pop("generated_at")
            self.assertEqual(canonical_payload, alias_payload)
            self.assertTrue(alias_payload["ok"])


if __name__ == "__main__":
    unittest.main()

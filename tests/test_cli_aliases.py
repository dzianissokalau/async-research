"""Regression tests for additive CLI command aliases."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from async_research_workflow import cli


def run_cli_json(argv: list[str]) -> tuple[int, dict]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = cli.main(argv)
    return code, json.loads(stream.getvalue())


class CliAliasTests(unittest.TestCase):
    def test_supported_aliases_dispatch_to_canonical_modules(self) -> None:
        cases = [
            (
                ["surface", "update", "research_ops"],
                ["review-surface", "update", "research_ops"],
                ("human_review_surface", ["update", "research_ops"]),
            ),
            (
                ["surface", "validate", "research_ops"],
                ["review-surface", "validate", "research_ops"],
                ("human_review_surface", ["validate", "research_ops"]),
            ),
            (
                ["accepted", "revalidation", "research_ops", "--write-schedule"],
                ["accepted", "revalidate", "research_ops", "--write-schedule"],
                ("update_accepted_outputs_index", ["revalidation-report", "research_ops", "--write-schedule"]),
            ),
        ]

        for canonical_argv, alias_argv, expected_call in cases:
            canonical_call = self.dispatch_call_for(canonical_argv)
            alias_call = self.dispatch_call_for(alias_argv)

            self.assertEqual(expected_call, canonical_call)
            self.assertEqual(canonical_call, alias_call)

    def dispatch_call_for(self, argv: list[str]) -> tuple[str, list[str]]:
        with mock.patch.object(cli, "module_main", return_value=cli.SUCCESS) as module_main:
            code = cli.main(argv)

        self.assertEqual(cli.SUCCESS, code)
        module_main.assert_called_once()
        module_name, module_argv = module_main.call_args.args
        return module_name, module_argv

    def test_accepted_revalidate_alias_matches_revalidation_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ops_dir = Path(tmp) / "research_ops"
            init_code, init_payload = run_cli_json(["init", str(ops_dir)])
            self.assertEqual(cli.SUCCESS, init_code)
            self.assertTrue(init_payload["ok"])

            canonical_code, canonical_payload = run_cli_json(["accepted", "revalidation", str(ops_dir)])
            alias_code, alias_payload = run_cli_json(["accepted", "revalidate", str(ops_dir)])

        self.assertEqual(cli.SUCCESS, canonical_code)
        self.assertEqual(canonical_code, alias_code)
        self.assertTrue(canonical_payload["ok"])
        self.assertTrue(alias_payload["ok"])
        self.assertEqual(set(canonical_payload), set(alias_payload))
        canonical_payload.pop("generated_at", None)
        alias_payload.pop("generated_at", None)
        self.assertEqual(canonical_payload, alias_payload)


if __name__ == "__main__":
    unittest.main()

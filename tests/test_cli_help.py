"""Regression tests for public CLI help and exit-code documentation."""

from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path

from async_research_workflow import cli


ROOT = Path(__file__).resolve().parents[1]


def help_text(argv: list[str]) -> str:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        with contextlib.redirect_stderr(io.StringIO()):
            try:
                cli.main([*argv, "--help"])
            except SystemExit as exc:
                if exc.code != 0:
                    raise AssertionError(f"help for {argv!r} exited {exc.code}") from exc
            else:
                raise AssertionError(f"help for {argv!r} did not exit")
    return stream.getvalue()


class CliHelpTests(unittest.TestCase):
    def assert_help_contains(self, argv: list[str], snippets: list[str]) -> None:
        text = help_text(argv)
        normalized = " ".join(text.split())
        for snippet in snippets:
            self.assertIn(" ".join(snippet.split()), normalized, f"missing {snippet!r} from help for {argv!r}")

    def test_top_level_help_lists_commands_and_exit_code_summary(self) -> None:
        self.assert_help_contains(
            [],
            [
                "file-backed research_ops workspaces",
                "version",
                "init",
                "starter-smoke",
                "acceptance-suite",
                "readiness",
                "surface",
                "review-surface",
                "result-acceptance",
                "simulate-week",
                "Exit codes:",
                "See README.md for the command-specific contract.",
            ],
        )

    def test_every_public_command_help_has_operator_context(self) -> None:
        cases = [
            (["version"], ["installed async-research package version"]),
            (["init"], ["Starter template", "--template", "--force", "existing non-empty"]),
            (["starter-smoke"], ["starter workspace", "--template", "--force"]),
            (["acceptance-suite"], ["isolated temporary fixtures", "Exits 0"]),
            (["readiness"], ["Readiness exit codes:", "human action required"]),
            (["health"], ["accepted-memory health", "--dry-run"]),
            (["surface"], ["daily_status.md", "update", "validate"]),
            (["review-surface"], ["daily_status.md", "update", "validate"]),
            (["surface", "update"], ["daily_status.md", "human_review_queue.md"]),
            (["review-surface", "update"], ["daily_status.md", "human_review_queue.md"]),
            (["surface", "validate"], ["rendered human review surfaces"]),
            (["review-surface", "validate"], ["rendered human review surfaces"]),
            (["schema-check"], ["schema versions", "versioned JSON artifacts"]),
            (["source"], ["data_source_audit.md", "validate", "freshness", "check-experiment", "check-claim"]),
            (["source", "validate"], ["source audit rows"]),
            (["source", "freshness"], ["freshness windows"]),
            (["source", "check-experiment"], ["source IDs allowed for experiment planning", "--claim-impact"]),
            (["source", "check-claim"], ["selected use case and impact", "--use-case", "--allow-tier4-explicit"]),
            (["cost"], ["cost_ledger.csv", "summary", "ingest-usage", "budget-check"]),
            (["cost", "summary"], ["aggregate spend", "--ledger"]),
            (["cost", "ingest-usage"], ["usage artifact", "--usage-file", "--dry-run"]),
            (["cost", "budget-check"], ["proposed cost", "--proposed-api-usd", "--threshold"]),
            (["metrics"], ["metrics_history.jsonl", "append", "summarize"]),
            (["metrics", "append"], ["--label", "--update-weekly-digest"]),
            (["metrics", "summarize"], ["metrics_history.jsonl trends", "--output"]),
            (["accepted"], ["accepted_outputs_index.md", "check-duplicate", "check-memory-use", "revalidation", "revalidate"]),
            (["accepted", "update"], ["Upsert accepted task rows"]),
            (["accepted", "check-duplicate"], ["duplicate risk", "--title"]),
            (["accepted", "revalidation"], ["--write-schedule", "revalidation_schedule.md"]),
            (["accepted", "revalidate"], ["--write-schedule", "revalidation_schedule.md"]),
            (["accepted", "check-memory-use"], ["stale accepted memory", "--allow-stale"]),
            (["review"], ["independent review files", "aggregate"]),
            (["review", "aggregate"], ["reviews/*.md", "--dry-run"]),
            (["result-acceptance"], ["result_acceptance.json", "--update-ledgers"]),
            (["exploration"], ["exploration-cycle tasks", "validate"]),
            (["exploration", "validate"], ["worker output", "--task-dir"]),
            (["idea"], ["idea-evaluation JSON artifacts", "score", "validate"]),
            (["idea", "score"], ["--budget-mode", "mission policy"]),
            (["idea", "validate"], ["idea-evaluation JSON"]),
            (["experiment"], ["source readiness", "validate"]),
            (["experiment", "validate"], ["source governance", "--task-dir"]),
            (["benchmark"], ["known-good and known-bad", "Exits 0"]),
            (["simulate-week"], ["simulated week", "Exits 0"]),
        ]
        for argv, snippets in cases:
            with self.subTest(argv=argv):
                self.assert_help_contains(argv, snippets)

    def test_readme_documents_exit_code_contract(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        normalized = " ".join(readme.split())
        for snippet in [
            "## Exit Code Contract",
            "`async-research --help` and subcommand help exit `0`",
            "Command-line usage errors from `argparse` exit `2`",
            "`review-surface` is an alias for `surface`",
            "`accepted revalidate` is an alias for `accepted revalidation`",
            "| `readiness` | `0` safe; `2` warnings only.",
            "| `cost budget-check` | `0` proposed spend is below the configured threshold.",
            "`check-duplicate` is advisory and reports duplicate risk in JSON",
            "| `accepted check-memory-use` | `0` artifact does not cite stale accepted memory",
            "| `starter-smoke` | `0` all starter checks passed.",
            "| `result-acceptance` | `0` gates passed.",
            "| `simulate-week` | `0` simulated week passed.",
        ]:
            self.assertIn(" ".join(snippet.split()), normalized)


if __name__ == "__main__":
    unittest.main()

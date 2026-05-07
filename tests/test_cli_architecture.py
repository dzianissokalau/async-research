"""Regression tests for the CLI parser registration structure."""

from __future__ import annotations

import argparse
import unittest
from unittest import mock

from async_research_workflow import cli


INTERNAL_ONLY_TOP_LEVEL_COMMANDS = [
    "validate-json-artifact",
    "validate-transition",
    "validate-mission-policy",
    "task-lock",
    "recover-status-json",
    "review-template",
    "framework-version-calibration",
    "escalate-review-tier",
    "decision-log",
    "version-metadata",
    "metrics-init",
]


def subparser_choices(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    raise AssertionError(f"no subparsers found for {parser.prog}")


class CliArchitectureTests(unittest.TestCase):
    def test_command_registrars_are_grouped_in_public_order(self) -> None:
        self.assertEqual(
            [
                "register_package_commands",
                "register_status_commands",
                "register_surface_commands",
                "register_schema_command",
                "register_queue_commands",
                "register_decision_commands",
                "register_escalation_commands",
                "register_source_commands",
                "register_cost_commands",
                "register_batch_commands",
                "register_metrics_commands",
                "register_accepted_commands",
                "register_anti_context_commands",
                "register_review_commands",
                "register_revision_commands",
                "register_result_command",
                "register_artifact_commands",
                "register_benchmark_commands",
            ],
            [register.__name__ for register in cli.COMMAND_REGISTRARS],
        )

    def test_build_parser_registers_expected_public_commands(self) -> None:
        choices = subparser_choices(cli.build_parser())

        self.assertEqual(
            [
                "version",
                "init",
                "starter-smoke",
                "acceptance-suite",
                "readiness",
                "health",
                "surface",
                "review-surface",
                "schema-check",
                "queue",
                "decision",
                "escalation",
                "source",
                "cost",
                "batch",
                "metrics",
                "accepted",
                "anti-context",
                "review",
                "revision",
                "result-acceptance",
                "exploration",
                "idea",
                "experiment",
                "benchmark",
                "simulate-week",
            ],
            list(choices),
        )
        self.assertIs(choices["surface"], choices["review-surface"])

    def test_internal_helpers_are_not_public_top_level_commands(self) -> None:
        choices = subparser_choices(cli.build_parser())

        for command_name in INTERNAL_ONLY_TOP_LEVEL_COMMANDS:
            with self.subTest(command_name=command_name):
                self.assertNotIn(command_name, choices)

    def test_acceptance_suite_debug_flags_route_to_public_wrapper(self) -> None:
        with mock.patch.object(cli, "module_main", return_value=cli.SUCCESS) as module_main:
            code = cli.main(["acceptance-suite", "--work-dir", "/tmp/arw-acceptance", "--keep-work-dir"])

        self.assertEqual(cli.SUCCESS, code)
        module_main.assert_called_once_with(
            "run_acceptance_suite",
            ["--work-dir", "/tmp/arw-acceptance", "--keep-work-dir"],
        )

    def test_health_budget_flags_route_to_public_wrapper(self) -> None:
        with mock.patch.object(cli, "module_main", return_value=cli.SUCCESS) as module_main:
            code = cli.main(
                [
                    "health",
                    "research_ops",
                    "--dry-run",
                    "--monthly-budget-usd",
                    "100",
                    "--weekly-budget-usd",
                    "25",
                ]
            )

        self.assertEqual(cli.SUCCESS, code)
        module_main.assert_called_once_with(
            "health_check",
            [
                "research_ops",
                "--dry-run",
                "--monthly-budget-usd",
                "100.0",
                "--weekly-budget-usd",
                "25.0",
            ],
        )

    def test_build_parser_registers_nested_aliases(self) -> None:
        choices = subparser_choices(cli.build_parser())
        source_choices = subparser_choices(choices["source"])
        queue_choices = subparser_choices(choices["queue"])
        decision_choices = subparser_choices(choices["decision"])
        escalation_choices = subparser_choices(choices["escalation"])
        cost_choices = subparser_choices(choices["cost"])
        batch_choices = subparser_choices(choices["batch"])
        metrics_choices = subparser_choices(choices["metrics"])
        accepted_choices = subparser_choices(choices["accepted"])
        anti_context_choices = subparser_choices(choices["anti-context"])
        review_choices = subparser_choices(choices["review"])
        revision_choices = subparser_choices(choices["revision"])
        idea_choices = subparser_choices(choices["idea"])
        idea_catalog_choices = subparser_choices(idea_choices["catalog"])

        self.assertEqual(["discovery-gate"], list(queue_choices))
        self.assertEqual(["append", "check", "resolve-task", "summarize"], list(decision_choices))
        self.assertEqual(["list", "scan-needs-human", "evaluate"], list(escalation_choices))
        self.assertEqual(["init", "upsert", "validate", "freshness", "check-experiment", "check-claim", "explain"], list(source_choices))
        self.assertEqual(["summary", "ingest-usage", "budget-check"], list(cost_choices))
        self.assertEqual(["init", "validate-manifest", "submit", "complete", "ingest", "mark-reviewed", "trust-status"], list(batch_choices))
        self.assertEqual(["append", "summarize"], list(metrics_choices))
        self.assertNotIn("init", metrics_choices)
        self.assertEqual(["update", "check-duplicate", "check-memory-use", "revalidation", "revalidate"], list(accepted_choices))
        self.assertEqual(["build"], list(anti_context_choices))
        self.assertEqual(["prepare-context", "install-context", "aggregate"], list(review_choices))
        self.assertEqual(["defaults", "request", "inspect", "scan-limits"], list(revision_choices))
        self.assertEqual(["score", "validate", "capture", "promote", "park", "reject", "catalog"], list(idea_choices))
        self.assertEqual(["init", "validate", "list", "show", "maintain"], list(idea_catalog_choices))
        self.assertIs(accepted_choices["revalidation"], accepted_choices["revalidate"])


if __name__ == "__main__":
    unittest.main()

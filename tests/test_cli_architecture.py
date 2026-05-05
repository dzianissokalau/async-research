"""Regression tests for the CLI parser registration structure."""

from __future__ import annotations

import argparse
import unittest

from async_research_workflow import cli


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
                "register_metrics_commands",
                "register_accepted_commands",
                "register_review_commands",
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
                "metrics",
                "accepted",
                "review",
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

    def test_build_parser_registers_nested_aliases(self) -> None:
        choices = subparser_choices(cli.build_parser())
        source_choices = subparser_choices(choices["source"])
        queue_choices = subparser_choices(choices["queue"])
        decision_choices = subparser_choices(choices["decision"])
        escalation_choices = subparser_choices(choices["escalation"])
        cost_choices = subparser_choices(choices["cost"])
        metrics_choices = subparser_choices(choices["metrics"])
        accepted_choices = subparser_choices(choices["accepted"])

        self.assertEqual(["discovery-gate"], list(queue_choices))
        self.assertEqual(["append", "check", "resolve-task", "summarize"], list(decision_choices))
        self.assertEqual(["list", "scan-needs-human", "evaluate"], list(escalation_choices))
        self.assertEqual(["validate", "freshness", "check-experiment", "check-claim"], list(source_choices))
        self.assertEqual(["summary", "ingest-usage", "budget-check"], list(cost_choices))
        self.assertEqual(["append", "summarize"], list(metrics_choices))
        self.assertEqual(["update", "check-duplicate", "check-memory-use", "revalidation", "revalidate"], list(accepted_choices))
        self.assertIs(accepted_choices["revalidation"], accepted_choices["revalidate"])


if __name__ == "__main__":
    unittest.main()

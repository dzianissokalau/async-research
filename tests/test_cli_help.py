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
                "workflow",
                "queue",
                "decision",
                "escalation",
                "data",
                "library",
                "result-acceptance",
                "batch",
                "anti-context",
                "revision",
                "analysis",
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
            (["acceptance-suite"], ["isolated temporary fixtures", "promotion-write end-to-end acceptance", "--work-dir", "--keep-work-dir", "Exits 0"]),
            (["readiness"], ["Readiness exit codes:", "human action required"]),
            (["health"], ["accepted-memory health", "--dry-run", "--monthly-budget-usd", "--weekly-budget-usd"]),
            (["surface"], ["daily_status.md", "update", "validate"]),
            (["review-surface"], ["daily_status.md", "update", "validate"]),
            (["surface", "update"], ["daily_status.md", "human_review_queue.md"]),
            (["review-surface", "update"], ["daily_status.md", "human_review_queue.md"]),
            (["surface", "validate"], ["rendered human review surfaces"]),
            (["review-surface", "validate"], ["rendered human review surfaces"]),
            (["schema-check"], ["schema versions", "versioned JSON artifacts"]),
            (["workflow"], ["schema", "readiness", "review aggregation", "accepted-memory", "surface", "health", "check", "advance"]),
            (["workflow", "check"], ["read-only workspace workflow checks", "schema-check", "readiness --dry-run", "surface validate", "health --dry-run"]),
            (["workflow", "advance"], ["post-worker task workflow", "--ops-dir", "--dry-run", "run only read-only checks"]),
            (["queue"], ["queue capacity", "read-only", "discovery-gate"]),
            (["queue", "discovery-gate"], ["action=discovery_allowed", "action=discovery_skipped", "--max-active", "without mutating research_ops"]),
            (["decision"], ["decisions.md", "append", "check", "resolve-task", "summarize"]),
            (["decision", "append"], ["decision row", "--item-id", "--dry-run"]),
            (["decision", "check"], ["matching decision row", "--item-id", "--decision"]),
            (["decision", "resolve-task"], ["needs_human task", "--status", "--dry-run"]),
            (["decision", "summarize"], ["decision rows by decision", "--month", "--output"]),
            (["escalation"], ["escalation policy", "list", "scan-needs-human", "evaluate"]),
            (["escalation", "list"], ["trigger table"]),
            (["escalation", "scan-needs-human"], ["structured needs_human gates", "Exits 0", "Exits 0 when structured gates are valid"]),
            (["escalation", "evaluate"], ["--apply", "source freshness", "Exits 0 when no escalation is needed"]),
            (["source"], ["data_source_audit.md", "init", "upsert", "validate", "freshness", "check-experiment", "check-claim", "explain"]),
            (["source", "init"], ["canonical source audit register", "--force"]),
            (["source", "upsert"], ["source audit row", "--source-id", "--approval-status", "--source-tier", "New rows require"]),
            (["source", "validate"], ["source audit rows"]),
            (["source", "freshness"], ["freshness windows"]),
            (["source", "check-experiment"], ["source IDs allowed for experiment planning", "--claim-impact"]),
            (["source", "check-claim"], ["selected use case and impact", "--use-case", "--allow-tier4-explicit"]),
            (["source", "explain"], ["one DS-* id", "--use-case", "--allow-tier4-explicit"]),
            (["data"], ["data foundation readiness", "validate", "dashboard"]),
            (["data", "validate"], ["research_ops/data", "profiles", "Read-only", "--now", "Exits 0"]),
            (["data", "dashboard"], ["Read-only dashboard", "approved", "candidate", "blocked", "join-caveat", "--now", "--use-case"]),
            (["library"], ["knowledge library", "init", "validate", "dashboard", "research_ops/library"]),
            (["library", "init"], ["research_ops/library", "--dry-run", "--write", "Without --write"]),
            (["library", "validate"], ["research_ops/library", "Read-only", "--now", "--stale-days", "Exits 0"]),
            (["library", "dashboard"], ["Read-only dashboard", "topic coverage", "stale reviews", "proposed library update tasks", "--now", "--stale-days", "Exits 0"]),
            (["cost"], ["cost_ledger.csv", "summary", "ingest-usage", "budget-check"]),
            (["cost", "summary"], ["aggregate spend", "--ledger"]),
            (["cost", "ingest-usage"], ["usage artifact", "--usage-file", "--dry-run"]),
            (["cost", "budget-check"], ["proposed cost", "--proposed-api-usd", "--threshold"]),
            (["batch"], ["batch_manifest.json lifecycle", "validate-manifest", "trust-status"]),
            (["batch", "init"], ["draft batch manifest", "--batch-id", "--input-file", "--dry-run"]),
            (["batch", "validate-manifest"], ["lifecycle invariants"]),
            (["batch", "submit"], ["log estimated cost", "--provider-batch-id", "--dry-run"]),
            (["batch", "complete"], ["output_trust=untrusted", "--output-file"]),
            (["batch", "ingest"], ["ingested_pending_review", "--ingest-task-id"]),
            (["batch", "mark-reviewed"], ["reviewed and trusted", "--review-task-id"]),
            (["batch", "trust-status"], ["Exits 0 when outputs are trusted", "--allow-untrusted"]),
            (["metrics"], ["metrics_history.jsonl", "append", "summarize", "operational"]),
            (["metrics", "append"], ["--label", "--update-weekly-digest"]),
            (["metrics", "summarize"], ["metrics_history.jsonl trends", "--output"]),
            (["metrics", "operational"], ["time-in-state", "human-decision latency", "--now"]),
            (["accepted"], ["accepted_outputs_index.md", "check-duplicate", "check-memory-use", "revalidation", "revalidate"]),
            (["accepted", "update"], ["Upsert accepted task rows"]),
            (["accepted", "check-duplicate"], ["duplicate risk", "--title"]),
            (["accepted", "revalidation"], ["--write-schedule", "revalidation_schedule.md"]),
            (["accepted", "revalidate"], ["--write-schedule", "revalidation_schedule.md"]),
            (["accepted", "check-memory-use"], ["stale accepted memory", "--allow-stale"]),
            (["anti-context"], ["anti_context.md", "rejected task failure modes", "build"]),
            (["anti-context", "build"], ["proposed task", "--task-dir", "--output"]),
            (["review"], ["Draft or submit role-specific reviews", "draft", "submit", "prepare-context", "install-context", "aggregate"]),
            (["review", "draft"], ["needs_human review scaffold", "--role", "--write", "--force"]),
            (["review", "submit"], ["explicit review flags", "--decision", "--claim-strength", "--confidence", "--dry-run"]),
            (["review", "prepare-context"], ["isolated reviewer", "--role", "--bundle-dir"]),
            (["review", "install-context"], ["completed isolated review output", "--force"]),
            (["review", "aggregate"], ["reviews/*.md", "--dry-run", "--record-review-start"]),
            (["revision"], ["bounded revision counters", "request", "scan-limits"]),
            (["revision", "defaults"], ["default max revisions", "--tier"]),
            (["revision", "request"], ["bounded task revision", "--dry-run", "--schema"]),
            (["revision", "inspect"], ["revision fields", "--schema"]),
            (["revision", "scan-limits"], ["revision-limit hits", "--markdown"]),
            (["result-acceptance"], ["result_acceptance.json", "--update-ledgers"]),
            (["analysis"], ["Preflight", "dashboard", "run-adapter", "preflight", "validate-run", "validate-results"]),
            (["analysis", "dashboard"], ["Read-only dashboard", "active run_analysis", "accepted empirical evidence", "--max-items", "--now"]),
            (["analysis", "run-adapter"], ["Optional", "local_script", "--execute", "--timeout-seconds", "validate-run"]),
            (["analysis", "preflight"], ["Read-only", "accepted experiment plan", "--ops-dir", "--now", "stale accepted memory"]),
            (["analysis", "validate-run"], ["completed run_analysis", "metrics", "robustness", "--ops-dir", "--now"]),
            (["analysis", "validate-results"], ["result summary", "claim_gates.json", "accepted experiment plan", "--ops-dir", "--now"]),
            (["exploration"], ["exploration-cycle tasks", "validate"]),
            (["exploration", "validate"], ["worker output", "--task-dir"]),
            (["idea"], ["idea-evaluation JSON artifacts", "score", "validate", "capture", "promote", "park", "reject", "catalog"]),
            (["idea", "capture"], ["discovery_inbox.md", "--from-inbox", "--title", "LOCK"]),
            (
                ["idea", "promote"],
                [
                    "promotion proposal",
                    "Dry-run is proposal-only",
                    "promotion_preflight_hash",
                    "--task-type",
                    "--allow-duplicate",
                    "--preflight-hash",
                    "--human-override",
                    "promoted_task_id",
                    "inbox.md",
                ],
            ),
            (["idea", "park"], ["catalog idea", "--reason", "--revisit", "--write"]),
            (["idea", "reject"], ["catalog idea", "--reason", "--write"]),
            (["idea", "catalog"], ["durable idea catalog", "init", "validate", "list", "dashboard", "show", "maintain", "discovery_inbox.md", "queue.md"]),
            (["idea", "catalog", "init"], ["--dry-run", "--write", "Without --write", "exact files"]),
            (["idea", "catalog", "validate"], ["canonical idea JSON", "generated projections", "lifecycle gates", "without mutating files"]),
            (["idea", "catalog", "list"], ["IDEA-*.json", "--status", "derived display labels"]),
            (["idea", "catalog", "dashboard"], ["portfolio dashboard", "candidate", "parked", "promoted", "rejected", "--max-blockers"]),
            (["idea", "catalog", "show"], ["canonical idea JSON", "derived catalog summary", "IDEA-0001"]),
            (["idea", "catalog", "maintain"], ["discovery_inbox.md", "LOCK", "never edits queue.md"]),
            (["idea", "score"], ["--budget-mode", "mission policy"]),
            (["idea", "validate"], ["idea-evaluation JSON"]),
            (["experiment"], ["source readiness", "validate"]),
            (["experiment", "validate"], ["source governance", "--task-dir"]),
            (["benchmark"], ["known-good and known-bad", "Exits 0"]),
            (["simulate-week"], ["simulated week", "--work-dir", "--keep-work-dir", "Exits 0"]),
        ]
        for argv, snippets in cases:
            with self.subTest(argv=argv):
                self.assert_help_contains(argv, snippets)

    def test_revision_defaults_help_hides_internal_tier_zero(self) -> None:
        normalized = " ".join(help_text(["revision", "defaults"]).split())
        self.assertIn("{1,2,3}", normalized)
        self.assertNotIn("{0,1,2,3}", normalized)

    def test_readme_documents_exit_code_contract(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        normalized = " ".join(readme.split())
        for snippet in [
            "## Exit Code Contract",
            "`async-research --help` and subcommand help exit `0`",
            "Command-line usage errors from `argparse` exit `2`",
            "`review-surface` is an alias for `surface`",
            "`accepted revalidate` is an alias for `accepted revalidation`",
            "| `idea catalog init` | `0` missing catalog files reported or created.",
            "| `idea catalog validate` | `0` catalog validation passed.",
            "| `idea catalog dashboard` | `0` dashboard rendered and catalog validation passed.",
            "| `idea catalog list` and `idea catalog show` | `0` catalog record or list printed.",
            "| `idea capture`, `idea catalog maintain`, `idea park`, and `idea reject` | `0` dry-run proposal printed or write succeeded.",
            "| `idea promote` | `0` dry-run proposal printed, promotion task write succeeded, or matching task write was already complete.",
            "changed preflight hash",
            "| `readiness` | `0` safe; `2` warnings only.",
            "| `workflow check` | `0` workspace checks passed; readiness warning `2` is reported as a warning but does not fail the orchestration.",
            "| `workflow advance` | `0` dry-run checks passed or the canonical post-worker sequence completed; readiness warning `2` is reported as a warning but does not fail the orchestration.",
            "JSON sets `partial_mutation: true`",
            "| `queue discovery-gate` | `0` active queue capacity is available.",
            "| `decision append` | `0` decision row appended or dry-run row printed.",
            "| `escalation evaluate` | `0` no escalation is needed.",
            "| `source upsert` | `0` source row written.",
            "| `data validate` | `0` data foundation contracts are ready.",
            "| `data dashboard` | `0` dashboard rendered and data foundation plus catalog read-model state are clean.",
            "| `library init` | `0` missing library files reported or created.",
            "| `library validate` | `0` knowledge library contracts are clean.",
            "| `library dashboard` | `0` dashboard rendered and knowledge library state is clean.",
            "| `batch trust-status` | `0` outputs are trusted.",
            "| `cost budget-check` | `0` proposed spend is below the configured threshold.",
            "| `metrics summarize` | `0` metrics summary printed or written.",
            "| `metrics operational` | `0` operational read model printed.",
            "`check-duplicate` is advisory and reports duplicate risk in JSON",
            "| `anti-context build` | `0` anti-context generated.",
            "| `revision request` | `0` revision route applied or dry-run transition printed.",
            "| `accepted check-memory-use` | `0` artifact does not cite stale accepted memory",
            "| `starter-smoke` | `0` all starter checks passed.",
            "| `result-acceptance` | `0` gates passed.",
            "| `analysis dashboard` | `0` dashboard rendered and analysis surface state is clean.",
            "| `analysis run-adapter` | `0` adapter plan or execution succeeded.",
            "| `analysis preflight`, `analysis validate-run`, and `analysis validate-results` | `0` clean preflight or validation.",
            "| `simulate-week` | `0` simulated week passed.",
        ]:
            self.assertIn(" ".join(snippet.split()), normalized)

    def test_readme_documents_internal_helper_boundary(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        normalized = " ".join(readme.split())
        for snippet in [
            "## Internal Helper Boundary",
            "`async-research` is the public user interface",
            "Direct `python -m async_research_workflow.scripts.<module>` calls are advanced/internal helper usage",
            "`validate_json_artifact`",
            "`validate_transition`",
            "`validate_mission_policy`",
            "`task_lock`",
            "`recover_status_json`",
            "`review_template`",
            "`framework_version_calibration`",
            "`escalate_review_tier`",
            "`metrics_history init`",
            "`decision_log`",
            "`version_metadata`",
        ]:
            self.assertIn(" ".join(snippet.split()), normalized)

    def test_library_help_documents_mvp_commands_and_exit_codes(self) -> None:
        self.assert_help_contains(
            ["library"],
            [
                "research_ops/library",
                "init",
                "validate",
            ],
        )
        self.assert_help_contains(
            ["library", "init"],
            [
                "research_ops/library starter files",
                "Without --write this command is a dry run",
                "Exits 0",
                "3 for conflicting flags",
                "4 for malformed workspace paths",
            ],
        )
        self.assert_help_contains(
            ["library", "validate"],
            [
                "Read-only validation for research_ops/library generated blocks",
                "Exits 0",
                "2 for warning-only findings",
                "3 for invalid request flags",
                "4 for malformed generated blocks",
            ],
        )


if __name__ == "__main__":
    unittest.main()

# Phase 7 Test Consolidation

Status: delivered
Roadmap: `roadmaps/delivered_framework_simplification_strategy.md`
Date: 2026-05-25

## Phase Contract

Phase 7 closes the first simplification wave by reducing tests only where prior
phases already installed replacement contracts or golden checks. It does not
change public CLI behavior, aliases, JSON envelopes, exit codes, workspace file
formats, task state values, the HTTP console, or fail-closed gates.

## Preserved Coverage

- Public command order and alias parser identity remain frozen by
  `tests.test_cli_architecture`.
- Public help, exit-code documentation, alias documentation, and command
  normalization coverage remain frozen by `tests.test_cli_help` and
  `tests.test_doc_references`.
- Starter workspace first-success behavior remains covered by
  `tests.test_cli_safety` and the required `starter-smoke` verification command.
- End-to-end package first-success behavior remains covered by
  `.venv/bin/async-research acceptance-suite`.
- Snapshot and console contracts remain covered by the Phase 3 snapshot golden
  and console suites; no snapshot tests were removed in this phase.

## Consolidated Tests

| Previous coverage | Replacement contract |
| --- | --- |
| `CliAliasTests.test_review_surface_alias_updates_and_validates_surface` initialized a workspace, then re-ran `review-surface update` and `review-surface validate` to prove the alias worked. | `CliArchitectureTests.test_build_parser_registers_expected_public_commands` proves `review-surface` is the same parser object as `surface`; `CliHelpTests.test_every_public_command_help_has_operator_context` covers the alias help; `CliAliasTests.test_supported_aliases_dispatch_to_canonical_modules` now proves both spellings dispatch to `human_review_surface` with identical argv. Workspace side effects stay covered by starter-smoke and surface tests. |
| `CliAliasTests.test_accepted_revalidate_alias_matches_revalidation_report` initialized a workspace, then ran both accepted-memory spellings and diffed timestamp-stripped JSON. | `CliArchitectureTests.test_build_parser_registers_nested_aliases` proves `accepted revalidate` is the same parser object as `accepted revalidation`; `CliHelpTests.test_every_public_command_help_has_operator_context` and the Phase 5 command-normalization design cover the public alias; `CliAliasTests.test_supported_aliases_dispatch_to_canonical_modules` now proves both spellings dispatch to `update_accepted_outputs_index revalidation-report` with identical argv. Accepted-memory behavior remains covered by workflow and accepted-memory regression tests. |

## Non-Goals

- Do not remove tests for source audit, freshness, claim verification, review
  aggregation, result acceptance, accepted-memory freshness, deliverable
  maturity, readiness, locking, workspace writes, or cost gates.
- Do not collapse command families or remove aliases.
- Do not change fixture schemas, starter workspace files, or `research_ops/`
  task state values.

## Verification

- `git diff --check`
- `.venv/bin/python -m unittest tests.test_cli_aliases tests.test_cli_architecture tests.test_cli_help tests.test_cli_safety`
- `.venv/bin/async-research starter-smoke /tmp/arw-simplification-smoke --force`
- `.venv/bin/python -m unittest discover -s tests`
- `.venv/bin/async-research acceptance-suite`

# Phase 2 Review - Iteration 1

Roadmap: `roadmaps/in_progress_framework_simplification_strategy.md`
Phase: Phase 2 - Init and starter smoke services
Reviewed at: 2026-05-25T09:14:22Z
Branch: `codex/framework-simplification-strategy-phase-2`
Verdict: delivered

## Findings

- None.

## Missing Tests Or Checks

- None blocking. Required verification passed after the final code changes:
  `.venv/bin/python -m unittest tests.test_packaged_resources tests.test_cli_safety`
  and `.venv/bin/async-research starter-smoke /tmp/arw-simplification-smoke --force`.
- Additional high-blast-radius verification also passed:
  `git diff --check`, `.venv/bin/python -m unittest discover -s tests`,
  and `.venv/bin/async-research acceptance-suite`.

## Finding Disposition

- No findings.

## Evidence

- `src/async_research_workflow/cli.py` now keeps `run_init` and
  `run_starter_smoke` as public CLI entry points while delegating to services.
- `src/async_research_workflow/workspace_install.py` owns template selection,
  staging, backup, rollback, metrics seeding, cleanup, and failure envelopes.
- `src/async_research_workflow/starter_smoke.py` owns work-dir safety checks,
  init wrapping, smoke check ordering, result aggregation, and JSON envelope
  assembly.
- `tests/test_cli_safety.py` keeps existing init/starter-smoke contract coverage
  and adds regression coverage for smoke check ordering and rollback failure
  backup reporting.

## Residual Risks

- Review ran in the same automation context because sub-agent delegation is not
  explicitly authorized. The verdict relies on direct acceptance evidence,
  focused regression coverage, real smoke execution, full unit discovery, and
  the acceptance suite.

## Verdict

delivered

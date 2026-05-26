# Documentation Drift Fix Requirements

Created: 2026-05-26

Source analysis:

- `DOCUMENTATION_DRIFT_REVIEW_SUMMARY.md`
- `/Users/dzianissokalau/Downloads/async-research-documentation-review.md`

## Goal

Fix the confirmed documentation and metadata drift from the documentation audit
without reopening stale or already-resolved findings from the external report.

The fix is intentionally small: normalize remaining user-facing references onto
the public `async-research` CLI, remove misleading legacy location wording, and
point package metadata at the current roadmap index.

## Scope

### Required Fixes

1. Replace stale public helper script names in
   `src/async_research_workflow/docs/autonomy_readiness_plan.md`.
   The readiness checklist should name public CLI commands, not old helper
   filenames.
2. Replace the remaining `simulate_scheduled_week.py` prose reference in
   `src/async_research_workflow/docs/operational_readiness_runbook.md`.
3. Replace repeated `implemented in docs/examples` wording in
   `src/async_research_workflow/docs/feedback_hardening_plan.md` with wording
   that reflects the current package layout.
4. Update the `Roadmap` project URL in `pyproject.toml` from a delivered
   historical roadmap to the current roadmap index.
5. Add a focused documentation-reference regression guard so user-facing docs do
   not reintroduce the stale public helper names:
   - `run_acceptance_suite.py`
   - `run_autonomy_benchmark.py`
   - `simulate_scheduled_week.py`
   - `autonomy_readiness_gate.py`

### Non-Goals

- Do not rewrite the package docs index. The current `Package Resources`
  section already reflects the package layout.
- Do not expand the root README command map. It already covers the broad public
  CLI surface.
- Do not remove every direct `python -m async_research_workflow.scripts...`
  invocation. Some helper calls are intentionally advanced/internal.
- Do not change framework behavior, command semantics, schemas, starter
  templates, or state-transition logic.
- Do not treat historical roadmap or review artifacts as current operator
  instructions unless they are in the active package docs surfaced to users.

## Acceptance Criteria

- No current user-facing docs instruct users to run the four stale public helper
  script filenames listed above.
- The operational readiness runbook describes `async-research simulate-week`
  as the rehearsal command.
- The feedback hardening implementation backlog no longer says features were
  implemented in `docs/examples`.
- `pyproject.toml` points the `Roadmap` project URL at `roadmaps/README.md`.
- The doc-reference regression test fails if one of the stale public helper
  filenames returns to current package docs, starter docs, root README, or
  roadmap docs outside explicitly historical contexts.

## Verification

Run:

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references tests.test_project_metadata tests.test_cli_help
```

Run full discovery only if the patch touches implementation code. This fix is
docs, metadata, and targeted test coverage only.

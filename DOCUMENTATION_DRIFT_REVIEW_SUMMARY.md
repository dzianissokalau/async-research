# Documentation Drift Review Summary

Created: 2026-05-26

Source report:
`/Users/dzianissokalau/Downloads/async-research-documentation-review.md`

## Summary

The attached documentation-to-implementation audit appears to be based on an
older public snapshot of the repository, not the current workspace. Most of its
largest claims are stale or already fixed.

I verified the current framework and documentation with:

- `.venv/bin/async-research --help`
- `pyproject.toml`
- `README.md`
- `src/async_research_workflow/docs/README.md`
- `src/async_research_workflow/docs/operational_readiness_runbook.md`
- current tests and CI configuration
- `.venv/bin/python -m unittest tests.test_doc_references tests.test_project_metadata tests.test_cli_help`

The 32 verification tests above pass.

## Claims That Are Not Real Anymore

| Report claim | Current reality |
| --- | --- |
| Version is `0.1.0a1`. | False. Current version is `0.3.0a1` in `pyproject.toml`, `src/async_research_workflow/__init__.py`, tests, fixtures, and README. |
| Tests are basically one import/version test. | False. There are 79 top-level test files under `tests/`, covering CLI, console, interaction modes, runtime, data foundations, knowledge library, idea catalog, deliverables, docs, packaging, and more. |
| CI only tests Python 3.11 and 3.12. | False. `.github/workflows/ci.yml` tests 3.11, 3.12, and 3.13. The package job also uses 3.13. |
| `docs/README.md` says scripts, schemas, and templates all live under `examples/`. | False now. `src/async_research_workflow/docs/README.md` has a `Package Resources` section with separate links for examples, schemas, templates, benchmark cases, domain packs, and starter templates. |
| Docs have broken `docs/examples/...` links. | Not supported by the current repo checks. `tests.test_doc_references` passes and explicitly guards against stale `examples/scripts/` references. |
| The operational runbook mainly tells users to run `async_research_workflow/examples/scripts/...`. | False now. The triage and readiness blocks use public `async-research ...` commands. |
| README under-documents the CLI. | Mostly false now. `README.md` has a broad command map covering mode, workflow, queue, prompts, schedules, decision, source, data, library, runtime, eval, evidence memory, model routing, scaling, brief, cost, batch, metrics, accepted, outcomes, deliverable, anti-context, reflection, review, revision, result acceptance, analysis, exploration, idea, experiment, benchmark, and simulate-week. |
| `CHANGELOG` and `CONTRIBUTING` are missing. | False. `CHANGELOG.md` and `CONTRIBUTING.md` both exist. `tests.test_project_metadata` enforces release hygiene files. |

## Real Drift To Fix

| Priority | Real issue | What to fix |
| ---: | --- | --- |
| P0 | `src/async_research_workflow/docs/autonomy_readiness_plan.md` still has readiness checklist items like `run_acceptance_suite.py`, `simulate_scheduled_week.py`, and `autonomy_readiness_gate.py research_ops`. | Replace with public commands: `async-research acceptance-suite`, `async-research benchmark`, `async-research simulate-week research_ops`, and `async-research readiness research_ops --dry-run`. |
| P0 | `src/async_research_workflow/docs/operational_readiness_runbook.md` still has prose saying ``simulate_scheduled_week.py` is a no-op rehearsal`. | Rename that prose to the public command: `async-research simulate-week`. |
| P1 | `src/async_research_workflow/docs/feedback_hardening_plan.md` repeatedly says items were "implemented in docs/examples." | Update wording to "implemented in package docs/scripts/templates and public CLI wrappers," or mark the section clearly as historical. |
| P1 | Some docs still use direct `python -m async_research_workflow.scripts...` helper calls. Many are legitimate advanced/internal helpers, but the boundary is uneven. | Audit remaining direct helper calls. Keep only those labeled `advanced/internal`; replace any public-wrapper equivalent with `async-research ...`. |
| P1 | `pyproject.toml` has `Project-URL: Roadmap` pointing to `roadmaps/delivered_public_alpha_hardening_roadmap.md`. | Point it to `roadmaps/README.md` or another current roadmap index rather than an old delivered roadmap. |
| P2 | The external audit process itself is stale. | Future review prompts should tell reviewers to audit the current branch/workspace, not an old GitHub tree snapshot. |

## What Not To Fix

- Do not rewrite `src/async_research_workflow/docs/README.md` based on the
  report's old `examples/` claim. The current package-resource section is
  already much closer to the implementation.
- Do not expand README solely for the command-coverage claim. The current
  command map is already broad.
- Do not add test coverage solely because the report saw one test file. The
  current test suite is much larger.
- Do not remove every direct `python -m async_research_workflow.scripts...`
  invocation blindly. Some are intentional advanced/internal helper paths.

## Recommended Fix Order

1. Replace stale user-facing script filenames in
   `autonomy_readiness_plan.md`.
2. Replace the lingering `simulate_scheduled_week.py` prose in
   `operational_readiness_runbook.md`.
3. Update the "implemented in docs/examples" wording in
   `feedback_hardening_plan.md`.
4. Update the `Roadmap` project URL in `pyproject.toml`.
5. Add or extend documentation-reference guards so future stale public-helper
   names are caught unless clearly marked as historical or advanced/internal.

## Bottom Line

The report's major drift claims are mostly already fixed. The remaining real
work is smaller: clean up a few stale script-name mentions, clarify
advanced/internal helper usage, and update the package metadata roadmap URL. No
major framework implementation drift was confirmed from this audit.

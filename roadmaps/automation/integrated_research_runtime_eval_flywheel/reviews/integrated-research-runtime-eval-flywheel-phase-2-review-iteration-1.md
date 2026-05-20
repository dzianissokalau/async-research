# Integrated Research Runtime Eval Flywheel Phase 2 Review

Phase: 2 - Clarifier and research brief rewrite
Iteration: 1
Reviewed at: 2026-05-20T13:57:23+0100
Verdict: delivered

## Scope Reviewed

- `research_brief.json` schema and contract documentation.
- Public `async-research brief draft`, `validate`, and `apply --dry-run`
  commands.
- Planner prompt guidance for broad or ambiguous research requests.
- `workflow create-task` and `idea promote` integration with validated ready
  briefs.
- Offline fixtures for clear, ambiguous, missing-audience, public-claim, and
  private-credential brief paths.

## Findings

No blocking findings remain.

The review found one fail-closed edge before final verdict:
`private_data_policy=blocked` or `status=blocked` could be validated as ready
when no other blocker was present. The delivery pass fixed this by treating any
non-`ready` status and blocked private-data policy as planning blockers, then
added a regression test for blocked brief validation.

## Verification Reviewed

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 16 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 756 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks
- `.venv/bin/python -m build`: passed, sdist and wheel built

## Residual Risks

- Review ran in the orchestration context after a full diff reread; no separate
  reviewer sub-agent was used.
- Phase 2 intentionally does not implement chat UI, runtime adapters, live
  fetching, automatic evidence acceptance, or a mandatory brief gate for tiny
  maintenance tasks when no brief exists.

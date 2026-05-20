# Integrated Research Runtime Eval Flywheel Phase 9 Review - Iteration 1

Date: 2026-05-20
Branch: `codex/integrated-research-runtime-eval-flywheel-phase-9`
Verdict: delivered

## Scope Reviewed

- Bounded `parallel_research` runtime mode and task-contract permissions.
- Planner-controlled branch plan validation, branch budgets, branch source
  path bounds, direct-acceptance blocking, and optional task lock checks.
- Runtime trace and evidence branch metadata plus deterministic merge packet
  emission under `research_ops/runtime/parallel_merges/`.
- Runtime validation and eval metrics for parallel branch counts and merge
  packet presence.
- Offline tests and docs for allowed parallel shapes, fail-closed behavior,
  merge/review constraints, and non-parallel eval cases.

## Findings

No blocking or needs-fix findings.

## Verification Reviewed

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 16 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 783 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks
- `.venv/bin/python -m build`: passed, sdist and wheel built

## Residual Risks

- Parallel execution is still deterministic/local or mocked in default tests;
  live external provider fan-out remains future adapter work.
- Merge packets are review context only and rely on downstream claim
  verification, review, result acceptance, deliverable maturity, and human
  gates to accept work.
- Review ran in the orchestration context after rereading scope, implementation
  diff, docs, tests, and verification output; no separate reviewer sub-agent was
  used.

# Integrated Research Runtime And Eval Flywheel Delivery Log

Append-only delivery notes for
`roadmaps/in_progress_integrated_research_runtime_eval_flywheel_roadmap.md`.

## Phase 0 - 2026-05-20

Status: delivered
Branch: `codex/integrated-research-runtime-eval-flywheel-phase-0`

### Scope

- Define the integrated runtime boundary without implementing adapters.
- Lock adapter classes, evidence object fields, trace fields, human gates,
  dependency posture, and quality metrics.
- Move the roadmap into the active lifecycle path and update the roadmap index.

### Changes

- Added `research_runtime_contract.md` with the runtime boundary, default
  fail-closed permission posture, adapter taxonomy, evidence object contract,
  trace contract, human gates, and standard-library-first dependency posture.
- Added `evaluation_flywheel.md` with success metrics, eval inputs, release
  policy, and benchmark honesty rules.
- Linked both docs from the package docs index and added doc-reference coverage
  for the locked Phase 0 terms.
- Advanced the roadmap/index to Phase 1 after marking Phase 0 delivered.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 16 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 745 tests
- `.venv/bin/python -m build`: passed, sdist and wheel built

### Review

- Review file: `roadmaps/automation/integrated_research_runtime_eval_flywheel/reviews/integrated-research-runtime-eval-flywheel-phase-0-review-iteration-1.md`
- Verdict: delivered

### Residual Risks

- Review is running in the orchestration context after rereading the Phase 0
  scope and staged diff; no separate reviewer sub-agent is used.

### Next Action

- Phase 0 is delivered. The next automation run should start Phase 1 on
  `codex/integrated-research-runtime-eval-flywheel-phase-1`.

## Phase 1 - 2026-05-20

Status: delivered
Branch: `codex/integrated-research-runtime-eval-flywheel-phase-1`

### Scope

- Add stable evidence object and runtime trace schemas.
- Add deterministic validators for fields, task links, `research_ops/` path
  boundaries, snapshot hashes, freshness, costs, and permissions.
- Add runtime ledger locations, CLI validate/summary/inspect commands,
  dashboard snapshot fields, starter runtime directories, and offline fixtures.

### Changes

- Added `runtime_evidence_object.schema.json` and `runtime_trace.schema.json`.
- Added `runtime_artifacts.py` with read-only validation, summary, and
  evidence inspection logic for `research_ops/runtime/`.
- Added public `async-research runtime validate`, `summary`, and
  `inspect-evidence` commands.
- Added runtime snapshot fields to the console/dashboard read model and static
  dashboard metrics.
- Added starter `runtime/` directories and runtime artifact documentation.
- Added regression coverage for valid runtime artifacts, missing required
  fields, stale/unknown-license warnings, bad paths, hash mismatches, and
  inspect fail-closed behavior.
- Advanced the roadmap/index to Phase 2 after marking Phase 1 delivered.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 16 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 750 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks
- `.venv/bin/python -m build`: passed, sdist and wheel built

### Review

- Review file: `roadmaps/automation/integrated_research_runtime_eval_flywheel/reviews/integrated-research-runtime-eval-flywheel-phase-1-review-iteration-1.md`
- Verdict: delivered

### Residual Risks

- Review ran in the orchestration context after rereading the Phase 1 scope and
  delivered diff; no separate reviewer sub-agent was used.
- Runtime adapters, live fetching, automatic evidence acceptance, and claim
  verification remain future-phase work.

### Next Action

- Phase 1 is delivered. The next automation run should start Phase 2 on
  `codex/integrated-research-runtime-eval-flywheel-phase-2`.

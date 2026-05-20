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

## Phase 2 - 2026-05-20

Status: delivered
Branch: `codex/integrated-research-runtime-eval-flywheel-phase-2`

### Scope

- Add a pre-planning research brief contract for broad or ambiguous requests.
- Add public draft, validate, and dry-run apply CLI support.
- Add planner prompt guidance and task/idea promotion integration where
  available.
- Add offline fixtures for clear, ambiguous, missing-audience, public-claim,
  and private-credential brief cases.

### Changes

- Added `research_brief.schema.json` and `research_brief_contract.md`.
- Added `research_brief.py` with deterministic brief drafting, validation,
  path-bound dry-run apply plans, readiness blockers, and human-gate detection.
- Added public `async-research brief draft`, `validate`, and `apply` commands.
- Updated planner prompt guidance to require a ready brief before broad
  research planning while leaving tiny maintenance tasks unblocked when no
  brief exists.
- Updated `workflow create-task` and `idea promote` to consume ready briefs,
  narrow permissions and budgets from the brief, include brief summaries in task
  proposals, and block on non-ready default briefs.
- Added regression fixtures and tests, including a review-discovered
  fail-closed regression for blocked brief status/private-data policy.
- Advanced the roadmap/index to Phase 3 after marking Phase 2 delivered.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 16 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 756 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks
- `.venv/bin/python -m build`: passed, sdist and wheel built

### Review

- Review file: `roadmaps/automation/integrated_research_runtime_eval_flywheel/reviews/integrated-research-runtime-eval-flywheel-phase-2-review-iteration-1.md`
- Verdict: delivered

### Residual Risks

- Review ran in the orchestration context after rereading the Phase 2 scope and
  delivered diff; no separate reviewer sub-agent was used.
- Runtime adapters, live fetching, automatic evidence acceptance, claim
  verification, and a chat UI remain future-phase or non-goal work.

### Next Action

- Phase 2 is delivered. The next automation run should start Phase 3 on
  `codex/integrated-research-runtime-eval-flywheel-phase-3`.

## Phase 3 - 2026-05-20

Status: delivered
Branch: `codex/integrated-research-runtime-eval-flywheel-phase-3`

### Scope

- Add a minimal unified runtime adapter interface.
- Implement deterministic local adapters first and mocked-only external
  adapters behind explicit task-contract permissions.
- Add runtime dry-run and execute CLI wrappers.
- Emit trace and evidence artifacts without transitioning task state.
- Add one offline vertical-slice fixture with a validated brief, local file
  source, mocked API source, worker output, and review packet.

### Changes

- Added `runtime_adapters.py` with `capabilities`, `dry_run`, `execute`,
  `to_trace`, and `to_evidence_objects` adapter flow.
- Added local `file_fetch`, `file_search`, and deterministic `code_execute`
  operations.
- Added mocked-only `web_search`, `web_open`, `mcp_search`, `mcp_fetch`, and
  `api_query` adapter classes that fail closed without task-contract permission
  and `mock_response`.
- Added public `async-research runtime dry-run` and `runtime execute` commands.
- Added `runtime_adapters.md` and linked adapter guidance from the docs index
  and runtime artifact docs.
- Added offline runtime vertical-slice fixtures and regression tests for
  dry-run read-only behavior, evidence/trace/dashboard visibility,
  fail-closed network and live-adapter behavior, malformed cost handling, and
  no task-state transition.
- Advanced the roadmap/index to Phase 4 after marking Phase 3 delivered.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 16 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 760 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks
- `.venv/bin/python -m build`: passed, sdist and wheel built

### Review

- Review file: `roadmaps/automation/integrated_research_runtime_eval_flywheel/reviews/integrated-research-runtime-eval-flywheel-phase-3-review-iteration-1.md`
- Verdict: delivered

### Residual Risks

- Review ran in the orchestration context after rereading the Phase 3 scope and
  delivered diff; no separate reviewer sub-agent was used.
- Live external fetching, automatic evidence acceptance, and claim verification
  remain future-phase work.

### Next Action

- Phase 3 is delivered. The next automation run should start Phase 4 on
  `codex/integrated-research-runtime-eval-flywheel-phase-4`.

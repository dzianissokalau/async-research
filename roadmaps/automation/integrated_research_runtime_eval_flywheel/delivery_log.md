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

## Phase 4 - 2026-05-20

Status: delivered
Branch: `codex/integrated-research-runtime-eval-flywheel-phase-4`

### Scope

- Add explicit claim objects and deterministic citation/evidence verification.
- Map claims to runtime evidence objects, source spans, quote/paraphrase status,
  freshness, and computation artifacts.
- Integrate claim gates with result acceptance, deliverable maturity, dashboard
  QA, and ledgers.
- Cover supported, missing, stale, contradicted, and numeric-no-computation
  cases with offline fixtures.

### Changes

- Added `claim_verification.py` and `claim_verification.schema.json`.
- Result acceptance now records claim-verification reports, blocks unsupported
  material claims, caps claim strength, writes claim ledgers, and routes
  contradictions to skeptic review.
- Deliverable maturity now requires resolved citation verification for
  working-paper and submission-ready outputs.
- Console snapshots surface claim-verification status, claim counts, caps, and
  unresolved citation blockers.
- Added claim/citation verification docs and linked them from runtime docs.
- Added regression tests and updated acceptance-suite/deliverable fixtures for
  the new publication-readiness gate.
- Advanced the roadmap/index to Phase 5 after marking Phase 4 delivered.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 16 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 766 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks
- `.venv/bin/python -m build`: passed, sdist and wheel built

### Review

- Review file: `roadmaps/automation/integrated_research_runtime_eval_flywheel/reviews/integrated-research-runtime-eval-flywheel-phase-4-review-iteration-1.md`
- Verdict: delivered

### Residual Risks

- Review ran in the orchestration context after rereading the Phase 4 scope and
  delivered diff; no separate reviewer sub-agent was used.
- The verifier checks local evidence linkage, quote presence, freshness, and
  computation artifacts; it does not perform live truth verification or
  bibliography-style enforcement.

### Next Action

- Phase 4 is delivered. The next automation run should start Phase 5 on
  `codex/integrated-research-runtime-eval-flywheel-phase-5`.

## Phase 5 - 2026-05-20

Status: delivered
Branch: `codex/integrated-research-runtime-eval-flywheel-phase-5`

### Scope

- Add trace-driven eval dataset schema, build/run/compare commands, automated
  graders, dashboard quality metrics, release policy, and fixture traces.

### Changes

- Added `runtime_evals.py` with `eval build-from-traces`, `eval run`, and
  `eval compare` support.
- Added runtime eval suite/run schemas, release-policy fields, deterministic
  grader outputs, metric deltas, and residual-risk reporting.
- Added console snapshot `evals` metrics for suite count, run count, latest run
  status, quality metrics, and release policy.
- Added starter `research_ops/evals/` locations and runtime eval documentation.
- Added offline fixture tests for suite building, grader execution, comparison
  regression blocking, dashboard visibility, and output path safety.
- Advanced the roadmap/index to Phase 6 after marking Phase 5 delivered.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 16 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 770 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks
- `.venv/bin/python -m build`: passed, sdist and wheel built

### Review

- Review file: `roadmaps/automation/integrated_research_runtime_eval_flywheel/reviews/integrated-research-runtime-eval-flywheel-phase-5-review-iteration-1.md`
- Verdict: delivered

### Residual Risks

- Review ran in the orchestration context after rereading the Phase 5 scope and
  delivered diff; no separate reviewer sub-agent was used.
- Expert preference and subjective task-success rubrics remain explicit
  placeholders until human-calibrated eval data is recorded.
- The eval flywheel is deterministic and offline; it does not yet benchmark live
  model quality or optimize prompts automatically.

### Next Action

- Phase 5 is delivered. The next automation run should start Phase 6 on
  `codex/integrated-research-runtime-eval-flywheel-phase-6`.

## Phase 6 - 2026-05-20

Status: delivered
Branch: `codex/integrated-research-runtime-eval-flywheel-phase-6`

### Scope

- Modernize prompt and model routing policy.
- Move hard routing and adoption rules into validators/contracts rather than
  prompt prose alone.
- Add provider-neutral role routing, cost caps, fallback policy, eval adoption
  gates, docs, and tests.

### Changes

- Added `model_routing.py` with public `async-research model-routing init`,
  `validate`, `select`, and `eval-check` commands.
- Added `model_routing_policy.schema.json` and deterministic semantic
  validation for required roles, provider-neutral routing, hard-rule ownership,
  role budgets, fallbacks, stop conditions, and adoption gates.
- Added an eval adoption gate that compares candidate eval runs against retained
  baselines and requires the candidate run to record the candidate policy id.
- Updated generated prompt-library prompts to reference
  `research_ops/prompts/model_routing_policy.json` and warn when prompt text
  lacks the routing policy reference.
- Added model routing docs, runtime eval adoption guidance, scheduler/prompt
  routing guidance, cost-control references, package-resource coverage, CLI
  architecture coverage, and focused offline tests.
- Advanced the roadmap/index to Phase 7 after marking Phase 6 delivered.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 16 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 775 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks
- `.venv/bin/python -m build`: passed, sdist and wheel built

### Review

- Review file: `roadmaps/automation/integrated_research_runtime_eval_flywheel/reviews/integrated-research-runtime-eval-flywheel-phase-6-review-iteration-1.md`
- Verdict: delivered

### Residual Risks

- The policy validates capability tiers and adoption gates; it does not execute
  live model calls or prove provider-specific quality without separately
  recorded calibrated eval runs.
- Review ran in the orchestration context after rereading the Phase 6 scope and
  delivered diff; no separate reviewer sub-agent was used.

### Next Action

- Phase 6 is delivered. The next automation run should start Phase 7 on
  `codex/integrated-research-runtime-eval-flywheel-phase-7`.

## Phase 7 - 2026-05-20

Status: delivered
Branch: `codex/integrated-research-runtime-eval-flywheel-phase-7`

### Scope

- Add API-first source preference policy and route-decision trace fields.
- Add mocked source profiles for statistical API, document repository, search
  endpoint, and private MCP-like routes.
- Keep browser fallback governed by task-contract browsing, network, domain,
  mock-response, and snapshot requirements.
- Add route-aware eval cases comparing API-only, browser-only, and hybrid
  behavior.

### Changes

- Runtime adapter execution now emits `route_decision` metadata on dry-run
  summaries and runtime traces, including selected adapter, selected source
  class, rejected alternatives, route reason, cost estimate, freshness
  expectation, license/use note, and browser fallback status.
- External mock adapters now expose source profiles without adding live
  provider integrations or dependencies.
- Runtime validation summarizes route decision and browser fallback counts and
  fails closed when web trace fallback metadata contradicts browser snapshot
  requirements.
- Runtime eval suites now carry source-route decisions, source-routing grader
  checks, API-first/browser-fallback metrics, and offline API-only,
  browser-only, and hybrid fixture coverage.
- Runtime docs, trace schema, eval schema, CLI text, and roadmap locked
  decisions were updated for Phase 7.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 16 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 777 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks
- `.venv/bin/python -m build`: passed, sdist and wheel built

### Review

- Review file: `roadmaps/automation/integrated_research_runtime_eval_flywheel/reviews/integrated-research-runtime-eval-flywheel-phase-7-review-iteration-1.md`
- Verdict: delivered

### Residual Risks

- Live production API/browser integrations remain future optional adapter work;
  the core package still uses offline mocks.
- Source profiles are fixture-level routing hints, not provider SDKs.
- Review ran in the orchestration context after rereading scope and diff; no
  separate reviewer sub-agent was used.

### Next Action

- Phase 7 is delivered. The next automation run should start Phase 8 on
  `codex/integrated-research-runtime-eval-flywheel-phase-8`.

## Phase 8 - 2026-05-20 - Delivery Pass 1

Status: delivered
Branch: `codex/integrated-research-runtime-eval-flywheel-phase-8`

### Scope

- Add machine-queryable structured evidence memory while preserving
  `research_ops/` source files as authoritative.
- Add targeted reflection records with failure classes, trigger conditions,
  affected stages, mitigations, anti-context text, and review evidence.
- Add public `evidence-memory` update/query and `reflection record` CLI
  surfaces plus offline fixtures.
- Surface stale or contradicted evidence before reuse and inject only relevant
  reflection context into planning anti-context.

### Changes

- Added `evidence_memory.py` with a derived
  `research_ops/memory/evidence_memory_index.json` builder, read-only query
  support, path-bounded reflection recording, schemas, and public
  `evidence-memory` / `reflection` CLI surfaces.
- Structured memory entries now expose claim IDs, evidence IDs, source IDs,
  source URIs, freshness status, accepted-memory status, contradiction edges,
  task lineage, deliverable links, and source-of-truth paths.
- Added targeted reflection records with failure class, trigger condition,
  affected stage, mitigation, anti-context injection text, review evidence, and
  expiry/status handling.
- Wired targeted reflections into `anti-context build` without replacing
  accepted-memory or rejected-idea anti-context sections.
- Added read-only console snapshot fields for evidence memory counts, recent
  contradiction edges, targeted reflections, warnings, and recovery commands.
- Added Phase 8 docs, schemas, package-resource coverage, CLI help/architecture
  coverage, and offline fixtures for contradiction, stale accepted evidence,
  repeated source-quality failure, and irrelevant reflection suppression.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 16 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 779 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks
- `.venv/bin/python -m build`: passed, sdist and wheel built

### Review

- Review file: `roadmaps/automation/integrated_research_runtime_eval_flywheel/reviews/integrated-research-runtime-eval-flywheel-phase-8-review-iteration-1.md`
- Verdict: delivered

### Residual Risks

- Existing unrelated dirty operator-skill/version files are intentionally
  outside this phase scope and will not be staged for the phase commit.
- Review ran in the orchestration context after rereading scope and diff; no
  separate reviewer sub-agent was used.
- The index is intentionally derived from repo files and is not a database or
  full-text search backend.

### Next Action

- Phase 8 is delivered. The next automation run should start Phase 9 on
  `codex/integrated-research-runtime-eval-flywheel-phase-9`.

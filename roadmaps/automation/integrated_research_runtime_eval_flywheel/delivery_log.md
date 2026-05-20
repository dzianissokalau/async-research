# Integrated Research Runtime And Eval Flywheel Delivery Log

Append-only delivery notes for
`roadmaps/delivered_integrated_research_runtime_eval_flywheel_roadmap.md`.

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

## Phase 9 - 2026-05-20 - Delivery Pass 1

Status: delivered
Branch: `codex/integrated-research-runtime-eval-flywheel-phase-9`

### Scope

- Add planner-controlled bounded parallel research for source gathering and
  literature extraction style fan-out.
- Enforce task-contract parallel permissions, branch budgets, branch-specific
  allowed paths, deterministic merge requirements, and lock/concurrency checks.
- Emit branch lineage on runtime traces and evidence objects while preserving
  task-state, review, claim-verification, result-acceptance, and human gates.
- Add runtime validation, eval metrics, offline fixtures, docs, and schemas for
  parallel and non-parallel cases.

### Changes

- Runtime requests now support `mode: "parallel_research"` only when
  `runtime_permissions.parallel_research` explicitly enables bounded fan-out.
- Parallel plan validation fails closed for unsupported branch shapes, missing
  planner control, missing deterministic review packets, invalid merge paths,
  unsafe branch IDs, source path escapes, budget/call-count overruns, direct
  acceptance, and gate-skip flags.
- Successful parallel execution tags trace/evidence rows with
  `parallel_branch` metadata and writes one Markdown merge packet under
  `research_ops/runtime/parallel_merges/`.
- Runtime validation and evals now report parallel branch, trace, and merge
  packet counts, and eval runs include a deterministic `bounded_parallelism`
  grader.
- Added bounded parallel research docs, task status schema fields, eval schema
  coverage, package-resource coverage, CLI help updates, and planner prompt
  guidance.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 16 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 783 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks
- `.venv/bin/python -m build`: passed, sdist and wheel built

### Review

- Review file: `roadmaps/automation/integrated_research_runtime_eval_flywheel/reviews/integrated-research-runtime-eval-flywheel-phase-9-review-iteration-1.md`
- Verdict: delivered

### Residual Risks

- Live external provider fan-out remains future adapter work; default coverage
  is deterministic and offline.
- Merge packets are review context only and still depend on downstream claim
  verification, review, result acceptance, deliverable maturity, and human
  gates.
- Existing unrelated dirty operator-skill/version files are intentionally
  outside this phase scope and will not be staged for the phase commit.
- Review ran in the orchestration context after rereading scope and diff; no
  separate reviewer sub-agent was used.

### Next Action

- Phase 9 is delivered. The next automation run should start Phase 10 on
  `codex/integrated-research-runtime-eval-flywheel-phase-10`.

## Phase 10 - 2026-05-20 - Delivery Pass 1

Status: delivered
Branch: `codex/integrated-research-runtime-eval-flywheel-phase-10`

### Scope

- Create one honest, repeatable domain pack and benchmark slice.
- Include source policies, brief/task templates, claim gates, reviewer rubrics,
  eval cases, example workspaces, and comparison reporting.
- Keep benchmark claims limited to the selected domain and fixture evidence.

### Changes

- Added the packaged `climate_coffee_economics` domain pack with source policy,
  preferred source classes, brief template, five benchmark task templates,
  claim gates, reviewer rubric, eval cases, comparison reports, static
  generic-baseline and upgraded-runtime eval runs, and an example
  `research_ops/` fixture skeleton.
- Added `domain_pack_path()` and package-data patterns so domain-pack Markdown,
  JSON, CSV, and JSONL resources are included in distributions.
- Updated eval and domain-pack docs to allow only benchmark-limited
  head-to-head claims with explicit wins, losses, unproven areas, source
  policies, reviewer rubrics, and human intervention points.
- Added offline tests for domain-pack artifact presence, benchmark case
  coverage, run-schema validity, `async-research eval compare`, package-data
  coverage, and resource availability.
- Advanced the roadmap/index to Phase 11 after marking Phase 10 delivered.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 16 tests
- `.venv/bin/python -m unittest tests.test_docs_packaging tests.test_domain_pack_benchmarks tests.test_runtime_evals`: passed, 17 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 787 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks
- `.venv/bin/python -m build`: passed, sdist and wheel built

### Review

- Review file: `roadmaps/automation/integrated_research_runtime_eval_flywheel/reviews/integrated-research-runtime-eval-flywheel-phase-10-review-iteration-1.md`
- Verdict: delivered

### Residual Risks

- The benchmark is deterministic and offline; live source acquisition,
  proprietary Deep Research-style outputs, and expert preference remain
  unproven until permissioned artifacts and calibrated paired reviews are
  recorded.
- Existing unrelated dirty operator-skill/version files are intentionally
  outside this phase scope and will not be staged for the phase commit.
- Review ran in the orchestration context after rereading scope and diff; no
  separate reviewer sub-agent was used.

### Next Action

- Phase 10 is delivered. The next automation run should start Phase 11 on
  `codex/integrated-research-runtime-eval-flywheel-phase-11`.

## Phase 11 - 2026-05-20 - Delivery Pass 1

Status: delivered
Branch: `codex/integrated-research-runtime-eval-flywheel-phase-11`

### Scope

- Measure scaling friction from task status files, runtime ledgers, dashboard
  snapshot latency, task locks, parallel merge packets, and eval artifacts.
- Decide whether repo files remain enough, whether an optional rebuildable
  index cache is justified, or whether an external queue/read model needs a
  human architecture decision.
- Preserve `research_ops/` files and task-local locks as the durable audit
  record unless measured evidence justifies a later optional backend.

### Changes

- Added `async-research scaling assess <research_ops>` as a read-only public
  CLI command backed by `async_research_workflow.scripts.scaling_state`.
- The assessor reports task status counts, task locks and stale locks, runtime
  trace/evidence ledger counts and bytes, eval suite/run/case pressure,
  parallel merge packet counts, and dashboard snapshot latency.
- Backend decisions are bounded to `repo_files_sufficient`,
  `optional_rebuildable_index_cache_candidate`, or
  `external_queue_or_read_model_needs_human_decision`; external orchestration
  is never selected automatically.
- CLI output now explains the source of every derived metric, marks itself
  read-only/unchanged, and warns when dashboard timing cannot be measured.
- Added the Phase 11 architecture decision record and updated scaling guidance,
  docs index, CLI help/architecture coverage, and roadmap backlog/status rows.

### Tests And Verification

- `git diff --check`: passed
- `.venv/bin/python -m unittest tests.test_doc_references`: passed, 16 tests
- `.venv/bin/python -m unittest tests.test_scaling_state_backend tests.test_cli_architecture tests.test_cli_help`: passed, 22 tests
- `.venv/bin/python -m unittest discover -s tests`: passed, 792 tests
- `.venv/bin/async-research acceptance-suite`: passed, 15 checks
- `.venv/bin/python -m build`: passed, sdist and wheel built
- `.venv/bin/async-research scaling assess src/async_research_workflow/domain_packs/climate_coffee_economics/example_workspace/research_ops --now 2026-05-20T12:00:00Z`: passed, `repo_files_sufficient`

### Review

- Review file: `roadmaps/automation/integrated_research_runtime_eval_flywheel/reviews/integrated-research-runtime-eval-flywheel-phase-11-review-iteration-1.md`
- Verdict: delivered

### Residual Risks

- Phase 11 adds a measurement and decision surface, not a production queue,
  database benchmark, or backend implementation.
- Future external queues or shared read models still require measured
  workspace friction and a human architecture decision.
- Existing unrelated dirty operator-skill/version files are intentionally
  outside this phase scope and will not be staged for the phase commit.
- Review ran in the orchestration context after rereading scope and diff; no
  separate reviewer sub-agent was used.

### Next Action

- All roadmap phases are delivered. Finalize the delivered branch, push only
  the all-phases-complete branch, and pause the cron automation.

## Final Completion - 2026-05-20

Status: completed_pending_pause
Branch: `codex/integrated-research-runtime-eval-flywheel-delivered`

### Summary

- All phases 0-11 in
  `roadmaps/delivered_integrated_research_runtime_eval_flywheel_roadmap.md`
  are marked delivered.
- Final verification passed after Phase 11.
- Final deep-review prompt was written for an independent LLM review.
- `automation_update` was not available from tool discovery in this session, so
  the automation is paused by hard-stop state:
  `completed_pending_pause` with `all_phases_complete: true`.

### Next Action

- Do not start new delivery work for this automation unless a human explicitly
  reactivates it for follow-up review findings.

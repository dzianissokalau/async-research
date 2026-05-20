# Integrated Research Runtime And Eval Flywheel Roadmap

Status: In Progress
Current phase: Phase 1 - Evidence objects and trace ledger
Last updated: 2026-05-20
Next action: Add stable runtime evidence and trace schemas, validators, ledgers, CLI summaries, dashboard fields, and offline fixtures
Blocked by: None

Created: 2026-05-20
Input reviewed: `/Users/dzianissokalau/Downloads/async-research-improving.md`

## Summary

This roadmap turns the async-research framework from a governed research-ops
kernel into a stronger integrated research system.

The feedback's core diagnosis is right: the framework already has unusually
strong governance primitives - task contracts, review gates, claim caps,
accepted-memory freshness, cost controls, and deterministic state transitions -
but it still relies too much on external agent surfaces for the actual research
runtime. The next quality leap should therefore come from execution substrate
and evaluation, not from adding more workflow prose.

The target is not to clone a consumer Deep Research product. The target is to
make async-research excellent for repeatable, domain-specific, high-accountability
research programs where auditability, private data, reproducibility, freshness,
and cost discipline matter.

## Product Thesis

Async-research should keep its file-backed governance model, but add an
integrated runtime layer that can:

- clarify and rewrite ambiguous research briefs before execution
- route work across web search, file search, MCP/private data, APIs, and code
- normalize every retrieved source, tool call, and computed result into evidence
  objects
- verify citations and claim support before acceptance
- convert traces into repeatable evals and regression gates
- use model routing deliberately: frontier models for planning, synthesis, and
  critique; cheaper models or deterministic code for extraction and repetition
- preserve human gates for public claims, paid services, credentials, and
  ambiguous evidence

## What I Think

The feedback is directionally strong, with one important framing adjustment:
async-research should not try to beat ChatGPT Deep Research on broad one-shot
open-web research first. That is the hardest battleground because Deep Research
already has a polished integrated browsing and reporting substrate.

The more sensible path is to win where async-research has natural structural
advantages:

- recurring research programs
- private or semi-private data workflows
- research that needs reproducible intermediate artifacts
- empirical or data-heavy research with claim gates
- work where stale-memory reuse, source governance, and review independence
  matter
- internal reports that later mature into shareable memos or working papers

The first implementation priority should be a narrow but real runtime/eval loop,
not a giant all-purpose agent platform. Build one high-quality vertical slice:
clarified brief -> runtime tool calls -> evidence objects -> verified claims ->
review -> accepted memory -> eval trace.

## Relationship To Existing Roadmaps

| Existing Roadmap Or Surface | Relationship |
| --- | --- |
| LLM Operator Skill Roadmap | The operator skill helps Codex/LLMs run the framework. This roadmap improves what the framework can do once operated. |
| Knowledge Library Roadmap | Provides source/library memory. This roadmap adds runtime retrieval and evidence normalization around it. |
| Data Foundations Roadmap | Provides data-source governance. This roadmap adds API-first routing and tool traces for accessed data. |
| Hypothesis Testing Framework Roadmap | Provides empirical analysis contracts. This roadmap adds runtime/tool evidence and eval traces around analysis work. |
| Deliverable Maturity And Editorial QA Roadmap | Provides deliverable gates. This roadmap adds claim/citation verification before deliverable review. |
| Dashboard | Should surface runtime traces, evidence verification, eval scores, and unresolved gaps. |
| Future Improvements Backlog | Some backlog items overlap; implementing this roadmap should retire or absorb overlapping future-improvement rows. |

## Design Principles

- Keep `research_ops/` files and public CLI outputs as source of truth.
- Add runtime capability as bounded adapters, not hidden autonomous behavior.
- Every external tool call must produce an auditable trace row and evidence
  object.
- Prefer API-first retrieval where stable structured APIs exist; browse as a
  fallback or for human-facing context.
- Block or downgrade claims that cannot be mapped to evidence spans.
- Treat evals as product infrastructure, not a one-off benchmark.
- Preserve standard-library-first package posture unless a phase explicitly
  decides an optional dependency boundary.
- Do not optimize for agent activity. Optimize for accepted evidence per dollar
  and per minute of human attention.

## Target Architecture

```mermaid
flowchart TD
    A["User question or recurring brief"] --> B["Clarifier"]
    B --> C["Research brief rewrite"]
    C --> D["Planner"]
    D --> E["Runtime router"]

    E --> F["Web search/open"]
    E --> G["File search"]
    E --> H["MCP/private data"]
    E --> I["Structured API adapters"]
    E --> J["Code sandbox/analysis"]

    F --> K["Evidence normalizer"]
    G --> K
    H --> K
    I --> K
    J --> K

    K --> L["Claim and citation verifier"]
    L --> M["Worker output or draft"]
    M --> N["Review panel"]
    N --> O["Result acceptance"]
    O --> P["Accepted memory and freshness"]
    O --> Q["Trace store and eval dataset"]
    Q --> R["Prompt/policy/model routing improvements"]
    R --> D
```

## Resolved Phase 0 Runtime And Evaluation Contract

Phase 0 is delivered as a contract-only slice. It defines the runtime boundary,
adapter taxonomy, evidence object fields, trace fields, quality metrics,
dependency posture, and human gates that later phases must implement.

Authoritative contract docs:

- [Research Runtime Contract](../src/async_research_workflow/docs/research_runtime_contract.md)
- [Evaluation Flywheel](../src/async_research_workflow/docs/evaluation_flywheel.md)

Locked decisions:

- Runtime adapters may fetch, search, parse, compute, summarize, and emit
  artifacts, but workflow commands still own task state transitions.
- Review, result acceptance, deliverable maturity, and accepted-memory commands
  remain the only surfaces that can accept evidence or publication readiness.
- Dashboard and console surfaces remain derived visibility layers, not sources
  of truth.
- Adapter classes are `web_search`, `web_open`, `file_search`, `file_fetch`,
  `mcp_search`, `mcp_fetch`, `api_query`, and `code_execute`.
- Runtime capability is read-only by default; missing task-contract permission
  data fails closed.
- Network, credentials, paid calls, unsafe source use, public claims, and
  ambiguous private/public boundaries require explicit task-contract permission
  or a recorded human gate.
- Evidence object minimum fields are `evidence_id`, `task_id`, `adapter_type`,
  `source_uri`, `source_title`, `retrieved_at`, `content_hash`,
  `snapshot_path`, `span_refs`, `license_or_use_policy`, `freshness_status`,
  `cost`, and `permission_basis`.
- Runtime trace minimum fields are `trace_id`, `task_id`, `tool_name`,
  `input_summary`, `output_summary`, `artifact_paths`, `return_code`,
  `duration_ms`, `token_usage`, `cost`, and `error`.
- Quality metrics are expert preference win rate, grounded claim rate,
  unsupported claim rate, task success rate, accepted-output rate, cost per
  accepted report, median latency to accepted report, freshness failure rate,
  reviewer disagreement rate, and reproducibility pass rate.
- Core dependency posture remains standard-library first. Provider SDKs,
  network adapters, and other external integrations belong in optional runtime
  extras or plugin adapter packages after the contracts are proven.
- Head-to-head Deep Research-style comparison claims remain out of scope until
  Phase 10 and must be benchmark-limited.

## Phased Plan

| Phase | Status | Priority | Focus | Scope | Exit Criteria |
| ---: | --- | --- | --- | --- | --- |
| 0 | Delivered | P0 | Runtime and evaluation contract | Define runtime boundary, adapter contract, evidence object schema, trace schema, dependency posture, and success metrics. | Another LLM can implement adapters and evals without guessing what counts as evidence or success. |
| 1 | Not Started | P0 | Evidence objects and trace ledger | Add schemas and validators for tool calls, source snapshots, extracted spans, computed outputs, hashes, costs, and permissions. | Every future runtime action has a stable, auditable artifact format. |
| 2 | Not Started | P0 | Clarifier and research brief rewrite | Add a pre-planning stage for clarifying questions, scope decisions, output target, source policy, and rewritten executable brief. | Ambiguous research requests are turned into bounded task briefs before planning. |
| 3 | Not Started | P0 | Minimal unified runtime adapters | Implement a narrow adapter interface for web, file, API, MCP, and code tools, with read-only defaults and trace emission. | One vertical-slice research task can call tools and write evidence objects without bespoke glue. |
| 4 | Not Started | P0 | Claim and citation verification | Extract claims, map them to evidence spans, verify citation provenance, and block or cap unsupported claims. | Review cannot accept source-grounded outputs with unmapped or unsupported material claims. |
| 5 | Not Started | P0 | Trace-driven eval flywheel | Turn runtime traces into fixture datasets, graders, regression commands, and dashboard metrics. | Quality changes can be evaluated against repeatable traces before release. |
| 6 | Not Started | P1 | GPT-5.5-era prompt and model routing | Slim prompts, move brittle rules into validators, and define planner/workhorse/critic routing policies. | The framework uses stronger models where they matter and cheaper paths where they are enough. |
| 7 | Not Started | P1 | Hybrid API-first routing | Prefer structured APIs where available, browse where necessary, and record source selection rationale. | Runtime chooses reliable machine interfaces before expensive or fragile browsing. |
| 8 | Not Started | P1 | Structured evidence memory and targeted reflection | Add queryable evidence state, contradiction links, failure classes, and targeted critic routing. | Accepted memory becomes machine-queryable without replacing repo artifacts as truth. |
| 9 | Not Started | P2 | Bounded parallel research threads | Allow planner-controlled source-gathering or literature-extraction fan-out with deterministic merge and review. | Parallelism improves coverage without uncontrolled swarms or hidden writes. |
| 10 | Not Started | P2 | Domain packs and head-to-head benchmark | Package one domain-specific runtime/eval pack and compare against baseline Deep Research-style outputs. | The framework has evidence of where it can beat general-purpose research products. |
| 11 | Not Started | P3 | Optional scalable state backend | Decide whether event-log, queue, or indexed state storage is needed beyond repo files. | Scaling work is justified by measured friction, not assumed upfront. |

## Phase 0 - Runtime And Evaluation Contract

### Objective

Define what the runtime is allowed to do, what every runtime action must record,
and how quality will be measured.

### Owned Files

- `roadmaps/in_progress_integrated_research_runtime_eval_flywheel_roadmap.md`
- optionally `src/async_research_workflow/docs/research_runtime_contract.md`
- optionally `src/async_research_workflow/docs/evaluation_flywheel.md`
- `roadmaps/README.md`

### Implementation Steps

1. Define the runtime boundary:
   - runtime adapters may fetch, search, parse, compute, and summarize
   - workflow commands still own task state transitions
   - review/result-acceptance commands still own acceptance
   - dashboard remains a visibility surface, not source of truth
2. Define adapter classes:
   - `web_search`
   - `web_open`
   - `file_search`
   - `file_fetch`
   - `mcp_search`
   - `mcp_fetch`
   - `api_query`
   - `code_execute`
3. Define allowed default posture:
   - read-only by default
   - network disabled unless task contract allows it
   - credentials require human gate
   - paid calls require budget/approval policy
   - no source is accepted merely because it was retrieved
4. Define evidence object minimum fields:
   - `evidence_id`
   - `task_id`
   - `adapter_type`
   - `source_uri`
   - `source_title`
   - `retrieved_at`
   - `content_hash`
   - `snapshot_path`
   - `span_refs`
   - `license_or_use_policy`
   - `freshness_status`
   - `cost`
   - `permission_basis`
5. Define trace minimum fields:
   - `trace_id`
   - `task_id`
   - `tool_name`
   - `input_summary`
   - `output_summary`
   - `artifact_paths`
   - `return_code`
   - `duration_ms`
   - `token_usage`
   - `cost`
   - `error`
6. Define quality metrics:
   - expert preference win rate
   - grounded claim rate
   - unsupported claim rate
   - task success rate
   - accepted-output rate
   - cost per accepted report
   - median latency to accepted report
   - freshness failure rate
   - reviewer disagreement rate
   - reproducibility pass rate
7. Decide dependency posture:
   - standard-library core only
   - optional runtime extras
   - plugin adapter packages
   - or hard runtime dependencies

### Acceptance Criteria

- Runtime boundary is explicit.
- Evidence and trace schemas are documented.
- Metrics are specific enough to drive eval implementation.
- Dependency posture is chosen before code work starts.
- Human gates are explicit for credentials, paid APIs, public claims, and unsafe
  source use.

### Verification

Use the shared roadmap checks in `roadmaps/README.md`.

### Non-Goals

- Do not implement adapters in Phase 0.
- Do not add external dependencies in Phase 0.
- Do not replace existing task/review/acceptance state machines.

## Phase 1 - Evidence Objects And Trace Ledger

### Objective

Create the artifact contracts that every future runtime adapter must write.

### Owned Files

- `src/async_research_workflow/schemas/` or equivalent schema location
- runtime/evidence docs
- CLI validators
- fixture workspaces
- tests

### Implementation Steps

1. Add schema files for evidence objects and runtime traces.
2. Add deterministic validators:
   - validate required fields
   - validate IDs and task links
   - validate artifact paths stay inside `research_ops/`
   - validate hashes when snapshots exist
   - warn on missing license/use-policy metadata
3. Add a trace ledger location, for example:
   - `research_ops/runtime/traces.jsonl`
   - `research_ops/runtime/evidence_objects.jsonl`
   - `research_ops/runtime/snapshots/`
4. Add CLI commands:
   - `async-research runtime validate <research_ops>`
   - `async-research runtime summary <research_ops>`
   - `async-research runtime inspect-evidence <research_ops> <evidence-id>`
5. Add dashboard snapshot fields:
   - runtime trace count
   - evidence object count
   - unsupported or stale evidence count
   - latest runtime errors
6. Add fixtures for valid, missing-field, stale, bad-path, and hash-mismatch
   evidence objects.

### Acceptance Criteria

- Runtime evidence can be validated without live external services.
- Bad paths and malformed evidence fail closed.
- Dashboard and console snapshot can summarize runtime evidence state.
- Existing accepted-memory and result-acceptance flows are not broken.

### Non-Goals

- Do not implement live web/API fetching yet.
- Do not make evidence objects accepted evidence automatically.

## Phase 2 - Clarifier And Research Brief Rewrite

### Objective

Add a pre-planning stage that turns vague user intent into a bounded executable
research brief.

### Owned Files

- brief schema/docs
- task templates
- prompt library entries
- CLI support
- tests/fixtures

### Implementation Steps

1. Define `research_brief.json` or equivalent Markdown+JSON contract:
   - user question
   - clarified objective
   - intended output maturity
   - target audience/venue
   - allowed source classes
   - forbidden source classes
   - private-data policy
   - browsing/API/code permissions
   - budget and time caps
   - known assumptions
   - unresolved questions
2. Add commands:
   - `async-research brief draft <research_ops>`
   - `async-research brief validate <brief-path>`
   - `async-research brief apply <research_ops> <brief-path> --dry-run`
3. Add prompt-library guidance for:
   - when to ask clarifying questions
   - when to proceed with assumptions
   - how to rewrite a brief for execution
   - when to stop for human approval
4. Wire idea promotion and task creation to consume a validated brief where
   available.
5. Add fixtures:
   - clear brief
   - ambiguous brief requiring human question
   - missing audience
   - public-claim brief requiring stricter gates
   - private-data brief requiring credential stop

### Acceptance Criteria

- Planner does not start broad research from ambiguous prompts without a brief.
- Output target and audience are available before synthesis/drafting.
- Human gates appear when the brief requires credentials, paid access, or public
  claims.

### Non-Goals

- Do not build chat UI.
- Do not require clarifier for every tiny maintenance task.

## Phase 3 - Minimal Unified Runtime Adapters

### Objective

Implement the smallest useful runtime adapter layer that can support one
end-to-end research vertical slice.

### Owned Files

- runtime adapter modules
- adapter docs
- CLI wrappers
- fixtures and tests
- dashboard/console read models

### Implementation Steps

1. Define a single adapter interface with:
   - `capabilities()`
   - `dry_run(request)`
   - `execute(request)`
   - `to_trace()`
   - `to_evidence_objects()`
2. Implement deterministic/local adapters first:
   - file search/fetch over workspace-approved files
   - local Markdown/PDF text extraction if dependencies already exist or are
     optional extras
   - code execution wrapper around existing analysis conventions
3. Add external adapters behind explicit capability flags:
   - web search/open adapter
   - MCP search/fetch adapter
   - generic structured API query adapter
4. Add task-contract integration:
   - `allowed_tools`
   - network permission
   - credentials required
   - max calls
   - max cost
   - allowed domains or API names
5. Ensure every adapter emits trace and evidence artifacts.
6. Add a runtime dry-run command that reports planned tool calls without
   executing network or paid actions.
7. Add one vertical-slice fixture:
   - validated brief
   - one file source
   - one mocked web/API source
   - evidence objects
   - worker output
   - review packet

### Acceptance Criteria

- Runtime adapters are optional and bounded by task contract permissions.
- Adapter outputs are auditable through evidence objects.
- Mocked external adapters allow tests to run offline.
- One end-to-end fixture proves the runtime can support a real research task.

### Non-Goals

- Do not implement every provider or source type.
- Do not let runtime adapters transition task state directly.

## Phase 4 - Claim And Citation Verification

### Objective

Prevent unsupported or mis-cited claims from reaching accepted evidence or
publication-oriented deliverables.

### Owned Files

- claim extraction/verifier modules
- result-acceptance integration
- deliverable maturity integration
- fixtures and tests
- docs

### Implementation Steps

1. Define atomic claim object fields:
   - `claim_id`
   - `text`
   - `claim_type`
   - `strength`
   - `required_support_level`
   - `evidence_refs`
   - `citation_refs`
   - `verification_status`
   - `failure_reason`
2. Add claim extraction from:
   - worker outputs
   - result summaries
   - deliverable drafts
3. Add citation/evidence mapping:
   - evidence ID
   - source URI
   - span reference
   - quote or paraphrase status
   - source freshness status
4. Add verifier outcomes:
   - `supported`
   - `weakly_supported`
   - `unsupported`
   - `contradicted`
   - `stale`
   - `unverifiable`
5. Integrate with result acceptance:
   - block hard unsupported empirical claims
   - cap claim strength where support is weak
   - route contradictions to skeptic review
   - record unresolved claims in ledgers
6. Integrate with deliverable maturity:
   - working-paper/submission-ready outputs require citation verification
   - unresolved citation gaps block readiness
7. Add fixtures:
   - supported citation
   - missing citation
   - stale source
   - contradicted source
   - numeric claim with no computation artifact

### Acceptance Criteria

- Unsupported material claims cannot be accepted silently.
- Claim caps are visible in result acceptance and dashboard surfaces.
- Citation verification can run without live network when evidence snapshots
  exist.

### Non-Goals

- Do not promise perfect truth verification.
- Do not require formal bibliography style enforcement in this phase.

## Phase 5 - Trace-Driven Eval Flywheel

### Objective

Turn real runtime activity into repeatable evaluation datasets and release
regression gates.

### Owned Files

- eval dataset schema
- grader modules or prompts
- CLI commands
- benchmark fixtures
- dashboard/metrics read models

### Implementation Steps

1. Define eval case fields:
   - `case_id`
   - `source_trace_ids`
   - `input_brief`
   - `expected_behavior`
   - `gold_or_reference_evidence`
   - `grader`
   - `metrics`
   - `known_limitations`
2. Add commands:
   - `async-research eval build-from-traces <research_ops>`
   - `async-research eval run <eval-suite>`
   - `async-research eval compare <baseline> <candidate>`
3. Add grader types:
   - deterministic schema/path/hash graders
   - groundedness grader
   - citation-support grader
   - task-success rubric grader
   - cost/latency grader
   - human-review placeholder
4. Add dashboard metrics:
   - grounded claim rate
   - unsupported claim rate
   - accepted-output rate
   - cost per accepted report
   - stale evidence reuse
   - reviewer disagreement
5. Add release policy:
   - prompt/runtime policy changes require eval comparison
   - regressions block marking roadmap phases delivered
   - human-calibrated evals remain marked separately from automated evals

### Acceptance Criteria

- At least one eval suite can be built from fixture traces.
- Eval comparison reports pass/fail, metric deltas, and residual risks.
- Quality claims are tied to eval evidence rather than anecdotes.

### Non-Goals

- Do not require paid live model calls in the default unit test path.
- Do not optimize prompts automatically yet.

## Phase 6 - GPT-5.5-Era Prompt And Model Routing

### Objective

Modernize prompts and model selection so stronger models get freedom where it
helps, while validators enforce hard rules.

### Owned Files

- prompt library
- scheduler/model routing docs
- cost controls
- eval cases
- tests

### Implementation Steps

1. Audit existing prompts for repeated procedural rules that can move into:
   - validators
   - task contracts
   - runtime adapter permissions
   - brief schema
2. Define role-specific prompt posture:
   - planner: brief-aware, high reasoning, fewer brittle lists
   - worker: bounded by task contract and runtime permissions
   - extractor: cheap model or deterministic parser when possible
   - methodology reviewer: frontier model
   - skeptic/contradiction checker: targeted, evidence-first
   - synthesizer: maturity-level aware
3. Add routing config:
   - model tier by role
   - max budget by role
   - escalation triggers
   - fallback model policy
4. Run prompt migration evals against Phase 5 suites.
5. Keep old prompt variants as baselines until new prompts outperform or match
   them on quality and cost.

### Acceptance Criteria

- Prompt changes are evaluated before adoption.
- Hard safety rules remain in validators/contracts, not only in prose.
- Model routing reduces cost without lowering groundedness or task success.

### Non-Goals

- Do not hard-code one proprietary provider as the only path.
- Do not remove explicit stop conditions.

## Phase 7 - Hybrid API-First Routing

### Objective

Prefer reliable structured interfaces over fragile browsing when both are
available.

### Owned Files

- API adapter contracts
- source policies
- runtime router
- fixtures and tests
- docs

### Implementation Steps

1. Add source preference policy:
   - official API
   - authoritative downloadable data
   - official page
   - reputable third-party database
   - general web page
   - user-provided source
2. Add router decision fields:
   - selected adapter
   - rejected alternatives
   - reason
   - cost estimate
   - freshness expectation
   - license/use-policy note
3. Add mock adapters for common classes:
   - statistical API
   - document repository
   - search endpoint
   - private MCP-like source
4. Add browser fallback rule:
   - use browsing when API is unavailable, incomplete, or needed for context
   - snapshot pages when used as evidence
5. Add eval cases comparing API-only, browser-only, and hybrid behavior.

### Acceptance Criteria

- Runtime traces explain why each source route was chosen.
- Hybrid routing improves groundedness or cost in at least one eval fixture.
- Browser fallback does not bypass source governance.

### Non-Goals

- Do not build dozens of production API integrations before the adapter contract
  is proven.

## Phase 8 - Structured Evidence Memory And Targeted Reflection

### Objective

Make accepted evidence and recurring failures easier for machines to query while
preserving repo artifacts as the authoritative record.

### Owned Files

- structured evidence memory schema
- accepted-memory integration
- reflection/failure taxonomy docs
- CLI commands
- tests

### Implementation Steps

1. Add structured evidence index fields:
   - claim IDs
   - evidence IDs
   - source IDs
   - contradiction edges
   - freshness status
   - task lineage
   - deliverable links
2. Add targeted reflection records:
   - failure class
   - trigger condition
   - affected stage
   - mitigation
   - future anti-context injection text
   - review evidence
3. Add commands:
   - `async-research evidence-memory update <research_ops>`
   - `async-research evidence-memory query <research_ops>`
   - `async-research reflection record <task-dir>`
4. Wire targeted reflection into planner context:
   - only inject relevant failure classes
   - avoid dumping stale global warnings
   - preserve rejected-idea anti-context
5. Add fixtures:
   - contradiction detected
   - stale accepted evidence
   - repeated source-quality failure
   - irrelevant reflection suppressed

### Acceptance Criteria

- Machine-queryable memory improves planning context without replacing source
  files.
- Reflection is targeted to recurring failure classes.
- Stale or contradicted evidence is visible before reuse.

### Non-Goals

- Do not add a database as a required runtime dependency in this phase.

## Phase 9 - Bounded Parallel Research Threads

### Objective

Allow controlled parallel source gathering or literature extraction where it
improves coverage, while keeping task state deterministic.

### Owned Files

- planner policy
- runtime router
- task contract extensions
- merge/review docs
- fixtures and tests

### Implementation Steps

1. Define allowed parallel task shapes:
   - source gathering
   - literature extraction
   - market map slices
   - policy/regulatory comparison by jurisdiction
   - data-source profiling
2. Define fan-out constraints:
   - max parallel branches
   - per-branch budget
   - allowed files
   - branch-specific evidence IDs
   - no direct acceptance from branch outputs
3. Define merge requirements:
   - branch summary
   - evidence coverage table
   - contradictions
   - unresolved gaps
   - reviewer packet
4. Add lock/concurrency integration.
5. Add eval cases where parallelism should and should not trigger.

### Acceptance Criteria

- Parallelism is planner-controlled and bounded.
- Branch outputs merge into one reviewable artifact.
- Parallelism cannot skip review, claim verification, or human gates.

### Non-Goals

- Do not create an uncontrolled many-agent swarm.

## Phase 10 - Domain Packs And Head-To-Head Benchmark

### Objective

Prove where async-research can outperform general-purpose Deep Research-style
products by packaging one repeatable domain and evaluating it honestly.

### Owned Files

- `domain_packs/` or agreed package location
- benchmark suites
- example research workspaces
- review rubrics
- docs

### Implementation Steps

1. Pick one first domain:
   - market intelligence
   - regulatory analysis
   - climate/coffee economics
   - real estate economics
   - literature review
2. Create domain pack contents:
   - source policy
   - preferred APIs/sources
   - brief templates
   - task templates
   - claim gates
   - reviewer rubrics
   - eval cases
3. Build benchmark tasks:
   - open-web synthesis
   - private/local file synthesis
   - data/API retrieval
   - empirical check
   - deliverable maturity check
4. Compare:
   - baseline async-research without runtime
   - upgraded async-research
   - manually captured Deep Research-style output where allowed
   - human review baseline where available
5. Report:
   - preference win rate
   - groundedness
   - unsupported claims
   - cost
   - latency
   - human intervention points

### Acceptance Criteria

- The project can state honestly where upgraded async-research wins, loses, or
  remains unproven.
- Domain pack improves at least one meaningful metric over generic operation.
- Benchmark artifacts are reproducible without hidden chat context.

### Non-Goals

- Do not claim broad superiority over ChatGPT Deep Research from one domain.

## Phase 11 - Optional Scalable State Backend

### Objective

Decide whether repo files plus lock directories are enough, or whether a queue,
event log, and indexed read model are needed for higher concurrency.

### Owned Files

- architecture decision record
- optional backend prototype
- migration/compatibility docs
- tests

### Implementation Steps

1. Measure friction from prior phases:
   - trace file size
   - dashboard latency
   - lock contention
   - concurrent branch conflicts
   - eval-suite runtime
2. Decide backend need:
   - no backend
   - optional local SQLite/index cache
   - append-only event log
   - external queue/read model
3. Preserve repo-first audit:
   - backend cache must be rebuildable
   - unique manual decisions stay in files
   - CLI must explain source of every derived value
4. Prototype only if metrics justify it.

### Acceptance Criteria

- Backend decision is evidence-based.
- Any backend is optional or clearly justified.
- Repo artifacts remain the durable audit record.

### Non-Goals

- Do not move core truth out of `research_ops/` by default.

## Prioritized Improvement Table

| Priority | Improvement | Description | Impact | Status |
| --- | --- | --- | --- | --- |
| P0 | Evidence objects and trace ledger | Stable schemas for source snapshots, tool calls, costs, hashes, permissions, and span refs. | Makes integrated runtime auditable instead of opaque. | Not Started |
| P0 | Clarifier and brief rewrite | Converts vague requests into bounded research briefs with audience, output maturity, source policy, and permissions. | Prevents broad, under-specified tasks from entering execution. | Not Started |
| P0 | Minimal unified runtime adapters | One adapter interface for file, web, API, MCP, and code execution, with traces and evidence outputs. | Closes the biggest execution gap versus integrated Deep Research products. | Not Started |
| P0 | Claim and citation verification | Maps atomic claims to evidence spans and blocks or caps unsupported claims. | Directly improves final research quality and trust. | Not Started |
| P0 | Trace-driven eval flywheel | Builds eval cases from traces and gates future prompt/runtime changes. | Turns quality into a measured loop instead of opinion. | Not Started |
| P1 | Prompt and model routing modernization | Slim prompts, keep hard rules in validators, and route model tiers by role. | Improves quality/cost balance with stronger models. | Not Started |
| P1 | Hybrid API-first routing | Prefer structured APIs and authoritative data before browsing. | Improves reliability, freshness, and cost. | Not Started |
| P1 | Structured evidence memory and targeted reflection | Adds queryable evidence and failure memory while preserving repo artifacts. | Improves longitudinal research quality. | Not Started |
| P2 | Bounded parallel research threads | Allows controlled fan-out/fan-in for source gathering and extraction. | Improves coverage without agent-swarm risk. | Not Started |
| P2 | Domain pack and head-to-head benchmark | Proves one vertical where the framework can beat general-purpose research products. | Creates credible external quality evidence. | Not Started |
| P3 | Optional scalable backend | Adds indexed state only if measured friction justifies it. | Helps scale without prematurely abandoning repo-first design. | Not Started |

## Suggested Delivery Order

1. Phase 0 to define contracts and metrics.
2. Phase 1 because runtime without evidence objects would become opaque.
3. Phase 2 because clarified briefs improve every downstream stage.
4. Phase 3 to deliver a narrow runtime vertical slice.
5. Phase 4 before accepting runtime-backed outputs as strong evidence.
6. Phase 5 before optimizing prompts, models, or routing.
7. Phase 6 and Phase 7 together if one implementation pass is desired; they
   both depend on evals.
8. Phase 8 after enough traces exist to identify recurring evidence/failure
   patterns.
9. Phase 9 only after the single-threaded runtime is reliable.
10. Phase 10 once the system is strong enough to benchmark honestly.
11. Phase 11 only if measured scaling friction appears.

## Verification Strategy

For every phase:

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
```

When implementation files or tests are added:

```bash
.venv/bin/python -m unittest discover -s tests
```

When runtime adapters or eval commands are added, include offline fixture tests
that do not require network, credentials, or paid API calls.

When network-capable adapters are added, include explicit tests that verify they
fail closed without task-contract permission.

## Open Decisions

- Should runtime schemas live under existing `schemas/`, a new `runtime/`
  package, or both?
- Should runtime adapters be standard-library only, optional extras, or plugin
  packages?
- What is the first domain pack for benchmarking?
- Which source classes are allowed in the first vertical slice?
- Should the first web/API adapters be mocked-only, local-only, or live behind
  explicit opt-in?
- How should human expert preference reviews be stored without making private
  reviewer notes public by default?

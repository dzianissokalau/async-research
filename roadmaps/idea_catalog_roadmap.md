# Idea Catalog Roadmap

Created: 2026-05-05

## Summary

Build a durable idea catalog that turns rough ideas into a managed research
portfolio. The catalog should capture, dedupe, score, park, reject, and promote
ideas based on mission fit, novelty, impact, feasibility, data readiness, cost,
robustness risk, reuse potential, and killability.

This feature builds on the existing discovery workflow, `discovery_inbox.md`,
`async-research idea score`, and `async-research idea validate`. Its job is to
make prioritization visible, repeatable, and easy to inspect before ideas become
real task folders.

## Product Decision

Keep three separate layers:

```text
discovery_inbox.md = what did we just find?
ideas/idea_catalog.md = what ideas are worth tracking?
queue.md = what are we actually working on next?
```

The catalog is not a second execution queue. It is a portfolio and planning
surface. Only the planner, or a human-approved helper, may turn a catalog idea
into a bounded task.

## What It Does

The idea catalog maintains an idea pipeline:

- rough idea capture
- structured idea candidates
- dedupe and clustering
- evidence seeds from discovery, accepted outputs, rejected ideas, future
  library refs, and future data foundation refs
- mission-weighted scoring
- skeptic notes and kill criteria
- known blockers
- recommended next smallest task
- promotion, parking, and rejection history

The catalog should prioritize useful, killable ideas over interesting but vague
ones. A high-scoring idea should usually become a `literature_extract`,
`data_readiness`, `hypothesis_card`, or `experiment_plan` task only after
required gates pass. Direct promotion from discovery into expensive experiments
remains blocked.

## Delivery Strategy

Build this as a sequence of small, deterministic slices. Because AI workers can
iterate quickly, do not optimize the plan around calendar duration. Optimize it
around state safety and clean sequencing:

1. Define the durable files.
2. Parse and validate those files.
3. Wire the CLI.
4. Add candidate references.
5. Add catalog maintenance.
6. Add promotion dry-runs.
7. Integrate planner and surfaces.
8. Add dashboard views.

Each slice should leave the package usable. Each mutation-capable slice should
ship after its read-only or dry-run version.

## Framework Integration

Existing artifacts:

```text
research_ops/discovery_inbox.md
research_ops/discovery/clusters.md
research_ops/discovery/rejected_ideas.md
research_ops/accepted_outputs_index.md
research_ops/queue.md
src/async_research_workflow/schemas/idea_candidate.schema.json
```

New workspace artifacts:

```text
research_ops/
  ideas/
    idea_catalog.md
    prioritization.md
    IDEA-0001.json
```

Initial catalog status values:

```text
raw
candidate
scored
promote
park
reject
promoted
needs_human
```

Use the existing candidate statuses where possible:

```text
candidate
promote
park
reject
```

The Markdown catalog may use broader display statuses such as `raw`, `scored`,
and `promoted`, but `IDEA-*.json` should stay aligned with the schema until the
schema is deliberately extended.

## Phase 0: Lock Product Invariants

Purpose: prevent the feature from becoming an unreviewed task generator.

Decisions to record in docs before implementation:

- `discovery_inbox.md` remains a short-lived buffer.
- `ideas/idea_catalog.md` is the durable portfolio.
- `queue.md` remains the execution queue.
- Catalog validation is read-only.
- Promotion starts as dry-run only.
- Empty catalog files are valid during cold start.
- Direct experiment promotion remains blocked unless existing source and data
  gates pass.

Acceptance:

- roadmap and docs state the three-layer model clearly
- no implementation step allows catalog maintenance to edit `queue.md`
- no worker can create a task folder as part of discovery or catalog validation

## Phase 1: Starter Files And Contracts

Purpose: make the catalog visible in every new workspace without changing
runtime behavior.

Files to add to both starter templates:

```text
research_ops/ideas/idea_catalog.md
research_ops/ideas/prioritization.md
```

Optional placeholder:

```text
research_ops/ideas/.gitkeep
```

Suggested `idea_catalog.md` table:

```markdown
| idea_id | status | title | weighted_score | next_task | blockers | promoted_task | updated |
| --- | --- | --- | ---: | --- | --- | --- | --- |
```

Suggested `prioritization.md` sections:

```markdown
# Idea Prioritization

## Recommended Promotions

## Parked Ideas

## Rejected Ideas

## Blockers
```

Implementation steps:

1. Add the files to `generic_research_ops_starter`.
2. Add the files to the real-estate worked example starter.
3. Update starter READMEs to explain `discovery_inbox.md` vs `ideas/`.
4. Add template/resource tests proving both starters include the files.
5. Run starter smoke for generic and real-estate templates.

Acceptance:

- `async-research init research_ops` creates `research_ops/ideas/`
- existing `schema-check`, `readiness`, `health`, `surface update`, and
  `surface validate` still pass
- empty catalog files are valid cold-start state

## Phase 2: Catalog Parser And Read Model

Purpose: create deterministic parsing before adding validation or mutation.

Recommended new module, to be created in this phase:

```text
idea_catalog
```

Start with read-only functions:

- parse `ideas/idea_catalog.md`
- find `ideas/IDEA-*.json`
- load candidate JSON using the existing idea candidate schema
- collect duplicate IDs across table and JSON files
- summarize counts by status
- report missing optional files as warnings

Do not add CLI first. Build a small tested module first so CLI wiring stays
thin.

Acceptance:

- empty catalog returns zero ideas and no failures
- missing `ideas/` returns a cold-start warning
- malformed JSON is reported with path and reason
- duplicate IDs are detected across Markdown and JSON
- parser does not mutate files

## Phase 3: Catalog Validator

Purpose: make the catalog safe enough to rely on.

Add:

```bash
async-research idea catalog validate research_ops
```

Suggested JSON output:

```json
{
  "ok": true,
  "action": "idea_catalog_validated",
  "catalog_path": "research_ops/ideas/idea_catalog.md",
  "candidate_count": 0,
  "status_counts": {},
  "warnings": [],
  "failures": []
}
```

Validation checks:

- duplicate idea IDs
- malformed catalog table
- malformed candidate JSON
- candidate JSON failing `idea_candidate.schema.json`
- scored idea missing mission policy version
- promotable idea missing kill reason
- promotable idea missing recommended next task
- `promote` candidate below score threshold
- `promote` candidate with failed hard gates
- `promote` candidate with duplicate or near-duplicate status
- direct `experiment_plan` route from discovery
- parked or rejected idea missing reason or revisit condition
- promoted idea missing promoted task reference after it is marked `promoted`

Failure policy:

- Empty catalog: success with warnings if starter files are absent.
- Malformed state: exit `4`.
- Valid shape but unsafe promotion state: exit `2`.
- Invalid request: exit `3`.
- Clean validation: exit `0`.

Implementation steps:

1. Add parser tests.
2. Add validator tests.
3. Wire CLI as nested `idea catalog validate`.
4. Update CLI architecture tests.
5. Update CLI help tests.
6. Update README command table and exit-code table.

Acceptance:

- validator is read-only
- tests cover empty catalog, duplicate IDs, malformed candidate, missing kill
  reason, unsafe experiment route, and invalid promotion state
- CLI output follows existing JSON conventions

## Phase 4: Candidate Reference Extension

Purpose: prepare catalog ideas to connect to knowledge library and data
foundations without requiring those features to exist yet.

Extend `idea_candidate.schema.json` with optional refs:

```json
{
  "library_refs": ["LIT-0001"],
  "data_refs": ["DS-0001"],
  "accepted_output_refs": ["TASK-0007"],
  "rejected_refs": ["TASK-0003"]
}
```

Reference policy:

- `library_refs` are optional and warning-only until the library feature lands.
- `data_refs` are optional during discovery, but invalid or unaudited data refs
  block direct `experiment_plan`.
- `accepted_output_refs` should point to `accepted_outputs_index.md` task IDs.
- `rejected_refs` should point to `discovery/rejected_ideas.md` or
  `rejected_results.md` entries.

Implementation steps:

1. Extend schema with optional arrays and ID patterns.
2. Add validation warnings for missing referenced records.
3. Keep missing library files warning-only.
4. Reuse existing source audit checks for strict data gates.
5. Add tests for valid refs, missing refs, and strict data route failures.

Acceptance:

- existing candidates still validate
- refs improve validation but do not block cold-start idea capture
- direct experiment route remains blocked without approved data/source refs

## Phase 5: Catalog Maintenance Dry Run

Purpose: bridge discovery output into the durable catalog without unsafe writes.

Add a dry-run maintenance helper:

```bash
async-research idea catalog maintain research_ops --dry-run
```

Initial behavior:

- read `discovery_inbox.md`
- read existing `ideas/idea_catalog.md`
- read `ideas/IDEA-*.json`
- read `accepted_outputs_index.md`
- read `discovery/rejected_ideas.md`
- identify candidate rows that should become `IDEA-*.json`
- identify duplicates and near-duplicates
- recommend `promote`, `park`, `reject`, or `needs_human`
- print proposed file changes without writing

Do not solve semantic dedupe with clever text similarity in v1. Start with
stable deterministic checks:

- same idea ID
- same normalized title
- same accepted/rejected task reference
- same cluster ID
- explicit duplicate marker

Acceptance:

- dry run explains exactly what it would write
- no files are changed
- duplicate recommendations are conservative
- maintenance never edits `queue.md`

## Phase 6: Catalog Maintenance Write Mode

Purpose: make catalog maintenance useful after dry-run behavior is trusted.

Add:

```bash
async-research idea catalog maintain research_ops --write
```

Write behavior:

- append new durable rows to `ideas/idea_catalog.md`
- create `ideas/IDEA-*.json` only when the candidate object is complete enough
- update `ideas/prioritization.md` generated sections
- write atomically
- preserve manual notes where possible

Safety rules:

- refuse to overwrite an existing `IDEA-*.json` unless `--update-existing` is
  explicitly provided
- do not delete ideas automatically
- parked and rejected ideas require a reason
- promotions remain recommendations, not queue mutations

Acceptance:

- write mode is idempotent
- rerunning maintenance does not duplicate rows
- manual notes outside generated sections are preserved
- all written candidates pass `idea catalog validate`

## Phase 7: Promotion Dry Run

Purpose: help the planner turn one catalog idea into one bounded task proposal
without bypassing governance.

Add:

```bash
async-research idea promote research_ops IDEA-0001 --dry-run
```

The command should produce:

- proposed task ID or slug
- task type
- title
- objective
- scope
- required sources and data refs
- allowed paths
- max minutes and max turns
- kill reason
- validation commands to run after task creation
- blockers that must be resolved first

Rules:

- dry-run only in the first implementation
- no task folder creation yet
- no `queue.md` edits yet
- no `experiment_plan` route unless existing gates pass
- if evidence is thin, recommend `literature_extract`
- if data is plausible but unaudited, recommend `data_readiness`

Acceptance:

- one input idea produces at most one next task proposal
- invalid or parked idea cannot be promoted
- duplicate or near-duplicate idea cannot be promoted without human override
- output is useful enough for a human or planner to create the task manually

## Phase 8: Promotion Write Mode

Purpose: optional, only after dry-run promotion is boring.

Add:

```bash
async-research idea promote research_ops IDEA-0001 --write
```

Write behavior:

- create one task folder
- write `task.md`
- write `status.json`
- append one row to `queue.md`
- update the idea record with `promoted_task_id`
- run transition/schema validation
- rollback if validation fails

This phase is intentionally later because it mutates execution state.

Acceptance:

- task creation is transactional
- queue update is not duplicated on retry
- validation runs after writes
- rollback leaves no partial task folder
- human override is required for high-cost or high-risk promotion

## Phase 9: Planner And Surface Integration

Purpose: make the catalog part of the operating loop.

Update:

- planner docs and prompts
- `idea_discovery_workflow.md`
- `task_contracts.md`
- `weekly_digest.md` generation
- health/readiness warnings where useful

Planner rules:

- promote few ideas
- prefer cheap killable next tasks
- create `literature_extract` if evidence is thin
- create `data_readiness` if data path is plausible but unaudited
- avoid direct experiment planning unless gates pass
- record human priority decisions

Surface additions:

- catalog count by status
- top recommended promotions
- parked/rejected counts
- ideas blocked by data or evidence gaps
- stale candidate warnings

Acceptance:

- weekly digest summarizes idea throughput and blockers
- health/readiness warns on malformed catalog state
- planner docs explain how to move from discovery inbox to catalog to queue

## Phase 10: Dashboard Read-Only View

Purpose: make the idea portfolio visible without opening Markdown files.

Add dashboard views after the catalog state model is stable.

Show:

- candidate ideas
- parked ideas
- promoted ideas
- rejected ideas
- top blockers
- score dimensions
- next recommended tasks
- idea-to-task links

Acceptance:

- operator can decide what to inspect or promote in a few minutes
- missing score artifacts render as `unavailable`
- dashboard does not mutate idea files in the first version

## AI Implementation Pattern

Use narrow AI work packets. Each packet should specify:

- owned files
- files to avoid
- expected command output
- exact tests to run
- whether writes are allowed

Recommended packet sequence:

1. Template worker:
   - owns starter template files and README updates
   - runs starter smoke and doc reference tests

2. Parser worker:
   - owns `scripts/idea_catalog.py` and parser tests
   - does not touch CLI

3. Validator worker:
   - owns validation logic and validator tests
   - reuses parser module

4. CLI worker:
   - owns CLI wiring, help tests, architecture tests, README command table
   - does not change validation semantics

5. Schema worker:
   - owns optional candidate refs schema and tests
   - avoids changing scoring behavior unless required

6. Maintenance worker:
   - owns dry-run maintenance command and tests
   - starts read-only

7. Promotion worker:
   - owns dry-run promotion command and tests
   - does not implement write mode until dry run is stable

8. Surface worker:
   - owns weekly digest and health/readiness integrations
   - consumes validator outputs

9. Dashboard worker:
   - owns read-only UI views after backend state is stable

Do not assign two workers to the same CLI or schema files in parallel unless the
write scopes are explicitly separated.

## Test Strategy

Minimum checks per implementation slice:

```bash
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest tests.test_cli_architecture tests.test_cli_help
.venv/bin/python -m unittest tests.test_packaged_resources
```

Feature-specific tests to add:

- `tests.test_idea_catalog_templates`
- `tests.test_idea_catalog_parser`
- `tests.test_idea_catalog_validation`
- `tests.test_idea_catalog_cli`
- `tests.test_idea_catalog_maintenance`
- `tests.test_idea_promotion_dry_run`

Regression scenarios:

- empty starter catalog
- missing `ideas/` directory
- malformed `idea_catalog.md`
- malformed `IDEA-*.json`
- duplicate idea ID
- scored candidate missing mission policy version
- promoted idea below threshold
- promoted idea missing kill reason
- direct experiment route
- parked idea missing revisit condition
- rejected idea missing rejected log entry
- candidate with missing accepted output ref
- candidate with missing data ref
- near-duplicate candidate marked for promotion
- maintenance dry-run idempotency
- promotion dry-run refuses unsafe candidates

Package-level checks before merging the feature:

```bash
.venv/bin/python -m unittest discover tests
.venv/bin/async-research acceptance-suite
.venv/bin/async-research benchmark
.venv/bin/async-research starter-smoke /tmp/async-research-starter-generic --force
.venv/bin/async-research starter-smoke /tmp/async-research-starter-real-estate --template real-estate --force
.venv/bin/python -m compileall src tests
```

## MVP Definition

The MVP is complete when:

- new workspaces include `research_ops/ideas/`
- empty idea catalogs are valid
- structured candidates can live under `research_ops/ideas/`
- `async-research idea catalog validate research_ops` exists
- unsafe promotion states fail closed
- discovery docs explain how inbox candidates move into the catalog
- tests cover malformed, duplicate, parked, rejected, and unsafe promotion
  states

## Full Feature Definition

The full feature is complete when:

- discovery can feed durable catalog maintenance
- catalog maintenance can run dry-run and write mode safely
- one idea can produce one bounded promotion proposal
- optional write-mode promotion is transactional
- weekly digest and health surfaces expose idea backlog quality
- dashboard has read-only portfolio views
- library and data foundation refs are supported without blocking cold starts

## Open Questions

- Should `idea_catalog.md` eventually replace `discovery_inbox.md`, or should
  the inbox remain a short-lived buffer forever?
- Should idea status values be aligned with task status values, or use a
  separate idea-specific lifecycle?
- Should human priority override scoring, or only adjust a separate priority
  field?
- Should novelty be scored by an agent, a human, or a library-aware reviewer?
- Should promotion write mode exist in alpha, or should the planner keep
  creating task folders manually until the catalog has real usage history?

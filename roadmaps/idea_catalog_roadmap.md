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

## Product Decisions

Keep three separate layers:

```text
discovery_inbox.md = what did we just find?
ideas/IDEA-*.json = canonical durable idea records
ideas/idea_catalog.md = generated portfolio projection
queue.md = what are we actually working on next?
```

The catalog is not a second execution queue. It is a portfolio and planning
surface. Only the planner, or a human-approved helper, may turn a catalog idea
into a bounded task.

### Source Of Truth

`ideas/IDEA-*.json` files are canonical.

`ideas/idea_catalog.md` is a generated projection from canonical JSON records.
It must not contain unique state that cannot be rebuilt from JSON.

`ideas/prioritization.md` is a generated planning summary with preserved
free-form notes outside explicit generated blocks.

If Markdown and JSON disagree, validation treats the JSON as authoritative and
reports the Markdown as stale projection state. Maintenance may regenerate the
Markdown projection from JSON, but it must not silently rewrite JSON to match
Markdown.

One `idea_catalog.md` row and one `ideas/IDEA-*.json` file with the same
`idea_id` is the expected healthy shape. Duplicate detection applies to multiple
JSON files with the same ID, multiple Markdown projection rows with the same ID,
or filename/JSON ID mismatches.

Canonical ownership matrix:

| Surface | Owns | Must not own |
| --- | --- | --- |
| `discovery_inbox.md` | short-lived discovery rows and capture markers | durable portfolio status, execution state |
| `research_ops/discovery/IDEA-*.json` | pre-catalog discovery artifacts and scoring inputs | canonical catalog state after capture |
| `ideas/IDEA-*.json` | canonical idea fields, score, refs, status, decision history, promotion refs | task execution state |
| `ideas/idea_catalog.md` | generated human-readable projection plus free-form notes outside generated blocks | canonical score/status/ref fields |
| `ideas/prioritization.md` | generated planning summary plus free-form notes outside generated blocks | canonical priority, score, or status |
| `inbox.md` | human/planner pre-task intake | canonical idea portfolio state |
| `queue.md` | execution queue rows | discovery or catalog state |

### Status Model

Stored idea statuses are separate from task statuses:

```text
candidate
promote
park
reject
promoted
needs_human
```

Derived display labels are computed at render time:

```text
raw_inbox = discovery inbox row not captured into canonical JSON
raw = canonical candidate without a score object
scored = candidate with score object
blocked = candidate with failed hard gates or missing required refs
```

Do not write derived labels into `IDEA-*.json`. If the Markdown table displays
`raw_inbox`, `raw`, `scored`, or `blocked`, those labels are rebuilt from
canonical JSON or from eligible inbox rows. In v1, a canonical catalog record
should be a structured idea candidate, not a loose raw note.

Status transition rules:

- `candidate -> promote` requires score, kill reason, next task, and passing
  hard gates.
- `candidate -> park` requires reason and revisit condition.
- `candidate -> reject` requires reason and rejected log entry.
- `promote -> promoted` requires `promoted_task_id` integrity.
- any status -> `needs_human` requires a human gate reason.
- `needs_human -> candidate|promote|park|reject` requires a recorded decision.

Human priority is a separate field. It may influence ordering, but it must not
overwrite the mission-weighted score.

Novelty is agent-proposed and human-confirmable. The scoring record should show
the proposed novelty score and, if edited, the human decision that changed it.

### Command Safety

Every mutating idea-catalog command must require explicit `--write`.

Without `--write`, commands are read-only or dry-run by default. Dry-run output
must describe the exact files and records that would change.

Single-writer operation is assumed for v1. Mutating commands should refuse to
run when a catalog lock exists. Locking can be simple at first, but the expected
behavior must be documented and tested so concurrent writes do not corrupt
state.

Promotion write mode is deferred to v2. In v1, promotion remains dry-run only.

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
- promotion, parking, rejection, and human-decision history

The catalog should prioritize useful, killable ideas over interesting but vague
ones. A high-scoring idea should usually become a `literature_extract`,
`data_readiness`, `hypothesis_card`, or `experiment_plan` task only after
required gates pass. Direct promotion from discovery into expensive experiments
remains blocked.

## Delivery Strategy

Build this as a sequence of small, deterministic slices. Because AI workers can
iterate quickly, do not optimize the plan around calendar duration. Optimize it
around state safety and clean sequencing:

1. Lock state ownership and invariants.
2. Add starter files, generated-block boundaries, and migration safety.
3. Extend the candidate schema before building new readers.
4. Parse and validate canonical JSON plus generated projections.
5. Wire read-only CLI inspection.
6. Add read-only surfaces.
7. Add catalog maintenance dry-run and then write mode.
8. Add promotion dry-run.
9. Integrate planner behavior.
10. Add dashboard views.

Each slice should leave the package usable. Each mutation-capable slice should
ship after its read-only or dry-run version.

Delivery boundary:

- MVP: Phases 0 through 4. This is starter state, schema/read model, validation,
  and read-only CLI inspection.
- V1 post-MVP: Phases 5 through 10. This adds read-only surfaces, explicit
  capture, maintenance write mode, promotion dry-run, planner guidance, and
  dashboard read views.
- V2: promotion write mode that mutates `inbox.md`, `queue.md`, or task folders.

## Progress

Last updated: 2026-05-07

| Phase | Step | Status | Evidence / Notes |
| ---: | --- | --- | --- |
| 0 | Lock product invariants | Complete | Three-layer ownership, source-of-truth, command safety, and v1/v2 promotion boundaries are captured in this roadmap and `idea_catalog_contract.md`. |
| 1 | Starter files, contracts, and migration safety | Complete | Shipped in `41607c5` with starter `ideas/` files, generated-block templates, docs, and `async-research idea catalog init`. |
| 1a | Review follow-up hardening | Complete | Shipped in `fa27c32` with dry-run lock warnings, bare dry-run tests, malformed bootstrap tests, and exact marker docs. |
| 2 | Candidate schema and lifecycle extension | Complete | Extends `idea_candidate.schema.json` with catalog lifecycle fields, new stored statuses, reference patterns, and schema regression tests. |
| 3 | Catalog parser and read model | Complete | Adds read-only `async_research_workflow.idea_catalog` parser for canonical JSON, generated projections, duplicate IDs, stale projections, counts, and cold-start warnings. |
| 4 | Catalog validator and read-only CLI | Complete | Completes the MVP with read-only `idea catalog validate`, `list`, and `show`, schema/lifecycle/reference validation, and CLI/README coverage. |
| 5 | Read-only surface integration | Complete | Adds read-only catalog throughput, blockers, stale projection warnings, and malformed-state warnings to weekly digest, daily status, health, and readiness surfaces without mutating canonical JSON. |
| 6 | Explicit capture and maintenance dry run | Complete | Adds dry-run `idea capture` and `idea catalog maintain` proposals with deterministic duplicate checks, explicit inbox markers, no JSON writes, and no queue/task mutation. |
| 7 | Catalog maintenance write mode | Complete | Adds lock-protected capture and maintenance writes, explicit park/reject commands, atomic JSON/projection writes, stale-lock recovery, idempotency coverage, and note-preserving generated block regeneration. |
| 8 | Promotion dry run | Complete | Adds read-only `idea promote` proposals with task-type routing, blocker reporting, duplicate override gating, experiment-plan gate checks, and no `queue.md` or task-folder mutation. |
| 9 | Planner promotion behavior | Complete | Teaches planner prompts and core docs to move from discovery inbox to durable catalog to dry-run promotion proposal to planner-created task and queue row, preserving v1 safety boundaries. |
| 10 | Dashboard read-only view | Complete | Adds read-only `idea catalog dashboard` portfolio views for active, parked, promoted, and rejected ideas, top blockers, score dimensions with `unavailable` for missing score artifacts, next tasks, and idea-to-task links. |
| V2 | Promotion write mode | In progress | V2.1 contract/preflight, V2.2 proposal write mode, and V2.3 recovery hardening shipped; task creation write mode remains deferred until transactional helpers exist. |

## Framework Integration

Existing artifacts:

```text
research_ops/discovery_inbox.md
research_ops/discovery/clusters.md
research_ops/discovery/rejected_ideas.md
research_ops/rejected_results.md
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

`discovery_inbox.md` should remain a short-lived buffer forever. It is useful
because discovery can stay cheap and noisy while the catalog stays durable and
governed.

Current workflow coexistence:

- `research_ops/discovery/IDEA-*.json` remains valid as discovery-stage output
  and as input to `async-research idea score` and `async-research idea validate`.
- Capturing a discovery artifact into the catalog copies or derives a canonical
  `research_ops/ideas/IDEA-*.json`; it does not move or delete the discovery
  artifact.
- Canonical catalog records should keep `source_discovery_path` when they were
  derived from `research_ops/discovery/IDEA-*.json`.
- `inbox.md` remains the human/planner intake surface for task requests and
  can receive future v2 promotion proposals.
- `queue.md` remains the execution queue and is never edited by v1 catalog
  maintenance, capture, validation, or promotion dry-run commands.

## Phase 0: Lock Product Invariants

Purpose: prevent the feature from becoming an unreviewed task generator.

Decisions to record in docs before implementation:

- `discovery_inbox.md` remains a short-lived buffer.
- `IDEA-*.json` files are canonical.
- `idea_catalog.md` and `prioritization.md` are projections.
- `queue.md` remains the execution queue.
- Catalog validation is read-only.
- Promotion starts and remains dry-run only in v1.
- Empty catalog files are valid during cold start.
- Existing workspaces without `ideas/` are valid partial-bootstrap state.
- Direct experiment promotion remains blocked unless existing source and data
  gates pass.
- Single-writer operation is assumed for mutating catalog commands in v1.

Acceptance:

- roadmap and docs state the three-layer model clearly
- no implementation step allows catalog maintenance to edit `queue.md`
- no worker can create a task folder as part of discovery or catalog validation
- promotion write mode is explicitly labeled v2

## Phase 1: Starter Files, Contracts, And Migration Safety

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

`idea_catalog.md` contract:

```markdown
# Idea Catalog

<!-- IDEA-CATALOG: AUTO-MAINTAINED - DO NOT EDIT INSIDE THIS BLOCK -->
| idea_id | status | title | weighted_score | next_task | blockers | promoted_task_id | updated_at |
| --- | --- | --- | ---: | --- | --- | --- | --- |
<!-- /IDEA-CATALOG -->

## Notes

Free-form notes. Tooling must not edit this section.
```

`prioritization.md` contract:

```markdown
# Idea Prioritization

<!-- IDEA-PRIORITIZATION: RECOMMENDED-PROMOTIONS AUTO-MAINTAINED -->
<!-- /IDEA-PRIORITIZATION: RECOMMENDED-PROMOTIONS -->

<!-- IDEA-PRIORITIZATION: PARKED AUTO-MAINTAINED -->
<!-- /IDEA-PRIORITIZATION: PARKED -->

<!-- IDEA-PRIORITIZATION: REJECTED AUTO-MAINTAINED -->
<!-- /IDEA-PRIORITIZATION: REJECTED -->

<!-- IDEA-PRIORITIZATION: BLOCKERS AUTO-MAINTAINED -->
<!-- /IDEA-PRIORITIZATION: BLOCKERS -->

## Notes

Free-form notes. Tooling must not edit this section.
```

Migration safety:

- Existing workspaces may not have `research_ops/ideas/`.
- `async-research idea catalog init research_ops --dry-run` should report the
  files it would add.
- `async-research idea catalog init research_ops --write` should add only
  missing catalog starter files.
- It must not overwrite existing files.
- Existing `async-research init` behavior should remain safe and should not be
  reused as an overwrite mechanism for live workspaces.

Implementation steps:

1. Add the files to `generic_research_ops_starter`.
2. Add the files to the real-estate worked example starter.
3. Update starter READMEs to explain `discovery_inbox.md` vs `ideas/`.
4. Add the idempotent catalog init helper.
5. Add template/resource tests proving both starters include the files.
6. Add migration tests proving missing files are added without overwriting
   existing notes.
7. Run starter smoke for generic and real-estate templates.

Acceptance:

- `async-research init research_ops` creates `research_ops/ideas/`
- existing workspaces can safely add missing catalog files
- existing `schema-check`, `readiness`, `health`, `surface update`, and
  `surface validate` still pass
- empty catalog files are valid cold-start state
- generated blocks are explicit and manual notes are outside them

## Phase 2: Candidate Schema And Lifecycle Extension

Purpose: land schema and lifecycle fields before parser and validator semantics
depend on them.

Extend `idea_candidate.schema.json` with optional and required fields as needed:

```json
{
  "created_at": "YYYY-MM-DDTHH:MM:SSZ",
  "updated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "human_priority": 2,
  "promoted_task_id": "TASK-0001",
  "human_gate_reason": "needs owner decision on geography",
  "status_reason": "score and hard gates passed",
  "source_discovery_path": "research_ops/discovery/IDEA-0001.json",
  "library_refs": ["LIT-0001"],
  "data_refs": ["DS-0001"],
  "accepted_output_refs": ["TASK-0007"],
  "rejected_idea_refs": ["IDEA-0003"],
  "rejected_result_refs": ["TASK-0003"],
  "decision_history": [
    {
      "at": "YYYY-MM-DDTHH:MM:SSZ",
      "from_status": "candidate",
      "to_status": "promote",
      "reason": "score and hard gates passed",
      "actor": "planner"
    }
  ]
}
```

Schema decisions:

- Add stored statuses `promoted` and `needs_human`.
- Keep `schema_version`.
- Require `id` to match filename for candidates under `ideas/`.
- Keep existing candidates valid where possible.
- `decision_history` is append-only once mutating commands exist.
- `status_reason` records the latest status rationale for list/show output.
- `updated_at` changes only when canonical JSON content changes.
- `created_at` never changes after first write.
- `source_discovery_path` is optional and records provenance when a catalog
  record was captured from a discovery-stage JSON artifact.

Reference policy:

- `library_refs` are optional and warning-only until the library feature lands.
- `data_refs` are optional during discovery, but invalid or unaudited data refs
  block direct `experiment_plan`.
- `accepted_output_refs` should point to `accepted_outputs_index.md` task IDs.
- `rejected_idea_refs` should point to rejected or parked idea IDs in
  `discovery/rejected_ideas.md`.
- `rejected_result_refs` should point to rejected task IDs in
  `rejected_results.md`.
- `cluster_id`, when present, should point to `discovery/clusters.md` or be
  declared as a new cluster during maintenance.

Acceptance:

- existing candidates still validate or fail with clear migration guidance
- optional refs improve validation but do not block cold-start idea capture
- direct experiment route remains blocked without approved data/source refs
- tests cover old-schema candidates, new refs, missing refs, and new statuses

## Phase 3: Catalog Parser And Read Model

Purpose: create deterministic parsing before adding validation or mutation.

Recommended new module, to be created in this phase:

```text
idea_catalog
```

Start with read-only functions:

- read canonical `ideas/IDEA-*.json`
- parse generated blocks in `ideas/idea_catalog.md`
- parse generated blocks in `ideas/prioritization.md`
- collect duplicate IDs across JSON files
- detect orphaned Markdown rows with no JSON record
- detect orphaned JSON records missing from the Markdown projection
- summarize counts by stored status and derived display label
- validate filename and ID agreement
- report missing optional files as warnings

Do not add mutation first. Build a small tested read model so CLI wiring stays
thin.

Acceptance:

- empty catalog returns zero ideas and no failures
- missing `ideas/` returns a cold-start warning
- malformed JSON is reported with path and reason
- duplicate IDs are detected across JSON records
- stale Markdown projection is reported as warning, not used as source of truth
- parser does not mutate files

## Phase 4: Catalog Validator And Read-Only CLI

Purpose: make the catalog safe enough to rely on and inspect without opening
Markdown files.

Add:

```bash
async-research idea catalog validate research_ops
async-research idea catalog list research_ops [--status STATUS]
async-research idea catalog show research_ops IDEA-0001
```

Suggested validation JSON output:

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
- filename and `id` mismatch
- malformed generated table blocks
- orphaned table row with no JSON record
- orphaned JSON record missing from generated table
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
- `needs_human` idea missing human gate reason
- `promoted` idea missing `promoted_task_id`
- stale `promoted_task_id` not found in `queue.md`, active task folders, or
  `accepted_outputs_index.md`
- missing referenced accepted output, rejected idea, rejected result, library
  source, data source, or cluster

Failure policy:

- Empty catalog: success with warnings if starter files are absent.
- Malformed state: exit `4`.
- Valid shape but unsafe promotion state: exit `2`.
- Invalid request: exit `3`.
- Clean validation: exit `0`.

Score threshold policy:

- The validator should read thresholds from the scored candidate and active
  mission policy metadata already written by `async-research idea score`.
- It must not hardcode promotion thresholds.
- If threshold fields are missing on a scored idea, validation fails for
  promotable statuses and warns for non-promotable statuses.

Implementation steps:

1. Add parser tests.
2. Add validator tests.
3. Wire CLI as nested `idea catalog validate`, `list`, and `show`.
4. Update CLI architecture tests.
5. Update CLI help tests.
6. Update README command table and exit-code table.

Acceptance:

- validator is read-only
- list and show commands are read-only
- tests cover empty catalog, duplicate IDs, malformed candidate, missing kill
  reason, unsafe experiment route, invalid promotion state, stale projection,
  and stale promoted task refs
- CLI output follows existing JSON conventions

## Phase 5: Read-Only Surface Integration

Purpose: expose catalog health early without waiting for promotion behavior.

Update:

- `weekly_digest.md` generation
- health/readiness warnings where useful
- operator docs that explain the three-layer model

Surface additions:

- catalog count by status
- derived raw/scored/blocked counts
- top recommended promotions from canonical JSON
- parked/rejected counts
- ideas blocked by data or evidence gaps
- stale projection warnings

Acceptance:

- weekly digest summarizes idea throughput and blockers
- health/readiness warn on malformed catalog state
- no surface update mutates canonical idea JSON
- docs explain how to move from discovery inbox to catalog to queue

## Phase 6: Explicit Capture And Maintenance Dry Run

Purpose: bridge discovery output into the durable catalog without unsafe writes
or implicit batch ingestion.

Add explicit capture:

```bash
async-research idea capture research_ops --from-inbox IDEA-0001 --dry-run
async-research idea capture research_ops --from-inbox row-7 --id IDEA-0007 --dry-run
async-research idea capture research_ops --title "..." --dry-run
```

Add maintenance dry-run:

```bash
async-research idea catalog maintain research_ops --dry-run
```

Discovery to catalog ingestion rule:

- Ingestion is explicit, not automatic.
- A discovery inbox row is eligible only when it has an explicit catalog marker
  such as `catalog: candidate`, or when the user calls `idea capture` with the
  row ID.
- A write-mode capture requires a valid `IDEA-0000` style ID. The ID may come
  from the inbox row or from an explicit `--id IDEA-0007` argument. If neither
  exists, dry-run returns a `needs_human` proposal and write mode refuses.
- A write-mode capture creates canonical JSON only when the candidate can pass
  `idea_candidate.schema.json` and `async-research idea validate` after any
  required scoring step. Incomplete rows can produce a dry-run draft, but they
  must not become canonical JSON.
- The row must include, or link to, the fields required by the current idea
  candidate schema: title, question, why it matters, required data, minimum
  viable test, main risks, kill reason, score, and recommended next task.
- Rows without enough information produce a `needs_human` capture proposal. A
  durable `needs_human` catalog record is allowed only when the candidate still
  satisfies the canonical schema and records `human_gate_reason`.
- Row presence alone never creates a catalog record.

Deterministic normalization and duplicate checks:

- Normalize titles by lowercasing, trimming leading/trailing whitespace,
  collapsing internal whitespace, and removing punctuation except letters,
  numbers, and spaces.
- Duplicate tie-break order is exact ID, explicit duplicate marker, normalized
  title, accepted/rejected refs, then cluster ID.
- If several existing ideas match at the same strongest tier, dry-run returns
  `needs_human` and write mode refuses.
- If one existing idea matches, capture should propose an update or duplicate
  route, not create a new canonical ID.
- If no existing idea matches and the candidate passes validation, capture may
  create a new canonical JSON record in write mode.

Initial maintenance behavior:

- read `discovery_inbox.md`
- read canonical `ideas/IDEA-*.json`
- read `accepted_outputs_index.md`
- read `discovery/rejected_ideas.md`
- identify explicitly marked inbox rows that can be captured
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
- row presence alone does not create candidate files
- duplicate recommendations are conservative
- maintenance never edits `queue.md`
- `idea capture` can propose one complete `IDEA-*.json` record

## Phase 7: Catalog Maintenance Write Mode

Purpose: make catalog maintenance useful after dry-run behavior is trusted.

Add:

```bash
async-research idea catalog maintain research_ops --write
async-research idea capture research_ops --from-inbox IDEA-0001 --write
async-research idea park research_ops IDEA-0001 --reason "..." --revisit "..." --write
async-research idea reject research_ops IDEA-0001 --reason "..." --write
```

Write behavior:

- acquire `research_ops/ideas/LOCK/` by atomic directory creation before reading
  files for a write transaction
- write `research_ops/ideas/LOCK/owner.json` with command, pid, started_at, and
  lock_expires_at
- write canonical `ideas/IDEA-*.json` files first
- regenerate `ideas/idea_catalog.md` from canonical JSON in memory
- regenerate generated blocks in `ideas/prioritization.md` in memory
- preserve all content outside generated blocks byte-for-byte
- write files only after validation passes
- use temp-file-plus-atomic-rename for JSON and Markdown writes
- release `research_ops/ideas/LOCK/` only after all writes and post-write
  validation complete

Safety rules:

- stale locks may be renamed to `LOCK.stale.<timestamp>` only after
  `lock_expires_at` passes
- default lock TTL should be short and explicit, such as 30 minutes
- refuse to overwrite an existing `IDEA-*.json` unless `--update-existing` is
  explicitly provided
- do not delete ideas automatically
- parked and rejected ideas require a reason
- parked ideas require a revisit condition
- status changes append to `decision_history`
- `updated_at` changes only when canonical content changes
- promotions remain recommendations, not queue mutations

Transaction order:

1. Acquire the catalog lock.
2. Read canonical JSON and generated Markdown projections.
3. Build proposed JSON and Markdown outputs in memory.
4. Validate proposed JSON records.
5. Validate generated Markdown blocks.
6. Write temp files.
7. Atomically rename temp files into place.
8. Re-read and run `idea catalog validate`.
9. Release the lock.

Crash recovery:

- leftover temp files are ignored by readers and may be cleaned by maintenance
- a fresh lock blocks writers
- a stale lock is surfaced by validation and may be renamed by a write command
  before retrying

Dry-run and write-mode roundtrip:

- dry-run should report the same logical changes that write mode applies
- after write mode, re-reading state should match the dry-run proposal except
  for timestamps and file paths explicitly documented as runtime-generated

Acceptance:

- write mode is idempotent
- rerunning maintenance with no input changes produces zero diffs
- manual notes outside generated blocks are preserved byte-for-byte
- all written candidates pass `idea catalog validate`
- concurrent write attempts refuse cleanly or wait according to documented lock
  behavior

## Phase 8: Promotion Dry Run

Purpose: help the planner turn one catalog idea into one bounded task proposal
without bypassing governance.

Add:

```bash
async-research idea promote research_ops IDEA-0001 --dry-run
```

Optional override:

```bash
async-research idea promote research_ops IDEA-0001 --task-type data_readiness --dry-run
```

Allowed task types:

```text
literature_extract
data_readiness
hypothesis_card
experiment_plan
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

- dry-run only in v1
- no task folder creation in v1
- no `queue.md` edits in v1
- no `experiment_plan` route unless existing gates pass
- if evidence is thin, recommend `literature_extract`
- if data is plausible but unaudited, recommend `data_readiness`
- duplicate or near-duplicate ideas require human override before proposal
- task type override is explicit and validated

Acceptance:

- one input idea produces at most one next task proposal
- invalid, parked, rejected, or blocked idea cannot be promoted
- duplicate or near-duplicate idea cannot be promoted without human override
- output is useful enough for a human or planner to create the task manually

## Phase 9: Planner Promotion Behavior

Purpose: teach the planner how to use dry-run promotion proposals.

Update:

- planner docs and prompts
- `idea_discovery_workflow.md`
- `task_contracts.md`

Planner rules:

- promote few ideas
- prefer cheap killable next tasks
- create `literature_extract` if evidence is thin
- create `data_readiness` if data path is plausible but unaudited
- avoid direct experiment planning unless gates pass
- record human priority decisions
- keep task creation in the planner layer, not catalog maintenance

Acceptance:

- planner docs explain how to move from discovery inbox to catalog to queue
- top ideas become bounded queue items only through planner-controlled task
  creation
- planner does not promote duplicate or blocked ideas without a reason

## Phase 10: Dashboard Read-Only View

Purpose: make the idea portfolio visible without opening Markdown files.

Add dashboard views after the catalog state model is stable. The dashboard
should read from the catalog read model or validator output, not parse files
through a separate path.

Command:

```bash
async-research idea catalog dashboard research_ops
```

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

## V2: Promotion Write Mode

Promotion write mode is intentionally outside v1. It is the only catalog feature
that mutates execution state, so it should wait until dry-run promotion has real
usage history.

Potential command:

```bash
async-research idea promote research_ops IDEA-0001 --write
```

Implementation steps:

| Step | Slice | Status | Goal | Acceptance / Tests |
| ---: | --- | --- | --- | --- |
| V2.1 | Contract and preflight design | Complete | Document exactly what `idea promote --write` may mutate, lock ordering, task ID allocation, idempotency keys, rollback boundaries, and human override rules. | Roadmap and `idea_catalog_contract.md` define proposal-write and task-write boundaries; tests describe duplicate retry, stale lock, changed candidate, and partial-output failure cases before implementation. |
| V2.2 | Proposal write mode | Complete | Add the first safe `--write` slice: write one planner-facing promotion proposal reference without creating task folders or editing `queue.md`. | `idea promote --write` appends one proposal through a transactional helper, updates the canonical idea with a proposal reference, refuses duplicate proposal writes, preserves generated projection notes, and passes catalog validation after writes. |
| V2.3 | Proposal write recovery tests | Complete | Harden proposal write mode before any queue mutation exists. | Tests cover lock present, stale lock rotation, duplicate retry, invalid candidate, partial inbox recovery, post-write validation failure, and no mutation of `queue.md` or `tasks/`. |
| V2.4 | Task transaction helper design | Planned | Build shared helpers for staged task-folder writes, queue append/remove, final validation, and rollback. | Unit tests prove staged files are removed if queue append fails, queue rows are not duplicated on retry, and rollback leaves no partial task folder. |
| V2.5 | Task ID and idempotency rules | Planned | Allocate deterministic or reserved task IDs safely for one idea-to-one-task promotion. | Tests cover existing task folder, existing queue row, existing `promoted_task_id`, stale `promoted_task_id`, and re-running the same write command. |
| V2.6 | Task creation write mode | Planned | Extend `idea promote --write` to create one task folder, `task.md`, `status.json`, queue row, and canonical `promoted_task_id` update in one transaction. | Write succeeds only after dry-run promotion gates pass; schema/transition validation passes; `queue.md`, task folder, and idea JSON are mutually consistent. |
| V2.7 | Failure and rollback hardening | Planned | Make all task-write failure paths observable and fail closed. | Tests cover validation failure after staged task files, queue append failure, idea JSON write failure, interrupted retry with existing artifacts, and rollback audit messages. |
| V2.8 | CLI, docs, and operator workflow | Planned | Update CLI help, README, planner docs, dashboard expectations, and review prompts for the new write behavior. | Help and docs distinguish proposal write mode from task creation write mode; dashboard displays `promoted_task_id` links after a successful write; exit-code contract is updated. |
| V2.9 | End-to-end acceptance | Planned | Prove one real catalog idea can be promoted safely through write mode. | Focused tests, full unit suite, starter smokes, acceptance suite, benchmark, and a temp-workspace end-to-end promotion write all pass. |

V2 should ship in two sub-slices:

1. Proposal write mode writes one planner-facing proposal to `inbox.md` and
   updates the idea with the proposal reference. It does not create task folders
   or edit `queue.md`.
2. Task creation write mode, if still needed after real usage, creates one task
   folder and one `queue.md` row through planner-approved transactional helpers.

Required task-creation behavior before the second sub-slice is allowed:

- create one task folder
- write `task.md`
- write `status.json`
- append one row to `queue.md`
- update the idea record with `promoted_task_id`
- run transition/schema validation
- rollback if validation fails

Atomicity requirements:

- proposal write mode appends to `inbox.md` through a transactional helper and
  then updates the canonical idea record
- stage all task files before touching `queue.md`
- validate staged task files before finalizing
- append to `queue.md` only through a transactional helper
- if queue append fails, remove staged task files
- if final validation fails, rollback task files and queue row together

Acceptance before v2 ships:

- task creation is transactional
- queue update is not duplicated on retry
- validation runs after writes
- rollback leaves no partial task folder
- human override is required for high-cost or high-risk promotion

## AI Implementation Pattern

Use narrow AI work packets. Each packet should specify:

- owned files
- files to avoid
- expected command output
- exact tests to run
- whether writes are allowed

Recommended packet sequence:

1. Template and migration worker:
   - owns starter template files, generated block contracts, and README updates
   - runs starter smoke and doc reference tests

2. Schema worker:
   - owns candidate status/ref/history schema updates and tests
   - avoids changing scoring behavior unless required

3. Parser worker:
   - owns the planned idea catalog read model and parser tests
   - does not touch CLI

4. Validator worker:
   - owns validation logic and validator tests
   - reuses parser module

5. CLI read worker:
   - owns CLI wiring for `validate`, `list`, and `show`
   - owns help tests, architecture tests, and README command table
   - does not change validation semantics

6. Surface worker:
   - owns weekly digest and health/readiness read-only integrations
   - consumes validator outputs

7. Capture and maintenance dry-run worker:
   - owns explicit capture and maintenance dry-run commands and tests
   - starts read-only

8. Maintenance write worker:
   - owns write mode, locks, atomic writes, generated block preservation, and
     idempotency tests
   - does not touch `queue.md`

9. Promotion dry-run worker:
   - owns dry-run promotion command and tests
   - does not implement write mode

10. Planner integration worker:
    - owns planner docs and task contract updates

11. Dashboard worker:
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
- `tests.test_idea_catalog_migration`
- `tests.test_idea_catalog_schema`
- `tests.test_idea_catalog_parser`
- `tests.test_idea_catalog_validation`
- `tests.test_idea_catalog_cli`
- `tests.test_idea_catalog_capture`
- `tests.test_idea_catalog_maintenance`
- `tests.test_idea_promotion_dry_run`

Regression scenarios:

- empty starter catalog
- missing `ideas/` directory
- partial files: Markdown exists without JSON records
- partial files: JSON records exist without Markdown projection
- expected pairing: one Markdown row plus one JSON record for the same ID
- malformed `idea_catalog.md`
- malformed `IDEA-*.json`
- filename and ID mismatch
- duplicate idea ID
- discovery-stage `research_ops/discovery/IDEA-*.json` copied into canonical
  `research_ops/ideas/IDEA-*.json`
- old-schema candidate after schema extension
- scored candidate missing mission policy version
- `promote` candidate below threshold
- promoted idea missing kill reason
- direct experiment route
- parked idea missing revisit condition
- rejected idea missing rejected log entry
- `needs_human` idea missing human gate reason
- stale `promoted_task_id`
- candidate with missing accepted output ref
- candidate with missing data ref
- near-duplicate candidate marked for promotion
- explicit capture from marked inbox row
- capture refuses unscored or schema-incomplete row in write mode
- capture with missing ID returns `needs_human` in dry-run and refuses write mode
- duplicate tie with several same-tier matches returns `needs_human`
- unmarked inbox row ignored by maintenance
- maintenance dry-run and write-mode roundtrip determinism
- maintenance write-mode idempotency under no input changes
- manual-notes preservation outside generated blocks
- concurrent write invocation refuses or locks cleanly
- stale catalog lock is surfaced and handled according to lock expiry rules
- leftover temp files do not affect reads
- promotion dry-run refuses unsafe candidates
- direct `experiment_plan` route without approved data refs is always refused

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
- existing workspaces can safely add missing catalog files
- `IDEA-*.json` files are canonical
- `idea_catalog.md` is a generated projection with preserved manual notes
- empty idea catalogs are valid
- structured candidates can live under `research_ops/ideas/` by manual creation
- `async-research idea catalog validate research_ops` exists
- `async-research idea catalog list research_ops` exists
- `async-research idea catalog show research_ops IDEA-0001` exists
- unsafe promotion states fail closed
- discovery docs explain how inbox candidates move into the catalog
- tests cover malformed, duplicate, parked, rejected, stale projection, stale
  promoted task refs, and unsafe promotion states

## V1 Full Feature Definition

The v1 feature is complete when:

- discovery can feed explicit capture and durable catalog maintenance
- catalog maintenance can run dry-run and write mode safely
- one idea can produce one bounded promotion proposal in dry-run mode
- weekly digest and health surfaces expose idea backlog quality
- dashboard has read-only portfolio views
- library and data foundation refs are supported without blocking cold starts
- promotion write mode remains deferred to v2

## Resolved Decisions

- `discovery_inbox.md` remains a short-lived buffer and should not be replaced
  by `idea_catalog.md`.
- Idea statuses are separate from task statuses because the lifecycles are
  different.
- Human priority is a separate field, not an override on the score.
- Novelty is agent-proposed and human-confirmable.
- Promotion write mode should not ship in v1.

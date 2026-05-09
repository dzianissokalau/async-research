# Idea Catalog Contract

Created: 2026-05-06

## Purpose

The idea catalog is a durable portfolio surface for research ideas before they
become execution tasks. It makes prioritization inspectable without turning
discovery output into work automatically.

## Ownership Model

Keep these layers separate:

```text
discovery_inbox.md = short-lived discovery buffer
ideas/IDEA-*.json = canonical durable idea records
ideas/idea_catalog.md = generated portfolio projection
ideas/prioritization.md = generated planning projection
queue.md = execution queue
```

`research_ops/ideas/IDEA-*.json` files are the planned source of truth for
catalog records. `idea_catalog.md` and `prioritization.md` are projections with
explicit generated blocks. Tooling may update generated blocks in later phases,
but it must preserve free-form notes outside those blocks.

`discovery_inbox.md` remains cheap and noisy. Capturing an idea into the catalog
must be explicit, and capture must copy or derive canonical catalog state
without deleting discovery-stage artifacts.

`queue.md` remains the execution queue. Idea catalog initialization,
validation, maintenance, capture, and v1 promotion dry runs must not edit
`queue.md` or create task folders.

## Bootstrap State

Empty catalog projection files are valid cold-start state:

```text
research_ops/ideas/idea_catalog.md
research_ops/ideas/prioritization.md
```

Existing workspaces without `research_ops/ideas/` are valid partial-bootstrap
state. Run this command to preview missing files:

```bash
async-research idea catalog init research_ops --dry-run
```

Run with `--write` to add only missing catalog files:

```bash
async-research idea catalog init research_ops --write
```

The initializer must not overwrite existing catalog files or manual notes.

## Generated Block Markers

Future parsers and renderers must use these exact generated-block markers.

`idea_catalog.md` has one generated table block:

```text
<!-- IDEA-CATALOG: AUTO-MAINTAINED - DO NOT EDIT INSIDE THIS BLOCK -->
<!-- /IDEA-CATALOG -->
```

`prioritization.md` has one generated block for each planning section:

```text
<!-- IDEA-PRIORITIZATION: RECOMMENDED-PROMOTIONS AUTO-MAINTAINED -->
<!-- /IDEA-PRIORITIZATION: RECOMMENDED-PROMOTIONS -->

<!-- IDEA-PRIORITIZATION: PARKED AUTO-MAINTAINED -->
<!-- /IDEA-PRIORITIZATION: PARKED -->

<!-- IDEA-PRIORITIZATION: REJECTED AUTO-MAINTAINED -->
<!-- /IDEA-PRIORITIZATION: REJECTED -->

<!-- IDEA-PRIORITIZATION: BLOCKERS AUTO-MAINTAINED -->
<!-- /IDEA-PRIORITIZATION: BLOCKERS -->
```

The supported prioritization sections are `RECOMMENDED-PROMOTIONS`, `PARKED`,
`REJECTED`, and `BLOCKERS`.

## Candidate Lifecycle Fields

Canonical catalog candidates reuse `idea_candidate.schema.json`. The schema
keeps existing discovery-stage candidates valid while adding optional lifecycle
metadata for catalog records:

```text
created_at
updated_at
human_priority
promoted_task_id
human_gate_reason
status_reason
source_discovery_path
library_refs
data_refs
accepted_output_refs
rejected_idea_refs
rejected_result_refs
decision_history
```

`library_refs` are optional background references to `LIT-*` source IDs in
`research_ops/library/source_library.md`. They are warning-level support for
normal catalog validation and cold-start planning. They must not point to
`research_ops/knowledge/`, and they do not replace source-level citation in
final accepted claims.

Stored idea statuses are:

```text
candidate
promote
park
reject
promoted
needs_human
```

Schema validation checks field shape, ID patterns, reference patterns, and
allowed statuses. Path-aware checks such as `ideas/IDEA-0001.json` matching
`id = IDEA-0001`, stale references, and conditional lifecycle rules are handled
by the catalog parser and validator phases.

## Read Model

The read-only catalog parser lives in `async_research_workflow.idea_catalog`.
It reads `research_ops/ideas/` without mutating files and returns a deterministic
model containing:

- canonical `ideas/IDEA-*.json` records
- parsed generated blocks from `ideas/idea_catalog.md`
- parsed generated blocks from `ideas/prioritization.md`
- duplicate canonical idea IDs
- filename/JSON ID mismatch warnings
- stale projection warnings for orphaned Markdown rows and orphaned JSON records
- stored status counts
- derived display-label counts such as `raw`, `scored`, and `blocked`
- cold-start warnings for workspaces missing `research_ops/ideas/`

The parser reports malformed or unreadable candidate JSON as a failure with the
offending path and reason. Stale or unreadable Markdown projection state is a
warning because canonical JSON remains authoritative.

## Validator And CLI

The Phase 4 MVP exposes read-only catalog inspection through:

```bash
async-research idea catalog validate research_ops
async-research idea catalog list research_ops [--status STATUS]
async-research idea catalog show research_ops IDEA-0001
```

`validate` reads the parser model, validates canonical JSON against
`idea_candidate.schema.json`, promotes parser warnings that represent invalid
canonical state to failures, and checks lifecycle gates for promotion, parking,
rejection, human gates, promoted task references, and optional refs. Empty or
partially bootstrapped catalogs remain valid with warnings.

Validation exit codes:

- `0`: catalog validation passed
- `2`: valid shape but unsafe lifecycle, promotion, or reference state
- `3`: invalid request such as a missing requested idea
- `4`: malformed catalog state such as malformed JSON, schema failures,
  duplicate IDs, filename/JSON ID mismatch, or malformed generated blocks

`list` and `show` are read-only inspection commands. `list` summarizes
canonical JSON records and can filter by stored status. `show` returns the
canonical payload, derived summary, and advisory validation for that one record.

## Operator Flow

Use the three layers deliberately:

1. `discovery_inbox.md` is the cheap discovery buffer. It can contain noisy
   rows, partial notes, and raw discovery output. Nothing in this file is
   durable portfolio state until a human or planner explicitly captures it.
2. `research_ops/ideas/IDEA-*.json` is the durable catalog. Capturing from
   discovery must create or update canonical JSON with schema-valid candidate
   fields, source links, score metadata, lifecycle status, and any human gate
   reason. The JSON record owns status, score, refs, kill criteria, and
   promotion readiness.
3. `queue.md` is the execution queue. A catalog idea can move toward execution
   only through a planner or human-approved helper that produces a bounded task
   proposal. Read-only catalog surfaces, validation, list/show commands, and
   surface updates must not edit `queue.md` or task folders.

The practical path is:

```text
discovery_inbox.md row
-> explicit capture into ideas/IDEA-0001.json
-> validate and inspect catalog health
-> human/planner promotion proposal
-> queue.md task row only after approval
```

## Read-Only Surfaces

Phase 5 exposes catalog health without enabling promotion writes:

- `async-research surface update research_ops` adds an Idea Catalog section to
  `weekly_digest.md` and `daily_status.md`.
- `async-research health research_ops --dry-run` includes an
  `checks.idea_catalog` summary and warning-level alerts when catalog validation
  or projection state needs attention.
- `async-research readiness research_ops --dry-run` includes the same catalog
  summary and warning-level issues so autonomous loops can continue with
  visibility while malformed catalog state is repaired.

These surfaces report stored status counts, derived `raw` / `scored` /
`blocked` counts, top `promote` ideas from canonical JSON, parked and rejected
counts, data or evidence gap issues, and stale projection warnings. They are
strictly read-only with respect to canonical `ideas/IDEA-*.json`.

## Phase 6 Dry-Run Capture And Maintenance

Phase 6 adds proposal commands only:

```bash
async-research idea capture research_ops --from-inbox IDEA-0001 --dry-run
async-research idea capture research_ops --from-inbox row-7 --id IDEA-0007 --dry-run
async-research idea capture research_ops --title "..." --id IDEA-0008 --dry-run
async-research idea catalog maintain research_ops --dry-run
```

`idea capture` is explicit ingestion. It may read one `discovery_inbox.md` row
or an explicit title, check deterministic duplicates, and print the exact
canonical `ideas/IDEA-*.json` it would create. Missing or invalid IDs return a
`needs_human` proposal. Existing IDs, duplicate titles, shared accepted/rejected
task refs, shared cluster IDs, and explicit duplicate markers route
conservatively to an update or human decision proposal rather than creating a
new canonical JSON file.

`idea catalog maintain` reads `discovery_inbox.md`, canonical catalog JSON,
`accepted_outputs_index.md`, and `discovery/rejected_ideas.md`. It only proposes
capture for inbox rows with an explicit marker such as `catalog: candidate`;
unmarked row presence never creates catalog candidates. Unknown marker statuses
default conservatively to `candidate` and remain visible in the dry-run proposal
as raw marker metadata so operators can audit the default. It also reports
conservative lifecycle recommendations for existing catalog records. Status
update proposals include a `proposed_decision_history_entry` with a write-time
timestamp placeholder for the eventual write-mode append.

Both commands are read-only in Phase 6. `--write` is accepted only to return a
clear refusal until Phase 7 write-mode locking and atomic writes ship. These
commands must not edit `queue.md`, task folders, canonical idea JSON, generated
Markdown projections, or manual notes.

## Phase 7 Catalog Write Mode

Phase 7 enables explicit write mode for safe catalog maintenance:

```bash
async-research idea capture research_ops --from-inbox IDEA-0001 --write
async-research idea catalog maintain research_ops --write
async-research idea park research_ops IDEA-0001 --reason "..." --revisit "..." --write
async-research idea reject research_ops IDEA-0001 --reason "..." --write
```

Write mode acquires `research_ops/ideas/LOCK/` with an `owner.json` containing
the command, process id, start time, and lock expiry before reading catalog
state. Fresh locks refuse writers. Expired locks may be moved to
`LOCK.stale.<timestamp>` before retrying. The lock is released only after
canonical JSON writes, generated projection writes, and post-write validation.
Concurrent stale-lock recovery attempts are fail-safe but not queued; one writer
may win and another may need to retry.

Writers use temp-file-plus-atomic-rename for canonical JSON and generated
Markdown projection files. They preserve bytes outside generated blocks in
`idea_catalog.md` and `prioritization.md`, regenerate generated blocks from
canonical JSON, and run catalog validation after writes. Capture write mode
refuses duplicate or ambiguous capture plans. By default it creates only new
ideas. With `--update-existing`, it may merge captured title, inbox source path,
and recommended next task into an existing same-ID catalog record; it still
refuses duplicate-title or otherwise ambiguous overwrite attempts. Maintenance
write mode applies only deterministic create/status proposals; promotion remains
a catalog status recommendation and never mutates `queue.md`.

Post-write validation failures do not automatically roll back files that were
already written. Failure responses include the written paths and direct the
operator to run `async-research idea catalog validate` before retrying so the
on-disk state can be inspected.

Explicit `park` and `reject` commands require a reason. `park` also requires a
revisit condition. Status-changing writes append `decision_history` and update
`updated_at` only when canonical content changes.

## Phase 8 Promotion Dry Run

Phase 8 adds planner-facing promotion proposals without enabling execution
writes:

```bash
async-research idea promote research_ops IDEA-0001 --dry-run
async-research idea promote research_ops IDEA-0001 --task-type data_readiness --dry-run
```

In dry-run mode, the command reads one canonical catalog idea, validates catalog
state, checks status, lifecycle, score gates, hard gates, duplicate status, data
refs, and task-type eligibility, then prints at most one bounded task proposal.
Dry-run never edits `queue.md` or creates task folders. V2 write behavior is
specified below.

Allowed proposal task types are `literature_extract`, `data_readiness`,
`hypothesis_card`, and `experiment_plan`. Without an override, thin evidence
routes to `literature_extract`; plausible but unaudited data routes to
`data_readiness`; direct `experiment_plan` is allowed only when audited
`data_refs` exist and hard gates pass. Duplicate or near-duplicate ideas require
an explicit `--allow-duplicate` human override before a proposal is emitted.

Promotion dry-run reports `evidence_support` separately from route choice so
planners can distinguish true thin evidence from missing library support.
`thin_evidence` means the idea has no refs or source discovery context.
`missing_library_support` means `library_refs` were present but did not resolve
against `research_ops/library/source_library.md`. Normal catalog validation and
data-readiness routing keep unresolved `library_refs` warning-level, but routes
that rely on library support, such as `hypothesis_card` or `experiment_plan`,
block until the refs resolve or a prior `literature_extract` task creates the
needed support.

The JSON proposal includes the reserved task id and slug, task type, title,
objective, scope, `evidence_support`, required sources and refs, allowed paths,
max minutes, max turns, kill reason, validation commands, blockers, draft
task/status content, and a `promotion_preflight_hash` that write mode must
receive unchanged.

## Current Planner Promotion Behavior

The planner still uses dry-run proposals as the authoritative preflight, but it
no longer hand-creates catalog promotion tasks. V2.6+ write mode owns the task
creation transaction.

The planner-controlled path is:

```text
discovery_inbox.md
-> async-research idea capture ... --write
-> ideas/IDEA-0001.json
-> async-research idea promote research_ops IDEA-0001 --dry-run
-> async-research idea promote research_ops IDEA-0001 --write --preflight-hash <hash>
-> reserved task folder + queue.md row + promoted_task_id
```

Rules for planner promotion writes:

- promote few ideas, normally at most 3 catalog ideas per planner run
- create the cheapest killable next task that the proposal selects
- use `literature_extract` when evidence is thin
- inspect `evidence_support.status` before writing tasks; unresolved
  `library_refs` are normal warning-level catalog state, but
  `missing_library_support` means a library-dependent proposal needs resolved
  `LIT-*` support or an earlier extraction task
- use `data_readiness` when data is plausible but unaudited; generated
  data-readiness tasks may update `data_source_audit.md` and `data/**`, must
  produce profile/audit recommendations, and should run both source and data
  validators before review
- write `experiment_plan` only when the proposal selects it, listed source
  checks pass, and a recorded human decision backs `--human-override`
- preserve proposal scope, allowed paths, limits, kill reason, validation
  commands, and review tier unless a human-approved reason is recorded
- use `proposal.proposed_task_id` and `proposal.proposed_task_slug` as the
  reserved task identity for V2.5-or-newer proposals
- do not write tasks from blocked proposals
- do not use `--allow-duplicate` without a human decision or explicit planner
  note naming the non-duplicate angle
- skip ideas that already have a task `status.json` with matching
  `catalog_idea_id`, unless a human decision or explicit planner note explains
  the distinct follow-up
- run `async-research idea promote ... --write --preflight-hash <hash>` only
  with the hash from the immediately preceding dry run
- do not hand-create task folders, `status.json`, `task.md`, or `queue.md` rows
  from the dry-run payload
- after a successful or idempotent write, rerun catalog validation and the
  dashboard; the promoted idea should show `promoted_task_id=<TASK-ID>` with
  `link_status=available`
- do not run the former v1 park closeout after write success; refresh any
  cached pre-V2.8 planner prompt that still calls
  `async-research idea park ... --reason "promoted to <TASK-ID>" --write`
- if write mode reports `promotion_preflight_changed`, recovery required,
  `rollback_ok=false`, or `requires_human=true`, stop and surface the exact
  recovery payload instead of repairing files ad hoc

Catalog commands own portfolio state and proposal generation. `idea promote
--write` is the one catalog command allowed to create the reserved task folder
and queue row. Catalog maintenance must not become a hidden queue writer.

## Phase 10 Dashboard Read-Only View

Phase 10 adds a portfolio dashboard command:

```bash
async-research idea catalog dashboard research_ops
```

The dashboard reads the catalog read model and validator output. It does not
parse catalog files through a separate path and does not write canonical idea
JSON, generated projections, `queue.md`, or task folders.

The JSON output includes:

- active candidate ideas, including `candidate`, `promote`, and `needs_human`
  statuses
- parked, promoted, and rejected idea lists
- top validation blockers, with failures sorted before warnings
- score dimensions for every canonical idea
- next recommended task groups for active candidate ideas
- idea-to-task links from `promoted_task_id`

Missing score artifacts render as `unavailable` across the dashboard summary,
score dimensions, and candidate rows. The command still returns the validator
exit code, so malformed or unsafe catalog state can render visibly while
automation fails closed.

The dashboard summary distinguishes issue volume from the capped blocker list:
`total_issue_count` reports all validator failures and warnings, while
`displayed_blocker_count` reports how many entries were included in
`sections.top_blockers` after applying `--max-blockers`.

## V2 Promotion Write Contract And Preflight

V2.1 was a design and test-preflight slice. V2.6 promotes the write path from
proposal-only to task creation: operators must run
`async-research idea promote ... --dry-run`, copy the returned
`promotion_preflight_hash`, then run `async-research idea promote ... --write
--preflight-hash <hash>`.

V2.6 `--write` appends one planner-facing proposal reference to
`research_ops/inbox.md`, creates one reserved `tasks/TASK-*/` folder with
`task.md` and `status.json`, appends one `queue.md` row, updates the selected
canonical idea with `promotion_proposal_refs`, `latest_promotion_proposal_id`,
`promoted_task_id`, and a `decision_history` entry, and regenerates idea
projections. It does not mutate source or accepted-output ledgers.

Promotion write mode remains split into two write slices:

| Slice | May mutate | Must not mutate |
| --- | --- | --- |
| Proposal write mode | `research_ops/inbox.md`, the selected `ideas/IDEA-*.json` proposal reference fields, generated idea projections, and `decision_history` for the proposal reference. | `queue.md`, `tasks/`, accepted-output ledgers, source audit rows, and unrelated idea records. |
| Task creation write mode | One new `tasks/TASK-*/` folder, one `queue.md` row, the selected idea's `promoted_task_id`, generated idea projections, and transaction/audit metadata. | More than one task, unrelated queue rows, unrelated ideas, source audit state, accepted-output ledgers, and manual notes outside generated blocks. |

CLI evolution is staged. In V2.2, `idea promote --write` performed proposal
writes only and did not create task folders or edit `queue.md`. As of V2.6,
`idea promote --write` composes proposal write and task creation write in one
invocation under one catalog lock acquisition.

Required lock ordering:

1. Acquire `research_ops/ideas/LOCK` before re-reading the selected idea for any
   write-mode promotion slice.
2. Re-read the idea, recompute the promotion preflight hash, and rerun catalog
   validation while the catalog lock is held.
3. Proposal write mode may then prepare an `inbox.md` append transaction; it
   must commit the inbox append and idea proposal reference together or report a
   recovery payload that names the partial artifact.
4. Task creation write mode may then reserve or allocate the task id, stage task
   files outside the final task path, and validate the staged `task.md` and
   `status.json` before touching `queue.md`.
5. Append `queue.md` only after staged task files validate. Update the idea's
   `promoted_task_id` only after the task folder and queue row are both
   finalized.
6. Release `research_ops/ideas/LOCK` last. If a future queue/task lock is added,
   it must be acquired after the catalog lock and released before the catalog
   lock to avoid deadlocks.

V2.5 defined the deterministic task-id reservation rule before task files are
finalized. The reserved TASK ID reuses the selected IDEA numeric suffix:
`IDEA-7501 -> TASK-7501`, with a task folder slug such as
`TASK-7501-data-readiness`. Promotion dry-run and task write payloads expose
this identity as `task_identity`, `proposal.proposed_task_id`, and
`proposal.proposed_task_slug`.

A write must refuse when the reserved task id already has a task folder, an
existing `queue.md` row, an accepted-output row, a different idea's
`promoted_task_id`, or a stale/existing `promoted_task_id` on the selected idea.
Queue checks must match the task cell, not arbitrary note text. Re-running the
same write command may be idempotent only when the existing task folder, queue
row, and idea `promoted_task_id` all match the same `catalog_idea_id`,
idempotency key, and transaction id.

The idempotency key for both write slices is:

```text
catalog_idea_id + task_type + promotion_preflight_hash
```

The transaction id is generated at write time after the idempotency key is
computed. Proposal write mode must persist it in the idea `decision_history`
entry and the `inbox.md` proposal metadata. Task creation write mode must also
persist it in task `status.json` and queue row metadata or notes. Recovery
payloads and rollback messages must include both the transaction id and the
idempotency key.

The promotion preflight hash must include at least the selected idea id, status,
score object, recommended next task, duplicate status, refs, kill reason, and
the dry-run proposal task type. If any of those fields change between dry-run
and write, the write must refuse with `reason=promotion_preflight_changed` and
tell the operator to rerun `--dry-run`.

V2.6 duplicate handling is conservative but retry-friendly: a second write with
the same preflight hash may return `action=idea_promotion_task_already_written`
only when the existing task folder, queue row, inbox row, idea `promoted_task_id`,
catalog idea id, idempotency key, and transaction id all match. An inbox row with
a matching idempotency key but no idea proposal reference must refuse with
`reason=promotion_proposal_recovery_required`.

Rollback boundaries:

- Proposal write mode must not leave an inbox proposal without a matching idea
  proposal reference unless the response returns an explicit recovery payload.
- Task creation write mode must remove staged task files if queue append fails.
- If final validation fails after queue append, the helper must roll back the
  task folder and queue row together before releasing the catalog lock.
- If rollback itself fails, the recovery payload must mark `requires_human`,
  set `rollback_ok=false`, include exact paths, transaction id,
  `rollback_failures`, and next recovery command suggestions.

Human override rules are slice-specific.

For promotion task write mode, human override is required when any of these are
true:

- `--allow-duplicate` is needed for a duplicate or near-duplicate idea.
- the dry-run proposal routes to `experiment_plan`.
- the proposal has `review_tier >= 2` or `max_minutes > 75`.
- catalog validation returns failures or blocking promotion reasons.
- an existing task, queue row, or proposal appears related but does not match
  the current idempotency key.

Future hardening may require an additional human override when any of these are
true:

- projected spend fails `async-research cost budget-check`.

Preflight and regression tests for V2.2 and later cover duplicate retry, stale
`research_ops/ideas/LOCK`, changed candidate between dry-run and write, partial
inbox proposal without idea reference, staged task validation failure, queue
append failure, idea JSON write failure, completion-check failure, interrupted
retry with existing artifacts, stale `promoted_task_id`, existing task folder,
and rollback audit reporting.

## Safety Rules

- Every mutating idea-catalog command requires explicit `--write`.
- Without `--write`, idea-catalog commands are read-only or dry-run by default.
- Promotion write mode requires a matching dry-run `promotion_preflight_hash`
  and must write at most one reserved task, one `queue.md` row, one `inbox.md`
  proposal reference, and the selected idea's promotion refs.
- Direct experiment promotion remains blocked unless existing source and data
  gates pass.
- Single-writer operation is enforced by `research_ops/ideas/LOCK` for
  mutating catalog commands.

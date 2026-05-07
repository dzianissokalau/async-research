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

The command reads one canonical catalog idea, validates catalog state, checks
status, lifecycle, score gates, hard gates, duplicate status, data refs, and
task-type eligibility, then prints at most one bounded task proposal. It never
edits `queue.md`, never creates task folders, and refuses `--write` until V2.

Allowed proposal task types are `literature_extract`, `data_readiness`,
`hypothesis_card`, and `experiment_plan`. Without an override, thin evidence
routes to `literature_extract`; plausible but unaudited data routes to
`data_readiness`; direct `experiment_plan` is allowed only when audited
`data_refs` exist and hard gates pass. Duplicate or near-duplicate ideas require
an explicit `--allow-duplicate` human override before a proposal is emitted.

The JSON proposal includes a task id placeholder or slug, task type, title,
objective, scope, required sources and refs, allowed paths, max minutes, max
turns, kill reason, validation commands, blockers, and draft task/status
content for a planner to turn into real task files manually.

## Phase 9 Planner Promotion Behavior

Phase 9 keeps promotion write mode disabled, but teaches the planner how to use
dry-run proposals safely.

The planner-controlled path is:

```text
discovery_inbox.md
-> async-research idea capture ... --write
-> ideas/IDEA-0001.json
-> async-research idea promote research_ops IDEA-0001 --dry-run
-> planner-created task folder
-> queue.md row
```

Rules for planner-created tasks:

- promote few ideas, normally at most 3 catalog ideas per planner run
- create the cheapest killable next task that the proposal selects
- use `literature_extract` when evidence is thin
- use `data_readiness` when data is plausible but unaudited
- create `experiment_plan` only when the proposal selects it and listed source
  checks pass
- preserve proposal scope, allowed paths, limits, kill reason, validation
  commands, and review tier unless a human-approved reason is recorded
- do not create tasks from blocked proposals
- do not use `--allow-duplicate` without a human decision or explicit planner
  note naming the non-duplicate angle
- skip ideas that already have a task `status.json` with matching
  `catalog_idea_id`, unless a human decision or explicit planner note explains
  the distinct follow-up
- append `queue.md` only after task files, anti-context, source checks, and
  applicable validation commands are coherent
- after appending `queue.md`, close the v1 loop with an explicit
  `async-research idea park ... --reason "promoted to TASK-0001" --revisit ... --write`
  status update, then rerun catalog validation

Catalog commands own portfolio state and proposal generation. The planner owns
execution task creation. Catalog maintenance must not become a hidden queue
writer in v1. The park closeout is a temporary v1 planner convention to prevent
repeat promotion; V2 promotion write mode will replace it with a transactional
`promoted_task_id` update.

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

## Safety Rules

- Every mutating idea-catalog command requires explicit `--write`.
- Without `--write`, idea-catalog commands are read-only or dry-run by default.
- Promotion write mode is outside v1.
- Direct experiment promotion remains blocked unless existing source and data
  gates pass.
- Single-writer operation is assumed for mutating catalog commands in v1.

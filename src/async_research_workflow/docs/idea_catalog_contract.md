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
warning because canonical JSON remains authoritative. CLI commands for
validation, listing, and showing catalog ideas are intentionally deferred to the
next phase.

## Safety Rules

- Every mutating idea-catalog command requires explicit `--write`.
- Without `--write`, idea-catalog commands are read-only or dry-run by default.
- Promotion write mode is outside v1.
- Direct experiment promotion remains blocked unless existing source and data
  gates pass.
- Single-writer operation is assumed for mutating catalog commands in v1.

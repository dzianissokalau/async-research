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

## Safety Rules

- Every mutating idea-catalog command requires explicit `--write`.
- Without `--write`, idea-catalog commands are read-only or dry-run by default.
- Promotion write mode is outside v1.
- Direct experiment promotion remains blocked unless existing source and data
  gates pass.
- Single-writer operation is assumed for mutating catalog commands in v1.

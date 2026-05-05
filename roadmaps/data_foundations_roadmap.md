# Data Foundations Roadmap

Created: 2026-05-05

## Summary

Build explicit data foundations before expensive research tasks start. This
feature makes data availability, access, quality, joins, freshness, and
restrictions visible and auditable.

The current framework already has `research_ops/data_source_audit.md`. This
roadmap extends that register into a fuller data-readiness layer while keeping
the audit register as the governance source of truth.

## What It Does

The data foundations feature answers:

- what datasets exist
- where they live
- how they can be accessed
- who owns or publishes them
- what fields, grain, geography, and time coverage they have
- what joins are plausible
- what data quality risks are known
- what licensing, privacy, and use restrictions apply
- what data gaps block or limit research ideas

It supports public and user-owned data. A source location can be a local file,
server path, database table, bucket, API, public URL, or manually described
dataset.

## Framework Integration

Existing artifact:

```text
research_ops/data_source_audit.md
```

New workspace artifacts:

```text
research_ops/
  data/
    data_catalog.md
    data_access.md
    join_map.md
    known_data_gaps.md
    profiles/
      DS-0001.md
```

Integration points:

- `data_source_audit.md` remains the source governance register.
- `data/data_catalog.md` becomes the human-readable inventory.
- `data/profiles/DS-*.md` holds dataset-level readiness details.
- `data/data_access.md` explains how to access approved local, server, cloud,
  API, or manual sources.
- `data/join_map.md` records plausible joins and known join risks.
- `data/known_data_gaps.md` feeds idea scoring, planning, and human review.
- Discovery can propose plausible data paths, but experiment planning still
  requires audited `DS-*` references.
- Accepted evidence records link back to approved source IDs.

## Implementation Steps

### Slice 1: Starter Files

Add data foundation files to the generic and real-estate templates.

Acceptance:

- `async-research init research_ops` creates `research_ops/data/`
- starter files can be empty or placeholder-only
- existing CLI checks pass with empty data foundation files

### Slice 2: Data Profile Contract

Add a data profile template:

```text
research_ops/data/profiles/DS-0000.md
```

Suggested sections:

- source ID and source name
- location and access method
- owner/publisher
- approved use cases
- blocked use cases
- fields and grain
- geography and time coverage
- refresh cadence
- known limitations
- join keys and join risks
- privacy/licensing restrictions
- reviewed date and reviewer

Acceptance:

- every profile points to one `DS-*` audit row
- profiles can represent public, local, cloud, database, and manual sources
- profile caveats are usable by reviewers and experiment planners

### Slice 3: Source Audit Linkage

Extend source audit docs and optional parsing so audit rows may reference a
profile file.

Acceptance:

- `data_source_audit.md` remains valid without profiles during cold start
- audited experiment-ready sources can link to `data/profiles/DS-*.md`
- missing profile links warn for data-readiness use and can block experiment
  planning once strict mode is enabled

### Slice 4: Validator

Add:

```bash
async-research data validate research_ops
```

Checks:

- duplicate `DS-*` profile IDs
- profile without matching audit row
- audit row pointing to missing profile
- missing access notes for approved sources
- stale review date
- missing approved or blocked use cases
- joins without caveats
- known gaps referenced by active ideas

Acceptance:

- valid empty data foundation passes or returns warning-only status
- approved source with missing access path is flagged
- blocked or stale sources remain blocked for experiment planning

### Slice 5: Data Readiness Task

Harden the `data_readiness` task type around data profiles.

The worker should produce:

- profile draft or update
- recommended audit status
- access check result
- field/grain coverage
- join feasibility
- known limitations
- recommended next task
- kill reason if data is unusable

Acceptance:

- a data-readiness task can promote a source from `candidate` to `approved` or
  `approved_with_caveats`
- a data-readiness task can mark a source `blocked`, `restricted`, or
  `deprecated`
- all changes are traceable to the reviewed task

### Slice 6: Health, Readiness, And Gates

Extend operational checks.

Rules:

- missing data foundations warn during cold start
- ideas can reference plausible unaudited data
- experiment planning requires approved or approved-with-caveats data refs
- accepted evidence cannot rely on stale, blocked, or unaudited data

Acceptance:

- `health` surfaces stale and blocked data sources
- `readiness` blocks unsafe experiment work without blocking all discovery
- `weekly_digest.md` shows data gaps affecting the idea backlog

### Slice 7: Dashboard Surface

Add read-only dashboard views.

Show:

- approved sources
- candidate sources
- blocked/restricted/deprecated sources
- stale source reviews
- data gaps
- ideas blocked by data readiness
- join paths and caveats

Acceptance:

- operator can tell which data is usable today
- operator can see why an idea is blocked by data
- dashboard does not mutate data files in the first version

## Open Questions

- Should every `DS-*` source require a profile, or only experiment-capable data?
- Should local file profiling helpers be included in v1, or deferred until
  after the Markdown contracts are stable?
- Should access checks run automatically, or only when the user explicitly
  grants access to local/cloud/server data?
- Should joins have their own IDs, such as `JOIN-0001`, once join maps become
  complex?

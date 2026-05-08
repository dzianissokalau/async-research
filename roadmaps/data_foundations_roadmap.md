# Data Foundations Roadmap

Created: 2026-05-05

## Summary

Build explicit data foundations before expensive research tasks start. This
feature makes data availability, access, quality, joins, freshness, and
restrictions visible and auditable.

The current framework already has `research_ops/data_source_audit.md`. This
roadmap extends that register into a fuller data-readiness layer while keeping
the audit register as the governance source of truth.

## Execution Decisions

V1 should be contract-first and backward-compatible. The first execution goal is
to make the data foundation file structure and profile contract real without
changing existing source-governance behavior.

### V1 Scope

V1 includes:

- starter data foundation files in both templates
- a documented `data/profiles/DS-0000.md` profile contract
- optional audit/profile linkage
- a read-only `async-research data validate research_ops` command

V1 defers:

- automatic local/cloud/API access checks
- profiling helpers for local files
- strict experiment-planning blocks for missing profiles
- dashboard views
- mutating data-readiness workers beyond current source-audit authoring commands

### Profile Requirement Policy

Cold-start workspaces must remain valid without profiles.

Profile expectations:

- `unknown`, `candidate`, `blocked`, `restricted`, and `deprecated` audit rows
  may omit a profile in v1.
- `approved` and `approved_with_caveats` rows should have a profile when data
  foundations are present.
- `explicitly_approved` rows may omit a profile by default, but should warn when
  used for governed data claims unless a profile or human approval note explains
  the exact approved use.
- Missing profiles for experiment-ready rows are warning-level in non-strict
  validation.
- Strict blocking can be added later behind an explicit strict mode.

### Audit Link Strategy

The first implementation should avoid changing the `data_source_audit.md` table
shape. Existing audit schema `1.0` must remain valid.

V1 linkage direction:

- profile files point back to one `DS-*` audit row
- audit rows remain valid without a profile column
- optional parser support for a future `profile_path` field can ship later only
  after backward-compatibility tests exist

### Validator Contract

Add:

```bash
async-research data validate research_ops
```

The command is read-only.

Exit codes:

- `0` when data foundations are valid
- `2` when validation findings or warnings are present
- `4` when the workspace or data foundation files are malformed enough that the
  validator cannot reason about them

Warning-only validation should return exit `2` with `ok: true`,
`warning_count > 0`, and no error-level findings. This keeps cold-start warnings
visible to schedulers without treating the workspace as malformed.

Cold-start behavior:

- missing `research_ops/data/` in existing workspaces warns, not fails
- empty starter data files pass or return warning-only status
- existing `data_source_audit.md` validation remains the source-governance gate

### Backward Compatibility

Implementation must preserve:

- existing `async-research init` behavior except for adding starter files
- existing `async-research source` commands
- existing `data_source_audit.md` schema `1.0`
- existing starter smoke, acceptance suite, and benchmark expectations

### First Test Matrix

Minimum tests for the first two implementation phases:

- `async-research init research_ops` creates `research_ops/data/`
- generic and real-estate starter resources include the data foundation files
- generic and real-estate starter smoke still pass
- empty data foundation validates
- missing `data/` in an existing workspace is warning-only
- duplicate profile IDs are flagged
- profile without matching audit row is flagged
- profile filename and internal `source_id` mismatch is flagged
- approved source without profile is warning-only in non-strict mode
- existing `async-research source validate` behavior is unchanged

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

## Delivery Strategy

Build this as a sequence of small, deterministic slices. Do not start with the
dashboard or strict planning gates. Those should consume a stable profile
contract and validator rather than inventing their own read path.

Recommended sequence:

1. Lock execution decisions and compatibility rules.
2. Add starter files and profile contract.
3. Add the read-only data foundation parser and validator.
4. Add optional audit/profile linkage.
5. Harden data-readiness task guidance around profiles.
6. Feed health, readiness, weekly digest, and experiment gates from validator
   output.
7. Add read-only dashboard views.

Each phase should leave the package usable. Any strict blocking behavior should
ship after a warning-only version has real test coverage.

Delivery boundary:

- MVP: Phases 0 through 2. This is roadmap decisions, starter state, profile
  contract, and read-only validation.
- V1 post-MVP: Phases 3 through 5. This adds linkage, data-readiness task
  hardening, and operational gates.
- V2: Phase 6 dashboard views, profiling helpers, automated access checks, and
  stricter data-dependency policy once contracts are stable.

## Progress

Last updated: 2026-05-08

| Phase | Step | Status | Description | Evidence / Notes |
| ---: | --- | --- | --- | --- |
| 0 | Lock execution decisions | Complete | Capture V1 scope, profile requirement policy, audit link strategy, validator exit codes, compatibility rules, and first test matrix before implementation starts. | This roadmap now defines contract-first execution and preserves `data_source_audit.md` schema `1.0`. |
| 1 | Starter files and profile contract | Complete | Add `research_ops/data/` starter files to generic and real-estate templates and document `data/profiles/DS-0000.md`. | Adds starter data catalog, access, join map, known gaps, profile contract README, and real-estate seed profiles for existing audited sources. |
| 2 | Data validator | Complete | Add read-only `async-research data validate research_ops` covering empty foundations, duplicate profiles, profile-to-audit mismatches, missing access notes, stale reviews, join caveats, and active idea gap refs. | Adds the public `data validate` command, README exit-code docs, and validator tests for generic/real-estate starters, warning-only cold start, profile identity errors, projection drift, template ignore, and idea gap refs. Audit-row-to-profile checks wait for Phase 3 optional audit-side linkage. |
| 3 | Optional source audit linkage | Complete | Add docs and optional parser support so experiment-ready audit rows may reference profiles without requiring old workspaces to change. | `data_source_audit.md` schema `1.0` remains valid without profiles; parser support accepts and preserves optional trailing `profile_path`; `data validate` warns on empty, missing, noncanonical, or mismatched audit profile links. |
| 4 | Data-readiness task hardening | Complete | Update `data_readiness` task guidance so workers produce profile drafts/updates, recommended audit status, access check results, field/grain coverage, join feasibility, limitations, and kill reasons. | Starter task, generated promotion task drafts, allowed paths, validation commands, and docs now require traceable audit/profile recommendations plus `source validate` and `data validate`. |
| 5 | Health, readiness, and gates | Complete | Surface stale, blocked, missing, and unaudited data dependencies in `health`, `readiness`, weekly digest, experiment planning, and result acceptance. | Health now reports stale/blocked sources plus data-foundation findings; readiness includes warning-only validator findings and keeps source-dependent unsafe work blocked; weekly digest includes data gap refs affecting active ideas; experiment/result gates consume validator output without making cold-start warnings strict. |
| 6 | Dashboard surface | Not started | Add read-only views for approved, candidate, blocked/restricted/deprecated, stale, gap-blocked, and join-caveat data states. | Should consume validator/read-model output and never mutate data files in the first version. |

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

Canonical profile ID:

- profile filenames use `research_ops/data/profiles/DS-0000.md`
- each profile must also declare the same `source_id`
- filename ID and internal `source_id` must match
- duplicate profile IDs are invalid even when filenames differ by path or case

Acceptance:

- every profile points to one `DS-*` audit row
- profile filename and internal `source_id` match
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
- profile filename and internal `source_id` mismatch
- audit row pointing to missing profile, only after Phase 3 optional audit-side
  linkage exists
- missing access notes for approved sources
- stale review date
- missing approved or blocked use cases
- joins without caveats
- known gaps referenced by active ideas

Authority and drift rules:

- `data_source_audit.md` remains authoritative for source governance fields.
- duplicated profile fields such as `source_name`, `audit_status`, use cases,
  reviewed date, and reviewer are checked for drift against the audit row.
- duplicated-field drift is warning-level in the first validator unless the
  drift affects `source_id` identity or makes the profile point to a missing
  audit row.
- if a literal `data/profiles/DS-0000.md` template file is added later, the
  validator must explicitly ignore it as a template rather than treating it as an
  active source profile.

Acceptance:

- valid empty data foundation passes or returns warning-only status
- approved source with missing access path is flagged
- blocked or stale sources remain blocked for experiment planning
- profile/audit projection drift is warning-level unless identity or missing
  audit-row checks fail
- warning-only findings return exit `2` with `ok: true`

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

- Should strict mode eventually require profiles for every `DS-*` source, or only
  experiment-capable data?
- Should local file profiling helpers be included in v1, or deferred until
  after the Markdown contracts are stable?
- Should access checks run automatically, or only when the user explicitly
  grants access to local/cloud/server data?
- Should joins have their own IDs, such as `JOIN-0001`, once join maps become
  complex?

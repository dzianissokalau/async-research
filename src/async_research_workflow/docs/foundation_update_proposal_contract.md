# Foundation Update Proposal Contract

Created: 2026-05-19

`foundation_update_proposal_v1` is the shared proposal envelope for data
foundation and knowledge library updates. Workers can propose durable
foundation changes without mutating `research_ops/data/`,
`research_ops/library/`, or `data_source_audit.md` directly. Reviewers inspect
the proposal first; accepted proposals can then go through the guarded
dry-run/write apply workflow.

## Envelope

Every proposal uses this envelope:

```json foundation_update_proposal_v1
{
  "proposal_version": "foundation_update_proposal_v1",
  "proposal_id": "PROP-0001",
  "source_task_id": "TASK-0001-example",
  "target": "data",
  "created_by": "worker",
  "rationale": "Why these foundation rows should change.",
  "operations": []
}
```

Allowed `target` values are `data` and `library`.

Allowed embedding forms:

- a standalone JSON artifact under a task `artifacts/` directory
- a fenced code block in `worker_output.md` whose info string contains
  `foundation_update_proposal_v1`

## Data Operations

Data proposals may use:

- `upsert_data_source` targeting `data_source_audit.md`
- `upsert_data_profile` targeting `data/profiles/DS-0000.md`
- `upsert_data_catalog_row` targeting `data/data_catalog.md`
- `upsert_data_access_row` targeting `data/data_access.md`
- `upsert_join_map_row` targeting `data/join_map.md`
- `upsert_known_data_gap` targeting `data/known_data_gaps.md`

Source, profile, catalog, and access rows use governed `DS-0000` row IDs.
Known gaps use `DG-0000` row IDs. Join rows use stable non-empty IDs without
spaces.

## Library Operations

Library proposals may use:

- `upsert_lit_source` targeting `library/source_library.md`
- `upsert_topic_summary` targeting `library/knowledge_index.md`
- `upsert_claim` targeting `library/claim_map.md`
- `upsert_method` targeting `library/method_index.md`
- `upsert_open_question` targeting `library/open_questions.md`
- `append_library_update_log` targeting `library/library_update_log.md`

Library source rows use governed `LIT-0000` row IDs. Topic, claim, method,
open-question, and update-log rows use stable non-empty IDs without spaces.

## Operation Fields

Every operation must include:

- `operation_id`
- `operation`
- `target_path`
- `row_id`
- `payload`
- `preserve_manual_notes`

`payload` must be a JSON object. The shared validator checks the envelope,
operation vocabulary, target path, row-id shape, duplicate operation IDs, and
basic payload type. Deeper semantic checks remain with the data and library
inspection phases.

## Diagnostics

Invalid proposals produce structured diagnostics with:

- `path`
- `proposal_id` when available
- `operation_id` when available
- `severity`
- `reason`
- `message`
- `remediation`

Multiple proposals with the same `proposal_id` are rejected because reviewers
and apply tooling need one unambiguous proposal target.

## Data Inspection

Data-readiness workers can hand reviewers a proposal artifact without editing
source-of-truth files. Inspect it with:

```bash
async-research data inspect-proposals research_ops <proposal-source>
```

`<proposal-source>` may be a task directory, `worker_output.md`, a JSON
proposal artifact, or a directory containing proposal artifacts. The command
returns JSON with proposal counts, per-operation diagnostics, warning-only
existing-row upserts, blockers, and next steps. It rejects non-data proposals,
path traversal, target paths that resolve outside the selected `research_ops/`
workspace, malformed row IDs, duplicate row operations, and payload row IDs
that do not match the operation `row_id`.

## Library Inspection

Literature-extract workers can hand reviewers a library proposal artifact
without manually copying rows into knowledge-library Markdown tables. Inspect it
with:

```bash
async-research library inspect-proposals research_ops <proposal-source>
```

`<proposal-source>` may be a task directory, `worker_output.md`, a JSON
proposal artifact, or a directory containing proposal artifacts. The command
returns JSON with proposal counts, per-operation diagnostics, warning-only
existing-row upserts, blockers, and next steps. It rejects non-library
proposals, path traversal, target paths outside `research_ops/library/`,
malformed library row IDs, duplicate proposed row IDs, and claim, method, or
topic payloads whose `source_refs` do not resolve to existing or proposed
`LIT-*` rows.

## Guarded Apply

Accepted proposals can be routed through dry-run-first apply commands:

```bash
async-research data apply-proposals research_ops <proposal-source> --dry-run
async-research library apply-proposals research_ops <proposal-source> --dry-run
```

Dry-run is the default. It reports proposed file edits, warnings, blockers,
post-write validators, and a `preflight_hash`. Write mode requires explicit
`--write`, the matching `--preflight-hash`, accepted source task status or an
accepted review/result-acceptance artifact inside `research_ops`, a foundation
apply lock, and clean proposal inspection. The write path re-reads proposals
after acquiring the lock, applies operations idempotently, preserves notes
outside generated table blocks, runs post-write validators, and rolls back
touched files when validation fails.

## Non-Goals

This contract does not auto-approve proposals, infer proposals from arbitrary
prose, import external files, bypass source/library validation, or treat
proposed rows as authoritative before a guarded write succeeds.

The packaged template is
[`foundation_update_proposal_template.md`](../templates/artifact_templates/foundation_update_proposal_template.md).

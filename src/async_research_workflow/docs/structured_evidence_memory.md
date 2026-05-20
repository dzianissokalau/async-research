# Structured Evidence Memory And Targeted Reflection

Status: Phase 8 runtime/eval contract

Structured evidence memory is a derived, machine-queryable view over existing
`research_ops/` artifacts. It does not replace accepted memory, runtime
evidence objects, claim verification, deliverable manifests, review artifacts,
or task state as the source of truth.

## Files

- `research_ops/memory/evidence_memory_index.json` is the derived structured
  index.
- `research_ops/reflections/targeted_reflections.jsonl` records targeted
  reflection rows.
- `research_ops/accepted_outputs_index.md` remains the accepted-memory source.
- `research_ops/runtime/evidence_objects.jsonl` remains the runtime evidence
  source.
- `research_ops/tasks/*/artifacts/claim_verification.json` and
  `research_ops/tasks/*/review_panel/result_acceptance.json` remain claim-gate
  sources.
- `research_ops/deliverables/deliverable_manifest.json` remains the deliverable
  linkage source.

## Evidence Memory Fields

Each `evidence_memory_index_v1.0` entry records:

- `memory_id`
- `task_id`
- `title`
- `key_finding`
- `claim_ids`
- `evidence_ids`
- `source_ids`
- `source_uris`
- `freshness_status`
- `accepted_memory_status`
- `task_lineage`
- `deliverable_links`
- `contradiction_edges`
- `accepted_memory_row`

Contradiction edges are derived from claim verification rows whose
`verification_status` is `contradicted`. Stale or due accepted memory remains
visible before reuse through `freshness_status`, `accepted_memory_status`, and
the index warnings.

Build or preview the index with:

```bash
async-research evidence-memory update research_ops
async-research evidence-memory update research_ops --dry-run
```

Query it with:

```bash
async-research evidence-memory query research_ops --query "source quality"
async-research evidence-memory query research_ops --contradictions-only
async-research evidence-memory query research_ops --freshness-status stale
```

If the index file is missing, query builds a read-only in-memory view and
reports that fallback in warnings.

## Targeted Reflection Records

Each `targeted_reflection_v1.0` row records:

- `reflection_id`
- `task_id`
- `task_title`
- `failure_class`
- `trigger_condition`
- `affected_stage`
- `mitigation`
- `anti_context_injection`
- `review_evidence`
- `source_task_dir`
- `status`
- optional `expires_at`

Supported failure classes are `source_quality`, `stale_evidence`,
`contradiction`, `citation_gap`, `unsupported_claim`, `route_policy`,
`reviewer_disagreement`, `reproducibility`, `cost_budget`, and
`scope_ambiguity`.

Record a reflection with:

```bash
async-research reflection record research_ops/tasks/TASK-0001-example \
  --failure-class source_quality \
  --trigger-condition "general web source reused for a public claim" \
  --affected-stage planner \
  --mitigation "require official or reviewed sources before drafting" \
  --anti-context "Do not reuse general web pages for this claim class." \
  --review-evidence review_panel/aggregate.json
```

Review evidence must resolve to an existing file inside `research_ops/`.

## Planner Context Injection

`async-research anti-context build` now includes a `Targeted Reflections`
section. It injects only active reflection rows whose trigger, mitigation,
failure class, or task title match the proposed task above the relevance
threshold. Expired, suppressed, superseded, or irrelevant rows are not injected.

The existing accepted-memory and rejected-idea anti-context sections are
preserved. Targeted reflection narrows planning context; it is not a global
warning dump.

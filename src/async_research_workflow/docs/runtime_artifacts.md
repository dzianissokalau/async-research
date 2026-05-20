# Runtime Artifacts

Created: 2026-05-20

Runtime artifacts are the Phase 1 machine-readable contract for integrated
research actions. They make future adapters auditable without giving adapters
authority to accept evidence, move task state, or publish claims.

## Ledger Locations

Runtime files live under a `research_ops/` workspace:

```text
research_ops/runtime/
  traces.jsonl
  evidence_objects.jsonl
  snapshots/
```

Missing ledgers are valid empty state. Once present, every JSONL row must
validate deterministically with:

```bash
async-research runtime validate research_ops
```

Use these read-only operator commands:

```bash
async-research runtime summary research_ops
async-research runtime inspect-evidence research_ops EVID-000001
```

Runtime adapter execution is a separate Phase 3 surface:

```bash
async-research runtime dry-run research_ops --request runtime_request.json
async-research runtime execute research_ops --request runtime_request.json
```

These commands still write only runtime traces, evidence objects, and snapshots;
they do not accept evidence or transition tasks.

## Evidence Objects

Evidence objects use
`schemas/runtime_evidence_object.schema.json`. Each row records the task,
adapter type, source URI, source title, retrieval time, snapshot hash, snapshot
path, span refs, license or use policy, freshness status, cost, and permission
basis.

Validation fails closed when:

- required fields are missing or malformed;
- `task_id` does not link to `research_ops/tasks/`;
- paths are absolute, escape `research_ops/`, or use parent traversal;
- `snapshot_path` is missing;
- `content_hash` does not match the snapshot bytes.

In validator output this appears as: content_hash does not match the snapshot
bytes.

Unknown license or use-policy metadata is warning-level because older or private
fixtures may not know the policy yet. Downstream review and result-acceptance
must treat those objects as unsupported until the policy is resolved.

## Runtime Traces

Runtime traces use `schemas/runtime_trace.schema.json`. Each row records the
task, adapter type, concrete tool name, redacted input and output summaries,
artifact paths, return code, duration, token use, cost, and any structured
error.

Traces are audit rows and eval inputs. They are not task-state transitions, and
they are not a substitute for human decisions in `decisions.md`.

## Dashboard Fields

The console snapshot includes a `runtime` group with:

- `trace_count`
- `evidence_object_count`
- `unsupported_or_stale_evidence_count`
- `latest_runtime_errors`
- validation errors and warnings

These fields are derived from `research_ops/runtime/` and remain read-only.
Runtime evidence is not accepted evidence until existing review and
result-acceptance gates say so.

Phase 4 claim and citation verification uses these same evidence objects and
snapshots to map explicit claims to source spans before accepted or
publication-oriented outputs can rely on them.

Phase 5 runtime evals use the same ledgers as fixture inputs. Eval suites live
under `research_ops/evals/` and compare quality changes without moving evidence
acceptance or task-state authority out of the original runtime, review, and
result-acceptance artifacts.

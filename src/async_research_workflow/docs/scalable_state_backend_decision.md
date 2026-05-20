# Scalable State Backend Decision

Created: 2026-05-20

## Decision

Keep `research_ops/` files and task-local lock directories as the default and
authoritative state backend. Do not introduce SQLite, an event log, an external
queue, or a derived read model as a required runtime dependency.

Add a read-only measurement surface instead:

```bash
async-research scaling assess research_ops
```

The command reports file-backed scaling friction and recommends one of:

- `repo_files_sufficient`
- `optional_rebuildable_index_cache_candidate`
- `external_queue_or_read_model_needs_human_decision`

## Evidence Considered

Phase 11 reviewed the friction signals requested by the roadmap:

| Signal | Measurement source | Current decision |
| --- | --- | --- |
| Trace file size | `research_ops/runtime/traces.jsonl` and `evidence_objects.jsonl` byte counts | Keep files; warn when ledgers exceed configured thresholds. |
| Dashboard latency | Timed read-only `console snapshot` render | Keep scans; warn when snapshot latency crosses threshold. |
| Lock contention | Count task `LOCK/` directories and stale locks | Keep locks; stale lock pressure is a measured warning, not a backend by itself. |
| Concurrent branch conflicts | Parallel merge packets and lock pressure | Keep deterministic merge packets and task locks as source of truth. |
| Eval-suite runtime pressure | Eval suite/run counts and case counts | Keep JSON fixtures; shard or index only when measured case counts justify it. |

The repository already contains guidance that the alpha target is tens to low
hundreds of tasks and ordinary Git review. Nothing in the delivered runtime,
eval, parallelism, or domain-pack phases proves a need for a required database
or external queue.

## Optional Future Backend Boundary

An optional backend is allowed only when measurements show file-backed scans are
hurting operators. Any backend must preserve these rules:

- Caches are rebuildable from `research_ops/`.
- Unique manual decisions, task state, accepted evidence, source policy, review
  artifacts, and human gates stay in files.
- CLI output explains which files produced each derived value.
- The package remains usable without optional backend dependencies.
- External queues or shared services require a human architecture decision.

## Current Thresholds

`async-research scaling assess` defaults to conservative warning thresholds:

- 250 task status files.
- 10 MB combined runtime trace/evidence ledgers.
- 500 eval cases across suite and run artifacts.
- 2000 ms console snapshot latency.
- 0 stale task locks older than 60 minutes.

These thresholds are not product claims. They are early warning defaults that
operators can override for local workspaces.

## Migration Posture

No migration is required for Phase 11. Existing workspaces remain valid. If an
optional index cache is introduced later, it must be generated under
`research_ops/` or another explicitly documented cache location and must be
safe to delete and rebuild.

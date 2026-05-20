# Runtime Artifacts

Runtime adapters write auditable artifacts here when a task contract explicitly
allows them.

Expected ledger locations:

- `runtime/traces.jsonl`
- `runtime/evidence_objects.jsonl`
- `runtime/snapshots/`

The default starter is read-only and contains no runtime evidence. Validate this
area with:

```bash
async-research runtime validate research_ops
```

Evidence objects are normalized inputs for claim verification and review. They
are not accepted evidence until existing review and result-acceptance gates say
so.

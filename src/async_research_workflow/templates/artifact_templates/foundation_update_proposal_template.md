# Foundation Update Proposal Template

Use this artifact when a worker needs to propose data or library foundation
updates without editing source-of-truth files directly.

Standalone proposal files belong under the source task's `artifacts/` directory,
for example `artifacts/foundation_update_proposal.json`.

Workers may also embed the same JSON in `worker_output.md` with an info string
that contains `foundation_update_proposal_v1`:

```json foundation_update_proposal_v1
{
  "proposal_version": "foundation_update_proposal_v1",
  "proposal_id": "PROP-0001",
  "source_task_id": "TASK-0001-example",
  "target": "data",
  "created_by": "worker",
  "rationale": "Why these foundation rows should change.",
  "operations": [
    {
      "operation_id": "OP-0001",
      "operation": "upsert_data_source",
      "target_path": "data_source_audit.md",
      "row_id": "DS-0001",
      "payload": {
        "source_id": "DS-0001",
        "source_name": "Example source"
      },
      "preserve_manual_notes": true
    }
  ]
}
```

Set `target` to `data` for data foundation rows and `library` for knowledge
library rows. Keep `target_path` workspace-relative and use only the canonical
foundation files. This proposal format is review input only; applying accepted
proposals is a separate guarded workflow.

For data proposals, reviewers can run:

```bash
async-research data inspect-proposals research_ops <proposal-source>
```

For library proposals, reviewers can run:

```bash
async-research library inspect-proposals research_ops <proposal-source>
```

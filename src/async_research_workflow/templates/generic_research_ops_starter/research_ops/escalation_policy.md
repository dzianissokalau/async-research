# Research Ops Escalation Policy

Policy version: `escalation_policy_v1.0`

Use this local policy before any autonomous worker, reviewer, or scheduler
continues a task that may require human judgment.

Executable gate:

```bash
python -m async_research_workflow.scripts.escalation_policy evaluate \
  research_ops/tasks/<TASK-ID> \
  --ops-dir research_ops
```

Apply a stop route:

```bash
python -m async_research_workflow.scripts.escalation_policy evaluate \
  research_ops/tasks/<TASK-ID> \
  --ops-dir research_ops \
  --apply
```

If the command exits `2`, stop autonomous work on that task. Resolve the
structured `human_gate` with:

```bash
python -m async_research_workflow.scripts.human_decision_log resolve-task \
  research_ops research_ops/tasks/<TASK-ID>
```

## Stop Triggers

Route to `needs_human` when deterministic gates identify missing source
approval, stale evidence, budget pressure, reviewer disagreement, ambiguous
scope, sensitive data, high-impact claims, or unverifiable assumptions.

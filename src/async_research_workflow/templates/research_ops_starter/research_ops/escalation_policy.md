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

If the command exits `2`, do not continue autonomous work on that task. Resolve
the structured `human_gate` with `async-research decision resolve-task`.

## Stop Triggers

Route to `needs_human` when any of these deterministic triggers fire:

| Trigger | Required Decision |
| --- | --- |
| `required_source_unaudited` | approve data use, request data-readiness, pause, or reject |
| `source_freshness_expired` | refresh source, approve stale use, pause, or reject |
| `accepted_memory_conflict` | decide whether accepted memory or new evidence changes |
| `reviewer_disagreement_beyond_threshold` | revise, reject, add review, or accept with caveats |
| `high_confidence_weak_evidence` | lower claim strength, revise, or reject |
| `task_exceeds_budget` | approve budget overrun, pause, or reject |
| `revision_limit_hit` | approve another revision, pause, or reject |
| `strategic_or_business_action` | approve/reject action use before it influences decisions |
| `accepted_memory_lacks_citations` | add citations, approve override, revise, or reject |
| `ambiguous_task_contract` | clarify scope, pause, or reject |
| `unauthorized_scope_change` | approve scope change, narrow task, or reject |
| `unverifiable_hidden_assumptions` | approve assumptions, request evidence, pause, or reject |

Full protocol: `async_research_workflow/escalation_policy_protocol.md`.

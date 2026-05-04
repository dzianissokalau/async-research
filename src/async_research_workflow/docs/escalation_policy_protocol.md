# Escalation Policy Protocol

Created: 2026-05-03

This document implements Phase 4 of the autonomy readiness plan. It defines
when the workflow must stop autonomous execution and ask for a structured human
decision.

## Purpose

Escalation is a fail-closed routing layer. It is used when a task is too risky,
ambiguous, stale, expensive, contradictory, or consequential for another worker
or reviewer to continue safely.

The policy is executable through:

```bash
python -m async_research_workflow.scripts.escalation_policy evaluate \
  research_ops/tasks/TASK-0001 \
  --ops-dir research_ops
```

Use `--apply` when the scheduler or worker should write the stop state:

```bash
python -m async_research_workflow.scripts.escalation_policy evaluate \
  research_ops/tasks/TASK-0001 \
  --ops-dir research_ops \
  --apply
```

If any trigger fires, the helper routes the task to `needs_human`, sets
`requires_human=true`, writes a structured `human_gate`, and exits `2` so the
scheduler stops expensive work.

## Structured Human Gate

Every `needs_human` task must include:

```json
{
  "human_gate_reason": "specific reason, not a vague placeholder",
  "human_gate": {
    "policy_version": "escalation_policy_v1.0",
    "trigger": "required_source_unaudited",
    "triggered_at": "2026-05-03T10:00:00Z",
    "severity": "high",
    "reason": "DS-0004 is not experiment-ready",
    "required_human_decision": "approve_data_use or create data_readiness task",
    "available_decisions": ["approve_data_use", "request_data_readiness", "pause", "reject"],
    "default_safe_action": "pause worker execution before using the source",
    "retry_behavior": "retry after data_source_audit.md records an experiment-ready source status",
    "ledger_update_behavior": "record the approval or rejection with human_decision_log.py before resuming"
  }
}
```

Validate existing human gates with:

```bash
python -m async_research_workflow.scripts.escalation_policy scan-needs-human research_ops
```

## Trigger Table

| Trigger | Condition | Severity | Destination | Required Human Decision | Default Safe Action | Retry Behavior | Ledger Update |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `required_source_unaudited` | Required `data_audit_refs` source is missing or not `available` / `usable_with_caveats` | high | `needs_human` | approve data use or create data-readiness task | pause source-dependent work | retry after source audit is ready | record approval/rejection in `decisions.md` |
| `source_freshness_expired` | Required source is older than the freshness window | high | `needs_human` | refresh source or approve stale use | pause source-dependent work | retry after refresh or stale-use approval | record refresh/approval in `decisions.md` |
| `accepted_memory_conflict` | Output explicitly conflicts with accepted memory | critical | `needs_human` | decide which evidence/memory changes | do not update accepted memory | retry after contradiction is resolved | record memory decision and artifacts |
| `reviewer_disagreement_beyond_threshold` | Review decisions split materially or claim-strength spread exceeds threshold | high | `needs_human` | choose revision, rejection, higher review, or caveated acceptance | do not accept | retry after revision or added review | record selected route |
| `high_confidence_weak_evidence` | Confidence is high while evidence/claim strength is weak or none | high | `needs_human` | lower claim, revise, or reject | block acceptance | retry after proportional claim restatement | record claim-strength decision |
| `task_exceeds_budget` | Logged task spend exceeds task budget | high | `needs_human` | approve budget overrun or stop | stop paid work | retry after budget approval or reduced scope | keep cost ledger and record approval |
| `revision_limit_hit` | Revision limit is reached | medium | `needs_human` | decide whether another revision is worth it | pause revisions | retry after explicit override/resume | record revision decision |
| `strategic_or_business_action` | Output proposes strategic, investment, pricing, public, policy, or business action | critical | `needs_human` | approve or reject action use | do not act on recommendation | retry after human approval or narrowing | record approval scope |
| `accepted_memory_lacks_citations` | Accepted-memory candidate lacks citations, URLs, or `DS-*` references | high | `needs_human` | add citations, revise, or reject | do not write accepted evidence | retry after citation repair | record any citation override |
| `ambiguous_task_contract` | `task.md` is missing, unresolved, or allowed paths are unclear | medium | `needs_human` | clarify, pause, or reject | pause before work | retry after contract is clarified | record clarification decision |
| `unauthorized_scope_change` | Output requests or performs scope expansion outside task contract | high | `needs_human` | approve scope change, narrow task, or reject | stop beyond original scope | retry after task contract update | record scope decision |
| `unverifiable_hidden_assumptions` | Output depends on assumptions reviewers cannot verify | high | `needs_human` | approve assumptions, request evidence, or reject | do not accept | retry after assumptions are explicit/testable | record assumption decision |

## Prompt Obligations

Workers and reviewers must read the local policy file:

```text
research_ops/escalation_policy.md
```

They must run `escalation_policy.py evaluate` before moving a risky task forward.
If it exits `2`, they must stop and leave the task in `needs_human`.

## Resolution

Never resolve a human gate by editing `status.json` directly. Use:

```bash
python -m async_research_workflow.scripts.human_decision_log resolve-task \
  research_ops \
  research_ops/tasks/TASK-0001 \
  --decision resume \
  --status ready_for_worker \
  --reason "human approved the recorded escalation gate" \
  --approver "<human-name>"
```

## Acceptance Criteria

This layer is implemented when:

- the same task evaluates to the same route and triggers on repeated runs;
- every `needs_human` task has a structured `human_gate`;
- human gates list clear available decisions;
- vague `needs_human` placeholders fail validation;
- workers and reviewers are instructed to use this policy before continuing.

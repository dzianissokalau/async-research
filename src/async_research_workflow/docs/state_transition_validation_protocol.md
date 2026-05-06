# State Transition Validation Protocol

Created: 2026-05-02

This document implements the P0 state transition validation requirement from the feedback hardening plan.

## Purpose

Prevent autonomous agents from silently corrupting the task state machine.

The workflow state machine is useful only if task status changes are valid. A worker should not be able to mark a task as `accepted`, and a rejected task should not be able to jump back to `in_progress`.

## Required Status Fields

Every `status.json` should include:

```json
{
  "schema_version": "1.0",
  "previous_status": "ready_for_worker",
  "status": "in_progress",
  "last_transition_reason": "worker_claimed"
}
```

For newly created tasks, `previous_status` may be `null` and `status` may be one of:

```text
inbox
ready_for_planning
ready_for_worker
```

There is one fail-closed recovery exception: `previous_status = null` may move to
`status = needs_human` only when `last_transition_reason = status_json_recovery`.
This is reserved for `recover_status_json.py` after the previous status cannot be
trusted because `status.json` was malformed, missing, or invalid.

## Allowed Transitions

Initial transition allowlist:

```text
null -> inbox | ready_for_planning | ready_for_worker
null -> needs_human only with last_transition_reason = status_json_recovery
inbox -> ready_for_planning | paused | rejected
ready_for_planning -> ready_for_worker | needs_human | paused | rejected
ready_for_worker -> in_progress | needs_human | paused | rejected
in_progress -> awaiting_review | needs_human | paused | rejected
awaiting_review -> single_review | panel_review | needs_human
single_review -> accepted | needs_revision | needs_human | paused | rejected | panel_review
panel_review -> accepted | needs_revision | needs_human | paused | rejected
needs_revision -> ready_for_worker | needs_human | paused | rejected
needs_human -> ready_for_worker | paused | rejected
accepted -> synthesized
paused -> terminal
rejected -> terminal
synthesized -> terminal
```

Unchanged status is allowed only when a role writes supporting artifacts without routing the task, such as a methodology reviewer writing `reviews/methodology.md` while the task remains in `panel_review`.

## Advanced/Internal Helper Script

Transition validation is an advanced/internal helper primitive. Public users
should normally move state through workflow commands such as `decision`,
`revision`, and `review aggregate`.

Use:

```text
async_research_workflow/scripts/validate_transition.py
```

Advanced/internal validation for one task:

```bash
python -m async_research_workflow.scripts.validate_transition \
  research_ops/tasks/TASK-0001/status.json
```

Advanced/internal validation for a task folder:

```bash
python -m async_research_workflow.scripts.validate_transition \
  research_ops/tasks/TASK-0001
```

Advanced/internal transition table listing:

```bash
python -m async_research_workflow.scripts.validate_transition --list
```

Exit codes:

| Code | Meaning |
| ---: | --- |
| 0 | transition valid |
| 2 | transition invalid |
| 3 | unknown status |
| 4 | missing or malformed status file |

## Agent Write Rule

Any agent changing task status must:

1. read the current `status`
2. write that value to `previous_status`
3. write the new `status`
4. write `last_transition_reason`
5. run `validate_transition.py`
6. if validation fails, stop and route to human or leave the task unchanged

Example:

```json
{
  "previous_status": "in_progress",
  "status": "awaiting_review",
  "last_transition_reason": "worker_completed_output"
}
```

## Role Rules

Worker may route:

```text
ready_for_worker -> in_progress
in_progress -> awaiting_review | needs_human | paused | rejected
```

Primary reviewer may route:

```text
awaiting_review -> single_review | panel_review
single_review -> accepted | needs_revision | needs_human | paused | rejected | panel_review
```

Specialist reviewer usually does not route. It may leave:

```text
panel_review -> panel_review
```

Aggregator may route:

```text
panel_review -> accepted | needs_revision | needs_human | paused | rejected
```

Human may route:

```text
needs_human -> ready_for_worker | paused | rejected
```

Transitions out of `needs_human` require a matching structured row in
`research_ops/decisions.md`. The validator infers the decision log path for
normal task folders and fails with `missing_human_decision` when the row is
absent.

Preferred resolver:

```bash
async-research decision resolve-task \
  research_ops \
  research_ops/tasks/TASK-0001 \
  --decision resume \
  --reason "Human approved a narrowed retry" \
  --approver "human-owner" \
  --status ready_for_worker
```

## GitHub Actions Guidance

After a worker or reviewer step, validate changed task statuses before creating a pull request:

Advanced/internal transition helper:

```bash
python -m async_research_workflow.scripts.validate_transition \
  research_ops/tasks/TASK-0001
```

When the selected task ID is not known ahead of time, the worker should report the task path in its final message and a wrapper script can validate that path.

## Acceptance Tests

The transition validator is considered implemented when:

- `ready_for_worker -> in_progress` passes
- `in_progress -> accepted` fails
- `rejected -> in_progress` fails
- initial `null -> ready_for_worker` passes
- recovery `null -> needs_human` passes only with `status_json_recovery`
- `needs_human -> ready_for_worker` fails without a matching decision row
- `needs_human -> ready_for_worker` passes after a matching decision row exists
- unknown status fails
- missing `last_transition_reason` fails when status changes
- unchanged `panel_review -> panel_review` passes

## Relationship To Atomic Locking

Atomic locking prevents two workers from claiming the same task.

State transition validation prevents the winning worker or reviewer from writing an invalid state.

Both are required before recurring autonomous jobs should run.

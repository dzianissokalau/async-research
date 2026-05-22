# First Success Quickstart

Use this when you want one quiet path from a fresh workspace to a reviewed
operator surface. It assumes `async-research` is installed; see the top-level
[README](../../../README.md) for install options and the full command map.

## 1. Create The Generic Workspace

Run these from the research repo where `research_ops/` should live:

```bash
async-research init research_ops
async-research schema-check research_ops
async-research mode show research_ops
async-research mode validate research_ops
async-research readiness research_ops --dry-run
async-research health research_ops --dry-run
async-research surface update research_ops
async-research surface validate research_ops
```

Stop if any command returns non-OK JSON; repair the reported file before worker
or reviewer work.

Ask: "How autonomous should this run be?" New workspaces start in `supervised`
mode: routine policy-backed gates can continue with audit rows, while hard
stops still interrupt. Use `manual` for explicit approval on most transitions;
existing workspaces without `interaction_mode.json` stay manual-compatible until
an explicit mode set succeeds.

## 2. Pick One Task

The generic starter has no live task on purpose. After a planner or human has
created a bounded task and a worker has written `worker_output.md`, point
`TASK` at that task folder:

```bash
TASK=research_ops/tasks/TASK-0001-example
```

The task should be in `awaiting_review`, with `status.json` and
`worker_output.md` present. If no task exists yet, stop here and create one from
the task contract instead of improvising state.

## 3. Author One Review

Preview the conservative scaffold first:

```bash
async-research review draft "$TASK" --role primary
```

Submit the first review through the public command. For a first pass through the
workflow, `needs_human` is the safest route because it proves the loop without
putting unapproved evidence into accepted memory:

```bash
async-research review submit "$TASK" \
  --role primary \
  --decision needs_human \
  --claim-strength none \
  --confidence 0.5 \
  --concern "First operator pass; keep the result out of accepted memory until a human checks it."
```

## 4. Aggregate And Refresh Surfaces

Run the aggregate as a dry run first:

```bash
async-research review aggregate "$TASK" --dry-run
```

If the dry run returns OK, write the aggregate route. On the first pass, include
`--record-review-start`; it records the missing review-start transition when
needed and still writes the aggregate route for `needs_human`:

```bash
async-research review aggregate "$TASK" --record-review-start
```

Then refresh accepted-memory and operator surfaces:

```bash
async-research accepted update research_ops
async-research accepted revalidation research_ops --write-schedule
async-research surface update research_ops
async-research surface validate research_ops
async-research health research_ops
```

You have completed the first pass when the surface validation succeeds and the
task route is visible in `daily_status.md` and `human_review_queue.md`.

## 5. Where To Go Next

- [Task Contracts](./task_contracts.md)
- [Structural Reviewer Isolation Protocol](./reviewer_isolation_protocol.md)
- [Algorithmic Review Aggregation Protocol](./algorithmic_review_aggregation_protocol.md)
- [Operational Readiness Runbook](./operational_readiness_runbook.md)

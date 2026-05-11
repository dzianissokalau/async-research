# First Success Quickstart

Use this when you want one quiet path from a fresh workspace to a reviewed
operator surface. It assumes `async-research` is already installed; see the
top-level [README](../../../README.md) for install options and the full command
map.

## 1. Create The Generic Workspace

Run these from the research repo where `research_ops/` should live:

```bash
async-research init research_ops
async-research schema-check research_ops
async-research readiness research_ops --dry-run
async-research health research_ops --dry-run
async-research surface update research_ops
async-research surface validate research_ops
```

Stop if any command returns non-OK JSON. Repair the reported file before
starting worker or reviewer work.

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

Submit the first review through the public command. For a first dry run of the
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

Use a real review decision once you have inspected the worker output.

## 4. Aggregate And Refresh Surfaces

Run the aggregate as a dry run first:

```bash
async-research review aggregate "$TASK" --dry-run
```

If the dry run says the review-start transition is missing, let the public
aggregate command record it:

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

- For task fields and worker expectations, read
  [Task Contracts](./task_contracts.md).
- For review isolation, read
  [Structural Reviewer Isolation Protocol](./reviewer_isolation_protocol.md).
- For aggregate routing, read
  [Algorithmic Review Aggregation Protocol](./algorithmic_review_aggregation_protocol.md).
- For repair and operations, read
  [Operational Readiness Runbook](./operational_readiness_runbook.md).

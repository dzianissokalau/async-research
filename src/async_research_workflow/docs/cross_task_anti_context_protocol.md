# Cross-Task Anti-Context Protocol

Created: 2026-05-02

This document implements P2-6 cross-task anti-context injection for the async research workflow.

## Purpose

The workflow should not rediscover the same accepted finding or repeat a known failed approach. Planner-created tasks must carry concise anti-context so workers know what not to redo.

## Required Helper

Use:

```text
async_research_workflow/examples/scripts/generate_anti_context.py
```

Build anti-context for a proposed task:

```bash
python3 async_research_workflow/examples/scripts/generate_anti_context.py build \
  research_ops \
  --title "EPC premium during energy shocks" \
  --task-dir research_ops/tasks/TASK-0007-epc-premium-energy-shocks
```

The helper writes:

```text
research_ops/tasks/<task>/anti_context.md
```

and injects the same section into:

```text
research_ops/tasks/<task>/task.md
```

## Required Section

Each generated section includes:

```text
## Cross-Task Anti-Context

### Similar Accepted Findings
...

### Similar Rejected Approaches
...

### Known Failure Modes
...

### Do-Not-Repeat Warnings
...
```

If no similar prior work is found, the section still says so and asks the worker to state novelty and cheap kill criteria explicitly.

## Sources

The helper checks:

- `research_ops/accepted_outputs_index.md`
- `research_ops/discovery/rejected_ideas.md`
- `research_ops/rejected_ideas.md`
- rejected or paused `research_ops/tasks/*/status.json`
- short summaries from rejected or paused task outputs

Accepted matches create duplicate/novelty warnings. Rejected matches create failure-mode and do-not-repeat warnings.

## Planner Rule

Before promoting an inbox or discovery item into a task folder:

1. refresh the accepted outputs index
2. create the task folder and draft `task.md`
3. run `generate_anti_context.py build ... --task-dir <task-dir>`
4. revise task scope if the anti-context shows the idea is duplicate or repeats a known failure
5. leave the anti-context section in `task.md`

## Worker Rule

Workers must read `task.md` and `anti_context.md` before writing output. They should explicitly address any do-not-repeat warning or route to `needs_human` if the task repeats a known failure without a new angle.

## Acceptance Checks

P2-6 is implemented when:

- a task plan references similar accepted prior work when present
- a task plan references similar rejected prior work when present
- `anti_context.md` gives the worker a concise anti-context section
- do-not-repeat warnings are generated from accepted/rejected matches

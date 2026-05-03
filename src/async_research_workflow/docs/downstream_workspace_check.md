# Downstream Workspace Check

Use this checklist when migrating an existing research repo to the packaged CLI.
Run the commands from the target research repo after installing this package.

```bash
async-research schema-check research_ops
async-research readiness research_ops --dry-run
async-research health research_ops --dry-run
async-research surface validate research_ops
async-research source validate research_ops
async-research cost summary research_ops
```

For a reviewed task, validate the result-acceptance gate with the task directory
that exists in your workspace:

```bash
async-research result-acceptance research_ops/tasks/TASK-0001-example --ops-dir research_ops
```

Keep any older repo-local scripts until the packaged CLI passes against the real
workspace and scheduled jobs have been updated to call `async-research`.

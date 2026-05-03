# Research Ops Starter Workspace

This is a clean starter workspace for the async research workflow alpha package.
The seed domain is real-estate market research, but the files are intended to
be edited for each research project.

Durable state lives in this folder. Use `async-research` commands to validate
transitions, source governance, health, accepted evidence, cost, and human
review surfaces.

## First Commands

```bash
async-research schema-check research_ops
async-research readiness research_ops --dry-run
async-research health research_ops --dry-run
async-research surface update research_ops
async-research surface validate research_ops
```

## Starter Cadence

- Run one bounded worker task at a time.
- Run result acceptance before adding durable evidence.
- Keep direct experiment launch blocked until a candidate passes setup-task gates.
- Use `human_review_queue.md` for exception-based supervision.

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
async-research idea catalog init research_ops --dry-run
async-research readiness research_ops --dry-run
async-research health research_ops --dry-run
async-research surface update research_ops
async-research surface validate research_ops
```

## Idea Catalog

`discovery_inbox.md` is the short-lived buffer for rough discoveries.
`ideas/` is the durable portfolio surface for cataloged ideas. The generated
blocks in `ideas/idea_catalog.md` and `ideas/prioritization.md` are maintained
by tooling in later phases; keep manual notes outside those blocks.

Catalog maintenance must not edit `queue.md` or create task folders. A planner
or human-approved helper turns catalog ideas into bounded execution tasks.

Planner promotion should stay catalog-first:

```bash
async-research idea catalog validate research_ops
async-research idea catalog list research_ops --status promote
async-research idea promote research_ops IDEA-0001 --dry-run
```

Create a task folder only from a successful, unblocked promotion proposal.
Append `queue.md` only after the task files, anti-context, source checks, and
listed validation commands are coherent.

## Starter Cadence

- Run one bounded worker task at a time.
- Run result acceptance before adding durable evidence.
- Keep direct experiment launch blocked until a candidate passes setup-task gates.
- Use `human_review_queue.md` for exception-based supervision.

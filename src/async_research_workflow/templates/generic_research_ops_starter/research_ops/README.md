# Generic Research Ops Workspace

This is a domain-neutral starter workspace for the async research workflow
alpha package. It contains the durable files needed for queue, evidence,
source governance, review, cost, metrics, and human decisions, but it does not
seed live tasks or project-specific sources.

Generated health state is intentionally absent from the template. Run the
health or readiness commands after editing the workspace so `health_report.json`
reflects the current repo state.

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

## First Setup Steps

1. Add project-specific sources to `data_source_audit.md`.
2. Add discovery sources to `discovery/source_register.md`.
3. Add one small task under `tasks/` and one row in `queue.md`.
4. Run the health and readiness checks before scheduling workers.

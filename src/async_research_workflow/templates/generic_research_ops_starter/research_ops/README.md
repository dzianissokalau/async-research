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

Catalog maintenance must not edit `queue.md` or create task folders. Promotion
write mode is the guarded helper that turns one catalog idea into one bounded
execution task.

Planner promotion should stay catalog-first:

```bash
async-research idea catalog validate research_ops
async-research idea catalog list research_ops --status promote
async-research idea promote research_ops IDEA-0001 --dry-run
async-research idea promote research_ops IDEA-0001 --write --preflight-hash <hash>
async-research idea catalog dashboard research_ops
```

Let promotion write create the task folder, `queue.md` row, `inbox.md` proposal
reference, and idea `promoted_task_id` only after a successful, unblocked
dry-run. The dashboard should show the promoted idea with `link_status=available`.

## First Setup Steps

1. Add project-specific sources to `data_source_audit.md`.
2. Add discovery sources to `discovery/source_register.md`.
3. Add one small task under `tasks/` and one row in `queue.md`.
4. Run the health and readiness checks before scheduling workers.

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
async-research source validate research_ops
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

## Data Foundations

`data_source_audit.md` remains the source-governance register. The `data/`
folder is the planning layer for dataset readiness:

- `data/data_catalog.md` inventories the starter data sources.
- `data/data_access.md` records public access routes and checks.
- `data/join_map.md` records plausible joins and caveats.
- `data/known_data_gaps.md` tracks data gaps that block ideas or tasks.
- `data/profiles/` contains reviewed starter profiles for `DS-0001`,
  `DS-0002`, and `DS-0003`.

Source governance still runs through `async-research source`. After editing
profiles, access notes, joins, or data gaps, run
`async-research data validate research_ops` before review.

## Starter Cadence

- Run one bounded worker task at a time.
- Run result acceptance before adding durable evidence.
- Keep direct experiment launch blocked until a candidate passes setup-task gates.
- Use `human_review_queue.md` for exception-based supervision.

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
async-research library init research_ops --dry-run
async-research library validate research_ops
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
async-research idea metrics research_ops
async-research idea trace research_ops IDEA-0001
```

Let promotion write create the task folder, `queue.md` row, `inbox.md` proposal
reference, and idea `promoted_task_id` only after a successful, unblocked
dry-run. The dashboard should show the promoted idea with `link_status=available`.
Use `idea trace` to inspect why a task exists, and `idea metrics` to review
read-only lifecycle timings; missing timestamps render as `unavailable`.

## Knowledge Library

`research_ops/library/` is the durable background-memory surface for reviewed
sources, topic summaries, claim memory, methods, open questions, and update
provenance. Empty library files are valid during cold start.

It is separate from accepted-output memory: `accepted_outputs_index.md` stores
reviewed task results, while `library/` stores background sources, caveats, and
open questions that can inform future planning and review.

- `library/source_library.md` owns `LIT-*` source IDs.
- `library/knowledge_index.md` stores topic summaries with source refs.
- `library/claim_map.md` stores durable claim memory and caveats.
- `library/method_index.md` stores methods, assumptions, and risks.
- `library/open_questions.md` stores gaps that may become future tasks.
- `library/library_update_log.md` records reviewed update provenance.

Run `async-research library init research_ops --dry-run` to inspect missing
library starter files in an existing workspace. Use `--write` to add only
missing files; existing notes are preserved. Run
`async-research library validate research_ops` after editing library tables.

`literature_extract` tasks can propose library updates without writing outside
their task folder. Worker output should list proposed generated-table rows for
the relevant `library/*.md` files, the exact files that would change, reviewer
notes for weak or disputed sources, and the `library_update_log.md` provenance
row. Reviewers can run
`async-research library inspect-proposals research_ops <proposal-source>` before
apply. For accepted tasks, use
`async-research library apply-proposals research_ops <proposal-source> --dry-run`
to review the exact edits and preflight hash, then rerun with `--write
--preflight-hash <hash>` only after acceptance proof is in place. The write path
uses a lock, preserves notes outside generated blocks, reruns
`async-research library validate research_ops`, and rolls back on validation
failure.

## Deliverable Maturity

`research_ops/deliverables/` tracks final-output maturity separately from task
acceptance. `deliverable_manifest.json` stores output type, target audience,
target venue, source task links, manuscript gate statuses, critic review
metadata, review-response matrix rows, review independence, and open gaps. Gate
statuses are `not_required`, `missing`, `partial`, `passed_with_caveats`,
`passed`, or `waived_by_human`; waivers require human rationale. An accepted
task can be linked as source evidence, but it does not by itself make a paper,
memo, or report shareable or submission-ready. Working papers and
submission-ready manuscripts need a distinct critic review with sufficient
independence, and critical or major critique rows must be closed or explicitly
human-waived in the response matrix.
Use `deliverables/templates/` for the manifest, manuscript checklist, critic
prompt, response matrix, and maturity-specific task templates.

```bash
async-research deliverable init research_ops --title "Draft title" --output-type working_paper --target-maturity internal_draft
async-research deliverable critic research_ops DELIV-0001 --independence-type separate_agent --confidence 0.8 --recommended-maturity-ceiling working_paper
async-research deliverable response research_ops DELIV-0001 --source-review CRITIC-0001 --severity major --target-section Methods --issue "Clarify method" --decision accepted --required-change "Add method detail" --owner "paper owner"
async-research deliverable check research_ops DELIV-0001
```

Packaged templates for manifests, manuscript checklists, critic prompts,
response matrices, and maturity-specific drafting/revision tasks are listed in
`deliverables/templates/README.md`.

## Data Foundations

`data_source_audit.md` remains the source-governance register. The `data/`
folder is the planning layer for dataset readiness:

- `data/data_catalog.md` inventories governed datasets.
- `data/data_access.md` records how approved sources can be accessed without
  storing secrets.
- `data/join_map.md` records plausible joins and caveats.
- `data/known_data_gaps.md` tracks data gaps that block ideas or tasks.
- `data/profiles/README.md` defines the `DS-0000.md` profile contract.

Profiles should be named like `data/profiles/DS-0001.md`, declare the same
`source_id` inside the file, and point back to one audit row.
After editing data foundation files, run
`async-research data validate research_ops` before review.

Data-readiness workers can propose source/profile/catalog/access/join/gap
updates with `foundation_update_proposal_v1`. Reviewers can run
`async-research data inspect-proposals research_ops <proposal-source>`, then use
`async-research data apply-proposals research_ops <proposal-source> --dry-run`
for accepted tasks. Write mode requires `--write --preflight-hash <hash>`,
accepted task or review proof, a foundation apply lock, and post-write
`source validate`/`data validate`; failed validation rolls back touched files.

## First Setup Steps

1. Add project-specific sources to `data_source_audit.md`.
2. Add durable background sources and caveats under `library/` when available.
3. Add matching data catalog, access, gap, join, and profile notes under `data/`.
4. Add discovery sources to `discovery/source_register.md`.
5. Add one small task under `tasks/` and one row in `queue.md`.
6. Run the health and readiness checks before scheduling workers.

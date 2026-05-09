# Task Contracts

## Queue Entry

Use `research_ops/queue.md` as a human-readable index.

Example:

```markdown
| ID | Status | Priority | Type | Title | Human needed | Updated |
| --- | --- | ---: | --- | --- | --- | --- |
| TASK-0001 | ready_for_worker | 2 | data_readiness | Land Registry PPD readiness | no | 2026-05-01 |
```

The authoritative machine state lives in each task's `status.json`.

## Discovery Inbox Entry

Use `research_ops/discovery_inbox.md` for autonomous idea discovery outputs.

Example:

```markdown
| ID | Status | Weighted score | Mission policy | Title | Required data | MVP test | Kill reason | Next task |
| --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| IDEA-0007 | candidate | 19.5 | real_estate_research_v1.0 | EPC premium during energy shocks | EPC, PPD, energy CPI | London flats 2018-2025 | reject if EPC-sale matching is weak | data_readiness |
```

Discovery entries are not execution tasks. The planner must capture promising
entries into the durable idea catalog before creating `research_ops/inbox.md`
or `queue.md` execution work.

## Idea Evaluation

Before a candidate is added to the discovery inbox or promoted into a task, run
mission policy validation, mission scoring, and idea-evaluation validation:

Mission policy validation is an advanced/internal helper. The scoring and
idea-validation commands are public:

```bash
python -m async_research_workflow.scripts.validate_mission_policy \
  async_research_workflow/mission_policy.json

async-research idea score \
  research_ops/discovery/IDEA-0001.json \
  --budget-mode auto \
  --ops-dir research_ops

async-research idea validate \
  research_ops/discovery/IDEA-0001.json \
  --ops-dir research_ops
```

`validate_idea_evaluation.py` writes `candidate.idea_evaluation` when the
candidate passes. The planner may promote only when:

```json
{
  "idea_evaluation": {
    "promotion_readiness": {
      "planner_may_promote": true
    }
  }
}
```

Rejected and parked candidates must be written to
`research_ops/discovery/rejected_ideas.md` before idea-evaluation validation.
Duplicate, near-duplicate, sensitive-data, failed-gate, or direct-experiment
routes fail closed.

`score_idea_candidate.py` refuses invalid mission policies. Direct
`experiment_plan` requests are rerouted to `data_readiness` before idea
evaluation.

## Catalog Promotion Write

The durable planner path is:

```text
discovery_inbox.md
-> async-research idea capture ... --write
-> research_ops/ideas/IDEA-0001.json
-> async-research idea promote research_ops IDEA-0001 --dry-run
-> async-research idea promote research_ops IDEA-0001 --write --preflight-hash <hash>
-> reserved TASK folder + queue.md row + promoted_task_id
```

The promotion command is split into a read-only planning pass and a guarded
write pass. The dry-run proposal remains authoritative for task type, scope,
reserved task identity, validation commands, review tier, and
`evidence_support.status`. `thin_evidence` means there are no support refs or
source discovery context; `missing_library_support` means `library_refs` did
not resolve against row-level source IDs in the generated
`research_ops/library/source_library.md` block. Write mode must
receive the matching `--preflight-hash`; it creates one reserved task folder,
appends one `queue.md` row, appends the planner-facing proposal reference to
`inbox.md`, updates the selected idea's `promoted_task_id` and proposal refs,
and regenerates catalog projections under the catalog lock.

Before writing a task from a catalog idea, run:

```bash
async-research idea catalog validate research_ops
async-research idea catalog show research_ops IDEA-0001
async-research idea promote research_ops IDEA-0001 --dry-run
async-research idea promote research_ops IDEA-0001 --write --preflight-hash <hash>
```

Use write mode only when dry-run returns `action=idea_promotion_planned` and
`ok=true`. Do not create tasks from blocked proposals. Duplicate or
near-duplicate ideas require `--allow-duplicate` plus a recorded human decision
or explicit planner note explaining the new angle. High-risk task writes such
as duplicates, direct `experiment_plan`, `review_tier >= 2`, `max_minutes > 75`,
blocking catalog validation, or related non-matching artifacts also require
`--human-override` backed by that recorded decision.

Before running promotion dry-run, scan `research_ops/tasks/*/status.json` for
`catalog_idea_id` matching the candidate idea. If a task already references the
idea, skip the idea unless a recorded human decision or explicit planner note
explains the different follow-up task type or scope.

Write mode uses `proposal.proposed_task_id` and `proposal.proposed_task_slug` as
the reserved task identity. V2.5-or-newer proposals derive the TASK ID from the
IDEA numeric suffix. Do not hand-create a fallback task from
`proposal.task_markdown_draft` unless a recovery runbook explicitly instructs a
human to do so. Preserve these proposal fields unless a human-approved reason is
recorded:

- `task_type`
- `objective`
- `scope`
- `allowed_paths`
- `data_refs`
- `max_minutes`
- `max_turns`
- `kill_reason`
- `validation_commands`
- `review_policy`

The write transaction stages `task.md` and `status.json`, validates the staged
task folder, appends `queue.md`, updates the canonical idea, and rolls back if
post-write consistency fails. If the proposal routes to `literature_extract`,
keep the task cheap and evidence gathering focused. If it routes to
`data_readiness`, include source/audit checks before experiment planning. If it
routes to `experiment_plan`, the referenced `DS-0000` data refs must pass
`async-research source check-experiment` before worker execution.

After write mode succeeds, verify the catalog and dashboard instead of parking
the idea manually:

```bash
async-research idea catalog validate research_ops
async-research idea catalog dashboard research_ops
```

The promoted idea should have `status=promoted`, `promoted_task_id=<TASK-ID>`,
and a dashboard `sections.idea_to_task_links` row with `link_status=available`.
Do not run the former v1 park closeout after a successful or idempotent
promotion write. A stale cached planner prompt that runs
`async-research idea park ... --reason "promoted to <TASK-ID>" --write` would
replace `status=promoted` and break the `promoted_task_id` dashboard link.
If write mode returns `idea_promotion_task_already_written`, treat it as
idempotent success only when the task folder, queue row, and
`promoted_task_id` all match the selected idea. If it returns
`promotion_preflight_changed`, rerun dry-run before retrying. If it returns
`promotion_proposal_recovery_required`, `promotion_task_recovery_required`, or a
recovery payload with `rollback_ok=false` or `requires_human=true`, stop and
surface the recovery payload for human repair.
It prevents the same `promote` idea from being selected again while preserving
the task reference and revisit condition in the catalog decision history.

## Knowledge Library Phase 0

Knowledge Library V1 uses `research_ops/library/` as the canonical workspace
path. Do not create a parallel `research_ops/knowledge/` namespace. `LIT-*`
references identify source rows in `library/source_library.md`; they are
background memory for planning and review, not final source-level citation for
accepted claims.

For V1, keep the executable task type as `literature_extract` and use the
library-update proposal expectations below. Do not add a separate
`library_review` task type unless the task schemas, promotion helpers,
review-tier defaults, and docs are updated together.

Library source statuses are:

```text
candidate
trusted
context_only
disputed
deprecated
```

Library trust tiers are:

```text
primary
supporting
background
weak
unknown
```

Workers may propose updates to `source_library.md`, `knowledge_index.md`,
`claim_map.md`, `method_index.md`, `open_questions.md`, and
`library_update_log.md`, but they must not write directly to
`research_ops/library/` unless the task explicitly grants those paths and the
reviewed update is traceable in `library_update_log.md`. Library maintenance
must not edit `queue.md` or create task folders.

The planned read-only validator contract is:

```bash
async-research library validate research_ops
```

Exit `0` means the library contract is valid. Exit `2` means warning-only
library findings with usable state. Exit `4` means malformed populated library
state. Empty or missing library files are cold-start warnings, not blockers for
discovery, idea scoring, or data readiness.

## Knowledge Library Phase 5 Literature Extraction

`literature_extract` is the bounded V1 task type for creating or improving
library state. The proposal must specify the topic or source set, allowed source
list, browsing allowance, extraction fields, source status and trust tier
rules, claim-strength rules, required caveats, anti-context and dead ends,
proposed output update targets, and `async-research library validate
research_ops`.

Workers propose generated-block rows in `worker_output.md` rather than editing
`research_ops/library/` directly. They may propose updates to
`source_library.md`, `knowledge_index.md`, `claim_map.md`, `method_index.md`
where relevant, `open_questions.md`, and `library_update_log.md`, and must list
the exact files that would be updated. A task may write those library files only
when its `allowed_paths` explicitly grants them. Accepted updates must be
traceable to the reviewed task through `library_update_log.md`.

Reviewer output should be able to accept, revise, reject, or route the proposed
library update to a human. Weak, disputed, deprecated, and context-only sources
need explicit reviewer notes. High-stakes claims and any proposed `strong`
claim require human approval before publication use.

Library-dependent routes resolve `LIT-*` support from row-level `source_id`
values parsed from the generated `library/source_library.md` block. Generic text
presence in notes, headings, examples, or malformed tables does not satisfy
library support.

## Exploration Cycle

Use `research_ops/discovery/source_register.md` as the approved discovery source
list. `idea_discovery` workers and discovery scouts must produce an executable
exploration-cycle contract in `exploration_cycle.json` or a fenced JSON block in
`worker_output.md`.

Validate it before updating the discovery inbox:

```bash
async-research exploration validate \
  research_ops/tasks/TASK-0002/worker_output.md \
  --ops-dir research_ops \
  --task-dir research_ops/tasks/TASK-0002
```

The validator enforces source-register references, explicit cycle limits,
candidate category tags, duplicate checks, parked/rejected revisit conditions,
promotion limits, human-load limits, and the direct-experiment block. Failed
validation routes to revision or human review; it must not update
`discovery_inbox.md`.

## Accepted Outputs Index

Use `research_ops/accepted_outputs_index.md` as compact memory for accepted evidence.

Example:

```markdown
| date | task_id | title | key_finding | claim_strength | evidence_link | followups |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-05-02 | TASK-0007 | EPC match readiness | EPC-to-sale matching is plausible after address normalization. | suggestive | tasks/TASK-0007/worker_output.md | Profile unmatched certificates |
```

Update it with:

```bash
async-research accepted update research_ops
```

Before promoting a related idea or task, check for overlap:

```bash
async-research accepted check-duplicate \
  research_ops \
  --title "EPC match readiness"
```

## Result Acceptance

Accepted and rejected review aggregates must pass result acceptance before they
become durable evidence or rejection history:

```bash
async-research result-acceptance \
  research_ops/tasks/TASK-0001 \
  --ops-dir research_ops \
  --write \
  --update-ledgers
```

`aggregate_reviews.py` runs this automatically for `accepted` and `rejected`
routes. Accepted routes write `review_panel/result_acceptance.json` and update
`research_ops/evidence_ledger.md`. Rejected routes update
`research_ops/rejected_results.md`.

For `run_analysis` and `evaluate_results` tasks, `worker_output.md` must include
a fenced JSON block following
`async_research_workflow/templates/artifact_templates/result_summary_template.md`. Predictive
results cap at `moderate`, causal claims without identification tests cap at
`weak`, and public/high-stakes or strong claims need human approval.

## Task Folder

```text
research_ops/tasks/TASK-0001-land-registry-readiness/
  LOCK/
    owner.json
  task.md
  anti_context.md
  status.json
  worker_output.md
  reviews/
    primary.md
    methodology.md
    skeptic.md
  review_panel/
    aggregate.md
  artifacts/
```

`LOCK/` exists only while a worker owns the task. It is created atomically and is the authoritative worker claim. The `lock_owner` and `lock_expires_at` fields in `status.json` mirror the lock for observability.

## `task.md`

Template:

```markdown
# TASK-0001: Land Registry PPD data readiness

## Objective

Produce a data-readiness note for using HM Land Registry Price Paid Data as the sale-price outcome.

## Scope

- Use only existing repo files and cited official docs already linked in the task.
- Do not browse unless `allow_browsing` is true in `status.json`.
- Do not write outside this task folder.

## Required Output

Write `worker_output.md` with:

- summary
- data coverage
- join keys
- known quality risks
- required validation checks
- recommendation: `ready`, `usable_with_caveats`, `blocked`, or `needs_human`
- for `data_readiness`: profile draft/update, recommended audit status, access
  check result, field/grain coverage, join feasibility, known limitations,
  recommended next task, and kill reason if data is unusable

## Acceptance Criteria

- All required sections are present.
- Caveats are explicit.
- No unsupported claims.
- Follow-up tasks are listed separately.
- For `data_readiness`, audit/profile changes are traceable to the reviewed
  task output and pass `async-research source validate` plus
  `async-research data validate`.

## Context

- Relevant source: `automated_research_system_design/artifact_contracts.md`
- Relevant source: `re_trends_research` data library if available locally

## Cross-Task Anti-Context

Generated by `async-research anti-context build`. Workers must read this before starting.
```

Every promoted or planner-created task should also have `anti_context.md`,
generated with:

```bash
async-research anti-context build \
  research_ops \
  --title "Land Registry PPD data readiness" \
  --task-dir research_ops/tasks/TASK-0001-land-registry-readiness
```

The anti-context section records similar accepted findings, similar rejected
approaches, known failure modes, and do-not-repeat warnings.

## `status.json`

Recommended fields:

```json
{
  "schema_version": "1.0",
  "prompt_versions": {
    "planner": "planner_v1.0",
    "worker": "worker_v1.0",
    "primary_reviewer": "primary_reviewer_v1.0",
    "review_aggregator": "review_aggregator_v1.0"
  },
  "framework_versions": {
    "mission_scoring": "mission_scoring_v1.0",
    "result_acceptance": "result_acceptance_v1.0",
    "review_aggregation": "review_aggregation_v1.0",
    "data_source_audit": "data_source_audit_v1.0"
  },
  "id": "TASK-0001",
  "title": "Land Registry PPD data readiness",
  "type": "data_readiness",
  "status": "ready_for_worker",
  "previous_status": null,
  "last_transition_reason": "planner_created_task",
  "priority": 2,
  "revision_count": 0,
  "max_revisions": 1,
  "revision_limit_hit": false,
  "created_at": "2026-05-01T09:00:00Z",
  "updated_at": "2026-05-01T09:00:00Z",
  "lock_owner": null,
  "lock_expires_at": null,
  "allowed_paths": [
    "research_ops/tasks/TASK-0001-land-registry-readiness"
  ],
  "allowed_tools": ["read_files", "write_task_files"],
  "allow_browsing": false,
  "allow_code_execution": false,
  "allow_network": false,
  "max_minutes": 45,
  "max_turns": 6,
  "model_tier": "codex_standard",
  "review_policy": {
    "tier": 1,
    "required_reviewers": ["primary"],
    "panel_required": false,
    "human_required_for_acceptance": false
  },
  "escalate_to_tier": null,
  "escalation_reason": null,
  "escalation_requested_by": null,
  "escalation_requested_at": null,
  "requires_human": false,
  "data_audit_refs": [],
  "human_gate_reason": null,
  "budget": {
    "max_api_usd": 0,
    "max_compute_usd": 0
  },
  "result": {
    "recommendation": null,
    "claim_strength": null,
    "followup_count": 0
  }
}
```

## Status Meanings

| Status | Meaning |
| --- | --- |
| `inbox` | unprocessed human idea |
| `ready_for_planning` | needs planner conversion into a task |
| `ready_for_worker` | can be picked by worker |
| `in_progress` | locked by worker |
| `awaiting_review` | worker output done |
| `single_review` | primary reviewer is reviewing |
| `panel_review` | multiple independent reviewers are reviewing |
| `accepted` | reviewer accepts output |
| `needs_revision` | worker can retry with reviewer guidance |
| `needs_human` | blocked on human judgement |
| `paused` | not worth running now or missing dependency |
| `rejected` | not useful or invalid |
| `synthesized` | incorporated into weekly/monthly output |

## Transition Validation

Every status change must record:

```json
{
  "previous_status": "in_progress",
  "status": "awaiting_review",
  "last_transition_reason": "worker_completed_output"
}
```

After changing `status.json`, run:

The generic schema and transition validators are advanced/internal helpers:

```bash
python -m async_research_workflow.scripts.validate_json_artifact \
  --schema async_research_workflow/schemas/task_status.schema.json \
  research_ops/tasks/TASK-0001/status.json

# advanced/internal transition helper
python -m async_research_workflow.scripts.validate_transition research_ops/tasks/TASK-0001
```

The task should not be treated as successfully routed until schema validation and transition validation both pass.

Every `status.json` file must include `"schema_version": "1.0"`. Missing or mismatched task schema versions fail validation; migrate or recover the status file before treating the task as routable.

New `status.json` files should also include `prompt_versions` and `framework_versions`. These are audit fields: accepted outputs must be able to identify which prompts and scoring/review frameworks were used.

`experiment_plan` tasks must include `data_audit_refs` with `DS-0000` source IDs
that pass `async-research source check-experiment`. Data-readiness tasks may
update `research_ops/data_source_audit.md`, but the planner should include that
file in `allowed_paths` when such updates are expected.

Experiment plans must also include an executable experimentation framework
contract. The worker output may be `experiment_plan.json` or `worker_output.md`
with a fenced JSON block conforming to:

```text
async_research_workflow/schemas/experiment_plan.schema.json
```

Validate the plan before review:

```bash
async-research experiment validate \
  research_ops/tasks/TASK-0001/worker_output.md \
  --ops-dir research_ops \
  --task-dir research_ops/tasks/TASK-0001
```

The validator enforces audited data refs, approved baseline families,
time/spatial validation design, leakage checklist, success/failure criteria,
budget limits, output manifest path, and bounded claim limits. Failed validation
routes to revision or human review; it must not advance to `run_analysis`.

If `status.json` is malformed or invalid and blocks progress, preserve it and
route the task to human review:

Use the advanced/internal recovery helper:

```bash
python -m async_research_workflow.scripts.recover_status_json research_ops/tasks/TASK-0001
```

The recovery wrapper writes a valid `needs_human` status and stores the broken
file beside it as `status.invalid.<timestamp>.<pid>.json`.

## Human Decisions

Human decisions live in the append-only decision log:

```text
research_ops/decisions.md
```

Columns:

```text
date | item_id | decision | reason | approver | related_artifacts
```

Do not move a task out of `needs_human` by editing `status.json` directly. Use:

```bash
async-research decision resolve-task \
  research_ops \
  research_ops/tasks/TASK-0001 \
  --decision resume \
  --reason "Human approved a narrowed retry" \
  --approver "human-owner" \
  --status ready_for_worker
```

The transition validator fails `needs_human -> ready_for_worker`, `paused`, or
`rejected` unless `decisions.md` has a matching row for the task ID.

## Revision Counters

Every task must track bounded reviewer retry loops:

```json
{
  "revision_count": 0,
  "max_revisions": 1,
  "revision_limit_hit": false
}
```

Defaults:

| Review tier | Default `max_revisions` |
| ---: | ---: |
| 0 | 1 |
| 1 | 1 |
| 2 | 2 |
| 3 | 1 |

Reviewers must not set `status = needs_revision` manually. They should run:

```bash
async-research revision request research_ops/tasks/TASK-0001
```

If the task is still under its limit, the helper increments `revision_count` and
routes to `needs_revision`. If the limit has been reached, it routes to
`needs_human` with `last_transition_reason = revision_limit_exceeded`.

## Task Types

Use a controlled vocabulary:

```text
literature_extract
idea_discovery
idea_dedupe
idea_scoring
batch_job
batch_ingest
hypothesis_card
data_readiness
experiment_plan
code_patch
run_analysis
evaluate_results
critic_review
memo_section
weekly_synthesis
status_update
admin
```

## Result Labels

Use:

```text
ready
usable_with_caveats
needs_revision
needs_human
blocked
reject
```

Claim strength:

```text
none
weak
suggestive
moderate
strong
```

Only a human can approve `strong` for publication or high-stakes use. That
approval must be recorded in `research_ops/decisions.md` with
`async-research decision append`.

Claim strength must be re-evaluated on every review pass. If a task routes to
`needs_revision`, helpers clear `result.claim_strength` and mark it stale until
the next accepted, rejected, or human-gated review pass writes a fresh current
claim strength.

## Review Policy

Every task should declare its review tier:

```json
{
  "review_policy": {
    "tier": 2,
    "required_reviewers": ["primary", "methodology"],
    "panel_required": true,
    "human_required_for_acceptance": false
  }
}
```

Tier meanings:

| Tier | Meaning |
| --- | --- |
| `0` | schema or formatting check only |
| `1` | single primary reviewer |
| `2` | primary plus specialist reviewer |
| `3` | primary, methodology, skeptic, and aggregator |

Default mapping:

| Task type | Default tier |
| --- | ---: |
| `idea_discovery` | 0 |
| `idea_dedupe` | 0 |
| `idea_scoring` | 1 |
| `batch_job` | 0 or 1 if paid submission needs review |
| `batch_ingest` | 1, or 2 if outputs feed an experiment or claim |
| `literature_extract` | 1 |
| `hypothesis_card` | 1 |
| `data_readiness` | 1 or 2 if it feeds an experiment |
| `experiment_plan` | 2 |
| `code_patch` | 1 or 2 if shared code |
| `run_analysis` | 1 |
| `evaluate_results` | 2 |
| `critic_review` | 2 |
| `memo_section` | 2 |
| `weekly_synthesis` | 1 |

Escalate to Tier 3 when:

- claim strength is `moderate` or `strong`
- output may be public
- output has policy, investment, legal, or valuation implications
- reviewers disagree after one revision
- expensive experiments would be triggered

Reviewers should not hand-edit `review_policy` when they need a higher tier. They should run:

Use the advanced/internal tier-escalation helper:

```bash
python -m async_research_workflow.scripts.escalate_review_tier apply \
  research_ops/tasks/TASK-0001 \
  --to-tier 2 \
  --reason "worker output needs methodology review" \
  --reviewer primary
```

The helper updates `review_policy.required_reviewers`, routes to `panel_review` when needed, records the escalation fields, and validates the status transition before writing.

## Review Files

Reviewers write separate files:

```text
reviews/primary.md
reviews/methodology.md
reviews/skeptic.md
review_panel/aggregate.md
```

Reviewers should not read other review files before writing their own. The aggregator reads all reviews and routes the task.

Structured review fields:

```json
{
  "reviewer_role": "primary",
  "decision": "accept",
  "claim_strength": "suggestive",
  "prompt_version": "primary_reviewer_v1.0",
  "framework_versions": {
    "result_acceptance": "result_acceptance_v1.0"
  },
  "main_concerns": [],
  "required_followups": [],
  "evidence_gaps": [],
  "escalate_to_tier": null,
  "escalation_reason": null,
  "confidence": 0.74
}
```

Panel aggregation is deterministic. After required reviews exist, run:

```bash
async-research review aggregate research_ops/tasks/TASK-0001
```

The helper writes `review_panel/aggregate.json`, writes `review_panel/aggregate.md`,
and updates `status.json` using the tier rules in the review ensemble policy.

## Follow-Up Tasks

Workers and reviewers may propose follow-ups, but they should not spawn work directly unless the planner approves.

Format:

```markdown
## Proposed Follow-Ups

- Type: data_readiness
  Title: Check postcode join coverage for 2018-2025 London flats
  Reason: Needed before experiment plan can be approved.
  Priority suggestion: 2
```

## Error Handling

If a worker cannot complete the task:

1. Write a short `worker_output.md`.
2. Explain the blocker.
3. Set `status = needs_human` or `paused`.
4. Do not keep retrying.

Common blockers:

- missing source files
- unclear task scope
- network needed but not allowed
- conflicting instructions
- data access required
- task too large for budget

## Definition Of Done

A task is done only when:

- `status.json` status is terminal or routable
- the required output file exists
- the reviewer has either accepted it or routed it
- panel review is complete if the task requires it
- proposed follow-ups are explicit
- human gates are flagged where needed

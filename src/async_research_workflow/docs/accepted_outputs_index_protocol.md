# Accepted Outputs Index Protocol

Created: 2026-05-02

This document implements the P1 accepted outputs index requirement from the
feedback hardening plan and Phase 6 memory decay/revalidation requirements.

## Purpose

Keep a compact, current memory of accepted task outputs so discovery and planning do not repeatedly rediscover the same findings or build new tasks from stale context.

The weekly digest is narrative memory. The accepted outputs index is operational memory.

## Required File

Use:

```text
research_ops/accepted_outputs_index.md
```

Columns:

```text
accepted_date | task_id | title | key_finding | claim_type | freshness_window_days | next_recheck_date | revalidation_status | source_ids | claim_strength | caveats | followups | supersedes | superseded_by | evidence_link
```

Legacy `date | task_id | title | key_finding | claim_strength | evidence_link |
followups` rows are still readable, but the helper rewrites the richer Phase 6
format on update.

## Required Helper

Use the public accepted-output commands:

```text
async-research accepted
```

Update the index from accepted task folders:

```bash
async-research accepted update research_ops
```

The helper:

- scans `research_ops/tasks/*/status.json`
- selects tasks with `status = accepted`
- refuses accepted `run_analysis` and `evaluate_results` tasks unless
  `review_panel/result_acceptance.json` exists, passes schema validation, and
  records `analysis_run.validation.ok = true`
- extracts accepted date, title, claim type, freshness window, source IDs, claim
  strength, evidence link, key finding, caveats, supersession links, and
  follow-ups. When `review_panel/result_acceptance.json` exists, its accepted
  memory fields take precedence so empirical analysis claims keep their
  validator-derived claim type, claim strength, and revalidation status.
- appends new task rows
- updates existing rows for the same task id instead of duplicating them
- writes `research_ops/accepted_outputs_index.md`

## Memory Decay

Accepted evidence is operational memory, not permanent truth. The helper uses
these default freshness windows unless a task result sets
`result.freshness_window_days` explicitly:

| claim_type | default freshness |
| --- | ---: |
| `market_price` | 45 days |
| `market_rent` | 45 days |
| `market_inventory` | 45 days |
| `market_supply` | 45 days |
| `source_data_readiness` | 90 days |
| `methodology_note` | 180 days |
| `framework_workflow_doc` | manual review |
| `evergreen_definition` | manual review |
| `descriptive` | 90 days |
| `associative` | 90 days |
| `predictive` | 45 days |
| `causal` | manual review |
| `probabilistic` | 45 days |
| `other` | manual review |

Accepted task results should set:

```json
{
  "result": {
    "claim_type": "market_price",
    "freshness_window_days": 45,
    "next_recheck_date": "2026-06-17",
    "revalidation_status": "current",
    "source_ids": ["DS-0001"],
    "caveats": ["latest month may be incomplete"],
    "supersedes": [],
    "superseded_by": []
  }
}
```

If `next_recheck_date` has passed, the helper marks the row `stale`. If it is
within seven days, it marks the row `due`. Manual-review claim types are never
treated as current market facts without a human decision.
Analysis result acceptance can also set `stale`, `due`, or `manual_review`
directly when old data versions, stale diagnostics, or diagnostic warnings are
found; the index preserves those statuses even when the calendar recheck date is
still in the future.

Generate a deterministic revalidation report:

```bash
async-research accepted revalidation research_ops
```

Write a schedule for due/stale evidence:

```bash
async-research accepted revalidation research_ops --write-schedule
```

This writes:

```text
research_ops/revalidation_schedule.md
```

Check whether a candidate, discovery note, or task output is trying to reuse
stale accepted memory:

```bash
async-research accepted check-memory-use research_ops research_ops/discovery/IDEA-0001.md
```

This fails closed when the artifact cites a stale `TASK-0000` accepted output.

## Task Metadata

Accepted task status files may include optional result fields:

```json
{
  "result": {
    "recommendation": "ready",
    "claim_strength": "suggestive",
    "key_finding": "EPC-to-sale matching is plausible for London flats after address normalization.",
    "evidence_link": "tasks/TASK-0007/worker_output.md",
    "followups": ["Profile unmatched EPC certificates"]
  }
}
```

If these fields are absent, the helper falls back to `worker_output.md`, `review_panel/aggregate.json`, and the task folder path.

Accepted tasks should also keep `prompt_versions` and `framework_versions` in
`status.json`. The accepted outputs index stays compact, while monthly
calibration uses the version metadata directly from accepted task status files.

For current outputs, claim strength should come from the latest
`review_panel/aggregate.json.aggregate_claim_strength`. The helper falls back to
older status/review metadata only for pre-P2-5 tasks.

## Duplicate Checks

Before promoting a discovery candidate or creating a new task, the planner should check whether the idea overlaps accepted outputs:

```bash
async-research accepted check-duplicate \
  research_ops \
  --title "EPC premium during energy shocks"
```

The helper returns matching accepted rows and a `duplicate_risk` flag. A duplicate risk does not always reject the task, but it must be mentioned in the planner note or task context.

For full P2 anti-context, use `async-research anti-context build` after
creating the task folder. It combines accepted-output overlap with rejected
ideas and rejected task failure modes.

## Scheduler Placement

Run the update helper:

- after deterministic review aggregation accepts a task
- before the weekly synthesizer writes `weekly_digest.md`
- before discovery scout jobs use accepted outputs as source material
- before planner jobs promote candidates into tasks

Run `revalidation-report --write-schedule` before discovery and weekly
synthesis. Discovery and planning must not reuse stale accepted evidence as a
current fact unless a revalidation task or human decision has refreshed it.

## Acceptance Tests

The accepted outputs index layer is considered implemented when:

- an accepted task appends an index row
- rerunning the helper does not duplicate the same task id
- discovery scout prompts read the index
- planner prompts check the index and warn about duplicates
- duplicate check returns a match for a similar accepted output title
- old market claims are flagged after their freshness window expires
- revalidation schedules include due/stale accepted outputs
- stale accepted memory reuse fails closed
- superseded claims remain visible in the evidence ledger

# Programmatic Cost Tracking Protocol

Created: 2026-05-02

This document implements P3-2 programmatic cost tracking for the async research
workflow.

## Purpose

When an API returns token usage, an agent must not summarize cost in prose and
hope someone copies it into the ledger. Usage should be ingested from the API
response artifact into `research_ops/cost_ledger.csv` with actual token fields.

## Required Helper

Use:

```text
async_research_workflow/scripts/cost_tracking.py
```

Ingest usage from a JSON or JSONL response:

```bash
python -m async_research_workflow.scripts.cost_tracking ingest-usage \
  research_ops \
  --usage-file research_ops/tasks/TASK-0007/artifacts/api_response.json \
  --item-id TASK-0007 \
  --role worker \
  --model gpt-5.4-mini \
  --input-usd-per-1m 0.25 \
  --output-usd-per-1m 2.00 \
  --status awaiting_review
```

The helper extracts common usage shapes, including:

```json
{"usage": {"input_tokens": 1200, "output_tokens": 300}}
```

```json
{"usage": {"prompt_tokens": 1200, "completion_tokens": 300, "total_tokens": 1500}}
```

```json
{"usage_metadata": {"prompt_token_count": 1200, "candidates_token_count": 300}}
```

## Codex CLI JSON Event Capture

For local `codex exec` jobs, run with JSON event output and save the stream as a
task artifact:

```bash
codex exec --json --cd "$RESEARCH_REPO_ROOT" \
  --output-last-message /tmp/codex-last-message.md \
  "<bounded prompt>" \
  > research_ops/tasks/TASK-0007/artifacts/codex_events.jsonl
```

Then ingest the file if the stream contains usage metadata:

```bash
python -m async_research_workflow.scripts.cost_tracking ingest-usage \
  research_ops \
  --usage-file research_ops/tasks/TASK-0007/artifacts/codex_events.jsonl \
  --item-id TASK-0007 \
  --role worker \
  --model codex-cli \
  --status awaiting_review
```

If the current product surface does not expose usable token fields, keep an
estimated `actual=false` ledger row. Budget gates still use estimates, and the
health monitor will show `actual_usage_rows=0` until real usage is available.

In shell wrappers, usage ingestion should not mask a successful worker run when
the event stream has no usage fields yet:

```bash
python -m async_research_workflow.scripts.cost_tracking ingest-usage \
  research_ops \
  --usage-file research_ops/tasks/TASK-0007/artifacts/codex_events.jsonl \
  --item-id TASK-0007 \
  --role worker \
  --model codex-cli \
  --status awaiting_review \
  || echo "No ingestible usage metadata found; keep estimated ledger row."
```

## Ledger Columns

Programmatic rows include:

```text
date,item_id,role,model_or_tool,usage_source,input_tokens,output_tokens,total_tokens,input_usd,output_usd,api_usd,compute_usd,amount_usd,human_minutes,status,actual,monthly_budget_usd,weekly_budget_usd,notes
```

`actual=true` means the row came from API usage data rather than manual
estimation. Older ledger rows are preserved and the helper adds missing columns
when it writes a new row.

## Budget Gate

Before promoting a discovery candidate into expensive work, submitting a paid
batch, or running a paid API/cloud task, run:

```bash
python -m async_research_workflow.scripts.cost_tracking budget-check \
  research_ops \
  --item-id TASK-0007 \
  --action expensive_task \
  --proposed-api-usd 4.00 \
  --proposed-compute-usd 0.50 \
  --monthly-budget-usd 25 \
  --weekly-budget-usd 10 \
  --threshold 0.8
```

The command exits nonzero with `halt=true` when projected monthly or weekly spend
would reach the threshold. Agents must route the task or promotion to
`needs_human` rather than proceeding.

## Health Monitor Integration

`health_check.py` aggregates:

- monthly and weekly cost
- budget usage ratios
- `input_tokens`
- `output_tokens`
- `total_tokens`
- `actual_usage_rows`

Budget alerts still come from the health monitor, but `budget-check` is the
pre-spend gate.

## Acceptance Checks

P3-2 is implemented when:

- API usage JSON/JSONL creates a ledger row with actual input/output tokens
- the health monitor includes token totals and cost totals from the ledger
- budget-check exits nonzero before projected spend crosses the configured threshold

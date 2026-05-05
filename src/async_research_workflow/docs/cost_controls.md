# Cost Controls

## Cost Model

There are three cost modes:

1. Fixed subscription cost: ChatGPT Plus/Pro or Codex plan allowance.
2. Metered API cost: OpenAI, Anthropic, Gemini, embeddings, search, tools.
3. Compute/storage cost: GitHub Actions, local machine, cloud warehouse, vector DB, GPUs.

The workflow should spend fixed subscription allowance first where appropriate, then use API only for repeatable automation or bulk jobs.

## Main Cost Levers

| Lever | Expected effect |
| --- | --- |
| One bounded task per worker run | prevents runaway agent sessions |
| Max turns and max minutes | caps coding loops |
| Data-readiness before experiment | rejects weak ideas before compute |
| Reviewer before synthesis | avoids compounding bad outputs |
| Discovery inbox before queue | prevents self-generated work explosion |
| Tiered review panels | spends multiple models only at gates |
| Batch API for bulk extraction | roughly halves async API cost |
| Prompt caching for repeated prefixes | reduces repeated input cost |
| Local model for extraction | shifts high-volume low-risk work off frontier APIs |
| Queue-based scheduler | avoids one scheduled task per idea |
| Human gates | prevents expensive/risky automatic escalation |

## Suggested Budgets

### Solo Prototype

```text
ChatGPT Plus or Pro: $20-$200/month
Additional API: $0-$100/month
Cloud compute: $0-$50/month
Human time: exception-based daily + 20-30 min/week
```

Use this mode until the workflow has completed at least 20 tasks and produced 2 useful memos.

### Active Research Pilot

```text
ChatGPT Pro: $100-$200/month
Additional API: $50-$500/month
Cloud compute/warehouse: $50-$300/month
Human time: 15 min/day + 1 hour/week
```

Use this when the queue is reliable and tasks are small enough that automation rarely thrashes.

### Avoided Expensive Mode

```text
Always-on multi-agent debate
Several frontier agents per hypothesis
No max turn limits
Repeated web search
Large repo context every run
Automatic experiments for every idea
```

This is where costs can jump to thousands per month without producing better research.

## Routing Table

| Stage | Default model/tool | Escalate to frontier when |
| --- | --- | --- |
| idea discovery | local 30B, mini model, or Batch API | top candidate will be promoted |
| idea dedupe/scoring | local 30B or cheap API | top candidate affects research portfolio |
| inbox cleanup | ChatGPT/Codex subscription | never, unless business-critical |
| task planning | Codex standard | task will spawn expensive work |
| literature chunk extraction | local 30B, mini model, Batch API | source supports a novelty claim |
| dataset metadata extraction | local 30B or mini model | data will enter an experiment |
| hypothesis draft | mini model or Codex | top-ranked portfolio item |
| experiment plan | frontier mid/high model | always before execution |
| code worker | Codex | shared pipeline or production code |
| code review | Codex review or frontier | accepted result depends on code |
| critic review | frontier or senior human | claim is policy/investment-sensitive |
| final memo | frontier plus human skim | public or external distribution |

## Review Cost Policy

Do not send every task to every model.

| Artifact | Review spend |
| --- | --- |
| discovery candidate | cheap/local review only |
| ordinary task | primary reviewer only |
| data readiness feeding no experiment | primary reviewer only |
| data readiness feeding experiment | primary + skeptic if risk is high |
| experiment plan | primary + methodology |
| result summary | primary + methodology; add skeptic for moderate claims |
| final memo | primary + methodology + skeptic + aggregator |
| public/high-stakes claim | review panel + human |

Monthly review budget rule:

```text
Spend at least 70 percent of review budget on Tier 2/3 gates.
Spend at most 30 percent on routine Tier 0/1 checks.
```

This keeps model diversity where it changes decisions.

## Prompt Caching Pattern

For API jobs, structure prompts like this:

```text
[static system instructions]
[static artifact schema]
[static examples]
[static review rubric]
[dynamic task-specific content]
```

OpenAI prompt caching works on repeated prompt prefixes. Keep the stable parts first and the task-specific material last.

## Batch Pattern

Use Batch API for:

- source classification
- paper chunk extraction
- idea scoring
- idea candidate dedupe
- citation metadata cleanup
- embedding or summary jobs
- low-priority nightly evaluations

Batch jobs must use `batch_lifecycle.py` and `batch_manifest.json`. Provider
outputs remain untrusted until a `batch_ingest` task ingests them and a reviewer
marks the manifest reviewed.

Do not use Batch API for:

- urgent interactive coding
- tasks requiring multi-step tool use
- human-in-the-loop decisions that need immediate clarification

## Search Cost Controls

Web search is useful but can quietly become expensive.

Rules:

- Worker may browse only when `allow_browsing=true`.
- Discovery may browse only when the source register allows it.
- Literature tasks should receive source URLs when possible.
- Reuse source notes from previous tasks.
- Keep a central `sources.md` per research topic.
- Prefer official sources for pricing, APIs, legal, and data documentation.

## Codex Worker Limits

Recommended defaults:

```json
{
  "max_minutes": 45,
  "max_turns": 6,
  "max_files_changed": 5,
  "max_new_tasks_proposed": 5,
  "max_discovery_candidates": 5,
  "allow_network": false,
  "allow_browsing": false
}
```

For larger tasks, split into smaller ones rather than raising the cap.

## Human Gate Thresholds

Require human approval when:

- API spend would exceed $10 for a single task during prototype
- cloud/warehouse spend would exceed $5 for a single task during prototype
- any task needs credentials
- any task needs private data
- any task changes workflow rules
- any task could publish or push externally
- any output uses `claim_strength = strong`
- any Tier 3 panel has material disagreement
- any discovery candidate would trigger an experiment or external data acquisition
- monthly API spend would exceed the active budget

## Cost Ledger

Track estimates when exact usage is unavailable:

```csv
date,item_id,role,model_or_tool,estimated_minutes,estimated_api_usd,estimated_compute_usd,status
2026-05-01,TASK-0001,worker,codex_subscription,35,0,0,awaiting_review
2026-05-01,IDEA-0007,discovery,local_30b,20,0,0,candidate
```

When APIs return usage, ingest the response programmatically:

```bash
async-research cost ingest-usage \
  research_ops \
  --usage-file research_ops/tasks/TASK-0001/artifacts/api_response.json \
  --item-id TASK-0001 \
  --role worker \
  --model gpt-5.4-mini \
  --input-usd-per-1m 0.25 \
  --output-usd-per-1m 2.00
```

Programmatic rows record `input_tokens`, `output_tokens`, `total_tokens`,
`api_usd`, `amount_usd`, and `actual=true`.

Before promotion into expensive work or paid API/cloud execution, run:

```bash
async-research cost budget-check \
  research_ops \
  --item-id TASK-0001 \
  --action expensive_task \
  --proposed-api-usd 4 \
  --monthly-budget-usd 25 \
  --threshold 0.8
```

If the command exits nonzero, route to `needs_human`.

The point is not accounting perfection. The point is noticing runaway categories early.

Batch submission uses `batch_lifecycle.py submit`, which appends rows with
`amount_usd`, `api_usd`, and `compute_usd` so health checks and metrics history
can include batch spend.

## Cost-Saving Heuristics

- Reject hypotheses at data-readiness stage when data is weak.
- Reject most discovery candidates before they enter the execution queue.
- Prefer "memo-ready" over "paper-ready" unless the idea has evidence.
- Cache source summaries.
- Never ask an agent to reread an entire repo if a context bundle will do.
- Use one reviewer for routine tasks and panels only at gates.
- Run high-cost critique only after cheap checks pass.
- Summarize accepted outputs weekly so future agents can read one digest.
- Let slow jobs run weekly if that improves review quality and lowers cost.

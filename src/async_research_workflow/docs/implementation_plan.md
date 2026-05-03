# Implementation Plan

## Phase 1: Manual File-Based Workflow

Duration: 2 to 3 days

Create:

```text
research_ops/
  discovery_inbox.md
  inbox.md
  queue.md
  daily_status.md
  weekly_digest.md
  cost_ledger.csv
  decisions.md
  data_source_audit.md
  metrics_baseline.json
  metrics_history.jsonl
  discovery/
  review_panel/
  tasks/
```

Manually create 3 tasks:

1. one hypothesis-card task
2. one data-readiness task
3. one critic-review task

Run them manually with Codex. Do not schedule anything yet.

Exit criteria:

- task statuses are understandable
- worker output is reviewable
- reviewer notes are useful
- human can scan status in under 5 minutes

## Phase 1B: Discovery Inbox

Duration: 1 to 2 days

Create:

```text
research_ops/discovery_inbox.md
research_ops/data_source_audit.md
research_ops/discovery/source_register.md
research_ops/discovery/rejected_ideas.md
research_ops/discovery/clusters.md
```

Manually run one discovery pass:

1. Read existing repo research notes and accepted outputs.
2. Generate at most 10 candidates.
3. Keep at most 5.
4. Promote at most 2 to `inbox.md`.

Exit criteria:

- every candidate has required data, MVP test, and kill reason
- planner can promote candidates without reinterpreting vague prose
- discovery does not create execution tasks directly

## Phase 2: Local Scheduled Worker

Duration: 2 to 5 days

Add a local scheduled job using Codex app automation, cron, or launchd.

Start with:

```text
Worker: twice daily
Reviewer: once daily
Discovery Scout: manual or weekly
```

Keep planner manual until the worker/reviewer loop is stable.

Exit criteria:

- no overlapping worker runs
- no edits outside allowed task folder
- failed tasks become `needs_human` or `paused`
- human can recover from any bad output without git surgery

## Phase 3: Daily Planner

Duration: 1 week

Add the planner job.

Rules:

- planner creates at most 3 tasks per day
- planner promotes at most 3 discovered ideas per run
- planner cannot create expensive tasks without `requires_human=true`
- planner prefers small setup tasks over experiments

Exit criteria:

- queue does not grow faster than review capacity
- tasks are usually completable in 45 minutes
- fewer than 20 percent of tasks are rejected for unclear scope

## Phase 4: Weekly Synthesizer

Duration: 1 week

Add the weekly digest job.

Digest sections:

- accepted outputs
- rejected or paused outputs
- decisions needed
- next-week priorities
- cost summary
- useful links

Exit criteria:

- human can understand the week in 10 minutes
- accepted outputs are easy to reuse
- stale tasks are visible

## Phase 5: GitHub Or Cloud Automation

Duration: optional

Move to GitHub Actions or cloud routines only if:

- local machine availability is a problem
- you want visible run logs in GitHub
- you want PR-based review
- you need cloud execution independent of your laptop

Recommended GitHub model:

- scheduled worker opens branch or PR
- reviewer comments or writes review file
- human merges

Avoid direct pushes to `main` from autonomous jobs.

## Phase 6: Bulk Extraction Optimization

Duration: optional

Add local 30B model or Batch API for:

- paper chunk classification
- dataset documentation extraction
- source summary refresh
- idea scoring
- idea candidate generation and dedupe

Keep the outputs as draft artifacts that a reviewer can accept or reject.

## Phase 7: Review Panel Gates

Duration: 1 to 2 weeks

Add panel review only for gates:

- experiment plans
- result summaries
- final memos
- moderate or strong claims

Create:

```text
research_ops/review_panel/policy.md
research_ops/review_panel/reviewer_registry.md
```

Start with:

```text
Tier 1: Codex primary reviewer
Tier 2: Codex primary + Claude or strong methodology reviewer
Tier 3: primary + methodology + Gemini/alternative skeptic + aggregator
```

Exit criteria:

- reviewers produce independent notes
- aggregator summarizes disagreements
- no Tier 3 acceptance happens without human approval for strong/public claims
- panel cost is tracked

## Minimal First Week Plan

Day 1:

- create `research_ops/`
- create task schema
- add 3 seed tasks

Day 2:

- run one worker manually
- run one reviewer manually
- revise prompt based on failure

Day 3:

- schedule worker twice daily
- keep reviewer manual

Day 4:

- schedule reviewer daily
- add daily status format

Day 5:

- add planner prompt
- human reviews queue and kills weak tasks

Day 7:

- write weekly digest
- decide whether to increase cadence

Week 2:

- add weekly discovery scout
- add discovery inbox
- promote only 1 or 2 candidates
- run Tier 2 review on one experiment plan or result summary

## Recommended First Tasks For Real-Estate Research

1. Convert the top 10 `re_trends_research` ideas into standardized hypothesis cards.
2. Draft data-readiness reports for Land Registry PPD, postcode geography, mortgage rates, EPC, schools, crime, and supply.
3. Review one existing study and extract reusable task templates.
4. Create a "blocked by data" list before any new experiments.
5. Build one experiment-plan template for area-panel studies.
6. Create discovery candidates from rejected or parked ideas.
7. Run a skeptic pass over the top 5 discovery candidates.

## Success Metrics

After 30 days:

- at least 30 small tasks processed
- at least 20 idea candidates generated
- at least 10 idea candidates rejected cheaply
- at least 10 accepted outputs
- at least 5 weak ideas rejected before experiment
- at least 2 research memos or memo sections produced
- human review under 1-2 hours per week
- no uncontrolled API/cloud spend
- no ambiguous "what happened?" job failures
- no expensive experiment launched directly from discovery

## Stop Conditions

Pause automation if:

- workers repeatedly edit outside allowed paths
- queue grows faster than review
- more than 30 percent of tasks need human due to unclear scope
- costs are not being logged
- reviewer accepts outputs with unsupported claims
- human cannot understand daily status quickly
- discovery promotes too many ideas for the planner to triage
- panel reviews disagree frequently because task outputs are underspecified

Fix the workflow before scaling cadence.

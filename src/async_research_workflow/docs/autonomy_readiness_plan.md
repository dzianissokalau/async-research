# Autonomy Readiness Plan

## Purpose

This plan defines the pre-flight hardening needed before running real autonomous research loops. The goal is to move the async research workflow toward 85-90% autonomous operation while preserving quality, independence, cost control, and fail-closed behavior.

Autonomy in this framework means that most routine workflow cycles can complete without human intervention. It does not mean that the system makes every important judgment alone. Human review remains required for priority changes, high-impact claims, unresolved contradictions, source approvals, budget exceptions, and strategic decisions.

## Target Autonomy Level

The meaningful near-term target is 90% autonomous workflow completion for narrow, repeated research loops.

This means:

- routine tasks move from queue to worker to review to acceptance without manual chasing;
- weak, malformed, risky, stale, or over-budget outputs route to `needs_human`;
- accepted evidence is current, cited, and traceable;
- daily and weekly status files explain what happened;
- costs stay within configured limits;
- the system can pause itself when it is not safe to continue.

For broad open-ended idea discovery, the practical target should remain closer to 85-90%. For narrow monitoring workflows, such as weekly real estate market scans, the system may eventually reach 93-95% autonomous completion after calibration.

## Success Criteria

The workflow is ready for controlled live loops when:

- the full acceptance suite passes;
- an autonomy benchmark suite passes deterministically;
- a no-op scheduled-week simulation passes;
- the readiness gate returns green or warning-only;
- source governance rules block unaudited or stale sources where required;
- accepted memory has freshness and revalidation rules;
- `needs_human` items are structured and actionable;
- cost budget settings are configured;
- the first live loop scope is narrow and documented.

## Phase 1: Autonomy Benchmark Set

Create a benchmark suite of 20-50 realistic test tasks that exercise happy paths, expected failures, and edge cases.

### Requirements

Each benchmark case must define:

- task id and task type;
- input task folder or fixture path;
- expected final state;
- expected acceptance or rejection outcome;
- expected human escalation, if any;
- expected source-quality outcome;
- expected cost tier;
- expected reviewer-routing outcome;
- expected ledger updates.

The benchmark set should include:

- strong valid result;
- weak evidence result;
- malformed `status.json`;
- invalid status transition;
- duplicate active task;
- reviewer disagreement;
- unaudited source;
- stale source;
- stale accepted memory reuse;
- source contradiction;
- duplicate idea candidate;
- over-budget task;
- repeated revision failure;
- missing reviewer metadata;
- missing claim-strength restatement;
- invalid result-acceptance artifact;
- queue overload;
- stale lock;
- accepted result with required follow-ups;
- rejected result with reusable anti-context.

Add a deterministic runner:

```bash
async-research benchmark
```

### Acceptance Criteria

- Benchmark suite passes deterministically.
- At least 90% of known-bad cases are rejected or routed to `needs_human`.
- No malformed output reaches accepted memory.
- No weak-evidence result is accepted without required caveats and follow-ups.
- Benchmark outputs are isolated from live `research_ops` state.

## Phase 2: Autonomy Metrics

Make autonomy measurable from workflow state, not manual impressions.

### Required Metrics

Track:

- `autonomous_completion_rate`;
- `needs_human_rate`;
- `false_accept_rate`;
- `false_reject_rate`;
- `cost_per_accepted_output`;
- `reviewer_disagreement_rate`;
- `stale_memory_reuse_count`;
- `unaudited_source_block_count`;
- `revision_limit_hit_count`;
- `average_task_age_hours`;
- `queue_overload_count`;
- `readiness_gate_skip_count`;
- `accepted_outputs_revalidated_count`;
- `accepted_outputs_expired_count`.

### Requirements

- Metrics must be derived from task states, ledgers, reviews, and health reports.
- Metrics must be appended to `research_ops/metrics_history.jsonl`.
- `research_ops/weekly_digest.md` must summarize current autonomy level.
- Health checks and readiness gates must warn when metrics drift outside thresholds.
- Metrics must distinguish warning conditions from hard blockers.

### Acceptance Criteria

- Weekly digest can report a current estimated autonomy percentage.
- Metrics update without manual editing.
- A benchmark or simulated week can produce a metrics snapshot.
- Budget, queue, source, and review-risk metrics appear in the same operational view.

## Phase 3: Pre-Loop Readiness Gate

Add one command that determines whether another autonomous loop is safe to run.

Example:

```bash
async-research readiness research_ops
```

### Checks

The readiness gate must inspect:

- schema validity;
- malformed or partial status files;
- stale locks;
- unresolved `needs_human` tasks;
- queue overload;
- reviewer capacity;
- stale or unaudited data sources;
- stale accepted evidence;
- budget pressure;
- failed previous runs;
- duplicate active tasks;
- missing required operational files;
- missing or stale metrics snapshots.

### Exit Codes

- `0`: safe to run;
- `2`: safe to run with warnings;
- `3`: skip loop;
- `4`: invalid ops state;
- `5`: human decision required.

### Requirements

- Expensive workers must not run when the gate returns `3`, `4`, or `5`.
- Warnings and blockers must be written to `research_ops/health_report.json`.
- Human-readable summary must be reflected in `research_ops/daily_status.md`.
- The gate must be deterministic for the same input state.

### Acceptance Criteria

- Scheduler can call the gate before every loop.
- Known unsafe states prevent autonomous worker execution.
- Known warning-only states allow execution with visible warnings.
- Readiness failures identify the exact file, task, or policy that needs attention.

## Phase 4: Escalation Policy

Define deterministic rules for when the workflow must stop and ask for human input.

### Escalation Triggers

Route to `needs_human` when:

- a required source is unaudited;
- source freshness has expired for the claim type;
- evidence conflicts with accepted memory;
- reviewer scores disagree beyond threshold;
- result claims high confidence with weak evidence;
- task exceeds budget;
- revision limit is hit;
- result proposes a strategic or business action;
- result affects durable accepted memory but lacks citations;
- task contract is ambiguous or contradictory;
- model output changes task scope without authorization;
- result depends on hidden assumptions that reviewers cannot verify.

### Requirements

Create:

```text
research_ops/escalation_policy.md
async_research_workflow/escalation_policy_protocol.md
```

The policy must define:

- trigger name;
- trigger condition;
- severity;
- routing destination;
- required human decision;
- default safe action;
- retry behavior;
- ledger update behavior.

Worker and reviewer prompts must reference the escalation policy. Scripts must enforce deterministic thresholds where possible.

### Acceptance Criteria

- The same task routes the same way on repeated runs.
- Every `needs_human` task includes a structured reason.
- Human review items include clear available decisions.
- `needs_human` is not used as a vague fallback without explanation.

## Phase 5: Source Governance

Improve source quality controls before live research loops.

### Source Tiers

Use the following source tiers:

- `tier_1_official`: government, regulator, primary database, exchange, official statistics body;
- `tier_2_institutional`: university, respected company, industry body, audited provider;
- `tier_3_media`: journalism, newsletters, blogs, market commentary;
- `tier_4_untrusted`: unknown, scraped, unverifiable, social-only, promotional.

### Required Source Fields

Each source record must include:

- source id;
- source name;
- URL or domain;
- publisher or owner;
- source tier;
- approval status;
- approved use cases;
- blocked use cases;
- freshness window;
- known limitations;
- citation requirements;
- last reviewed date;
- approved by;
- review notes.

### Requirements

- Experiment planning cannot use unaudited sources.
- High-impact claims require tier 1 or tier 2 support.
- Tier 3 sources may support context but must not independently justify promotion.
- Tier 4 sources must be blocked from accepted evidence unless explicitly approved.
- Stale sources must warn or block depending on claim type.
- Discovery and worker prompts must cite current source-governance rules.

### Acceptance Criteria

- Unapproved sources block promotion to experiment planning.
- Source freshness warnings appear in health reports and weekly digests.
- Accepted evidence records cite audited sources.
- The system can explain why a source was allowed or blocked.

## Phase 6: Memory Decay And Revalidation

Accepted evidence should not remain current forever. Add freshness rules and revalidation scheduling.

### Suggested Freshness Windows

- market price and rent claims: 30-45 days;
- market inventory and supply claims: 30-45 days;
- source/data readiness claims: 60-90 days;
- methodology notes: 180 days;
- framework or workflow docs: manual review only;
- evergreen definitions: manual review only.

### Required Accepted Evidence Fields

Accepted outputs should include:

- accepted date;
- claim type;
- freshness window;
- next recheck date;
- revalidation status;
- source ids;
- claim strength;
- caveats;
- required follow-ups;
- supersedes or superseded-by links where relevant.

### Requirements

- Discovery scout must be warned before using stale accepted outputs.
- Weekly digest must list evidence due for refresh.
- Stale evidence must not be reused as a current fact without revalidation.
- Contradictions between new findings and accepted memory must trigger escalation.

### Acceptance Criteria

- Old market claims are flagged after their freshness window expires.
- Revalidated outputs update the evidence ledger without losing history.
- Superseded claims remain auditable.
- Stale-memory reuse is counted in metrics.

## Phase 7: No-Op Scheduled Simulation

Before spending model budget, simulate a week of scheduled operation with fixture outputs.

Example:

```bash
async-research simulate-week research_ops
```

### Simulated Steps

The simulation should run:

- daily readiness gate;
- discovery scout;
- task creation;
- worker completion;
- primary review;
- methodology or skeptic review when triggered;
- review aggregation;
- result acceptance;
- accepted-output index update;
- evidence ledger update;
- cost ledger update;
- health check;
- weekly digest.

### Requirements

- The simulation must not call external APIs.
- Fixture/model-free outputs must cover both success and failure paths.
- Simulated outputs must write to a temporary ops directory or isolated fixture state.
- The simulation must report final queue size, accepted count, rejected count, `needs_human` count, and simulated cost.

### Acceptance Criteria

- Seven simulated days complete without corrupting state.
- Queue does not grow uncontrollably.
- `needs_human` items are visible and structured.
- Accepted and rejected ledgers update correctly.
- Readiness gate skips unsafe simulated days.
- Metrics history records the simulated week.

## Phase 8: Human Review Surface

Create a simple control surface for light human supervision.

### Files

Create or enhance:

```text
research_ops/daily_status.md
research_ops/weekly_digest.md
research_ops/human_review_queue.md
```

### Daily Status Requirements

Daily status must show:

- what ran;
- what changed;
- what was accepted;
- what was rejected;
- what needs human decision;
- budget used;
- risky or stale sources;
- current queue state;
- next scheduled tasks.

### Human Review Queue Requirements

Each item must include:

- decision id;
- task id;
- decision needed;
- reason for escalation;
- available options;
- recommended action;
- consequence of ignoring;
- urgency;
- owner;
- required update path after decision.

### Acceptance Criteria

- The human operator can review system state in under 10 minutes.
- Every human-needed item has a clear action.
- Resolved human decisions are append-only and auditable.
- Daily status and human review queue do not contradict task state.

## Phase 9: First Narrow Live Loop

Run the first real loop only after the benchmark, readiness gate, source governance, and no-op simulation are passing.

### Recommended First Loop

Weekly real estate market research readiness and trend-candidate discovery.

### Scope Limits

The first loop should use:

- one geography;
- one market segment;
- approved source list only;
- one discovery task;
- one worker task;
- one primary reviewer;
- one acceptance pass;
- no automatic experiment launch;
- explicit budget ceiling;
- explicit stop condition for weak or unaudited evidence.

### Acceptance Criteria

- Loop completes without manual intervention or routes cleanly to `needs_human`.
- Cost is logged.
- Evidence is accepted or rejected correctly.
- Daily and weekly status files are useful.
- No unaudited source is promoted.
- Follow-up tasks are created or logged where required.

## Implementation Order

Recommended build order:

1. Autonomy metrics.
2. Pre-loop readiness gate.
3. Escalation policy.
4. Source governance.
5. Memory decay and revalidation.
6. Autonomy benchmark cases.
7. No-op weekly simulation.
8. Human review queue.
9. First narrow live loop.

This order makes the workflow measurable and safe before adding more autonomous execution.

## Definition Of Ready For Real Loops

The workflow is ready for controlled real loops when:

- `async-research acceptance-suite` exits `0`;
- `async-research benchmark` exits `0`;
- `async-research simulate-week research_ops` exits `0`;
- `async-research readiness research_ops --dry-run` exits `0` or `2`;
- no unresolved high-severity `needs_human` items remain;
- source register has approved seed sources;
- freshness windows are configured for accepted evidence;
- cost budget is configured;
- first live loop scope is documented;
- rollback/recovery instructions are available in the operational runbook.

At that point, the expected practical autonomy level is 80-85% immediately, with a credible path to 90% after several real cycles and benchmark calibration.

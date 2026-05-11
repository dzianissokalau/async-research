# Idea Discovery Workflow

## Purpose

Add autonomy without letting the system manufacture expensive work.

The discovery workflow continuously looks for promising research ideas, but it writes only to a discovery inbox. Promotion into real execution tasks requires planner triage or human approval depending on cost and risk.

## Design Goal

Priorities:

```text
high quality > independence > low cost > speed
```

Discovery can take a week per loop. The goal is not to generate many ideas. The goal is to generate a few ideas that survive cheap rejection.

## Discovery Pipeline

```text
source scout
  -> signal extractor
  -> idea generator
  -> deduper/clusterer
  -> cheap scorer
  -> skeptic filter
  -> discovery_inbox.md
  -> planner capture into ideas/IDEA-*.json
  -> promotion dry-run proposal
  -> promotion write with matching preflight hash
  -> reserved task, queue row, and promoted_task_id
```

## Source Classes

Use a source register rather than browsing freely.
Use the data source audit register for known data readiness, but do not block
early discovery only because a plausible source has not been audited yet.

Recommended source classes:

- existing repo research notes
- `accepted_outputs_index.md` and rejected task outputs
- prior weekly digests
- official dataset release notes
- literature/library files
- recent papers from curated search queries
- dataset freshness reports
- failed experiment reports
- user-added rough ideas

Default rule:

```text
Read internal and already-approved sources first.
Use web browsing only when the source register says it is allowed.
```

## Discovery Inbox

`research_ops/discovery_inbox.md` is the buffer between idea generation and execution.

Example row:

```markdown
| ID | Status | Weighted score | Mission policy | Title | Evidence | Required data | MVP test | Kill reason | Promoted? |
| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| IDEA-0007 | candidate | 19.5 | real_estate_research_v1.0 | EPC premium during energy shocks | EPC + PPD + inflation sources | EPC `DS-0002`, PPD `DS-0001`, energy CPI candidate | London flats 2018-2025 | weak EPC-to-sale matching may kill it | no |
```

## Idea Candidate Contract

Each promoted candidate should have:

```json
{
  "schema_version": "1.0",
  "id": "IDEA-0007",
  "title": "EPC premium during energy shocks",
  "question": "Did high energy prices increase the sale-price premium for efficient homes?",
  "why_it_might_matter": "It could improve valuation and energy-policy evidence.",
  "evidence_seeds": [
    "existing EPC idea in research backlog",
    "inflation housing components dataset"
  ],
  "required_data": ["EPC", "Price Paid Data", "inflation energy components"],
  "minimum_viable_test": "Greater London flats, 2018-2025",
  "baseline": "hedonic model with area and time controls",
  "novelty_angle": "interaction of energy shock timing and EPC capitalization",
  "main_risks": [
    "property matching error",
    "selection into EPC certificate timing",
    "unobserved renovation quality"
  ],
  "kill_reason": "Reject if EPC-to-sale match quality is below threshold or timing leaks post-sale information.",
  "score": {
    "mission_policy_version": "real_estate_research_v1.0",
    "budget_mode": "normal",
    "decision_impact": 4,
    "novelty": 4,
    "data_availability": 3,
    "feasibility": 3,
    "robustness_risk": 3,
    "cost": 2,
    "killability": 4,
    "reuse_potential": 4,
    "weighted_total": 19.5,
    "promotion_threshold": 14.0,
    "minimum_killability": 3,
    "hard_gate_results": [],
    "score_explanation": "Mission policy real_estate_research_v1.0 in normal mode gives weighted_total=19.50; route=promote because mission-weighted score and hard gates allow it."
  },
  "recommended_next_task": "data_readiness"
}
```

## Discovery Scoring

Use `score_idea_candidate.py` to compute a mission-weighted score. Agents may draft dimension values, but the helper computes the weighted total, hard gates, route, and policy version.

| Dimension | Meaning |
| --- | --- |
| Decision impact | Could it change a research, policy, risk, or valuation decision? |
| Novelty | Is the question, data linkage, geography, or method meaningfully different? |
| Data availability | Can public or owned data support an MVP? |
| Feasibility | Can a small task validate the first gate? |
| Killability | Can the idea be rejected quickly if weak? |
| Reuse potential | Would data, code, or findings support other ideas? |
| Robustness risk | Penalty dimension: higher means worse leakage, confounding, or measurement risk. |
| Cost | Penalty dimension: higher means more expensive first validation. |

Promotion formula:

```text
score =
  2.0 * decision_impact
+ 1.5 * data_availability
+ 1.5 * killability
+ 1.0 * feasibility
+ 1.0 * reuse_potential
+ 0.5 * novelty
- 2.0 * robustness_risk
- 1.0 * cost
```

Every scored candidate must record `mission_policy_version`. Automatic budget mode reads current ledger usage and switches to budget-constrained mode near budget limits. Budget-constrained mode raises `minimum_killability` from 3 to 5, raises the promotion threshold, and lowers `max_promotions_per_week` from 3 to 1.

Ideas may use plausible unaudited data paths in `required_data`. Promotion to
`experiment_plan` requires `DS-0000` style references that pass
`async-research source check-experiment`; otherwise the next task should be
`data_readiness`.

## Catalog-To-Queue Promotion

The planner must not turn a discovery inbox row directly into execution work.
The safe path is:

```bash
async-research idea capture research_ops --from-inbox row-7 --id IDEA-0007 --dry-run
async-research idea capture research_ops --from-inbox row-7 --id IDEA-0007 --write
async-research idea catalog validate research_ops
async-research idea promote research_ops IDEA-0007 --dry-run
async-research idea promote research_ops IDEA-0007 --write --preflight-hash <hash>
```

`--from-inbox` selects only explicit Markdown table rows. Free-form notes in
`discovery_inbox.md` are surfaced as warnings with line numbers, and a missing
selector reports nearby candidate rows instead of silently failing.

Only a successful `idea_promotion_planned` response may be passed to write mode,
and the write must use the returned `promotion_preflight_hash`. Blocked
promotion proposals remain catalog/planning state and should be parked,
rejected, repaired, or routed to human review. Duplicate or near-duplicate ideas
must not become tasks unless `--allow-duplicate` is backed by a human decision
or explicit planner note describing the different source, geography, mechanism,
or decision use.

The promotion proposal chooses the cheapest safe next task:

- thin evidence -> `literature_extract`
- missing library support -> resolve `library_refs` against row-level source IDs
  in the generated `source_library.md` block or run `literature_extract` before
  library-dependent routes
- plausible but unaudited data -> `data_readiness`
- bounded hypothesis work -> `hypothesis_card`
- `experiment_plan` only when audited data refs and hard gates already pass

Promotion dry-run exposes `evidence_support.status` so planners can distinguish
true thin evidence from unresolved `LIT-*` support.

Write mode creates the reserved task folder, `status.json`, `task.md`, one
`queue.md` row, the planner-facing `inbox.md` proposal reference, and the
canonical idea's `promoted_task_id`. After write mode succeeds, run
`async-research idea catalog validate research_ops` and
`async-research idea catalog dashboard research_ops`; the promoted idea should
appear in `sections.idea_to_task_links` with `link_status=available`.

## Weekly Discovery Limits

Default:

- scan at most 10 sources or internal artifacts
- generate at most 20 raw candidates
- keep at most 10 after dedupe
- write at most 5 to `discovery_inbox.md`
- planner promotes at most 3 catalog ideas into task folders
- no direct experiment tasks from discovery

These limits are quality controls, not merely cost controls.

## Autonomy Rules

Discovery may:

- read allowed source registers
- summarize gaps
- create idea candidates
- cluster duplicate ideas
- score and reject candidates
- write `discovery_inbox.md`
- propose next tasks
- score candidates with `score_idea_candidate.py --budget-mode auto --ops-dir research_ops`
- respect `score.max_promotions_per_week` when recommending promotions
- cite known data audit IDs when available

Discovery may not:

- edit `queue.md`
- create worker task folders directly
- run experiments
- acquire new data
- browse unboundedly
- claim novelty as fact
- spend paid API/cloud budget unless explicitly allowed

## Skeptic Filter

Before a candidate enters the discovery inbox, run a cheap skeptic check:

```text
Why might this idea be obvious, infeasible, not supported by data, or likely to produce a misleading result?
```

Every idea needs a kill reason. If there is no cheap way to kill it, it is probably too vague.

## Accepted Output Memory

Before adding candidates, refresh and read the accepted outputs index:

```bash
async-research accepted update research_ops
```

Discovery should avoid adding duplicate candidates unless the new idea has a clearly different data path, geography, mechanism, or decision use.

## Human Loop

Human involvement can be weekly:

1. Read top candidates in `discovery_inbox.md`.
2. Mark any as `promote`, `park`, or `reject`.
3. Add a short priority note.

If the human does nothing, the planner can still promote low-cost `hypothesis_card` or `data_readiness` tasks, but not expensive experiments.

## Recommended First Discovery Jobs

1. Mine existing accepted and rejected tasks for follow-up ideas.
2. Convert the top ranked `re_trends_research` ideas into standardized candidates.
3. Find dataset gaps that block multiple ideas.
4. Generate "cheap kill tests" for top candidates.
5. Cluster overlapping ideas into research themes.

## Success Metrics

Track:

- raw candidates generated
- candidates kept after dedupe
- candidates promoted
- candidates rejected cheaply
- promoted candidates that later become accepted outputs
- cost per accepted idea
- number of ideas requiring human clarification

The healthiest discovery system rejects most candidates early.

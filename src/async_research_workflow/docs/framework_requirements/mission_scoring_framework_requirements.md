# Mission Scoring Framework Requirements And Framework v1.0

## Purpose

The mission scoring framework defines what the research system optimizes for across a domain or research program.

It is the stable policy layer above all task-specific rubrics.

This document now defines both the requirements and the executable
`mission_scoring_v1.0` framework used before idea evaluation and planner
promotion.

## Default Mission Objective

For real-estate and economic research, the system should optimize for:

```text
accepted, reproducible, evidence-backed research outputs
per dollar, per human minute, and per data-risk unit
```

## Default Weights

Initial weights:

| Dimension | Weight | Meaning |
| --- | ---: | --- |
| Quality and robustness | 35% | validity, reproducibility, data quality, leakage control, honest limitations |
| Decision usefulness | 20% | ability to change research, policy, risk, valuation, or operational decisions |
| Feasibility | 15% | realistic data, time, compute, and implementation path |
| Cost efficiency | 10% | value per dollar and per human minute |
| Novelty | 10% | non-obvious question, data linkage, method, geography, or output |
| Autonomy | 5% | can advance with low human intervention |
| Speed | 5% | useful turnaround time, but secondary to quality and cost |

These weights are intentionally slow-biased: a one-week high-quality loop is better than a fast weak result.

The executable idea-candidate scoring policy uses the equivalent operational
dimensions in:

```text
async_research_workflow/mission_policy.json
```

That file is validated by the advanced/internal mission policy helper:

```bash
python -m async_research_workflow.scripts.validate_mission_policy \
  async_research_workflow/mission_policy.json
```

Scoring must fail closed when the mission policy is invalid.

## Executable Framework Contract

Mission scoring has two executable layers:

1. Validate the stable mission policy.
2. Score candidate ideas against that policy.

Required commands:

The policy validation command is an advanced/internal helper; the scoring
command is public:

```bash
python -m async_research_workflow.scripts.validate_mission_policy \
  async_research_workflow/mission_policy.json

async-research idea score \
  research_ops/discovery/IDEA-0001.json \
  --budget-mode auto \
  --ops-dir research_ops
```

The policy record conforms to:

```text
async_research_workflow/schemas/mission_policy.schema.json
```

The scored candidate record conforms to:

```text
async_research_workflow/schemas/idea_candidate.schema.json
```

The score template lives at:

```text
async_research_workflow/templates/artifact_templates/mission_score_template.md
```

## Mission Scoring Lifecycle

```text
candidate idea JSON
-> validate mission policy
-> apply mission-weighted score
-> apply hard gates and route adjustment
-> write score.mission_policy_version and score.hard_gate_results
-> idea_evaluation_v1.0 validation
```

Mission scoring decides the first route: `promote`, `park`, or `reject`.
Idea evaluation decides whether the workflow may act on that route.

## Policy Validation Rules

`validate_mission_policy.py` enforces:

- policy has `schema_version="1.0"` and
  `framework_version="mission_scoring_v1.0"`
- policy validates against `mission_policy.schema.json`
- weights exactly match the candidate scoring dimensions
- positive dimensions have positive weights
- penalty dimensions have negative weights
- novelty cannot exceed decision impact, data availability, or killability
- robustness and cost penalties must be at least as strong as novelty
- every scoring dimension maps to mission dimensions
- required hard gates are present
- required human approval thresholds are present
- budget-constrained mode is stricter than normal mode
- budget pressure references valid promotion modes
- monthly calibration has required inputs

Policy changes may be proposed by agents, but a changed policy is not valid for
scheduled use until the human owner approves it through the human decision log.

## Operational Candidate Formula

The current idea-candidate formula is:

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

The formula intentionally makes novelty helpful but unable to overpower weak
data, weak killability, high robustness risk, or high cost.

## Route Rules

Hard gates override composite scores:

- missing research question: reject
- missing credible data path: reject
- missing minimum viable test: reject
- missing baseline or comparison: reject
- missing kill reason: reject
- low killability: park
- direct `experiment_plan` request: reroute to `data_readiness`

Direct discovery promotion to experiment planning is never allowed. If a strong
candidate asks for `experiment_plan`, the scorer records
`direct_experiment_blocked` as passed only after the next task has been safely
rerouted away from `experiment_plan`.

## Functional Requirements

### MSF-FR1: Stable Mission Policy

The system shall store a mission-level scoring policy for each research program.

Abbreviated shape; the operational file must include every field required by
`mission_policy.schema.json`:

```json
{
  "schema_version": "1.0",
  "framework_version": "mission_scoring_v1.0",
  "mission_id": "real_estate_research",
  "mission_policy_version": "real_estate_research_v1.0",
  "objective": "accepted, reproducible, evidence-backed research outputs per dollar, per human minute, and per data-risk unit",
  "weights": {
    "decision_impact": 2.0,
    "data_availability": 1.5,
    "killability": 1.5,
    "feasibility": 1.0,
    "reuse_potential": 1.0,
    "novelty": 0.5,
    "robustness_risk": -2.0,
    "cost": -1.0
  },
  "dimension_map": {
    "decision_impact": ["decision_usefulness"],
    "data_availability": ["quality_robustness", "feasibility"]
  },
  "promotion": {
    "normal": {
      "promotion_threshold": 14.0,
      "park_threshold": 9.0,
      "minimum_killability": 3,
      "max_promotions_per_week": 3
    }
  },
  "budget_pressure": {
    "threshold": 0.8,
    "default_mode": "normal",
    "constrained_mode": "budget_constrained"
  },
  "hard_gates": [
    "research_question_present",
    "data_path_identified"
  ],
  "human_approval_required_for": [
    "mission_policy_change"
  ],
  "last_reviewed": "2026-05-02",
  "calibration": {
    "cadence": "monthly",
    "next_due": "2026-06-02"
  }
}
```

The example policy for this repository lives at:

```text
async_research_workflow/mission_policy.json
```

Initial policy version:

```text
real_estate_research_v1.0
```

### MSF-FR2: Human-Owned Weight Changes

Agents may propose weight changes, but only the human owner may approve changes to mission weights.

Every change shall record:

- previous weights
- proposed weights
- reason
- expected behavior change
- approver
- date

### MSF-FR3: Task Rubric Inheritance

Every task-specific rubric shall map its dimensions back to the mission policy.

Example:

```text
experiment validation design -> quality and robustness
data availability -> feasibility
killability -> cost efficiency and quality
decision impact -> decision usefulness
```

### MSF-FR4: Hard Gate Registry

The mission policy shall define global hard gates.

Required initial global hard gates:

- no unsupported strong claims
- no public or high-stakes claims without human approval
- no expensive compute/API/data acquisition without approval
- no use of private, scraped, or legally sensitive data without approval
- no accepted result without source or artifact provenance

### MSF-FR5: Monthly Calibration

The system shall produce a monthly calibration note comparing:

- high-scoring ideas versus accepted outputs
- rejected ideas and why they were rejected
- average cost per accepted output
- average human time per accepted output
- common reviewer disagreements

## Non-Functional Requirements

### MSF-NFR1: Stability

Weights should not change automatically or more often than monthly unless the human explicitly requests it.

### MSF-NFR2: Interpretability

Every score should be explainable in one short paragraph.

### MSF-NFR3: Auditability

Every final decision should cite:

- mission policy version
- task rubric version
- hard gates applied
- reviewer decision

## Score Anchors

Use the shared 1 to 5 scale:

```text
1 = absent, invalid, or unsafe
2 = weak; major gaps remain
3 = acceptable with explicit caveats
4 = strong and reusable
5 = excellent; should become a reference example
```

## Acceptance Criteria

The mission scoring framework is ready when:

- a mission policy file exists
- the mission policy validates with `validate_mission_policy.py`
- scoring refuses invalid mission policies
- weights match the executable scoring dimensions and signs
- hard gates are listed
- task rubrics map to mission dimensions
- reviewer prompts refer to the current policy
- human-approved changes are logged
- scored candidates include `score.mission_policy_version`,
  `score.budget_mode`, `score.hard_gate_results`, and `score_explanation`
- high novelty cannot promote weak-data/high-risk ideas
- budget-constrained mode tightens thresholds deterministically
- direct experiment requests are rerouted before idea evaluation

## Failure Modes

Watch for:

- agents optimizing novelty while ignoring data quality
- speed becoming a hidden objective
- scores changing silently across tasks
- high composite score overriding hard gates
- all ideas clustering around cheap but low-impact work

## Recommended First Artifact

Create:

```text
research_ops/mission_policy.md
```

with:

- mission objective
- scoring weights
- hard gates
- allowed autonomy level
- human approval thresholds
- calibration schedule

The checked-in JSON example can be copied into the operational repo and reviewed by the human owner before scheduled jobs depend on it.

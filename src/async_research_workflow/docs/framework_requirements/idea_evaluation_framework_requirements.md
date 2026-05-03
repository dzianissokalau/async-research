# Idea Evaluation Framework Requirements And Framework v1.0

## Purpose

The idea evaluation framework decides whether a discovered idea deserves promotion into the execution queue.

It should reject weak ideas early and cheaply.

This document now defines both the requirements and the executable
`idea_evaluation_v1.0` framework used after mission-weighted scoring and before
planner promotion.

## Core Principle

An idea is valuable only if it can become evidence.

Novelty alone is not enough. The system should prefer ideas that are testable, decision-relevant, and killable.

## Executable Framework Contract

Every candidate that may enter `discovery_inbox.md` or be promoted by the
planner shall first be scored with:

```bash
python3 async_research_workflow/examples/scripts/score_idea_candidate.py \
  research_ops/discovery/IDEA-0001.json \
  --budget-mode auto \
  --ops-dir research_ops
```

Then validate and attach the idea-evaluation record:

```bash
python3 async_research_workflow/examples/scripts/validate_idea_evaluation.py \
  research_ops/discovery/IDEA-0001.json \
  --ops-dir research_ops
```

The validator writes `candidate.idea_evaluation` when validation passes. It
fails closed when the candidate violates hard gates, duplicate handling,
rejection logging, direct-experiment blocking, sensitive-data rules, or route
consistency.

The evaluation record conforms to:

```text
async_research_workflow/examples/idea_evaluation.schema.json
```

## Idea Evaluation Lifecycle

```text
exploration cycle
-> raw candidate JSON
-> mission-weighted scoring
-> idea_evaluation_v1.0 validation
-> discovery inbox
-> planner promotion to hypothesis_card, data_readiness, or literature_extract
```

Planner promotion is allowed only when
`idea_evaluation.promotion_readiness.planner_may_promote` is true.

## Required Evaluation Object

The validator adds `idea_evaluation` with:

- identifiers: candidate ID, framework version, evaluation timestamp
- route: one of `promote_to_hypothesis_card`,
  `promote_to_data_readiness`, `promote_to_literature_extract`, `park`,
  `reject`, or `needs_human`
- scorecard copied from the scored candidate
- hard gate results copied from mission scoring
- dedupe audit: duplicate status, checked indexes, cluster ID, representative
  flag
- rejection logging audit: whether logging was required and completed
- promotion readiness: planner permission and blocked reasons
- review notes for downstream reviewer audit

## Hard Gate Enforcement

`validate_idea_evaluation.py` enforces:

- scored candidate passes `idea_candidate.schema.json`
- evaluation record passes `idea_evaluation.schema.json`
- title, research question, decision rationale, data path, minimum viable test,
  baseline, risks, and kill reason are present
- mission score hard gates have no failures
- promoted candidates meet promotion threshold and minimum killability
- direct `experiment_plan` routing is blocked
- promoted candidates route only to `hypothesis_card`, `data_readiness`, or
  `literature_extract`
- duplicates and near-duplicates cannot be promoted
- dedupe targets exist: accepted outputs, discovery inbox, queue, rejected ideas
- parked and rejected candidates have concrete revisit conditions
- parked and rejected candidates are logged in `discovery/rejected_ideas.md`
- candidates that appear to rely on private, scraped, sensitive, or restricted
  data fail closed

Warnings do not block validation but should be reviewed. Examples include
near-duplicate candidates and speculative candidates that are otherwise
promotable.

## Relationship To Mission Scoring

Mission scoring answers:

```text
How good is this idea under current mission weights?
```

Idea evaluation answers:

```text
May the workflow act on this scored idea?
```

Mission scoring can route a candidate to `promote`, `park`, or `reject`.
Idea evaluation audits whether that route is safe, logged, deduplicated, and
consistent with workflow policy.

## Functional Requirements

### IEF-FR1: Required Idea Candidate Fields

Every idea candidate shall include:

- title
- research question
- why it might matter
- evidence seeds or source references
- required data
- minimum viable test
- likely baseline
- novelty angle
- main risks
- kill reason
- recommended next task
- scorecard

### IEF-FR2: Scoring Dimensions

Each idea shall be scored from 1 to 5 on:

| Dimension | Meaning |
| --- | --- |
| Decision impact | Could this change a real decision, monitoring process, or research direction? |
| Novelty | Is the contribution non-obvious relative to known literature and existing outputs? |
| Data availability | Can public or owned data support a credible MVP? |
| Feasibility | Can a small first task make progress? |
| Killability | Is there a cheap test that can reject the idea? |
| Robustness risk | Are leakage, bias, confounding, and measurement risks manageable? |
| Cost | Is the first validation step cheap enough? |
| Reuse potential | Would data, code, or findings support other ideas? |

### IEF-FR3: Promotion Score

The default mission-weighted promotion score shall be:

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

The score is only a ranking aid. Hard gates still apply, and every score shall cite the active mission policy version.

### IEF-FR4: Hard Gates

An idea shall not be promoted if:

- it has no clear research question
- it has no identifiable data path
- it has no minimum viable test
- it lacks a kill reason
- it depends on unapproved private, scraped, or legally sensitive data
- it requires expensive compute or API spend before data readiness
- it cannot state a baseline or comparison

### IEF-FR5: Promotion Routes

Every idea shall route to one of:

```text
promote_to_hypothesis_card
promote_to_data_readiness
promote_to_literature_extract
park
reject
needs_human
```

Direct promotion to experiment execution is not allowed.

### IEF-FR6: Dedupe And Clustering

Before promotion, the system shall compare each idea against:

- existing discovery inbox
- active queue
- accepted outputs
- parked ideas
- rejected ideas

The system should cluster similar ideas and promote the strongest representative.

### IEF-FR7: Rejection Logging

Rejected ideas shall be logged with:

- idea title
- rejection reason
- source
- date
- whether rejection is permanent or temporary
- condition that would make the idea worth revisiting

## Non-Functional Requirements

### IEF-NFR1: Low Cost

Idea evaluation should usually use local, cheap, or batch models. Frontier review is reserved for top candidates.

### IEF-NFR2: Independence

The discovery job may propose ideas without human input, but the planner must control promotion into execution tasks.

### IEF-NFR3: Diversity

The framework should avoid promoting only one type of idea.

Recommended portfolio:

```text
70% exploit known high-value research lanes
20% adjacent exploration
10% high-upside speculative ideas
```

## Score Anchors

Example for `data_availability`:

```text
1 = no known data path
2 = possible data path, but major access or quality gaps
3 = data likely usable with caveats
4 = strong available data and known joins
5 = data already profiled and ready for experiment planning
```

Example for `killability`:

```text
1 = no cheap way to reject
2 = rejection requires large experiment
3 = one data-readiness task can reject
4 = one small analysis can reject
5 = existing metadata or prior output can reject quickly
```

## Acceptance Criteria

The idea evaluation framework is ready when:

- every discovery candidate uses a standard scorecard
- every scored candidate cites the mission policy version
- every promoted idea has a kill reason
- direct promotion to experiment execution is blocked
- rejected ideas are logged
- duplicate ideas are clustered
- reviewer prompts can audit idea scores
- `validate_idea_evaluation.py` accepts valid scored candidates
- `validate_idea_evaluation.py` fails candidates that skip rejection logging,
  promote duplicates, route directly to experiments, or fail mission hard gates
- the durable acceptance suite covers idea-evaluation hard gates

## Failure Modes

Watch for:

- too many ideas promoted
- high novelty but weak data
- no cheap rejection path
- repeated duplicate ideas
- discovery generating work faster than review capacity
- score inflation across all dimensions

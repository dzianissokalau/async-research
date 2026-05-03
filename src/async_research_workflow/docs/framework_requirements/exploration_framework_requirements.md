# Exploration Framework Requirements And Framework v1.0

## Purpose

The exploration framework controls how the system searches for new ideas and chooses what to investigate next.

It prevents the autonomous discovery loop from drifting into endless novelty hunting or creating more work than the system can review.

This document now defines both the requirements and the executable
`exploration_v1.0` framework used by idea discovery and discovery-scout cycles.

## Exploration Policy

Default allocation:

```text
70% exploit known high-value lanes
20% adjacent exploration
10% high-upside speculative ideas
```

Definitions:

- exploit: known data, known methods, clear decision value
- adjacent: nearby domain, new linkage, or new mechanism using mostly known data
- speculative: unusual hypothesis, uncertain data path, or high upside

## Executable Framework Contract

Every `idea_discovery` task or discovery-scout run shall produce either:

- `exploration_cycle.json`
- or a fenced JSON block inside `worker_output.md`

The JSON cycle must conform to:

```text
async_research_workflow/examples/exploration_cycle.schema.json
```

Validate the cycle with:

```bash
python3 async_research_workflow/examples/scripts/validate_exploration_cycle.py \
  research_ops/tasks/TASK-0002-idea-discovery/worker_output.md \
  --ops-dir research_ops \
  --task-dir research_ops/tasks/TASK-0002-idea-discovery
```

The validator fails closed when exploration limits, source constraints,
duplicate handling, drift controls, direct-experiment blocks, or source-register
requirements are violated.

## Exploration Lifecycle

```text
source register
-> accepted/rejected memory scan
-> bounded exploration cycle
-> exploration cycle validation
-> mission-weighted idea scoring
-> discovery inbox
-> planner promotion to small tasks
```

Discovery outputs remain candidates. They may update `discovery_inbox.md` and
`discovery/rejected_ideas.md`, but they must not directly edit `queue.md` or
create executable task folders.

## Required Source Register

The source register lives at:

```text
research_ops/discovery/source_register.md
```

Required columns:

```text
source_id | source_name | source_type | location | allowed_browsing |
update_cadence | trust_level | expected_idea_types | last_checked
```

`source_id` values use the `SRC-0000` format. Candidate source refs must point
to these source IDs.

Allowed source types:

- `internal`
- `official_data`
- `literature`
- `repo_artifact`
- `user_seed`
- `web`

Allowed trust levels:

- `high`
- `medium`
- `low`

## Exploration Cycle Object

The cycle object records:

- identifiers: `exploration_id`, `task_id`, `framework_version`
- mission boundary: `mission_scope`
- limits: sources, candidates, inbox additions, promotions, API/compute, human
  decisions
- search modes used
- target category allocation
- sources scanned
- raw and kept candidate counts
- candidate records with category, source refs, trigger, status, rank,
  duplicate status, and revisit condition
- stop rules triggered
- duplicate and parking summaries
- exploration health summary

This object is not a substitute for idea scoring. It controls exploration
discipline before or alongside `score_idea_candidate.py`.

## Hard Gate Enforcement

`validate_exploration_cycle.py` enforces:

- source register exists, is parseable, and has at least one source
- every scanned source exists in the source register
- every candidate references at least one registered source
- default weekly limits are not exceeded unless the framework is explicitly
  changed
- observed counts do not exceed declared cycle limits
- `kept_candidates` equals the number of candidate records
- every candidate has one category: `exploit`, `adjacent`, or `speculative`
- category distribution in `health_summary` matches candidate records
- accepted-output duplicate checking happened
- duplicates cannot be promoted
- parked and rejected ideas have revisit conditions and are logged
- high-drift candidates cannot be promoted
- direct `experiment_plan` promotion is blocked
- `status.json` records `framework_versions.exploration =
  "exploration_v1.0"` when a task directory is provided

Warnings do not block review, but they must be discussed. The main warning is
an unusually high speculative share.

## Ranking Rule

Within a valid cycle:

```text
candidate_rank = idea_score + diversity_bonus - duplicate_penalty - drift_penalty
```

The exploration validator checks that the fields are present. Mission-weighted
scoring still controls promotion quality; exploration ranking controls
portfolio discipline and prevents duplicate overload.

## Functional Requirements

### EF-FR1: Source Register

The system shall maintain a source register for discovery.

Minimum fields:

- source name
- source type
- location or URL
- allowed browsing status
- update cadence
- trust level
- expected idea types
- last checked date

### EF-FR2: Exploration Budget

Each discovery cycle shall define:

- maximum sources scanned
- maximum raw candidates generated
- maximum candidates kept
- maximum candidates promoted
- maximum API or compute spend
- maximum human decisions requested

Default weekly limits:

```text
sources_scanned <= 10
raw_candidates <= 20
kept_candidates <= 10
discovery_inbox_additions <= 5
promotions_to_tasks <= 3
```

### EF-FR3: Search Modes

The exploration framework shall support:

- internal mining of existing notes and accepted outputs
- rejected idea revisiting
- source-register scanning
- dataset-gap driven idea generation
- method-transfer idea generation
- contradiction and anomaly detection
- user-seeded exploration

### EF-FR4: Exploration Categories

Each idea candidate shall be tagged as:

```text
exploit
adjacent
speculative
```

The weekly digest shall report the distribution.

### EF-FR5: Exploration Stop Rules

A discovery job shall stop when:

- it reaches the candidate limit
- it cannot find candidates above threshold
- it hits budget limits
- source quality is too weak
- duplicate rate is too high
- required source access is unavailable

### EF-FR6: Parked Idea Revisit

Parked ideas shall include a revisit condition.

Examples:

- new data source becomes available
- existing join quality improves
- related accepted output exists
- human raises priority
- cost falls below threshold

## Non-Functional Requirements

### EF-NFR1: Low Human Load

The human should see only the top candidates and blocked decisions, not all raw exploration output.

### EF-NFR2: Diversity Without Drift

The system should preserve portfolio diversity but avoid exploring outside the mission without explicit approval.

### EF-NFR3: Traceability

Every candidate should link to the source or prior artifact that triggered it.

## Exploration Score

The exploration layer should rank candidates using the idea evaluation score plus a diversity adjustment:

```text
candidate_rank = idea_score + diversity_bonus - duplicate_penalty - drift_penalty
```

Where:

- diversity_bonus rewards underexplored but mission-relevant categories
- duplicate_penalty lowers near-duplicates
- drift_penalty lowers ideas outside the mission scope

## Hard Gates

Discovery shall not:

- write directly to the execution queue
- create experiment tasks directly
- browse outside approved sources
- use private, scraped, or sensitive data without approval
- generate unlimited candidates
- hide rejected candidates

## Acceptance Criteria

The exploration framework is ready when:

- a source register exists
- weekly exploration limits are explicit
- every candidate has a category and source
- duplicate and parked ideas are handled
- promotion limits are enforced
- weekly digest reports exploration health
- `validate_exploration_cycle.py` accepts valid cycles and fails cycles that
  exceed limits, omit source refs, promote duplicates, or route directly to
  `experiment_plan`
- the durable acceptance suite covers exploration hard gates

## Failure Modes

Watch for:

- speculative ideas consuming too much attention
- overfitting to sources that are easiest to scan
- repeated rediscovery of same ideas
- no rejected idea log
- discovery inbox becoming a second unreviewed queue
- agents optimizing for novelty instead of accepted evidence

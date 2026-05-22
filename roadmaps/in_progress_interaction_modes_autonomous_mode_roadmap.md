# Interaction Modes And Autonomous Mode Roadmap

Status: In Progress
Current phase: Phase 5 - Dashboard And Operator UX
Last updated: 2026-05-22
Next action: Expose mode, interrupt policy, auto-decisions, and progression-flow effects in the dashboard
Blocked by: None

Created: 2026-05-21

## Summary

This roadmap delivers interaction modes for the async research framework so a
user can decide how much authority the system has before a run starts. The goal
is to stop routine research work from requiring human input at every step while
preserving the framework's quality gates, auditability, and safety boundaries.

The current framework is careful, but too interruptive. `needs_human` is used as
the default safe route for many uncertain states, which protects quality but
forces the operator to approve routine transitions, revisions, source choices,
and prioritization decisions. In real research use, this makes progress feel
slow and fragmented.

The desired product behavior is mode-aware:

- in manual mode, the framework asks before most important transitions;
- in guided mode, it recommends and asks before meaningful forks;
- in supervised mode, it handles routine decisions and asks only for high-risk
  or strategic issues;
- in autonomous mode, it makes decisions under a conservative policy and records
  them without interrupting the user;
- in publication-guarded mode, internal research proceeds autonomously while
  external/publication-quality claims still require stricter review and explicit
  approval.

Autonomous mode must not skip quality gates. It should resolve them with
conservative policies: revise, downgrade claim strength, park ideas, substitute
approved sources, reject unsafe outputs, or defer publication claims.

## Product Promise

> Choose the level of autonomy once, then let the framework advance routine
> research work without repeatedly asking for human input.

## Non-Goals

- Do not remove human gates for credentials, destructive operations, private
  data, legal/policy-sensitive claims, publication/submission approval, or hard
  budget breaches.
- Do not let autonomous mode mark weak internal outputs as publication-ready.
- Do not silently mutate task state without an audit row.
- Do not make mode decisions dependent on model memory alone. Workspace config,
  task state, CLI validation, and audit logs remain the source of truth.

## Mode Taxonomy

| Mode | Human Role | Framework Behavior | Best Use |
| --- | --- | --- | --- |
| `manual` | Human approves most transitions. | Current careful/debug behavior. | Framework debugging, new workflows, sensitive research. |
| `guided` | Human approves important forks. | Recommends next actions and asks before meaningful changes. | Early project setup and unfamiliar domains. |
| `supervised` | Human handles high-risk blockers. | Routine revisions, source substitutions, and prioritization can proceed automatically. | Normal research operations. |
| `autonomous` | Human is not required during the run unless a hard stop is hit. | Makes conservative policy decisions and writes audit logs. | Long-running research loops and dogfood runs. |
| `publication_guarded` | Human approval is required for external/publication claims. | Internal research can proceed autonomously; publication gates remain strict. | Drafting papers, public memos, and external reports. |

## Phased Plan

| Phase | Status | Priority | Focus | Scope | Exit Criteria |
| ---: | --- | --- | --- | --- | --- |
| 0 | Complete | P0 | Mode contract and authority model | Define modes, authority boundaries, interrupt classes, and default behavior. | A future implementer can tell exactly which decisions each mode may make. |
| 1 | Complete | P0 | Workspace mode config | Add a durable `research_ops` mode config, validators, and CLI visibility. | Operators and LLMs can inspect and set the current mode safely. |
| 2 | Complete | P0 | Mode-aware `needs_human` policy | Split gates by category and map each category to automatic or human resolution by mode. | Routine `needs_human` states stop blocking autonomous runs. |
| 3 | Complete | P0 | Auto-decision audit trail | Record framework-made decisions with policy, reason, confidence, actor, and artifacts. | Autonomy remains inspectable without requiring approval. |
| 4 | Complete | P0 | Workflow integration | Wire modes into readiness, workflow next/advance, review aggregation, idea catalog, and deliverable gates. | The main workflow can advance under mode policy end to end. |
| 5 | Not Started | P1 | Dashboard and operator UX | Show mode, interrupt policy, auto-decisions, and progression-flow effects in the console. | Users can understand what the framework is allowed to do and what it already did. |
| 6 | Not Started | P1 | Tests and autonomous simulations | Add mode contract tests, fixture gates, and zero-human loop simulations. | Autonomous mode is proven by tests, not just configuration. |
| 7 | Not Started | P1 | Default behavior and migration | Decide default mode, migration behavior, quickstart copy, and LLM operator prompts. | New users get less interruptive behavior without surprising existing workspaces. |

## Phase 0 - Mode Contract And Authority Model

### Objective

Define the exact authority model before changing state transitions. This phase
should answer what the framework may decide, what it must audit, and what still
requires the human.

### Scope

- mode names and definitions
- default mode for new workspaces
- migration behavior for existing workspaces
- interrupt categories
- per-mode decision matrix
- hard-stop conditions that cannot be auto-resolved
- publication and external-claim boundary
- conservative fallback hierarchy

### Implementation Steps

1. Create a mode contract document under framework docs.
2. Define interrupt categories:
   - quality uncertainty
   - source freshness or approval problem
   - review disagreement
   - revision limit reached
   - idea prioritization ambiguity
   - budget warning
   - hard budget breach
   - missing credentials or inaccessible data
   - destructive file/system operation
   - private or sensitive data use
   - external/publication claim approval
3. Define per-mode resolution behavior for every category.
4. Define hard stops that autonomous mode cannot bypass.
5. Define default safe actions:
   - revise before accepting
   - downgrade claim strength before blocking
   - park before deleting or losing context
   - reject unsafe outputs
   - defer publication claims until explicit approval
6. Add examples for the same gate resolving differently in `manual`,
   `supervised`, and `autonomous` modes.

### Acceptance Criteria

- Every operating mode has an explicit authority boundary.
- Every interrupt category has a default route for each mode.
- Autonomous mode has no path that skips result acceptance, source governance,
  or deliverable maturity gates.
- The contract states which actions always require human approval.

### Verification

- Run `git diff --check`.
- Run `.venv/bin/python -m unittest tests.test_doc_references`.

## Phase 1 - Workspace Mode Config

### Objective

Make interaction mode a durable workspace setting that both humans and LLM
operators can inspect before acting.

### Scope

- new workspace config file, likely `research_ops/interaction_mode.json`
- schema validation
- starter template defaults
- CLI commands to show, set, and validate mode
- console snapshot inclusion

### Suggested Config Shape

```json
{
  "schema_version": "1.0",
  "mode": "supervised",
  "risk_tolerance": "conservative",
  "interrupt_policy": {
    "allow_interrupts": true,
    "interrupt_only_for": [
      "credentials_missing",
      "hard_budget_breach",
      "destructive_operation",
      "external_publication_approval",
      "private_data_approval"
    ]
  },
  "auto_decisions": {
    "allow_resume": true,
    "allow_revision": true,
    "allow_reject": true,
    "allow_claim_downgrade": true,
    "allow_source_substitution": true,
    "allow_idea_prioritization": true
  },
  "audit": {
    "write_decisions": true,
    "write_auto_decisions": true,
    "explain_auto_decisions": true
  }
}
```

### Implementation Steps

1. Add `interaction_mode.schema.json`.
2. Add starter `research_ops/interaction_mode.json`.
3. Add CLI commands:
   - `async-research mode show research_ops`
   - `async-research mode set research_ops --mode supervised`
   - `async-research mode validate research_ops`
4. Include mode summary in `console snapshot`.
5. Make LLM operator docs require reading mode before mutating workflow state.

### Acceptance Criteria

- Missing mode config has a deterministic default.
- Invalid mode config fails closed with actionable errors.
- Existing workspaces are not silently changed.
- CLI output is JSON-readable for LLM operators.

## Phase 2 - Mode-Aware `needs_human` Policy

### Objective

Turn `needs_human` from a universal stop sign into a mode-aware routing state.

### Scope

- structured gate categorization
- policy resolver for human gates
- per-mode target status selection
- dry-run behavior
- validation integration

### Implementation Steps

1. Extend structured `human_gate` payloads with a normalized `gate_category`.
2. Add a resolver that evaluates:
   - current mode
   - gate category
   - task status and allowed transitions
   - source, budget, review, and deliverable constraints
   - configured risk tolerance
3. Map automatic outcomes:
   - resume to `ready_for_worker`
   - revise to `ready_for_worker` with a bounded revision instruction
   - pause only when safe progress is impossible
   - reject when output is unsafe or invalid
4. Keep manual resolution available through existing
   `async-research decision resolve-task`.
5. Add dry-run output explaining why a gate can or cannot be auto-resolved.

### Acceptance Criteria

- In `manual`, the current explicit human decision behavior is preserved.
- In `autonomous`, routine quality/source/revision gates resolve without
  operator input when policy allows.
- Hard stops still block autonomous mode.
- Every auto-resolution validates through the existing transition rules.

## Phase 3 - Auto-Decision Audit Trail

### Objective

Preserve trust by making autonomous decisions visible, durable, and reviewable.

### Scope

- append-only auto-decision rows
- link to task, policy, mode, and artifacts
- confidence/rationale fields
- summary command for calibration

### Implementation Steps

1. Decide whether auto-decisions share `decisions.md` with a framework actor or
   live in a separate `auto_decisions.md`.
2. Add fields:
   - date
   - item id
   - mode
   - policy version
   - decision
   - target status
   - reason
   - confidence
   - actor
   - related artifacts
3. Add helper command:
   - `async-research decision auto-resolve-task ... --dry-run`
4. Add summary command support for human and auto decisions.
5. Add audit completeness validation.

### Acceptance Criteria

- No autonomous state transition occurs without an audit row.
- The audit row explains why the framework did not interrupt the user.
- Operators can distinguish human approvals from framework policy decisions.

## Phase 4 - Workflow Integration

### Objective

Make operating mode affect the actual workflow path, not just dashboard labels.

### Scope

- readiness gate
- health check
- `workflow next`
- `workflow advance`
- review aggregation
- idea catalog
- source/data/library gates
- deliverable maturity gates

### Implementation Steps

1. Update readiness so unresolved gates are evaluated against the current mode.
2. Update `workflow next` to recommend automatic actions when mode allows them.
3. Update `workflow advance` to run approved auto-resolution steps.
4. Update review aggregation:
   - disagreement can auto-route to revision or bounded adjudication
   - public/high-stakes acceptance still requires the proper gate
5. Update idea catalog:
   - autonomous mode can park, reject, reprioritize, or promote when gates pass
   - high-risk promotion still requires explicit approval if configured
6. Update deliverable maturity:
   - internal draft maturity can advance autonomously
   - submission-ready/publication-ready claims require explicit gate completion

### Acceptance Criteria

- A routine task loop can advance without repeated human confirmations.
- The same workspace behaves differently under different modes.
- Publication gates remain stricter than internal acceptance gates.

## Phase 5 - Dashboard And Operator UX

### Objective

Make autonomy visible and understandable to the user.

### Scope

- mode indicator
- interrupt policy panel
- auto-decision feed
- workflow progression flow diagram integration
- mode switch controls

### Implementation Steps

1. Show current mode near the top of the dashboard.
2. Show what can still interrupt the user.
3. Show recent auto-decisions with reasons and artifact links.
4. Add mode-aware status to the progression flow diagram:
   - current stage
   - blocked stage
   - auto-resolved gates
   - next automatic action
   - hard stops
5. Add guarded dashboard actions for mode switch and validation.

### Acceptance Criteria

- The user can tell whether the framework is in `manual`, `supervised`, or
  `autonomous` mode without inspecting files.
- The dashboard distinguishes "blocked because policy cannot continue" from
  "auto-resolved by policy".
- The progression flow explains where the research is, not just how many files
  exist.

## Phase 6 - Tests And Autonomous Simulations

### Objective

Prove the feature with tests and end-to-end simulations.

### Scope

- mode contract tests
- gate-resolution fixtures
- no-human autonomous loop simulation
- publication gate regressions
- audit completeness tests

### Implementation Steps

1. Add fixtures for each gate category.
2. Test the same fixture under multiple modes.
3. Add simulation where autonomous mode completes a routine workflow with zero
   human input.
4. Add simulation where autonomous mode correctly stops for a hard blocker.
5. Test that publication-ready status cannot be reached without required gates.
6. Test that every auto-decision has an audit row and artifact link.

### Acceptance Criteria

- Autonomous mode is demonstrated end to end.
- Human-interrupt count is measurable.
- Tests prevent future changes from reintroducing routine interruptions.

## Phase 7 - Default Behavior And Migration

### Objective

Make the framework less interruptive for new users without surprising existing
workspaces.

### Scope

- default mode decision
- migration note
- quickstart update
- LLM operator prompt updates
- release notes

### Implementation Steps

1. Decide the new default:
   - recommended: `supervised` for new workspaces
   - keep existing workspaces unchanged unless mode config is added explicitly
2. Update quickstart to ask: "How autonomous should this run be?"
3. Update operator skill and prompts to read mode first.
4. Add release notes explaining the behavior change.
5. Add troubleshooting docs for unexpectedly frequent interrupts.

### Acceptance Criteria

- New users get a less interruptive default experience.
- Existing users do not unexpectedly lose manual control.
- LLM operators can explain why the framework did or did not ask for input.

## Priority Recommendation

Deliver this before adding more dashboard polish or more research features. The
current product pain is not only missing capability; it is too much required
operator intervention. Interaction modes create the authority layer that makes
the rest of the framework usable for real research runs.

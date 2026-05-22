# Interaction Mode Contract

Created: 2026-05-22
Status: Active contract

## Purpose

This contract defines the authority model for interaction modes before any
workflow state transitions change. It answers which decisions the framework may
make, which decisions it may only recommend, which decisions must be audited,
and which decisions always require a human.

Interaction modes reduce routine interruptions. They do not weaken result
acceptance, source governance, deliverable maturity, transition validation,
budget controls, or publication approval.

## Non-Goals

- Do not change task transitions in this phase.
- Do not resolve `needs_human` automatically until a policy-backed resolver and
  durable audit row exist.
- Do not approve credentials, private data, destructive operations, legal or
  policy-sensitive claims, hard budget breaches, or publication/submission
  claims without a human.
- Do not make mode behavior depend on chat memory. Workspace config, task state,
  validation output, and audit logs are the source of truth.

## Modes

| Mode | Authority Boundary | Human Role | Default Use |
| --- | --- | --- | --- |
| `manual` | The framework may inspect state, validate, and recommend actions, but it must not resolve human gates or mutate task status without an explicit human decision. | Approves most meaningful transitions and all human gates. | Existing workspaces, framework debugging, sensitive research. |
| `guided` | The framework may prepare a recommended route and dry-run validation, but it asks before status changes, source substitutions, claim downgrades, or prioritization changes. | Chooses among recommended options. | Early project setup and unfamiliar domains. |
| `supervised` | The framework may resolve routine, reversible gates when policy and transition validation allow it, but it stops for hard blockers and strategic choices. | Handles high-risk blockers and reviews audit trails. | Normal research operations. |
| `autonomous` | The framework may make conservative policy decisions without interrupting the operator, but every mutating decision requires validation and an audit row. | Intervenes only for hard stops or explicit review requests. | Long-running internal research loops. |
| `publication_guarded` | The framework may run internal research like `autonomous`, but external, public, submission-ready, or high-stakes claims still require explicit approval. | Approves publication boundary crossings. | Drafting papers, public memos, and external reports. |

## Defaults And Migration

New starter workspaces default to `supervised` through a checked-in
`interaction_mode.json`. That is the less-interruptive default for fresh
research runs: routine, reversible gates may continue only when policy,
transition validation, and audit logging allow them.

Existing workspaces without an interaction-mode config keep manual-compatible
behavior for mutating commands. Tools may report an effective mode such as
`manual` or `manual_legacy_default`, but they must not silently write a new mode
config or reduce interruptions for an existing workspace without an explicit
migration action.

Missing or invalid mode config fails closed. If a command cannot prove the
current mode, policy version, task status, and required gates, it must preserve
the current manual behavior.

## Interrupt Categories And Default Routes

| Interrupt Category | `manual` | `guided` | `supervised` | `autonomous` | `publication_guarded` |
| --- | --- | --- | --- | --- | --- |
| quality uncertainty | Ask the human to accept, revise, or reject. | Recommend a revision or rejection and ask before routing. | Auto-route to bounded revision when validation allows; otherwise ask. | Revise, downgrade claim strength, or reject under policy; audit every route. | Same as `autonomous` for internal work; defer external claims until approval. |
| source freshness or approval problem | Ask for source approval, substitution, or scope reduction. | Recommend an approved substitute, claim downgrade, or narrower scope and ask. | Substitute only already-approved fresh sources or downgrade claims; ask if approval is missing. | Substitute approved sources, downgrade claims, or pause when no approved source exists; audit the decision. | Internal claims may be downgraded or substituted; external claims require approved sources and publication approval. |
| review disagreement | Ask for adjudication, panel review, revision, or rejection. | Recommend adjudication or revision and ask. | Route to bounded revision or configured adjudication when thresholds allow. | Route to bounded revision, configured adjudication, or rejection; never accept disputed outputs by skipping review. | Internal disagreement follows `autonomous`; public disagreement requires explicit approval before external use. |
| revision limit reached | Ask whether to extend, narrow, pause, or reject. | Recommend pause, narrowed retry, or rejection and ask. | Park or reject the task when no accepted output is safe; do not reset limits automatically. | Park or reject with audit when the policy says more retries are low value; do not reset limits automatically. | Park, reject, or defer public work; publication readiness cannot be claimed after an exhausted revision loop. |
| idea prioritization ambiguity | Ask for priority, scope, or rejection. | Recommend a score, parking decision, or promotion and ask. | Apply configured scoring and park low-confidence ideas; ask on close or strategic choices. | Score, park, reject, reprioritize, or promote only when gates pass; audit the route. | Internal prioritization may proceed; external/high-risk promotion still requires approval when configured. |
| budget warning | Ask whether to continue, narrow, or pause. | Recommend cheaper scope or pause and ask. | Choose cheaper approved work, narrow scope, or park before breaching budget. | Choose cheaper approved work, narrow scope, or park before breaching budget; audit the action. | Same as `autonomous`; public deliverables remain approval-bound. |
| hard budget breach | Human approval required; pause or stop. | Human approval required; pause or stop. | Human approval required; pause or stop. | Human approval required; pause or stop. | Human approval required; pause or stop. |
| missing credentials or inaccessible data | Human approval or setup required. | Human approval or setup required. | Human approval or setup required. | Human approval or setup required. | Human approval or setup required. |
| destructive file or system operation | Human approval required. | Human approval required. | Human approval required. | Human approval required. | Human approval required. |
| private or sensitive data use | Human approval required. | Human approval required. | Human approval required. | Human approval required. | Human approval required. |
| external or publication claim approval | Human approval required. | Human approval required. | Human approval required before external use. | Defer, downgrade, or keep internal until a human approves external use. | Human approval required before external use. |

## Hard Stops

These conditions are never auto-resolved by interaction mode:

- missing credentials, inaccessible private systems, or unavailable paid
  services;
- destructive file, repository, cloud, or system operations;
- private, sensitive, regulated, or non-consented data use;
- hard budget breaches or requests to increase budget limits;
- legal, policy-sensitive, or high-stakes claims that require accountable
  approval;
- publication, submission, public distribution, or external-claim approval;
- missing source-governance evidence for claims that require approved sources;
- missing result-acceptance evidence for accepted outputs;
- missing deliverable maturity gates for submission-ready or publication-ready
  status.

## Gate Preservation Rules

Autonomous mode has no path that skips result acceptance, source governance, or
deliverable maturity gates.

Mode policy may choose a conservative route around an unsafe gate: revise,
downgrade claim strength, substitute an already-approved source, park the idea,
reject the output, or defer publication. It may not relabel an unsafe output as
accepted, silently approve an unaudited source, or mark an internal draft as
publication-ready.

Task status changes must still validate through the existing transition rules.
An automatic route out of `needs_human` must use an allowed transition and must
have a matching audit record before the mutation is considered valid.

## Conservative Fallback Hierarchy

When a mode has authority to act, it should prefer the first safe option in this
order:

1. Validate that the current state and mode config are readable.
2. Preserve the current state when required evidence is missing.
3. Revise before accepting.
4. Downgrade claim strength before blocking broad internal progress.
5. Substitute only already-approved sources.
6. Park before deleting, dropping context, or losing future options.
7. Reject unsafe outputs instead of accepting them with caveats.
8. Defer publication claims until explicit approval exists.
9. Ask a human when no policy-backed safe route remains.

## Audit Requirements

Every framework-made mutating decision must write a durable audit row. The row
must identify the item, mode, policy version, decision, target status, reason,
confidence, actor, validation result, and related artifacts.

The actor for framework-made decisions is not a human approver. Existing human
decision logs must remain distinguishable from policy decisions. Until a
dedicated auto-decision log exists, implementations must either use a clearly
marked framework-policy audit row or stay in dry-run mode for autonomous
mutation.

## Examples

### Quality Uncertainty

A worker output has useful evidence but weak support for one claim.

- `manual`: route to `needs_human` and ask whether to revise, accept with
  caveats, or reject.
- `supervised`: route to bounded revision if the revision limit allows it and
  the transition validates.
- `autonomous`: downgrade the weak claim or request bounded revision, write an
  audit row, and continue only after validation passes.

### Source Freshness Problem

An accepted-memory claim depends on a stale source.

- `manual`: ask for source approval or claim downgrade.
- `supervised`: substitute an already-approved fresh source or downgrade the
  claim; ask if no approved source exists.
- `autonomous`: substitute only approved sources, otherwise downgrade or pause;
  never silently approve a new source.

### Publication Boundary

An internal draft is ready to become a public memo.

- `manual`: ask for publication approval.
- `supervised`: keep the draft internal and surface the approval request.
- `autonomous`: defer publication or downgrade to internal-only status.
- `publication_guarded`: require explicit approval before any external claim.

## Implementation Notes For Later Phases

- Phase 1 should persist the selected mode and expose it through CLI-readable
  JSON without changing existing workspaces silently.
- Phase 2 should keep `manual` behavior intact and evaluate automatic
  `needs_human` routes through policy and transition validation.
- Phase 3 must make auto-decision audit rows durable before autonomous mutation
  is treated as complete.
- Phase 4 and later phases may integrate mode policy into readiness, workflow
  advancement, review aggregation, idea catalog actions, deliverable gates, and
  dashboard views only within the hard-stop and gate-preservation rules above.

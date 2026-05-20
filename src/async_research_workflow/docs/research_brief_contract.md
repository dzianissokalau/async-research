# Research Brief Contract

Status: Phase 2 contract

The research brief is the pre-planning artifact that turns vague user intent
into a bounded executable brief before task creation. It does not replace the
task state machine, review gates, result acceptance, runtime traces, or evidence
objects.

Canonical path:

```text
research_ops/briefs/research_brief.json
```

Schema:

```text
schemas/research_brief.schema.json
```

Public commands:

```bash
async-research brief draft research_ops --question "<request>" --audience "<audience>" --output-maturity internal_draft --write
async-research brief validate research_ops/briefs/research_brief.json
async-research brief apply research_ops research_ops/briefs/research_brief.json --dry-run
async-research workflow create-task research_ops --title "<task>" --brief research_ops/briefs/research_brief.json --dry-run
```

Phase 2 apply is dry-run only. The apply command returns a planner-facing task
creation command and status overrides, but it never creates task folders,
updates `queue.md`, or starts worker execution.

## Required Fields

Each `research_brief.json` must record:

- `user_question`
- `clarified_objective`
- `intended_output_maturity`
- `target_audience`
- `target_venue`
- `allowed_source_classes`
- `forbidden_source_classes`
- `private_data_policy`
- `public_claims_policy`
- browsing, API, code, network, credential, and paid-service permissions
- API, compute, human-time, and runtime caps
- `known_assumptions`
- `unresolved_questions`
- `human_gates`

`intended_output_maturity` and `target_audience` must be concrete before the
brief is ready for planning. `unspecified` is valid draft state, but it blocks
`brief validate` and `brief apply --dry-run`.

## Planning Gate

A brief is ready for planning only when all of these are true:

- the JSON schema validates
- the user question and clarified objective are non-empty
- output maturity is not `unspecified`
- target audience is not missing or `unspecified`
- no unresolved clarifying questions remain
- no required human gate remains open
- allowed and forbidden source classes do not overlap

Ambiguous research requests should become `status=needs_clarification` briefs
with explicit `unresolved_questions`. The planner must not start broad research
from those prompts.

## Human Gates

The validator fails closed when a brief requires human approval before planning
or synthesis. Required gates include:

- `credentials` for external credentials
- `paid_services` for paid access or paid tools
- `private_data` for private-data use outside a pre-approved workspace policy
- `public_claims` for public-facing claims or publication-oriented claims
- `budget` when paid API spend is both allowed and nonzero

These gates appear in the brief validation payload and block apply. A human may
resolve them by creating a revised brief with narrower permissions, internal-only
claims, approved source classes, or an explicit decision recorded through the
normal decision workflow before task creation.

## Task Integration

`workflow create-task --brief <path>` consumes a validated ready brief when
present. It adds a `research_brief` summary to `status.json`, carries audience
and output maturity into `task.md`, and derives browsing, network, code, and
budget caps from the brief.

`idea promote --brief <path>` also consumes a validated ready brief. The dry-run
proposal includes the brief summary, and the promotion preflight hash includes
the brief contract so write mode fails if the brief changes after dry-run.

If `research_ops/briefs/research_brief.json` exists, task creation and idea
promotion consume it by default. Tiny maintenance tasks can still proceed
without a brief when no brief file is available.

## Non-Goals

- No chat UI is implemented.
- Briefs are not accepted evidence.
- Briefs do not authorize runtime adapters by themselves; task contracts and
  runtime permission checks still govern execution.
- Briefs do not bypass review, result acceptance, deliverable maturity, or human
  gates.

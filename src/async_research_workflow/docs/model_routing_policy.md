# Model Routing Policy

Created: 2026-05-20

The model routing policy keeps prompt posture separate from hard safety rules.
Prompts describe what each role should focus on. Validators, task contracts,
runtime adapter permissions, claim verification, result acceptance, deliverable
maturity checks, and eval comparisons enforce the rules.

## Location

The default policy lives at:

```text
research_ops/prompts/model_routing_policy.json
```

Create it with:

```bash
async-research model-routing init research_ops --write
```

Validate it with:

```bash
async-research model-routing validate research_ops/prompts/model_routing_policy.json
```

The default policy is provider-neutral. It names capability tiers such as
`deterministic`, `cheap`, `standard`, `frontier`, and `human`; it does not name
one proprietary provider or require a live paid model in default tests.

## Required Roles

The policy defines routes for:

- `planner`
- `worker`
- `extractor`
- `methodology_reviewer`
- `skeptic_reviewer`
- `synthesizer`

Each route records the model tier, reasoning effort, budget cap, prompt posture,
escalation triggers, fallback tier, hard-rule owners, and stop conditions.

Use:

```bash
async-research model-routing select \
  research_ops/prompts/model_routing_policy.json \
  --role planner
```

to inspect the configured route without mutating the workspace.

## Adoption Gate

Prompt or routing changes should remain candidates until a candidate eval run
matches or improves the retained baseline on groundedness, unsupported-claim
rate, task success, accepted-output rate, freshness, reproducibility, and cost
per accepted report.

Gate adoption with:

```bash
async-research model-routing eval-check \
  research_ops/prompts/model_routing_policy.json \
  --baseline research_ops/evals/runs/baseline.json \
  --candidate research_ops/evals/runs/candidate.json
```

The candidate run must record the policy's `policy_id` in its
`model_routing_policy` field. If deterministic eval comparison fails, keep the
old prompt or routing baseline and treat the candidate as blocked.

## Boundaries

- Do not move credentials, paid-service approval, public-claim approval, or
  private/public boundary decisions into prompt prose.
- Do not adopt routing changes from anecdotes. Cite eval runs and residual
  risks.
- Do not use this policy to make Deep Research-style superiority claims.
  Head-to-head claims remain out of scope until a Phase 10 benchmark pack exists.

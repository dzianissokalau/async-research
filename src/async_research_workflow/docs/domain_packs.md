# Domain Packs And Benchmarking

Created: 2026-05-20

Domain packs bundle source policy, templates, claim gates, reviewer rubrics,
eval cases, example workspaces, and comparison reports for one bounded research
domain. They are benchmark fixtures, not broad product claims.

## Packaged Domain

The first packaged domain is climate/coffee economics:

```text
async_research_workflow/domain_packs/climate_coffee_economics/
```

It was selected because the roadmap named climate/coffee economics and the repo
already had a coffee deliverable maturity fixture, so the first domain could be
implemented with offline artifacts instead of external credentials or live
network access.

The pack includes:

- `source_policy.md` for source classes, preferred sources, and fail-closed
  rules;
- `brief_templates/` and `task_templates/` for bounded task creation;
- `claim_gates.json` for material-claim, numeric-claim, freshness, and
  private/public gates;
- `reviewer_rubric.md` for paired review;
- `eval_cases.json` plus baseline and candidate eval runs;
- `comparison_report.json` and `comparison_report.md`;
- an `example_workspace/research_ops/` fixture skeleton.

## Reproducible Comparison

The packaged comparison uses existing eval commands:

```bash
async-research eval compare \
  src/async_research_workflow/domain_packs/climate_coffee_economics/eval_runs/generic_baseline.json \
  src/async_research_workflow/domain_packs/climate_coffee_economics/eval_runs/upgraded_runtime.json
```

This command is read-only. The bundled fixture records no live web browsing,
credentials, paid calls, private-public publication permission, or proprietary
Deep Research-style output.

## Honest Claim Boundary

Permitted:

- In the packaged climate/coffee economics fixture, the runtime-backed domain
  pack improves deterministic metrics over the generic baseline.
- The report may cite groundedness, unsupported-claim rate, accepted-output
  rate, freshness failures, cost, latency, and reproducibility when it cites the
  comparison report and run artifacts.

Not permitted:

- Claiming broad superiority over ChatGPT Deep Research or other
  Deep Research-style products from this one domain pack.
- Reporting expert preference win rate before calibrated paired human review
  data is attached.
- Using private/local fixture evidence for public claims without an explicit
  human publication gate.

## Extending A Pack

New domain packs should preserve the same contract:

1. Name the domain and source permission policy.
2. Include brief and task templates for all benchmark cases.
3. Record claim gates and reviewer rubrics before reporting wins.
4. Store baseline and candidate run artifacts that existing eval commands can
   compare.
5. State wins, losses, unproven areas, human intervention points, and forbidden
   claims in the comparison report.

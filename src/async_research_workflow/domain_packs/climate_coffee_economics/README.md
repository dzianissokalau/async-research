# Climate Coffee Economics Domain Pack

Created: 2026-05-20

This pack is the first Phase 10 domain pack for honest head-to-head
benchmarking. It covers climate and coffee economics tasks where the workflow
benefits from explicit source policies, runtime traceability, claim gates,
review rubrics, private/local evidence handling, and deliverable maturity
checks.

The pack does not claim broad superiority over Deep Research-style products.
It records a narrow fixture result: the upgraded runtime-backed workflow beats
the generic async-research baseline on groundedness, unsupported-claim rate,
accepted-output rate, freshness failures, and cost in this packaged domain
benchmark. Proprietary Deep Research-style outputs and expert preference
reviews are placeholders until permissioned, human-calibrated evidence is
attached.

## Contents

- `pack.json`: machine-readable manifest and source policy summary.
- `source_policy.md`: allowed source classes, preferred sources, and fail-closed
  rules.
- `brief_templates/climate_coffee_supply_brief.json`: reusable clarified brief
  template.
- `task_templates/benchmark_tasks.json`: five benchmark task templates.
- `claim_gates.json`: material-claim and citation gates for the domain.
- `reviewer_rubric.md`: paired review rubric for human or LLM reviewers.
- `eval_cases.json`: deterministic benchmark case definitions.
- `eval_runs/generic_baseline.json`: generic async-research baseline run.
- `eval_runs/upgraded_runtime.json`: runtime-backed candidate run.
- `comparison_report.json` and `comparison_report.md`: metric deltas, wins,
  losses, unproven areas, and permitted claims.
- `example_workspace/research_ops/`: minimal fixture workspace skeleton that
  shows where briefs, tasks, sources, and eval runs live.

## Reproduce The Packaged Comparison

From a source checkout, compare the bundled run artifacts:

```bash
async-research eval compare \
  src/async_research_workflow/domain_packs/climate_coffee_economics/eval_runs/generic_baseline.json \
  src/async_research_workflow/domain_packs/climate_coffee_economics/eval_runs/upgraded_runtime.json
```

The comparison is read-only. It uses deterministic JSON artifacts and does not
call live websites, model APIs, paid services, credentials, or private data.

## Benchmark Scope

The fixture includes five task shapes:

- open-web synthesis over public climate and coffee market reports;
- private/local file synthesis over a redacted buyer memo;
- data/API retrieval from mocked official price and weather tables;
- empirical check over a small deterministic yield and price table;
- deliverable maturity review for an internal coffee economics draft.

Only the source and metric classes above are in scope. Broader Deep
Research-style comparisons require permissioned outputs, calibrated reviewers,
and a report that names the product, model, capture date, prompt, source
permissions, and residual risks.

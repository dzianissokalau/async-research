# Deep Review Prompt - Integrated Research Runtime Eval Flywheel

You are reviewing the completed Integrated Research Runtime And Eval Flywheel
delivery.

Repository: `dzianissokalau/async-research`
Final branch: `codex/integrated-research-runtime-eval-flywheel-delivered`
Pre-delivery base branch: `main`

Roadmap:
`roadmaps/delivered_integrated_research_runtime_eval_flywheel_roadmap.md`

Delivery log:
`roadmaps/automation/integrated_research_runtime_eval_flywheel/delivery_log.md`

Delivery state:
`roadmaps/automation/integrated_research_runtime_eval_flywheel/delivery_state.json`

Review files:
`roadmaps/automation/integrated_research_runtime_eval_flywheel/reviews/`

Verification commands that passed after the final phase:

- `git diff --check`
- `.venv/bin/python -m unittest tests.test_doc_references`
- `.venv/bin/python -m unittest tests.test_scaling_state_backend tests.test_cli_architecture tests.test_cli_help`
- `.venv/bin/python -m unittest discover -s tests`
- `.venv/bin/async-research acceptance-suite`
- `.venv/bin/python -m build`
- `.venv/bin/async-research scaling assess src/async_research_workflow/domain_packs/climate_coffee_economics/example_workspace/research_ops --now 2026-05-20T12:00:00Z`

## Review Instructions

Inspect the full diff against the pre-delivery base branch:

```bash
git fetch origin
git switch codex/integrated-research-runtime-eval-flywheel-delivered
git diff --stat main...codex/integrated-research-runtime-eval-flywheel-delivered
git diff main...codex/integrated-research-runtime-eval-flywheel-delivered
```

Then review the roadmap, delivery log, state file, phase review files, code,
schemas, docs, fixtures, CLI behavior, and tests. Treat `research_ops/` files,
public CLI JSON output, dashboard snapshots, evidence objects, trace ledgers,
review artifacts, and eval outputs as higher authority than chat history.

Focus especially on:

- runtime boundary clarity and whether adapters remain bounded by explicit
  contracts
- evidence object and runtime trace contracts, including schema stability and
  source normalization
- path and permission safety, including fail-closed behavior for network,
  credentials, paid calls, unsafe source use, and task-contract permission
- offline test coverage and fixture quality for runtime, evidence, claim,
  eval, routing, parallelism, domain-pack, and scaling behavior
- adapter fail-closed behavior without task-contract permission
- claim/citation verification, including supported, missing, stale,
  contradicted, and numeric claims
- eval reproducibility, deterministic graders, rubric graders, dashboard
  metrics, and release policy
- model-routing honesty, optional provider boundaries, and explicit stop
  conditions
- benchmark claims, including whether the domain pack avoids unsupported broad
  claims over general-purpose Deep Research-style products
- repo-first audit guarantees, including whether any backend, cache, memory,
  or routing feature moves core truth out of `research_ops/` by default
- whether the delivered system avoids unsupported Deep Research comparisons and
  clearly labels unproven areas

## Expected Output

Lead with findings ordered by severity. For every finding, include file and line
references, the behavioral risk, and the concrete fix needed. Then list missing
tests, residual risks, and a final verdict:

- `delivered`
- `needs-fix`
- `blocked`

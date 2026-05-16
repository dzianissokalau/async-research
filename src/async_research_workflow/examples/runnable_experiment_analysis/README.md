# Runnable Experiment And Analysis Example

This fixture is a small, deterministic `research_ops/` workspace that exercises
the public Hypothesis Testing Framework commands without needing external data,
network access, or modeling libraries.

It includes:

- one accepted `experiment_plan` task: `TASK-8001-experiment-plan`
- one completed `run_analysis` task: `TASK-8002-run-analysis`
- source and data-readiness files for `DS-0001`
- accepted-memory linkage for the experiment plan
- completed analysis run artifacts: manifest, metrics, diagnostics,
  robustness checks, claim gates, and result summary

## Run It

From a source checkout:

```bash
EXAMPLE=src/async_research_workflow/examples/runnable_experiment_analysis
WORKDIR=/tmp/async-research-runnable-example-$(date +%s)
mkdir -p "$WORKDIR"
cp -R "$EXAMPLE/research_ops" "$WORKDIR/research_ops"
cd "$WORKDIR"

async-research experiment validate \
  research_ops/tasks/TASK-8001-experiment-plan/worker_output.md \
  --ops-dir research_ops \
  --task-dir research_ops/tasks/TASK-8001-experiment-plan

async-research analysis preflight \
  research_ops/tasks/TASK-8002-run-analysis \
  --ops-dir research_ops \
  --now 2026-05-09T00:00:00Z

async-research analysis validate-run \
  research_ops/tasks/TASK-8002-run-analysis \
  --ops-dir research_ops \
  --now 2026-05-09T00:00:00Z

async-research analysis validate-results \
  research_ops/tasks/TASK-8002-run-analysis \
  --ops-dir research_ops \
  --now 2026-05-09T00:00:00Z
```

Each command should exit `0` and return JSON with `ok: true`.

## Boundaries

This is an operator example, not a benchmark and not an endorsement of the toy
analysis. The values are fixture values chosen to make the validation path easy
to inspect. Use it to see where files live, which public commands gate each
step, and how an accepted plan connects to a completed analysis run.

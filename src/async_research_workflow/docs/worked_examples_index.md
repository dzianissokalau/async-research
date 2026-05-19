# Worked Examples Index

Created: 2026-05-19

This index lists packaged examples and fixtures that can be run locally without
live credentials, external APIs, or private user workspaces. Copy examples to a
temporary directory before experimenting with write-capable commands.

## Generic Starter Template

Path:
`async_research_workflow/templates/generic_research_ops_starter/research_ops/`

What it proves:

- `async-research init research_ops` can create a domain-neutral workspace
- schema, readiness, health, and surface commands have the expected files to
  inspect
- cold-start workspaces avoid project-specific seed tasks

Smoke command:

```bash
.venv/bin/async-research starter-smoke /tmp/async-research-starter-generic --force
```

## Real-Estate Worked Example Template

Path:
`async_research_workflow/templates/research_ops_starter/research_ops/`

What it proves:

- the explicit worked example initializes with data, source, library, and task
  surfaces present
- operators can inspect a populated workspace before adapting the pattern to
  their own domain

Smoke command:

```bash
.venv/bin/async-research starter-smoke /tmp/async-research-starter-real-estate --template real-estate --force
```

## Runnable Experiment And Analysis Example

Path:
`async_research_workflow/examples/runnable_experiment_analysis/`

What it proves:

- experiment-plan validation, analysis preflight, adapter planning, completed
  run validation, result validation, result acceptance, accepted-memory linkage,
  and analysis dashboard output can run from packaged resources
- no network access, modeling library, warehouse, notebook, SQL, or dbt adapter
  is required

Start from source:

```bash
EXAMPLE=src/async_research_workflow/examples/runnable_experiment_analysis
WORKDIR=/tmp/async-research-runnable-example
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"
cp -R "$EXAMPLE/." "$WORKDIR/runnable_experiment_analysis"
cd "$WORKDIR/runnable_experiment_analysis"
```

Start from an installed package:

```bash
WORKDIR=/tmp/async-research-runnable-example
export WORKDIR
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"
python - <<'PY'
import os
import shutil
from pathlib import Path
from async_research_workflow.resources import examples_path

target = Path(os.environ["WORKDIR"]) / "runnable_experiment_analysis"
shutil.copytree(examples_path("runnable_experiment_analysis"), target)
PY
cd "$WORKDIR/runnable_experiment_analysis"
```

Then run the command sequence in
[Runnable Experiment And Analysis Example](../examples/runnable_experiment_analysis/README.md).

## Coffee Pilot Deliverable Maturity Fixture

Path:
`async_research_workflow/examples/coffee_pilot_deliverable_maturity/`

What it proves:

- accepted task evidence is not automatically shareable or working-paper-ready
- deliverable maturity checks can explain missing manuscript gates, critic
  review, response matrix closure, and review independence

Smoke command after copying the fixture:

```bash
async-research deliverable check research_ops DELIV-0015
```

The expected first check exits nonzero because the fixture is deliberately below
working-paper readiness.

## GitHub Worker Example

Path:
`async_research_workflow/examples/github_actions_codex_worker.yml`

What it proves:

- a repository can store an example scheduled-worker shape without installing
  an active workflow
- the file remains packaged as an example only and does not run unless a human
  copies it into `.github/workflows/`

Review it as reference material, not as an enabled automation.

## Benchmark Cases

Path:
`async_research_workflow/benchmarks/autonomy_benchmark_cases.json`

What it proves:

- known-good and known-bad autonomy cases stay available from installed package
  resources
- the benchmark command can exercise deterministic safety cases locally

Smoke command:

```bash
.venv/bin/async-research benchmark
```

## What These Examples Do Not Prove

The packaged examples do not prove real-world research validity, publication
readiness, external data access, statistical generality, or production scale.
They prove that the local contracts are runnable and inspectable from source and
installed package resources.

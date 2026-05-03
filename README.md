# Async Research Workflow

Alpha Python CLI and starter template for low-cost asynchronous research workflows.

This package provides an installable CLI, reusable `research_ops` starter workspace,
schemas, benchmark fixtures, and operational docs for running slow, low-cost,
human-supervised research loops in any repo.

It is intended for GitHub install and real-project dogfooding before PyPI.

## Install For Development

```bash
git clone https://github.com/dzianissokalau/async-research
cd async-research
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
async-research version
```

## Start A Research Workspace

```bash
async-research init ../my-research-repo/research_ops
async-research readiness ../my-research-repo/research_ops --dry-run
async-research health ../my-research-repo/research_ops --dry-run
async-research surface update ../my-research-repo/research_ops
async-research surface validate ../my-research-repo/research_ops
```

## Core Checks

```bash
async-research acceptance-suite
async-research starter-smoke /tmp/async-research-starter
async-research benchmark
async-research simulate-week research_ops
```

## Validate An Existing Workspace

After installing the package, run these commands from any research repo that has
or will have a `research_ops/` folder:

```bash
async-research schema-check research_ops
async-research readiness research_ops --dry-run
async-research health research_ops --dry-run
async-research surface validate research_ops
```

For a reviewed task, validate result acceptance with:

```bash
async-research result-acceptance research_ops/tasks/TASK-0001-example --ops-dir research_ops
```

Keep any older local workflow scripts until these commands pass against your real
workspace and scheduled jobs have been updated to call `async-research`.

## Status

Version `0.1.0a1` is an alpha. The CLI is intentionally standard-library-only.

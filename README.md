# Async Research Workflow

Alpha Python CLI and starter template for low-cost asynchronous research workflows.

This package turns the workflow engine from `ideas_ai` into an installable tool:
scripts, schemas, benchmark fixtures, docs, and a clean `research_ops` starter
workspace. It is intended for GitHub install and dogfooding before PyPI.

## Install For Development

```bash
git clone https://github.com/dzianissokalau/async-research-workflow
cd async-research-workflow
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

## Dogfood With `ideas_ai`

From the `ideas_ai` repo after installing this package:

```bash
async-research schema-check research_ops
async-research readiness research_ops --dry-run
async-research health research_ops --dry-run
async-research surface validate research_ops
async-research result-acceptance research_ops/tasks/TASK-0002-idea-discovery --ops-dir research_ops
```

Keep the old `ideas_ai/async_research_workflow` folder until these commands pass
against the live `ideas_ai/research_ops` workspace.

## Status

Version `0.1.0a1` is an alpha. The CLI is intentionally standard-library-only.

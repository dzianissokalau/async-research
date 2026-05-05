# Contributing

Thanks for helping harden `async-research-workflow`.

This project is still a public alpha. Prefer small, reviewable changes that
preserve the existing CLI contracts and improve safety, docs, or test coverage.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
async-research version
```

Runtime dependencies must remain standard-library-only unless a maintainer
explicitly changes that policy.

## Before Opening A PR

Run the checks that match your change. For broad changes, run the full local
suite:

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/async-research acceptance-suite
.venv/bin/async-research benchmark
.venv/bin/async-research starter-smoke /tmp/async-research-starter --force
.venv/bin/python -m compileall src tests
git diff --check
```

For package-resource or installation changes, also build and smoke the wheel:

```bash
.venv/bin/python -m build --sdist --wheel
python -m venv /tmp/async-research-wheel-venv
/tmp/async-research-wheel-venv/bin/python -m pip install dist/*.whl
/tmp/async-research-wheel-venv/bin/async-research version
/tmp/async-research-wheel-venv/bin/async-research acceptance-suite
```

## Change Guidelines

- Keep changes scoped to the roadmap item or bug being addressed.
- Preserve command names, JSON output contracts, and exit-code behavior unless
  the change explicitly targets those contracts.
- Keep fail-closed behavior for malformed state, invalid transitions, stale
  sources, stale accepted memory, missing reviewer metadata, budget pressure,
  and human escalation.
- Prefer package resources and `async_research_workflow.resources` helpers over
  source-tree path assumptions.
- Do not commit generated local workspaces, build artifacts, virtualenvs, or
  temporary benchmark output.
- Do not rewrite unrelated docs or templates while fixing code.

## Working With LLM Implementers

When handing a task to an LLM agent, include:

- the roadmap item or issue being implemented
- exact files or modules in scope
- commands to run before and after the change
- behavior that must not change
- acceptance criteria and a review prompt

Ask agents to make narrow commits and to report any unrelated dirty worktree
files rather than reverting them.

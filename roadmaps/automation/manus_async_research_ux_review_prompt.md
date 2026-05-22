# Manus UX Review Prompt

Use this prompt to ask Manus to conduct a UX review of the async-research
framework.

````markdown
You are reviewing the UX of the async-research framework.

Repo: https://github.com/dzianissokalau/async-research

## Context

async-research is a Python CLI and file-backed research-ops framework for slow,
reviewable, human-governed research workflows. It uses a `research_ops/`
workspace with queues, tasks, source/data governance, review gates,
accepted-evidence memory, deliverable maturity checks, cost logs, and a local
console/dashboard.

It is not meant to be a polished consumer app. The intended users are technical
researchers, AI operators, and LLM agents such as Codex/Claude/Manus helping
operate a research workflow.

The key UX question is:

> Can a new technical user or AI operator understand what the framework is,
> install it, initialize or inspect a workspace, know what to do next, and avoid
> unsafe mistakes?

## Setup Instructions

Please clone and inspect the repo:

```bash
git clone https://github.com/dzianissokalau/async-research
cd async-research
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/async-research version
.venv/bin/async-research --help
```

If setup fails, document exactly where and why. If you cannot run commands,
perform a static UX review and clearly label it as static-only.

## Review Scope

Focus on UX, not code architecture.

Review these surfaces:

1. README and first-time onboarding
2. Installation and setup flow
3. CLI discoverability and help text
4. `research_ops/` workspace mental model
5. "What should I do next?" workflow clarity
6. Error messages, blockers, and recovery guidance
7. Dashboard / console usefulness
8. Operator experience for LLMs using the framework
9. Difference between accepted task evidence and publication-ready deliverables
10. Friction points for real research dogfooding

Please try to simulate a first-time user journey:

1. Understand what the framework does.
2. Install it.
3. Create or inspect a workspace.
4. Find the next safe action.
5. Understand a task/review/acceptance loop.
6. Understand where dashboard/console fits.
7. Identify where a user or LLM operator would get confused.

## Output Format

Please produce a UX review with:

1. Executive summary
2. What works well
3. Main UX weaknesses
4. First-time user journey assessment
5. AI/operator journey assessment
6. Prioritized recommendations table

Use this table format:

| Priority | Area | Issue | Why It Matters | Recommendation | Expected Impact |
| --- | --- | --- | --- | --- | --- |

Also include:

- top 5 quick wins
- top 5 deeper product improvements
- confusing terminology or mental-model gaps
- missing docs or missing examples
- commands/screens you tested
- screenshots or logs if useful
- any assumptions or limitations of your review

Be blunt and practical. The goal is to make async-research easier to understand,
adopt, and operate without weakening its governance and safety model.
````

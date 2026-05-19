# Trigger Evals

Phase 1 selected the `SKILL.md` description by comparing three candidates
against held-out trigger prompts. The selected description is Candidate C because
it covers setup, inspection, continuation, review, reporting, dashboard/console,
`research_ops/`, and near-miss exclusions.

## Candidate Descriptions

### Candidate A

Operate async-research workspaces through public CLI commands and file-backed
state. Use for setup, status checks, workflow continuation, task operation,
review, reporting, and dashboard-aligned updates for repositories that contain
or need `research_ops/`.

### Candidate B

Help Codex safely run async-research workflows. Use when a user asks to inspect
`research_ops/`, run `async-research workflow next/status`, continue an
operator loop, review acceptance/readiness, or summarize dashboard state.

### Candidate C - Selected

Operate async-research workspaces through public CLI commands, dashboard
snapshots, and file-backed research_ops state. Use when Codex is asked to
inspect, set up, continue, run, review, report on, or find the next safe action
for an async-research workflow, including research_ops, async-research
dashboard/console, workflow next/status, acceptance, readiness, gates, or
operator automation requests. Use for guided setup and bounded operation; do not
use for generic research advice, unrelated coding tasks, or non-async-research
project status.

## Score Summary

| Candidate | Should Trigger Recall | Should Not Trigger Precision | Notes |
| --- | ---: | ---: | --- |
| A | 16/18 | 8/10 | Missed abbreviated dashboard and "what next" phrasings. |
| B | 15/18 | 9/10 | Good precision; weaker setup and reporting coverage. |
| C | 18/18 | 10/10 | Best coverage and clearest near-miss exclusions. |

## Should Trigger

1. "Use Codex to continue my async-research worker loop."
2. "What is the next safe action in this `research_ops` workspace?"
3. "Inspect the async-research dashboard snapshot and summarize blockers."
4. "Run the framework status checks and tell me whether acceptance is blocked."
5. "Set up this repo for async-research, but ask before installing anything."
6. "The task is awaiting review; use async-research to decide what comes next."
7. "Check `async-research workflow next research_ops` and report the result."
8. "I need an operator pass on the research_ops gates."
9. "Resume the async research automation from the file-backed state."
10. "Can you guide initialization of `research_ops/` in this private repo?"
11. "Look at readiness and health before continuing this async-research task."
12. "Review whether accepted memory and deliverable readiness disagree."
13. "Run a bounded autonomous loop for one safe async-research task."
14. "Use the console snapshot JSON to produce a status report."
15. "The dashboard says blocked; inspect the source files and CLI state."
16. "Continue from workflow status, but stop at human gates."
17. "Check whether the async-research CLI version has drifted."
18. "Prepare a human decision request for this async-research gate."

## Should Not Trigger

1. "Give me general research advice about survey design."
2. "Refactor this unrelated React component."
3. "Summarize the status of my generic software project."
4. "Build a new standalone dashboard UI."
5. "Run a non-async-research workflow for a marketing campaign."
6. "Explain how LLM agents work at a high level."
7. "Install a global Python package without asking."
8. "Write a paper submission readiness claim from memory."
9. "Review this CSV without any async-research workspace."
10. "Create a GitHub Actions workflow unrelated to async-research."

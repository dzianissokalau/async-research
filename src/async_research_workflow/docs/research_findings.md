# Research Findings

## Question

Can a simplified scheduled workflow reduce autonomous research costs by multiple times while keeping light human presence?

## Short Answer

Yes. The best design is not a multi-agent swarm. It is a small async operations loop with durable state in repository files:

```text
discovery -> planner -> worker -> reviewer -> synthesizer
```

Each job is short, scoped, and writes to a specific file or folder. Human review is reserved for priority, budget, public claims, legally sensitive data, and ambiguous failures.

For the user's stated priorities, the operating order should be:

```text
quality > independence > low cost > speed
```

That changes the cadence. The system should prefer slow, evidence-backed loops over frequent shallow runs.

## What Current Tooling Supports

### ChatGPT And Codex Plans

OpenAI states that Codex is included with ChatGPT Plus, Pro, Business, and Enterprise/Edu plans. ChatGPT Pro tiers are positioned for heavier Codex and Deep Research usage, with Plus at $20, Pro $100 for "real projects", and Pro $200 for heavier continuous workflows. Scheduled agent invocations count against agent usage limits.

Implication:

- ChatGPT Pro can be a fixed-cost control plane for a solo workflow.
- It should not be used as an unlimited background crawler or scraper.
- Scheduled tasks are useful, but they should be few and high-leverage.

### ChatGPT Scheduled Tasks And Agent Scheduling

OpenAI Help describes ChatGPT tasks as prompts that can run later or recur. ChatGPT agent can also be scheduled daily, weekly, or monthly after a task completes, and scheduled agent requests count as agent invocations.

Implication:

- Use ChatGPT tasks for status reminders, daily summaries, and prompts that do not need repo write access.
- Use Codex or GitHub Actions for work that modifies repository files.
- Keep under the active task limit and avoid one scheduled task per research idea.

### Codex CLI Non-Interactive Mode

Local inspection showed that this machine has Codex CLI available at:

```text
/Applications/Codex.app/Contents/Resources/codex
```

`codex exec --help` confirms non-interactive execution supports:

- `--cd` to choose a working directory
- `--sandbox` with `read-only`, `workspace-write`, or `danger-full-access`
- `--ask-for-approval` policies
- `--json` event output
- `--output-last-message <FILE>`
- `--output-schema <FILE>`
- `--oss` and `--local-provider` for local providers

Implication:

- Codex CLI is a good automation worker if run in short bounded jobs.
- Use `workspace-write`, a constrained prompt, and per-task folders.
- Use output files and schemas so the scheduler can inspect results cheaply.

### GitHub Actions Scheduling

GitHub Actions supports scheduled workflows using POSIX cron. Scheduled workflows run on the latest commit on the default branch and, according to GitHub Docs, can run as frequently as every 5 minutes. GitHub also supports concurrency controls so only one worker for a group is active at once.

Implication:

- GitHub Actions is a clean scheduler if cloud execution is acceptable.
- Use concurrency groups to prevent overlapping workers.
- Use minimal `GITHUB_TOKEN` permissions.
- Keep workflow files explicit and reviewable.

### OpenAI API Cost Optimizers

OpenAI Batch API provides asynchronous processing with 50 percent lower costs and a 24-hour turnaround, useful for classification, evaluation, and repository embedding jobs.

OpenAI prompt caching can reduce latency and input cost for repeated prompts when static prefixes match. OpenAI docs say caching starts at prompts of at least 1024 tokens and can reduce input token costs substantially for repeated prompt prefixes.

Implication:

- Use Batch API for bulk literature extraction and idea scoring.
- Use stable prompt prefixes and append variable task content at the end.
- Do not use expensive interactive agents for bulk chunk processing.

### Claude As A Comparison

Anthropic provides Claude Code GitHub Actions for issue/PR-triggered work and Claude Code routines for scheduled/API/GitHub-triggered automation. Routines are in research preview. Claude Code GitHub Actions can be configured with `claude_args`, including max turns.

Implication:

- Claude Code is a viable alternative for GitHub-native automation.
- The same architecture applies: short tasks, max turns, restricted write paths, review gates.
- Do not let "automatic PR creation" become automatic truth acceptance.

## What Research Suggests About Idea Discovery

Recent scientific-discovery systems converge on a similar pattern:

- generate many candidate hypotheses
- debate or rank them with structured criteria
- evolve or refine the best candidates
- test only a small subset
- keep human or external validation in the loop

The AI Co-Scientist paper explicitly uses a generate, debate, and evolve process, with asynchronous task execution and tournament-style evolution. The AI Scientist includes idea generation, code, experiments, paper writing, and automated review. Robin integrates literature search, hypothesis generation, experiment proposal, data analysis, interpretation, and updated hypotheses.

Implication:

- Add idea discovery, but make it upstream of the execution queue.
- The discovery job should write to `discovery_inbox.md`, not directly to `queue.md`.
- The planner or human should promote only the best candidates.
- The system should generate many cheap ideas, then discard most of them early.

## What Research Suggests About Reviewers

The evidence is mixed but useful:

- self-consistency improves reasoning by sampling multiple paths and selecting the most consistent answer
- multi-agent debate can improve reasoning and factuality in some settings
- LLM-as-judge can approximate human preferences, but has position, verbosity, self-enhancement, and limited-reasoning biases
- G-Eval-style form filling improves structured evaluation but can still bias toward LLM-generated text
- multi-agent evaluator systems such as ChatEval are motivated by the fact that human evaluation often uses multiple annotators

Implication:

- one reviewer is enough for low-risk task hygiene
- multiple reviewers are worth it at gates, especially experiment plans, result summaries, and final memos
- reviewers should first work independently, then an aggregator compares decisions
- cross-model reviews help, but vendor diversity does not magically guarantee truth
- disagreement should trigger a bounded adjudication or human gate, not endless debate

## Architecture Finding

The best cost-control architecture is not:

```text
many agents talk until they converge
```

It is:

```text
one discovery job writes candidates -> one planner promotes a few
-> one worker writes one output -> reviewers independently score gates
-> aggregator routes the task -> human gates risky transitions
```

Agents should communicate through small typed artifacts:

- `task.md`
- `status.json`
- `worker_output.md`
- `reviews/<reviewer>.md`
- `review_panel/aggregate.md`
- `artifacts/`

## Why This Drops Cost

| Expensive behavior | Low-cost replacement |
| --- | --- |
| rereading the full repo every run | per-task context bundle |
| long agent debates | planner/reviewer state transitions |
| frontier model for extraction | local model, mini model, or Batch API |
| continuous multi-agent loop | scheduled small jobs |
| unbounded coding retries | max turns and time budget |
| every hypothesis becomes an experiment | data-readiness gate first |
| repeated free-form prompts | stable prompts and schemas |
| manual status discovery | `daily_status.md` and `status.json` |
| every output reviewed by expensive panels | tiered review escalation |
| model reviewers influencing each other too early | independent blind first-pass reviews |

## Recommended Operating Model

Use five roles:

1. Human owner
2. Discovery job
3. Planner job
4. Worker job
5. Reviewer or review panel
6. Synthesizer job

The human owner should not babysit each job. They should set priorities, approve risky actions, and check accepted results weekly or on exception.

## What To Avoid

- One scheduled job per hypothesis.
- Discovery jobs writing directly to the execution queue.
- Long-running open-ended "keep researching" prompts.
- Agents editing shared queue files without a lock/claim protocol.
- Multiple jobs pushing directly to `main`.
- Automated public release.
- Automated use of private, scraped, or legally sensitive data.
- Treating reviewer-agent approval as scientific truth.
- Sending every small task to Claude, Gemini, and OpenAI reviewers.

## Best First Implementation

Start file-based:

```text
research_ops/
  discovery_inbox.md
  inbox.md
  queue.md
  daily_status.md
  weekly_digest.md
  review_panel/
  tasks/
    TASK-0001/
      task.md
      status.json
      worker_output.md
      reviews/
        primary.md
        methodology.md
        skeptic.md
      review_panel/
        aggregate.md
      artifacts/
```

Use the scheduler only after the manual version works for a week.

## Decision

Build the expanded async workflow before building a full autonomous research OS. Add autonomy through queues, schemas, discovery inboxes, and review gates, not through always-on multi-agent activity.

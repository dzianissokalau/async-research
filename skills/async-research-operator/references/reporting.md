# Reporting

Reports should be concise, evidence-backed, and tied to framework state.
Use this reference when answering the human after startup, task work, decision
gates, deliverable checks, or maintenance.

## Report Rules

- Keep reports short enough for conversation. Prefer five to eight bullets plus
  a short next action.
- Include the commands used and important file paths. If a command was skipped,
  say why.
- Use `async-research console snapshot research_ops --json` before broad
  workspace reports when the CLI and workspace are available.
- Treat dashboard or console snapshot data as a consistency check, not as the
  only authority.
- If a dashboard snapshot and raw public CLI output disagree, trust the raw CLI
  for that specific object and mention the discrepancy.
- Distinguish task acceptance from deliverable readiness. Accepted task
  evidence does not make a memo, draft, report, or paper ready.
- Do not claim a task is accepted when `status.json`, aggregate or result
  acceptance, and accepted memory disagree. Stop and request a human decision.
- Do not claim a deliverable is ready when `deliverable check` fails, has not
  run, or contradicts the requested maturity.

## Startup Report

Use after the startup protocol or a read-only status request.
Required fields: framework version, workspace path, privacy status,
health/readiness/workflow summary, next safe action, commands used, and approvals
needed.

```text
Mode: <role> / <autonomy_level>
Framework: <cli path or missing> / <version or unknown> / <version drift if any>
Workspace: <workspace path> / <privacy status>
Commands used: <command list, or skipped commands with reason>
State: <health, readiness, workflow next, dashboard snapshot status>
Next safe action: <one bounded action, or stop reason>
Needs approval: <writes, setup, network, credentials, gate, or none>
Caveats: <capability gaps, dashboard mismatch, unsupported environment, or none>
```

If broad state is reported without a console snapshot, include the reason, such
as missing CLI, missing `research_ops/`, or a failed read-only command.

## Task Completion Report

Use after a bounded worker, review, gate, or acceptance action.
Required fields: task ID, files changed, worker output, review status,
acceptance route, validation commands, caveats, and next safe action.

```text
Task: <task ID and status>
Files changed: <paths, or "none">
Worker output: <worker_output.md path, or not applicable>
Review status: <drafted, submitted, needs-fix, accepted, blocked, or not run>
Acceptance route: <command/file proving acceptance, or stop reason>
Validation: <commands run and result>
Caveats: <same-agent review, missing independence, unresolved evidence, or none>
Next safe action: <one command/action, human decision, or stop>
```

Do not merge "review passed", "task accepted", and "deliverable ready" into one
status. Report each separately when relevant.

## Human Decision Request

Use when a human gate, approval boundary, product decision, privacy boundary,
source governance question, credentials, paid service, target venue, or maturity
choice blocks progress.
Required fields: decision needed, evidence links, options, consequences,
recommended default if safe, post-approval write command, and stop condition.

```text
Decision needed: <specific decision>
Evidence: <file paths and command outputs to inspect>
Options: <safe options, including "do nothing" when valid>
Consequences: <what each option changes or blocks>
Recommended default: <only if framework state supports a low-risk default>
Write command after approval: <exact command, or "none">
Stop condition: <why automation is paused>
```

The evidence section comes before recommendations. If no safe default exists,
say so directly.

## Deliverable Maturity Report

Use before claiming a memo, draft, working paper, public artifact, or other
deliverable is usable at a requested maturity.
Required fields: target maturity, current maturity, failed gates, critic status,
open response rows, task acceptance, and readiness claim.

```text
Target maturity: <requested target or missing decision>
Current maturity: <framework-reported maturity>
Deliverable check: <command run and pass/fail/not run>
Failed gates: <citations, figures, audience, response rows, or none>
Critic status: <separate_agent, same_agent_visible, missing, or not required>
Open response rows: <count and path, or none>
Task acceptance: <accepted evidence state, or mismatch stop>
Readiness claim: <allowed claim, or explicit stop reason>
```

Stop if the target maturity is missing, `deliverable check` is failing or
stale, critic independence is too weak for the claim, or task acceptance and
deliverable readiness are being conflated.

## Maintenance Report

Use after validation, dashboard refresh, accepted-memory updates, surface
updates, or other upkeep that does not decide research direction.
Required fields: checks run, warnings, stale evidence, dashboard URL or snapshot
summary, files changed, and next safe action.

```text
Checks run: <schema/readiness/health/surface/validator commands>
Warnings: <version drift, capability gaps, privacy risk, stale lock, or none>
Stale evidence: <paths or task IDs needing refresh, or none>
Dashboard: <URL if served, or console snapshot summary>
Files changed: <derived state paths, or none>
Next safe action: <maintenance follow-up, human gate, or none>
```

Maintenance reports must not hide failed checks behind an overall "healthy"
summary. If any required check failed or could not run, report the blocker and
avoid write actions until it is resolved.

## Dashboard Alignment Rules

- Prefer `async-research console snapshot research_ops --json` before broad
  workspace status reports.
- Use `workflow status`, `workflow next`, `review`, `decision`, or
  `deliverable` CLI output for object-specific truth.
- Mention dashboard or console snapshot disagreement, but do not let it override
  higher-priority file-backed state or raw public CLI output.
- Stop before summarizing a task as accepted if `status.json`, aggregate/result
  acceptance, and accepted memory disagree.
- Stop before summarizing a deliverable as ready if `deliverable check` fails,
  has not run, or conflicts with the reported maturity.

# Safety And Stop Conditions

Use this reference whenever deciding whether to continue autonomously.

## Source-Of-Truth Hierarchy

1. `research_ops/` files.
2. Public `async-research` CLI JSON output.
3. Dashboard or console snapshot.
4. User messages.
5. Model memory.

When sources disagree, prefer the higher source and report the discrepancy. Do
not silently choose between conflicting acceptance, readiness, or dashboard
states.

## Mandatory Stops

- Destructive file or git operations.
- Public/private boundary ambiguity.
- Publishing, submission, release, or publication-readiness claims.
- Credentials, external accounts, paid API/cloud/data use, network installs,
  cloning, or fetching without approval.
- Human decision gates, source governance approval, missing target audience,
  deliverable maturity choice, target venue choice, or product direction.
- Required tests or validators cannot run.
- Required public CLI commands are missing.
- Task acceptance sources disagree.
- Dashboard state conflicts with file-backed state.
- Deliverable readiness checks fail, have not run, or disagree with reported
  maturity.
- Same-agent review or critic independence is weaker than the requested task,
  deliverable maturity, or public claim requires.
- The requested role or autonomy level would require files, commands, or
  decisions outside the current bounded task.

## Default Behavior

In `guided` mode, stop before writes and present the exact command that would be
run. In `bounded_autonomous` mode, still stop at every mandatory stop condition.

## Role And Autonomy Gates

- The first status report must name the current role and `autonomy_level`.
- `read_only` means no writes, no setup, no task creation, and no gate
  resolution.
- `guided` is the default for ambiguous "continue" requests and requires user
  approval before writes.
- `bounded_autonomous` is available only after an explicit request and covers
  one bounded task loop or one bounded recipe. It never includes self-acceptance
  or publication/readiness claims.
- `maintenance` may run validation and derived-state upkeep, but must not change
  research content or decide direction.
- If the role changes from worker to reviewer or critic in the same
  conversation, disclose `same_agent_visible` review independence and stop when
  stronger independence is required.

## Reporting And Dashboard Alignment Stops

- Before broad workspace reports, use
  `async-research console snapshot research_ops --json` when the CLI and
  workspace are available.
- Use dashboard or console snapshots as consistency checks, not as the sole
  source of truth.
- If dashboard state conflicts with raw public CLI output, trust the raw CLI for
  the specific object and report the dashboard discrepancy.
- Stop instead of saying a task is accepted when `status.json`,
  aggregate/result acceptance, and accepted memory disagree.
- Stop instead of saying a deliverable is ready when `deliverable check` fails,
  has not run, or contradicts the requested maturity.
- Stop when a report would blur task acceptance, review status, accepted memory,
  and deliverable readiness into one unsupported success claim.

## High-Impact Claims

Do not claim a deliverable is working-paper-ready, submission-ready, published,
externally validated, or ready for a target venue unless the relevant public
checks have passed and the needed human approvals and review independence are
present. If the user asks for such a claim and evidence is incomplete, report
the missing check or approval instead of approximating.

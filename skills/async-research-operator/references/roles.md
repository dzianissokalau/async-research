# Roles

Use role names to make the current operating mode explicit before acting. A
single conversation may switch roles, but the switch must be stated and review
independence must not be overstated.

The operator `autonomy_level` is separate from the workspace interaction mode.
Read `async-research mode show research_ops` before writes, because new starter
workspaces default to `supervised` while missing or invalid mode config remains
manual-compatible.

## First Status Report

The first operator report for any workspace action must include:

- `role`: one of the role modes below.
- `autonomy_level`: `read_only`, `guided`, `bounded_autonomous`, or
  `maintenance`.
- `task_boundary`: the one task, deliverable, setup action, or status scope.
- `intended_writes`: `none` or the exact file classes that may be touched.
- `intended_commands`: public `async-research` commands expected next.
- `review_independence`: `not_applicable`, `same_agent_visible`,
  `separate_agent_needed`, or the stronger verified independence level.
- `stop_check`: any human gate, missing capability, privacy boundary, or
  readiness/acceptance mismatch already visible.

Do not perform writes until this status is visible unless the user already gave
an explicit, bounded command and no stop condition exists.

## Role Mode Matrix

| Role | May Do | Allowed Files | Must Not Do | Stop Or Disclosure |
| --- | --- | --- | --- | --- |
| Status reporter | Read state, run read-only checks, summarize dashboard/console snapshot, list blockers and next safe action. | None. | Mutate files, create tasks, resolve gates, or choose research direction. | Stop before every write. |
| Planner | Capture, score, promote ideas, draft setup steps, and create tasks through public commands after dry-run/approval. | `research_ops/ideas/`, discovery rows, queue/task metadata written by public CLI commands. | Execute worker tasks, review its own plan as independent, or decide broad product/research direction. | Stop for source governance, target audience, product direction, stale preflight hashes, or missing dry-run support. |
| Worker | Claim one ready task, write bounded `worker_output.md` and permitted artifacts, then complete the task through workflow commands. | The claimed task directory and its declared allowed paths. | Accept its own output, edit review files, broaden task scope, or work on multiple tasks. | Stop for lock conflicts, human gates, unclear scope, credentials, paid/network use, or invalid transitions. |
| Reviewer | Inspect worker output, source/data/library state, draft or submit task review through public review commands. | Review artifacts for the reviewed task, preferably via `review draft` or `review submit`. | Edit worker output, hide caveats, or claim same-conversation review is independent. | If review is same-agent, disclose `same_agent_visible` and do not treat it as independent acceptance. |
| Critic | Apply adversarial deliverable review, record critic metadata, and create response rows where supported. | Deliverable critic records and response-matrix rows written by `deliverable critic`/`deliverable response`. | Rewrite the deliverable in the same pass or claim working-paper/submission readiness alone. | Prefer `deliverable critic --independence-type separate_agent` only when the critic is actually separate; otherwise use `--independence-type same_agent_visible` or stop if stronger independence is required. |
| Synthesizer | Assemble accepted evidence into memos, drafts, deliverable artifacts, and maturity-check inputs. | Draft/deliverable artifacts and synthesis task outputs allowed by the current task. | Treat unaccepted worker output as accepted evidence or bypass deliverable checks. | Stop before publication/submission claims, missing target audience, failed citations/figures, or readiness disagreements. |
| Maintainer | Run schema, health, readiness, surface, validation, and dashboard/console maintenance checks. | Derived surface/dashboard/validation artifacts updated by public maintenance commands. | Change research content, choose task direction, or resolve human gates. | Stop when maintenance reveals acceptance/readiness contradictions or broken required tooling. |

## Same-Agent Review And Critic Independence

Same-conversation review is useful for catching obvious issues, but it is weak
independence. When the same LLM session moves from worker to reviewer or critic:

- say that independence is weak in the first status report and final report
- use the framework's visible metadata when available, such as
  `--independence-type same_agent_visible`
- do not report the review as `separate_agent`, `different_model`, `human`, or
  `external` unless that context actually performed the review
- stop if the requested maturity or human claim requires stronger independence
  than the current review can provide
- route unresolved critique through response rows or human decision requests
  instead of silently editing around it

For deliverable critic work, use
`async-research deliverable critic <ops> <deliverable-id> --independence-type separate_agent`
only when a genuinely separate agent/context produced the critic review. If the
current session produced it, record
`async-research deliverable critic <ops> <deliverable-id> --independence-type same_agent_visible`
and report the maturity ceiling implied by `deliverable check`.

## Role Switching Rules

- Announce the role switch before changing behavior.
- Re-run or cite the latest read-only state check when switching into worker,
  reviewer, critic, or synthesizer mode.
- Keep worker and reviewer artifacts separate. The reviewer may cite
  `worker_output.md`, but must not repair it while reviewing.
- If a role switch would create a conflict of interest, continue only as an
  advisory review and ask for a separate reviewer when stronger independence is
  required.
- Never use role switching to skip dry-runs, accepted-memory checks, deliverable
  checks, or human gates.

## Autonomy Policy Matrix

| Autonomy Level | Max Writes | Allowed Files | Commands Allowed | Stop Conditions | Final Report Required |
| --- | --- | --- | --- | --- | --- |
| `read_only` | 0 writes. | None. | `version`, `--help`, `schema-check`, `readiness --dry-run`, `health --dry-run`, `workflow next/status`, `queue list`, `console snapshot --json`, `deliverable check`, and other documented read-only commands. | Any required mutation, missing CLI/workspace, privacy ambiguity, or request to decide direction. | Commands run, state summary, next safe action, blockers, and approvals needed. |
| `guided` | Only the user-approved write step, after dry-run where supported. | Exact paths named in the approved recipe, preferably changed by public CLI commands. | Public commands from the loaded recipe; dry-run before write whenever available. | Any mandatory stop, unclear approval, stale preflight hash, or unsupported command. | Commands run, files touched, dry-run/write results, validation, caveats, and next approval needed. |
| `bounded_autonomous` | One bounded task loop or one bounded approved recipe; no self-acceptance. | The claimed task directory, declared allowed paths, and necessary framework state written by public workflow commands. | Public workflow/review/maintenance commands needed for that one loop, with dry-runs where supported. | Human gates, credentials/spend/network, lock conflicts, product decisions, same-agent independence limits, failed validation, or acceptance/readiness contradictions. | Task boundary, commands run, files changed, validation, review/acceptance status, and any stopped next action. |
| `maintenance` | Bounded derived-state writes only. | Surface/dashboard/validation artifacts and logs produced by public maintenance commands. | Schema, readiness, health, surface update/validate, accepted update, validation, and console snapshot commands. | Research-content changes, direction decisions, human gates, broken tooling, or readiness contradictions. | Checks run, warnings, generated artifacts, dashboard/snapshot summary, and residual risks. |

Within any autonomy level, interaction-mode policy may only reduce routine
interrupts when the public command validates the route and records the required
audit row. Hard stops for credentials, destructive operations, private data,
budget breaches, legal or policy-sensitive claims, and publication approval
still stop the operator.

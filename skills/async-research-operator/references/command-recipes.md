# Command Recipes

Use this reference when operating a workspace through the public
`async-research` CLI. Replace `<ops>` with the detected workspace path, usually
`research_ops`; replace `<task>` with a task directory; replace
`<proposal-source>` with a task directory, `worker_output.md`, proposal JSON, or
proposal directory accepted by the CLI.

## Global Command Rules

- Prefer public `async-research` commands. Do not call internal Python helper
  modules to bypass missing CLI capability.
- Treat `research_ops/` files and public CLI JSON output as higher authority
  than chat history or model memory.
- Run read-only checks before write-capable commands.
- Run dry-run before writes whenever the command supports it.
- Stop rather than inventing a fallback when a required public command is
  missing from the capability probe.
- Operate one bounded task at a time unless the user explicitly changes scope.
- Ask before environment creation, package installs, network use, cloning or
  fetching, shell configuration changes, `research_ops/` initialization, or
  writes outside the workspace.
- The only direct file write in these recipes is task-local worker output,
  usually `<task>/worker_output.md`. Do not hand-edit `status.json`, queue,
  review, accepted-memory, catalog, foundation, or deliverable state when a
  public command owns the transition.

## Command Capability Probe

Run the startup probe before choosing a recipe, then probe the command family
used by the recipe.

```bash
async-research version
async-research --help
async-research workflow --help
async-research queue --help
async-research console --help
```

Probe only the families needed for the current action:

```bash
async-research idea --help
async-research review --help
async-research decision --help
async-research data --help
async-research library --help
async-research deliverable --help
async-research accepted --help
async-research surface --help
```

Stop if a recipe-critical command or flag is absent. Report the detected
version, missing command, and the recipe that cannot safely run.

## Recipe 1 - Status-Only Check

Mode: `read_only`.

Mutates: nothing.

Read-only commands: all commands in this recipe.

Use when the user asks for status, inspection, dashboard alignment, or the next
safe action only.

```bash
async-research workflow next <ops>
async-research queue list <ops> --group all --limit 50
async-research console snapshot <ops> --json
```

Report only:

- current workspace path and detected CLI version
- next safe action from `workflow next`
- active, review, human-gate, and blocked counts from `queue list`
- dashboard or console snapshot caveats

Stop conditions:

- CLI or `<ops>` is missing
- the dashboard snapshot conflicts with object-level CLI output
- the next action requires writes, credentials, network use, payment, public
  release, or human judgment

## Recipe 2 - Guided Framework Setup

Mode: `guided`.

Mutates: setup commands may create `.venv`, install packages, clone or fetch
code, or write shell config. Diagnosis mutates nothing.

Read-only commands: `pwd`, `git rev-parse`, `command -v`, `test -x`,
`inspect_workspace.py`, `async-research version`, and `async-research --help`.
Write-capable commands: `python -m venv`, `pip install`, clone/fetch commands,
shell configuration edits, and any command writing outside the workspace.

Diagnosis is allowed without approval:

```bash
pwd
git rev-parse --is-inside-work-tree
command -v async-research
test -x .venv/bin/async-research
.venv/bin/python skills/async-research-operator/scripts/inspect_workspace.py --workspace .
```

If no CLI is available, report setup options in this order:

1. Use an existing CLI path supplied by the user.
2. Use the checked-out framework repo with a project-local `.venv`.
3. Install the pinned package only after explicit package or network approval.

Only after the user approves the specific write may you run a local source setup
sequence:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/async-research version
.venv/bin/async-research --help
```

Only after explicit package or network approval may you run a pinned package
sequence:

```bash
python -m venv .venv
.venv/bin/python -m pip install async-research-workflow==0.2.0a5
.venv/bin/async-research version
.venv/bin/async-research --help
```

After any approved setup action, restart startup discovery and run the command
capability probe before operating a workspace.

Stop conditions:

- approval is missing for `.venv` creation, package install, network use,
  cloning, fetching, shell configuration changes, or writes outside workspace
- credentials, paid services, private package indexes, or external accounts are
  required
- install or version checks fail
- the detected version drifts from `async-research-workflow==0.2.0a5` and a
  recipe-critical command is missing
- the user requests a global install without acknowledging the broader scope

## Recipe 3 - New Workspace Setup

Mode: `guided`.

Mutates: `async-research init` creates `research_ops/`; `surface update` writes
human-facing status files.

Read-only commands: `schema-check`, `readiness --dry-run`, `health --dry-run`,
`surface validate`, `workflow next`, and `console snapshot --json`.
Write-capable commands: `init` and `surface update`.

Before writing, report the exact target path and confirm the repo is private or
explicitly approved for research state. There is no universal dry-run for
`init`, so approval is mandatory.

```bash
async-research init <ops>
async-research schema-check <ops>
async-research readiness <ops> --dry-run
async-research health <ops> --dry-run
async-research surface update <ops>
async-research surface validate <ops>
async-research workflow next <ops>
async-research console snapshot <ops> --json
```

Stop conditions:

- target path is unclear
- `<ops>` would be created in a public repo, framework/tool repo, or repo with
  unknown visibility
- existing non-empty target would require `--force`
- schema, readiness, health, or surface validation fails after initialization
- the user asks to create private research state outside the current workspace
  without approving that path

## Recipe 4 - Idea Capture And Promotion

Mode: `guided` or `bounded_autonomous` when the user explicitly asks for one
bounded planning loop.

Mutates: write mode creates idea catalog records, generated projections,
promotion task folders, queue rows, inbox rows, and selected idea metadata.

Read-only or preview commands: `idea catalog validate`,
`idea capture --dry-run`, `idea promote --dry-run`, `schema-check`, and
`workflow next`.
Write-capable commands: `idea capture --write` and `idea promote --write`.

First validate and identify the source row or explicit title:

```bash
async-research idea catalog validate <ops>
async-research idea capture <ops> --from-inbox row-7 --id IDEA-0007 --dry-run
```

If no inbox row exists and the user gives an explicit idea title, use the public
title-only capture path rather than hand-editing `discovery_inbox.md`:

```bash
async-research idea capture <ops> --title "New research angle" --id IDEA-0007 --dry-run
```

After a clean dry-run and approval for the catalog write:

```bash
async-research idea capture <ops> --from-inbox row-7 --id IDEA-0007 --write
async-research idea catalog validate <ops>
async-research idea promote <ops> IDEA-0007 --dry-run
async-research idea promote <ops> IDEA-0007 --write --preflight-hash <hash>
async-research schema-check <ops>
async-research workflow next <ops>
```

Use the exact `promotion_preflight_hash` from the immediately preceding clean
dry-run. If the dry-run returns blockers, report `next_step` and
`remediation_steps` instead of writing.

Stop conditions:

- source governance, duplicate, or score gate requires a human decision
- dry-run is blocked or lacks a preflight hash
- the preflight hash is stale or changed
- the write requires `--human-override` and no recorded human decision exists
- catalog validation fails after capture or promotion

## Recipe 5 - Manual Or LLM Task Creation

Mode: `guided` for normal task authoring; `bounded_autonomous` only when the
user explicitly asks for one safe task setup.

Mutates: write mode creates one task folder with `task.md`, `status.json`, and
review or artifact directories.

Read-only or preview commands: `workflow create-task --dry-run`,
`schema-check`, `queue list`, and `workflow next`.
Write-capable command: `workflow create-task --write`.

Preview the task first:

```bash
async-research workflow create-task <ops> \
  --title "Check data readiness for source set" \
  --task-type data_readiness \
  --objective "Verify whether the named source set is ready for analysis." \
  --allowed-path research_ops/data \
  --dry-run
```

After approval and a clean preview, write the same task:

```bash
async-research workflow create-task <ops> \
  --title "Check data readiness for source set" \
  --task-type data_readiness \
  --objective "Verify whether the named source set is ready for analysis." \
  --allowed-path research_ops/data \
  --write
async-research schema-check <ops>
async-research queue list <ops> --group ready_for_worker
async-research workflow next <ops>
```

Stop conditions:

- task scope, allowed paths, source refs, cost/network permissions, or review
  tier are unclear
- the task would require browsing, network, external data, or paid services
  without explicit approval
- dry-run reports invalid workspace state or task collision
- the requested task is a broad product, venue, or publication-readiness
  decision rather than bounded work

## Recipe 6 - Worker Loop

Mode: `bounded_autonomous` only after explicit user request, or `guided` when
the user approves each write.

Mutates: `worker-start` writes task status and `LOCK/`; worker output writes
`<task>/worker_output.md`; `worker-complete` writes status and releases the
lock.

Read-only or preview commands: `workflow status`, `worker-start --dry-run`, and
`worker-complete --dry-run`.
Write-capable actions: `worker-start`, task-local `worker_output.md`, and
`worker-complete`.

Inspect and claim only one task:

```bash
async-research workflow status <task>
async-research workflow worker-start <task> --dry-run
async-research workflow worker-start <task> --owner <agent-id>
```

Do the bounded work inside the task's allowed paths, then write the worker
artifact:

```text
<task>/worker_output.md
```

Complete only after the output is non-empty and within scope:

```bash
async-research workflow worker-complete <task> --owner <agent-id> --dry-run
async-research workflow worker-complete <task> --owner <agent-id>
async-research workflow status <task>
```

Stop conditions:

- task is not `ready_for_worker`
- lock conflict or stale-lock takeover needs human confirmation
- allowed files or task scope are unclear
- worker needs credentials, network access, paid services, or source governance
  approval not already recorded
- task status indicates `needs_human`, review work, or acceptance work instead
  of worker execution
- worker output would claim publication readiness or public suitability

## Recipe 7 - Review Loop

Mode: `guided`. Same-agent review is allowed only as weak review and must be
reported as such.

Mutates: `review submit` writes `reviews/<role>.md`; `workflow advance` writes
post-review task state and accepted-memory outputs when gates pass.

Read-only or preview commands: `workflow status`, `review draft` without
`--write`, `review submit --dry-run`, `workflow advance --dry-run`, and
`result-acceptance` without `--write`.
Write-capable commands: `review submit` without `--dry-run`, `workflow advance`
without `--dry-run`, and `result-acceptance --write --update-ledgers`.

Inspect the task and draft a conservative scaffold:

```bash
async-research workflow status <task>
async-research review draft <task> --role primary
```

Validate the explicit review before writing it:

```bash
async-research review submit <task> \
  --role primary \
  --decision needs_human \
  --claim-strength none \
  --confidence 0.4 \
  --concern "Same-agent review is not independent." \
  --dry-run
```

After the review text and decision are explicit:

```bash
async-research review submit <task> \
  --role primary \
  --decision needs_human \
  --claim-strength none \
  --confidence 0.4 \
  --concern "Same-agent review is not independent."
async-research workflow advance <task> --dry-run
async-research workflow advance <task>
async-research workflow status <task>
```

When result acceptance is needed, validate before ledger writes:

```bash
async-research result-acceptance <task> --ops-dir <ops>
async-research result-acceptance <task> --ops-dir <ops> --write --update-ledgers
```

Stop conditions:

- reviewer is the same agent and the user needs independent review
- worker output, evidence, source governance, or data/library validation is
  incomplete
- review flags do not match the written critique
- `workflow advance --dry-run` reports blockers
- task acceptance sources disagree with accepted memory or dashboard state

## Recipe 8 - Human Gate Handling

Mode: `guided`.

Mutates: `decision resolve-task` without `--dry-run` appends a decision row and
updates task status.

Read-only or preview commands: `workflow status`, `decision summarize`,
`decision resolve-task --dry-run`, and `workflow next`.
Write-capable command: `decision resolve-task` without `--dry-run`.

Inspect first and present evidence-backed options:

```bash
async-research workflow status <task>
async-research decision summarize <ops>
```

Report the decision needed, evidence files, safe default, and consequences.
Only after the human makes an explicit decision, preview the transition:

```bash
async-research decision resolve-task <ops> <task> \
  --decision approve \
  --reason "Human approved the bounded task after reviewing evidence." \
  --approver "<human>" \
  --status ready_for_worker \
  --dry-run
```

After the human confirms the exact decision and the dry-run is clean:

```bash
async-research decision resolve-task <ops> <task> \
  --decision approve \
  --reason "Human approved the bounded task after reviewing evidence." \
  --approver "<human>" \
  --status ready_for_worker
async-research workflow status <task>
async-research workflow next <ops>
```

Stop conditions:

- the human decision is absent, ambiguous, or bundled with unrelated approvals
- evidence files are missing or contradict the requested resolution
- decision concerns public release, paid services, credentials, target venue,
  maturity target, or publication readiness and the user has not explicitly
  accepted that responsibility
- dry-run reports invalid task state

## Recipe 9 - Foundation Proposal Loop

Mode: `guided`.

Mutates: data apply writes source audit and `research_ops/data/**`; library
apply writes `research_ops/library/*.md`. Both require accepted proof and a
matching preflight hash.

Read-only or preview commands: `data inspect-proposals`,
`library inspect-proposals`, `data apply-proposals --dry-run`,
`library apply-proposals --dry-run`, `source validate`, `data validate`,
`library validate`, and `workflow next`.
Write-capable commands: `data apply-proposals --write` and
`library apply-proposals --write`.

Inspect with the matching proposal family first. If the family is unclear, run
one inspection command, treat a non-matching proposal-family failure as a
diagnostic stop, and ask which route to use instead of trying private helpers.

Available inspection commands:

```bash
async-research data inspect-proposals <ops> <proposal-source>
async-research library inspect-proposals <ops> <proposal-source>
```

For data proposals:

```bash
async-research data apply-proposals <ops> <proposal-source> --dry-run
async-research data apply-proposals <ops> <proposal-source> --write --preflight-hash <hash>
async-research source validate <ops>
async-research data validate <ops>
async-research workflow next <ops>
```

For library proposals:

```bash
async-research library apply-proposals <ops> <proposal-source> --dry-run
async-research library apply-proposals <ops> <proposal-source> --write --preflight-hash <hash>
async-research library validate <ops>
async-research workflow next <ops>
```

If the source task is not already accepted, include the explicit accepted proof:

```bash
async-research data apply-proposals <ops> <proposal-source> --write --preflight-hash <hash> --accepted-artifact <accepted-result-json>
async-research library apply-proposals <ops> <proposal-source> --write --preflight-hash <hash> --accepted-artifact <accepted-result-json>
```

Stop conditions:

- proposal inspection fails or identifies unsafe target paths
- proposal type does not match the command family
- accepted task or result-acceptance proof is missing
- dry-run does not emit a clean preflight hash
- preflight hash is stale or changed
- write rolls back or post-write validation fails
- source governance needs human approval

## Recipe 10 - Deliverable Maturity Loop

Mode: `guided`.

Mutates: `deliverable init`, `deliverable target`, `deliverable critic`, and
`deliverable response` write deliverable maturity artifacts. `deliverable check`
is read-only.

Read-only command: `deliverable check`.
Write-capable commands: `deliverable init`, `deliverable target`,
`deliverable critic`, and `deliverable response`.

Create a deliverable record only after the user approves the target identity and
maturity intent:

```bash
async-research deliverable init <ops> \
  --title "Research memo title" \
  --output-type memo \
  --target-maturity internal_draft \
  --current-maturity research_note \
  --target-audience "Internal research team" \
  --owner "<owner>"
```

Update target metadata only after the user decides target audience, venue, and
maturity:

```bash
async-research deliverable target <ops> DELIV-0001 \
  --target-maturity shareable_memo \
  --target-audience "Internal research team" \
  --source-task TASK-0001 \
  --primary-artifact tasks/TASK-0001-example/artifacts/memo.md
```

Record critic review metadata and response rows:

```bash
async-research deliverable critic <ops> DELIV-0001 \
  --independence-type same_agent_visible \
  --confidence 0.4 \
  --recommended-maturity-ceiling internal_draft \
  --major 1 \
  --required-revision-row "Clarify evidence limitations before sharing."
async-research deliverable response <ops> DELIV-0001 \
  --critique-id RRM-0001 \
  --source-review CRITIC-0001 \
  --severity major \
  --target-section "Evidence limits" \
  --issue "Limitations are underspecified." \
  --decision accepted \
  --required-change "Add limitations section." \
  --owner "<owner>" \
  --status open
async-research deliverable check <ops> DELIV-0001 --target-maturity shareable_memo
```

Stop conditions:

- target audience, target venue, maturity target, or owner is a human decision
  and has not been supplied
- the user asks for publication, submission, release, or public-readiness claims
- critic independence is weak and the requested maturity requires stronger
  independence
- response rows are open or deliverable check fails
- accepted task outputs are being treated as deliverable readiness without a
  deliverable check

## Recipe 11 - Maintenance Loop

Mode: `maintenance`.

Mutates: `accepted update` refreshes accepted memory; `surface update` writes
human-facing status files. Other commands below are read-only or dry-run.

Read-only or preview commands: `schema-check`, `accepted revalidation`,
`readiness --dry-run`, `health --dry-run`, `surface validate`,
`console snapshot --json`, and `workflow next`.
Write-capable commands: `accepted update` and `surface update`.

Use for validation, dashboard refresh, and bookkeeping, not for research content
decisions:

```bash
async-research schema-check <ops>
async-research accepted update <ops>
async-research accepted revalidation <ops>
async-research readiness <ops> --dry-run
async-research health <ops> --dry-run
async-research surface update <ops>
async-research surface validate <ops>
async-research console snapshot <ops> --json
async-research workflow next <ops>
```

Stop conditions:

- accepted-memory revalidation is stale or requires research judgment
- readiness exits with skip, invalid state, or human action required
- health reports blockers that need source governance, credentials, paid
  services, or human decisions
- surface validation disagrees with workspace state
- maintenance uncovers an actionable task that requires worker, reviewer, or
  planner mode

## Command Capability Table

| Command Area | Read-Only? | Dry-Run? | Mutates What? | Typical Stop Condition |
| --- | --- | --- | --- | --- |
| Framework setup | Mixed | No universal dry-run | `.venv`, package files, local install state. | Missing approval, network need, global install request, credentials, failed install. |
| Workspace setup | Mixed | Required after init where available | `research_ops/`, dashboard/surface files. | Public/private ambiguity, unclear target path, existing non-empty target, failed validation. |
| `workflow next/status` | Yes | Not needed | Nothing. | Missing or invalid workspace, dashboard conflict, missing command capability. |
| `queue list` / `console snapshot` | Yes | Not needed | Nothing. | Snapshot conflicts with object-level CLI state or workspace cannot be read. |
| `idea capture/promote` | Mixed | Required before write | Idea catalog, generated projections, queue, inbox, task folders. | Missing source/governance decision, stale preflight hash, human override required. |
| `workflow create-task` | Mixed | Required before write | One task folder with `task.md`, `status.json`, and subdirectories. | Unclear task scope, invalid allowed paths, cost/network approval missing. |
| `worker-start/complete` | Mixed | Required before write | Task status, `LOCK/`, task-local `worker_output.md`. | Lock conflict, unclear task scope, human gate, output missing. |
| `review` / `decision` | Mixed | Required before decision writes; required for `review submit` | Review files, decision log, task state, accepted memory. | Same-agent independence issue, unresolved critique, missing human decision. |
| Foundation proposals | Mixed | Required before write | Source audit, `research_ops/data/**`, `research_ops/library/*.md`. | Missing accepted proof, unsafe target path, stale preflight hash, post-write validation failure. |
| `deliverable` | Mixed | `check` is read-only; write commands lack universal dry-run | Deliverable manifest, critic reviews, response matrix. | Missing audience, maturity target, citations, figures, critic response, or review independence. |
| Maintenance | Mixed | Use dry-run where available | Accepted-memory index and surface files. | Readiness blocker, stale accepted memory, surface mismatch, human decision needed. |

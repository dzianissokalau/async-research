# LLM Operator Skill Roadmap

Status: Not Started
Current phase: Phase 0 - Contract review gate
Last updated: 2026-05-19
Next action: Resolve the contract gate, then create the Codex-first skill skeleton with trigger evals
Blocked by: None

Created: 2026-05-19

## Summary

This roadmap creates an `async-research-operator` skill/playbook so Codex can
operate the async-research framework mostly autonomously through the public CLI,
with Claude Code and other capable LLM interfaces treated as later ports after
Codex dogfood proves the operating model.

This is not a new standalone UI. The intended human interaction model is:

- the human talks to an LLM interface such as Codex App
- the LLM uses the skill to inspect and operate `research_ops/`
- the framework CLI remains the action and validation layer
- the dashboard remains the shared progress/control-plane view
- durable truth remains in repository files, not chat memory

The v0.1 scope assumes a local or cloud agent with file and terminal access.
Web-only chat clients can review or advise from copied artifacts, but they are
not supported operator targets because they cannot verify repo state or run the
framework commands.

The skill should let an LLM reliably answer:

- where is the framework installed?
- where is the research workspace?
- what is the current state?
- what is the next safe action?
- can the next action be done autonomously?
- what files may be changed?
- what validations must run?
- when must the LLM stop and ask the human?
- what should be reported back?

## Design Principles

- Treat `research_ops/` files as source of truth. Chat history is never the
  authority.
- Prefer public `async-research` CLI commands over direct file mutation.
- Dry-run before write whenever the command supports it.
- Operate one bounded task at a time unless an explicit roadmap/automation phase
  says otherwise.
- Use the dashboard and console snapshot for visibility, not as the only state
  source.
- Stop at human gates, credentials, paid services, destructive actions, broad
  product decisions, target-venue decisions, and publication-readiness judgment.
- Treat acceptance/readiness disagreement as a stop condition: if task status,
  review/acceptance state, accepted memory, or deliverable checks conflict, stop
  and surface the discrepancy instead of choosing silently.
- Support framework setup only in guided mode: detect missing installs, explain
  options, ask before creating environments, network installs, package installs,
  or `research_ops/` initialization, then verify with public CLI checks.
- Keep the skill concise. Put long command recipes and provider-specific details
  in reference files loaded only when needed.
- Make v0.1 Codex-first. Keep the operating contract portable, but defer Claude
  Code, ChatGPT-agent, API-agent, and remote-gateway work until after real Codex
  dogfood.
- Prefer explanations over brittle commandments in skill text except for hard
  safety rules. For example, explain that file-backed state outranks chat memory
  because chat context can drift across sessions.

## Target Deliverable

The primary deliverable is a repository-backed Codex skill package that can be
copied or installed into a Codex skills directory. `SKILL.md` is the canonical
skill body. `agents/openai.yaml` is UI metadata generated from the skill body,
not a separate operating contract.

Preferred source layout:

```text
skills/async-research-operator/
  SKILL.md
  agents/
    openai.yaml
  references/
    startup.md
    setup.md
    command-recipes.md
    roles.md
    safety-and-stop-conditions.md
    reporting.md
    provider-notes.md
  scripts/
    inspect_workspace.py
    validate_skill_pack.py
```

If the repo chooses a different skill source root, update this roadmap and
`roadmaps/README.md` before implementation. The installed copy can later live
under `$CODEX_HOME/skills/async-research-operator/`.

## Review Synthesis

Two external reviews were incorporated into this roadmap. They agreed that the
framework is already well suited to an operator skill because the state is
file-backed, the CLI is broad enough for the intended workflow, and the skill can
wrap public commands instead of inventing a second automation layer.

The changes below reflect the strongest review findings:

- Choose one v0.1 target. Codex is now first-class; cross-provider exports move
  after Codex dogfood.
- Treat the skill `description` as a primary product surface. Phase 1 now
  requires candidate descriptions and trigger evals.
- Add behavioral validation. Structural checks remain necessary, but Phase 6 now
  requires fixture-based LLM/operator behavior tests and forward-testing.
- Add startup robustness. Phase 2 now includes framework version comparison,
  command capability probing, and a privacy-boundary script path.
- Add guided framework setup. The skill can help install and initialize the
  framework, but only after explicit approval for local writes or network use.
- Promote acceptance/readiness mismatches to stop conditions instead of mere
  reporting caveats.
- Keep verification in one shared strategy section and let phases list only
  phase-specific checks.

## Relationship To Existing Framework Surfaces

| Existing Surface | Skill Use |
| --- | --- |
| `async-research workflow next` | First-choice next-action recommender. |
| `async-research workflow status` | Task-level truth surface for locks, reviews, gates, and legal commands. |
| `async-research console snapshot --json` | Compact workspace overview for reporting and dashboard consistency checks. |
| Idea Catalog commands | Capture, inspect, score, resolve, promote, and trace ideas without hand-editing catalog state. |
| Source/data/library validators | Check whether evidence and foundation state are usable before tasks or acceptance. |
| Proposal inspect/apply commands | Inspect and apply accepted foundation proposals where available, with dry-run/write guards. |
| Review and result-acceptance commands | Route task outputs through review instead of treating worker output as truth. |
| Deliverable maturity commands | Keep accepted evidence separate from shareable or publication-ready deliverables. |
| Dashboard | Human progress view and sanity check for what the LLM reports. |

## Phased Plan

| Phase | Status | Focus | Scope | Exit Criteria |
| ---: | --- | --- | --- | --- |
| 0 | Not Started | Contract review gate | Resolve v0.1 target, source root, framework version range, autonomy defaults, stop categories, and source-of-truth rules. | Phase 1 can start without rediscovering product boundaries or provider scope. |
| 1 | Not Started | Codex-first skill skeleton and trigger contract | Create concise `SKILL.md`, generated Codex UI metadata, reference-file structure, candidate descriptions, and trigger eval set. | Codex can discover the skill reliably and load detailed references only when needed. |
| 2 | Not Started | Workspace discovery, guided setup, and startup protocol | Add startup recipe, guided framework setup flow, version guardrail, capability probe, privacy-boundary check, and optional read-only helper script. | The skill can safely pick up an existing project, guide first-time setup, and report unsupported CLI drift clearly. |
| 3 | Not Started | Command recipes for setup and core loop | Document exact dry-run/write command sequences plus a command capability table for setup, planning, workers, review, acceptance, gates, deliverables, and foundation proposals. | Another LLM can set up and operate common workflows without improvising command order or mutation safety. |
| 4 | Not Started | Role modes and autonomy policy | Define planner, worker, reviewer, critic, synthesizer, status reporter, and maintainer modes with allowed files, independence limits, and stop rules. | The LLM can switch roles deliberately and expose weak review independence. |
| 5 | Not Started | Reporting, dashboard alignment, and stop invariants | Define response formats, dashboard snapshot checks, artifact summaries, decision requests, progress reports, and acceptance/readiness mismatch stops. | Human-facing updates become consistent, concise, and tied to framework state. |
| 6 | Not Started | Skill validation and behavioral evals | Add simulated workspaces, structural tests, trigger evals, and fixture-based behavior/forward tests. | The skill has regression coverage for realistic states, unsafe requests, and actual operator behavior. |
| 7 | Not Started | Packaging, install, and Codex dogfood rollout | Add install instructions, validation command, dogfood checklist, and first real-project trial procedure. | A new Codex session can install/use the skill and pass a real workspace dogfood run. |
| 8 | Not Started | Cross-provider exports and remote gateway scoping | After Codex dogfood, create Claude/API/read-only export notes and decide whether a safe remote command gateway deserves its own roadmap. | Portability is based on proven behavior, and unsupported web-only operation is not over-promised. |

## Phase 0 - Contract Review Gate

### Objective

Resolve the few product decisions that shape the skill before implementation.
This phase is a gate, not a standalone prose deliverable; the contract content
should move directly into `SKILL.md` and `references/safety-and-stop-conditions.md`
in Phase 1.

### Owned Files

- `roadmaps/not_started_llm_operator_skill_roadmap.md`
- optionally `src/async_research_workflow/docs/llm_operator_contract.md`
- `roadmaps/README.md`

### Implementation Steps

1. Confirm the skill name: `async-research-operator`.
2. Define the skill's primary job in one sentence:
   "Operate an async-research workspace safely through public CLI commands,
   dashboard snapshots, and file-backed state."
3. Confirm the v0.1 target: Codex with file and terminal access.
4. Define the supported framework version range the skill is authored against.
5. Define autonomy levels:
   - `read_only`: inspect state and report next action
   - `guided`: ask before writes
   - `bounded_autonomous`: run one safe task loop when no human gate exists
   - `maintenance`: run validation, dashboard refresh, and bookkeeping
6. Define mandatory stop conditions by category:
   - **Irreversibility**: destructive file/git operation, public/private
     boundary ambiguity, publishing or submission claims
   - **External access or spend**: credentials, external accounts, paid
     API/cloud/data use
   - **Human judgment**: human decision gate, source governance approval,
     missing target audience, deliverable maturity choice, publication-readiness
     judgment
   - **Broken tooling or inconsistent truth**: required tests/validators cannot
     run, task acceptance sources disagree, deliverable readiness checks fail or
     disagree with dashboard state
7. Define source-of-truth hierarchy:
   - `research_ops/` files
   - public CLI JSON outputs
   - dashboard snapshot
   - user messages
   - model memory last
8. Decide where the repo stores the skill source package.
9. Update the roadmap index.

### Acceptance Criteria

- The roadmap states exactly what the skill does and does not do.
- Autonomy levels are named and usable in prompts.
- Stop conditions are explicit enough that another LLM can enforce them.
- Source-of-truth priority is explicit.
- Primary provider target, version range, and default autonomy level are
  explicit before implementation starts.

### Verification

Use the shared roadmap checks in [Verification Strategy](#verification-strategy).

### Non-Goals

- Do not change framework behavior.
- Do not design a standalone app UI.

## Phase 1 - Codex-First Skill Skeleton And Trigger Contract

### Objective

Create the Codex-first skill package with a concise `SKILL.md`, generated UI
metadata, reference-file structure, and validated trigger description.

### Owned Files

- `skills/async-research-operator/SKILL.md`
- `skills/async-research-operator/agents/openai.yaml`
- `skills/async-research-operator/references/*.md`
- `skills/async-research-operator/scripts/validate_skill_pack.py`
- tests for skill packaging if the repo has a suitable test location

### Implementation Steps

1. Create `skills/async-research-operator/`.
2. Draft 2-3 candidate `description` values for `SKILL.md`. Each candidate
   should describe what the skill does and when to trigger, including setup,
   inspection, continuation, operation, review, reporting, `research_ops/`, and
   async-research dashboard/workflow references.
3. Keep `SKILL.md` short. It should include:
   - quick purpose
   - first five commands to run
   - source-of-truth rule
   - stop conditions
   - reference-file map
4. Create reference files:
   - `startup.md`
   - `setup.md`
   - `command-recipes.md`
   - `roles.md`
   - `safety-and-stop-conditions.md`
   - `reporting.md`
   - `provider-notes.md`
5. Create `agents/openai.yaml` using deterministic metadata generated from the
   skill body.
6. Add a trigger eval file with roughly 20 prompts:
   - should-trigger examples covering formal, casual, abbreviated, dashboard,
     `research_ops`, "continue", and "what next" phrasings
   - should-not-trigger near misses covering generic research advice, unrelated
     coding tasks, generic project status, and non-async-research workflows
7. Pick the `description` candidate that scores best on held-out trigger evals.
8. Add a small `validate_skill_pack.py` script that checks required files,
   frontmatter fields, reference links, and forbidden clutter files.
9. Add tests or a documented validation command.

### Acceptance Criteria

- Skill package exists in the agreed repo path.
- `SKILL.md` is concise and does not duplicate long recipes.
- Every reference file is linked from `SKILL.md`.
- Trigger eval examples exist and the chosen description is recorded.
- No unnecessary README/changelog/extra docs are added inside the skill folder.
- Validation catches missing required files and broken reference links.

### Verification

Use the shared roadmap checks plus the skill-pack validator once it exists.
If `python` is not the repo's expected interpreter, use `.venv/bin/python`.

### Non-Goals

- Do not implement an MCP server.
- Do not add external service integration.
- Do not bundle large framework docs into the skill.

## Phase 2 - Workspace Discovery, Guided Setup, And Startup Protocol

### Objective

Make it easy for a fresh LLM session to locate or set up the framework, locate
a research workspace, verify safety, detect CLI drift, and summarize current
state. Setup is always guided: the skill may diagnose and propose commands, but
must ask before creating environments, installing packages, using the network,
or initializing research state.

### Owned Files

- `skills/async-research-operator/references/startup.md`
- `skills/async-research-operator/references/setup.md`
- `skills/async-research-operator/scripts/inspect_workspace.py`
- skill validation tests/fixtures

### Startup Protocol

The skill must instruct the LLM to:

1. Run `pwd` and `git rev-parse --is-inside-work-tree`.
2. Determine whether the current repo is the framework repo or a research repo.
3. Locate `async-research`:
   - prefer active shell command
   - then `.venv/bin/async-research`
   - then installed package command
4. If no usable CLI is found, enter guided setup mode:
   - report that the framework is not available in the current environment
   - list safe setup options, such as using an existing CLI path, creating a
     project-local `.venv`, installing from the checked-out framework repo, or
     installing a pinned package/release
   - ask before creating a virtual environment, installing packages, cloning or
     fetching from the network, modifying shell config, or writing outside the
     workspace
   - avoid global installs by default
   - after approved setup actions, restart detection from step 3
5. Run `async-research version`.
6. Compare the detected version to the skill's declared supported range and
   report drift without refusing to operate automatically.
7. Run `async-research --help` and probe the available top-level subcommands.
   If a recipe references a missing command, report the gap and avoid inventing
   a replacement action.
8. Locate `research_ops/`:
   - explicit user path first
   - current repo `research_ops/`
   - known private workspace path only if user provided one
9. If no `research_ops/` exists, offer guided workspace bootstrap:
   - explain where the workspace would be created
   - confirm the repo is private or explicitly approved for research state
   - ask before running `async-research init` or creating files
   - run validation checks immediately after approved initialization
10. Check privacy boundary:
   - if `research_ops/` is inside a public tool repo or unknown public repo,
     stop and ask before creating or writing research state
11. Run read-only checks:
   - `async-research schema-check research_ops`
   - `async-research readiness research_ops --dry-run`
   - `async-research health research_ops --dry-run`
   - `async-research workflow next research_ops`
   - `async-research console snapshot research_ops --json`
12. Summarize current state, setup actions taken or still needed, capability
    gaps, version drift, and next safe
    action.

### Helper Script

`inspect_workspace.py` should be optional. It may:

- detect candidate CLI path
- detect candidate `research_ops/`
- detect git repo status
- check likely privacy boundary from repo remotes and paths
- compare framework version to the skill-supported range
- list available top-level CLI subcommands
- emit setup recommendations when CLI or `research_ops/` is missing
- run read-only commands when explicitly invoked
- emit JSON only

It must not write files, create environments, install packages, clone repos, or
initialize workspaces.

### Acceptance Criteria

- A fresh LLM can pick up a workspace without relying on chat history.
- A fresh LLM can explain how to set up a missing framework install without
  silently writing files or using the network.
- The startup flow stops before writing into an unsafe public repo.
- Version drift and missing command capabilities are surfaced clearly.
- Missing `research_ops/` bootstrap is offered as an explicit user-approved
  action, not performed automatically.
- Read-only checks produce a compact state summary.
- Helper script is optional and read-only.

### Verification

Use the shared roadmap checks plus
`.venv/bin/python skills/async-research-operator/scripts/inspect_workspace.py --help`
once the helper exists.

### Non-Goals

- Do not auto-install dependencies, clone repositories, or create virtual
  environments.
- Do not create `research_ops/` unless the user explicitly asks.
- Do not open browsers or dashboards automatically.

## Phase 3 - Command Recipes For Setup And The Core Loop

### Objective

Give the skill exact command sequences for framework setup and common workflows
so an LLM does not improvise unsafe environment changes or state edits.

### Owned Files

- `skills/async-research-operator/references/command-recipes.md`
- supporting fixtures/tests if useful

### Required Recipes

Document exact sequences for:

1. **Status-only check**
   - `workflow next`
   - `queue list`
   - `console snapshot --json`
   - report only
2. **Guided framework setup**
   - detect missing `async-research`
   - report available setup options and tradeoffs
   - ask before creating `.venv`, running package installs, cloning/fetching, or
     writing outside the workspace
   - prefer project-local `.venv` and checked-out source installs when the
     framework repo is already present
   - avoid global installs unless the user explicitly requests them
   - rerun `async-research version` and `async-research --help`
   - stop if install commands fail, require credentials, require paid services,
     or need network approval not already granted
3. **New workspace setup**
   - `init`
   - `schema-check`
   - `readiness --dry-run`
   - `health --dry-run`
   - `surface update`
   - `surface validate`
4. **Idea capture and promotion**
   - add or confirm discovery row
   - `idea capture --dry-run`
   - `idea capture --write`
   - `idea catalog validate`
   - `idea promote --dry-run`
   - `idea promote --write --preflight-hash`
5. **Manual/LLM task creation**
   - `workflow create-task --dry-run`
   - `workflow create-task --write`
   - validation checks
6. **Worker loop**
   - `workflow status`
   - `worker-start --dry-run`
   - `worker-start`
   - write `worker_output.md`
   - `worker-complete --dry-run`
   - `worker-complete`
7. **Review loop**
   - `review draft`
   - `review submit --dry-run`
   - `review submit`
   - `workflow advance --dry-run`
   - `workflow advance`
8. **Human gate**
   - inspect `workflow status`
   - inspect evidence files
   - report options
   - use `decision resolve-task --dry-run`
   - write only after human decision
9. **Foundation proposal loop**
   - inspect proposal
   - dry-run apply
   - write apply only when accepted proof and preflight hash match
10. **Deliverable maturity loop**
   - `deliverable init`
   - `deliverable target`
   - `deliverable critic`
   - `deliverable response`
   - `deliverable check`
11. **Maintenance loop**
    - accepted update
    - revalidation
    - surface update/validate
    - health
    - dashboard snapshot

Also add a compact command capability table:

| Command Area | Read-Only? | Dry-Run? | Mutates What? | Typical Stop Condition |
| --- | --- | --- | --- | --- |
| Framework setup | Mixed | No universal dry-run | `.venv`, package files, local install state. | Missing approval, network need, global install request, credentials, failed install. |
| Workspace setup | Mixed | Required after init where available | `research_ops/`, dashboard/surface files. | Public/private ambiguity or unclear target path. |
| `workflow next/status` | Yes | Not needed | Nothing | Missing or invalid workspace. |
| `idea capture/promote` | Mixed | Required before write | Idea catalog, queue/tasks. | Missing source/governance decision or stale preflight hash. |
| `worker-start/complete` | Mixed | Required before write | Task status, worker outputs. | Lock conflict, unclear task scope, or human gate. |
| `review` / `decision` | Mixed | Required before write | Review files, task state, accepted memory. | Same-agent independence issue or unresolved critique. |
| `deliverable` | Mixed | Required where available | Deliverable maturity artifacts. | Missing audience, maturity target, citations, figures, or critic response. |

### Acceptance Criteria

- Every recipe says which commands are read-only and which mutate files.
- Framework setup recipes distinguish diagnosis, proposed commands, approved
  writes, network use, and verification.
- Every write recipe starts with a dry-run when supported.
- Every recipe includes stop conditions.
- The command capability table is present and checked against startup capability
  probing.
- Recipes reference public commands, not internal helper modules, unless no
  public command exists and the route is labeled advanced.

### Verification

Use the shared roadmap checks plus the skill-pack validator once it exists.

### Non-Goals

- Do not duplicate the entire README command map.
- Do not invent commands that do not exist.

## Phase 4 - Role Modes And Autonomy Policy

### Objective

Define clear LLM role modes so one conversation can act as planner, worker,
reviewer, critic, synthesizer, or status reporter without blurring review
independence.

### Owned Files

- `skills/async-research-operator/references/roles.md`
- `skills/async-research-operator/references/safety-and-stop-conditions.md`
- optional role prompt templates

### Role Modes

Define these modes:

| Role | May Do | Must Not Do |
| --- | --- | --- |
| Status reporter | Read state, summarize dashboard, list blockers. | Mutate files or choose research direction. |
| Planner | Capture/score/promote ideas, create tasks through public commands. | Do worker execution or review its own worker output as independent. |
| Worker | Claim one task, produce bounded `worker_output.md`, complete task. | Accept its own output or edit review files. |
| Reviewer | Inspect worker output, source/data/library state, submit review. | Edit worker output or hide caveats. |
| Critic | Apply adversarial deliverable review, prefer `deliverable critic --independence-type separate_agent` when available, and create response rows. | Rewrite the deliverable in the same pass. |
| Synthesizer | Assemble accepted evidence into memo/draft/deliverable artifacts. | Claim publication readiness without deliverable checks. |
| Maintainer | Run health/readiness/surface/revalidation checks. | Change research content. |

### Autonomy Levels

Document:

- `read_only`
- `guided`
- `bounded_autonomous`
- `maintenance`

Each level must specify:

- max writes
- allowed files
- commands allowed
- stop conditions
- final report required

### Acceptance Criteria

- Same-agent review limitations are explicit.
- The skill can tell the user when review independence is weak.
- The critic role maps to framework-level independence metadata where commands
  support it.
- Autonomy level is visible in the LLM's first status report.
- The skill stops before high-impact/public claims need human approval.

### Verification

Use the shared roadmap checks plus the skill-pack validator once it exists.

### Non-Goals

- Do not implement actual multi-agent spawning.
- Do not require a specific LLM provider.

## Phase 5 - Reporting, Dashboard Alignment, And Stop Invariants

### Objective

Make the LLM's conversational reports match framework state and dashboard
surfaces, while treating acceptance/readiness disagreement as a stop condition.

### Owned Files

- `skills/async-research-operator/references/reporting.md`
- optional report templates under the skill
- tests/fixtures for reporting examples if useful

### Required Report Types

Define templates for:

1. **Startup report**
   - framework version
   - workspace path
   - privacy status
   - health/readiness status
   - next safe action
2. **Task completion report**
   - task ID
   - files changed
   - worker output path
   - review status
   - acceptance route
   - caveats
3. **Human decision request**
   - decision needed
   - evidence links
   - options
   - consequences
   - recommended default if safe
4. **Deliverable maturity report**
   - target maturity
   - current maturity
   - failed gates
   - critic status
   - open response rows
5. **Maintenance report**
   - checks run
   - warnings
   - stale evidence
   - dashboard URL or snapshot summary

### Dashboard Alignment Rules

- When possible, run `async-research console snapshot research_ops --json`
  before reporting broad workspace state.
- If the dashboard and raw CLI disagree, trust raw CLI for the specific object
  and mention the discrepancy.
- Stop instead of summarizing a task as accepted when `status.json`,
  aggregate/result acceptance, and accepted memory disagree.
- Stop instead of summarizing a deliverable as ready when `deliverable check`
  fails or has not run.

### Acceptance Criteria

- Reports are short enough for conversation but include file paths and commands
  used.
- Human decision requests are evidence-first.
- Reports distinguish task acceptance from deliverable readiness.
- Dashboard state is used as a consistency check, not as sole authority.
- Acceptance/readiness mismatch rules are present in
  `safety-and-stop-conditions.md`, not only in `reporting.md`.

### Verification

Use the shared roadmap checks plus the skill-pack validator once it exists.

### Non-Goals

- Do not build a new web dashboard.
- Do not change dashboard UI behavior.

## Phase 6 - Skill Validation And Behavioral Evals

### Objective

Forward-test the skill against realistic framework states so it is not just a
well-formed document. Structural validation proves the package is shaped
correctly; behavioral validation proves an LLM can use it safely.

### Owned Files

- `skills/async-research-operator/scripts/validate_skill_pack.py`
- test fixtures under an existing repo fixture location or a new
  `tests/fixtures/skill_operator/`
- tests for skill references and simulated reports
- trigger eval prompts and expected labels
- behavioral eval prompts, transcripts, and scoring rubric

### Fixture Scenarios

Add minimal fixtures for:

1. No usable `async-research` CLI installed.
2. Framework repo present but no project-local environment.
3. Valid CLI but no `research_ops/` workspace.
4. Fresh workspace, no tasks.
5. Workspace with one ready task.
6. Workspace with one in-progress locked task.
7. Workspace with one awaiting-review task.
8. Workspace with `needs_human` gate.
9. Workspace with accepted task evidence but deliverable not ready.
10. Workspace with source/data/library blocker.
11. Workspace where chat request asks for unsafe action.

### Validation Approach

Structural tests should validate that:

- skill references contain required headings
- command recipes mention required public commands
- stop conditions include required blockers
- report templates include required fields
- fixture expected-next-action files match the startup/status recipes
- `description` trigger evals cover should-trigger and should-not-trigger
  prompts

Behavioral evals should validate that a fresh LLM/operator session using the
skill:

- recommends the expected next safe action for each fixture
- proposes guided setup steps when the framework or workspace is missing, but
  asks before writes, network use, or initialization
- stops at human gates, missing credentials, paid spend, destructive requests,
  privacy-boundary ambiguity, and publication-readiness judgment
- reports version drift and missing CLI capabilities without inventing commands
- distinguishes accepted task evidence from deliverable readiness
- includes commands run, files touched, caveats, and unresolved gaps in reports
- avoids mutating files in read-only scenarios

Optional helper scripts can render expected prompts or check recipe coverage.
When live LLM/subagent testing is available, use it for at least one pass before
marking this phase complete. When it is unavailable, record that limitation and
keep the skill in `Not Started` or `In Progress`, not stable.

### Acceptance Criteria

- Skill validation runs locally without external services.
- Fixtures cover normal operation and stop conditions.
- The skill cannot lose core safety rules without a test failing.
- Trigger evals demonstrate the chosen skill description is discoverable without
  excessive false positives.
- Behavioral evals or recorded forward-test transcripts show the skill works in
  realistic operator situations.

### Verification

Use the shared roadmap checks, full test discovery when fixtures are added, and
the skill-pack validator.

### Non-Goals

- Do not turn this into a general LLM benchmark.
- Do not require cross-provider calls before Codex dogfood.

## Phase 7 - Packaging, Install, And Codex Dogfood Rollout

### Objective

Make the skill easy to install, validate, and use in a real research project
from a fresh Codex session.

### Owned Files

- skill package files
- setup guide updates
- roadmap closeout notes
- optional install helper script if safe and local-only

### Implementation Steps

1. Add install instructions:
   - copy `skills/async-research-operator/` into
     `$CODEX_HOME/skills/async-research-operator/`
   - restart/reload Codex if needed
   - ask Codex to use `async-research-operator`
2. Add a first-use prompt:
   - "Use the async-research-operator skill. Inspect this workspace, report the
     current state, and recommend the next safe action without writing files."
3. Add a dogfood checklist:
   - missing CLI setup diagnosis
   - approved project-local install or explicit skip decision
   - missing `research_ops/` bootstrap diagnosis
   - fresh workspace status
   - existing coffee-style workspace status
   - one bounded worker loop
   - one review loop
   - one human gate stop
   - one deliverable maturity report
   - one acceptance/readiness mismatch stop
   - one command-capability or version-drift report
4. Add uninstall/update notes.
5. Update roadmap status after validation.

### Acceptance Criteria

- A new Codex session can install or reference the skill without hidden context.
- The first-use prompt results in a read-only state report.
- Dogfood checklist covers both autonomous action and stop behavior.
- Dogfood covers guided setup from a missing or incomplete local framework state.
- Dogfood evidence includes at least one fresh-session transcript or delivery log.
- Skill rollout does not require a new UI.

### Verification

Use the shared roadmap checks, full test discovery, and the skill-pack
validator.

Manual dogfood should be recorded in a delivery log before marking the roadmap
delivered.

### Non-Goals

- Do not auto-install into the user's local Codex directory unless explicitly
  requested.
- Do not publish the skill externally.
- Do not create a ChatGPT/Claude marketplace integration.

## Phase 8 - Cross-Provider Exports And Remote Gateway Scoping

### Objective

Use the Codex dogfood results to decide what portability should mean. Create
minimal provider notes and exports only after the Codex skill has proven its
core behavior.

### Owned Files

- `skills/async-research-operator/references/provider-notes.md`
- provider export files if the repo chooses to store them as skill references
- a follow-on gateway roadmap only if API/browser operation is worth pursuing

### Provider Profiles

Document:

| Provider Context | Expected Capability | Skill Instructions |
| --- | --- | --- |
| Codex App | File edits, terminal, git, dashboard/browser. | Full operator mode when workspace-write is available. |
| Codex CLI/automation | Terminal and file edits with sandbox. | Phase/task automation mode with strict stop conditions. |
| Claude Code | Repo and terminal access. | Port after Codex dogfood; use the same public CLI recipes. |
| ChatGPT agent with repo tools | Depends on connector/tool access. | Read-only/status mode unless file and command tools are proven. |
| ChatGPT/Claude web chat only | No reliable repo write access. | Not an operator target; advisory review only from copied artifacts. |
| API agent wrapper | Calls controlled actions. | Requires capability manifest and safe command gateway. |

### Prompt Packs

Create or document prompts only for provider contexts that can honor the skill's
file, terminal, dry-run, and stop-condition contract:

- setup/startup operator
- daily status reporter
- planner
- worker
- reviewer
- critic
- synthesizer
- maintenance runner
- read-only external reviewer

Each prompt must include:

- workspace root variables
- allowed files
- forbidden files
- dry-run/write policy
- stop conditions
- expected final report
- explicit capability assumptions

### Gateway Decision

If API or browser agents need real write capability, split a new roadmap for a
safe remote command gateway or MCP surface. The gateway should expose a small
allowlist over the public CLI, capability probing, budget policy, path allowlist,
and audit logs. Do not hide this work inside the skill package.

### Acceptance Criteria

- Provider notes are explicit about what each environment can and cannot do.
- Cross-provider exports reuse the proven skill contract instead of duplicating
  long command maps.
- Web-only LLMs are not instructed to perform repo mutations they cannot verify.
- The roadmap clearly states whether remote/API operation is deferred, rejected,
  or split into a new roadmap.

### Verification

Use the shared roadmap checks plus the skill-pack validator.

### Non-Goals

- Do not implement OAuth, connectors, or external APIs.
- Do not build a hosted gateway inside the skill phase.

## Suggested Delivery Order

1. Phase 0 to lock the contract gate and remove provider ambiguity.
2. Phase 1 to create the Codex-first skill shell and prove the trigger
   description.
3. Phase 2 and Phase 3 together if one implementation pass is desired; startup
   probing, guided setup, and command recipes are tightly coupled but should
   still be reviewed separately.
4. Phase 4 before serious dogfood, because role boundaries protect review
   quality.
5. Phase 5 before presenting the skill to a user, because reporting is the
   human interface and stop invariants prevent false readiness claims.
6. Phase 6 before calling the skill stable; structural checks alone are not
   enough.
7. Phase 7 to run Codex dogfood on a real workspace.
8. Phase 8 only after Codex dogfood shows which provider ports or remote-gateway
   work are worth doing.

## Verification Strategy

For every phase:

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
```

When implementation files or tests are added:

```bash
.venv/bin/python -m unittest discover -s tests
```

When the skill validation script exists:

```bash
.venv/bin/python skills/async-research-operator/scripts/validate_skill_pack.py
```

## Open Decisions

- Should the skill source live in this repo under `skills/`, or in a separate
  Codex-skill repository?
- What exact framework version range should v0.1 declare support for?
- Which framework install sources should guided setup support first: checked-out
  repo, pinned PyPI package, Git URL, or all three?
- Which helper scripts are worth including in v0.1 beyond
  `inspect_workspace.py` and `validate_skill_pack.py`?
- Should an API-agent gateway be a future roadmap after the skill stabilizes?
- Should `guided` be the default autonomy level when the user says "continue",
  with `bounded_autonomous` requiring explicit wording?
- What real workspace should be the first Codex dogfood target?

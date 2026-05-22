# Codex Plugin Product Roadmap

Status: Not Started
Current phase: Phase 0 - Product contract and plugin boundary
Last updated: 2026-05-21
Next action: Decide the plugin product boundary, canonical source layout, and first-run promise
Blocked by: None

Created: 2026-05-21

## Summary

This roadmap delivers async-research as a Codex plugin product: install the
plugin, open a repository, ask Codex to start async research, and get guided
setup, workspace inspection, next-safe-action navigation, and dashboard-aware
progress without losing the framework's governance advantages.

The plugin must remain an operator and navigation layer over the existing
framework. It should not become a second framework, a hidden state store, or an
unbounded remote command runner.

The starting product target is Codex. The architecture should leave a clear path
to Claude Code and other agent platforms by keeping the operating contract,
prompt/reference content, and command wrappers provider-portable.

## Product Thesis

Async-research is already strong as a governed research kernel:

- file-backed `research_ops/` state
- public CLI state transitions
- task contracts and locks
- source/data/library governance
- independent review and result acceptance
- deliverable maturity gates
- accepted-memory freshness
- dashboard/console visibility
- cost and health surfaces

The UX problem is navigation. Users and AI operators need a product shell that
answers:

- Is the framework installed?
- Is this a valid research workspace?
- What should I do next?
- Is the next action safe?
- What will change if I run it?
- Where is the dashboard?
- Why is the workflow blocked?
- What does this status or gate mean?

Codex is a natural product interface for this because it can read files, run
commands, explain state, edit bounded artifacts, and stop for approval when a
write, credential, network call, or human judgment is required.

## Product Promise

> Plug in async-research, open a repo, and Codex guides you from setup to the
> next safe research action while preserving file-backed auditability and human
> review gates.

## Non-Negotiable Governance Rules

- `research_ops/` files remain the durable source of truth.
- Public `async-research` CLI commands remain the action and validation layer.
- The plugin may guide setup, but must ask before installs, network use,
  virtualenv creation, `research_ops/` initialization, or writes outside the
  workspace.
- The plugin must dry-run before writes whenever the CLI supports it.
- The plugin must not summarize accepted task evidence as publication-ready
  deliverables.
- The plugin must stop at human gates, credentials, paid services, destructive
  operations, target-audience/venue decisions, public claims, and
  acceptance/readiness contradictions.
- The plugin must not expose arbitrary shell access through remote tools.
- Provider portability must reuse the same operating contract instead of
  duplicating drifting command maps.

## Target Architecture

```text
Codex Plugin: async-research
  .codex-plugin/plugin.json
  skills/
    async-research-operator/
      SKILL.md
      references/
      scripts/
  scripts/
    install_or_link_skill.py
    validate_plugin_pack.py
    first_run_check.py
  assets/
    first-success-prompts/
    screenshots-or-static-guides/
  optional later:
    .mcp.json
    apps/action metadata

Async-Research Framework
  async-research CLI
  research_ops/
  console/dashboard
  validators, gates, ledgers, reviews
```

The plugin packages the operator experience. The framework keeps the research
state machine. If a future remote/API gateway is needed, it should remain a
separate roadmap with a narrow allowlist over public CLI commands.

## Canonical Source Decision

Phase 0 must decide whether the canonical operator skill lives:

1. inside the plugin under `plugins/async-research/skills/async-research-operator/`;
2. at repo root under `skills/async-research-operator/`, copied into the plugin
   during packaging; or
3. in both places with a generator and drift tests.

Recommended default: keep the current root skill as the canonical source for
now, add a plugin packaging step that copies or links it into
`plugins/async-research/skills/`, and add drift validation. Once the plugin is
stable, the canonical source can move into the plugin if that reduces confusion.

## Relationship To Existing Work

| Existing Surface | Plugin Role |
| --- | --- |
| `async-research-operator` skill | Reuse as the core operator instructions and safety policy. |
| `inspect_workspace.py` | Reuse as first-run inspection; expose through plugin onboarding. |
| `validate_skill_pack.py` | Extend or wrap with plugin validation. |
| `workflow next` | Main next-safe-action engine; plugin translates output into human language. |
| `console snapshot --json` | Programmatic status read model for plugin reports. |
| `console <ops>` dashboard | Human visual surface; plugin should make launch/discovery easy. |
| `roadmaps/not_started_llm_operator_remote_gateway_roadmap.md` | Future write-capable remote/API tool surface; not part of plugin v1. |

## Phased Plan

| Phase | Status | Priority | Focus | Scope | Exit Criteria |
| ---: | --- | --- | --- | --- | --- |
| 0 | Not Started | P0 | Product contract and plugin boundary | Define v1 product promise, source layout, supported Codex environments, install path, safety rules, and portability posture. | A future LLM can scaffold the plugin without reopening product boundaries. |
| 1 | Not Started | P0 | Codex plugin skeleton | Create repo-local plugin structure, `.codex-plugin/plugin.json`, marketplace metadata decision, validator, and packaging manifest. | Codex can recognize the plugin package shape locally without runtime behavior yet. |
| 2 | Not Started | P0 | Skill bundling and drift control | Bundle or generate the existing operator skill into the plugin, preserve progressive disclosure, and add drift tests. | Plugin ships the same operating contract as the validated root skill. |
| 3 | Not Started | P0 | First-run and guided setup UX | Add plug-and-start flows for install detection, framework setup guidance, workspace bootstrap, and safe first inspection. | A new Codex session can move from empty repo to validated next-safe-action report with approval gates. |
| 4 | Not Started | P0 | Navigation commands and action recipes | Add product-level prompts/scripts for inspect, explain next action, run guided task loop, review/advance, deliverable check, and dashboard launch. | Users can ask natural product-level questions without memorizing CLI command order. |
| 5 | Not Started | P1 | Human-readable summaries and dashboard bridge | Add concise report formats, dashboard URL handling, summary wrappers, and UX copy for common states/blockers. | Human operators can understand state quickly while JSON remains available for agents. |
| 6 | Not Started | P1 | Safety, permission, and failure-mode hardening | Validate stop behavior for installs, network, credentials, destructive operations, human gates, and acceptance/readiness contradictions. | Plugin cannot make unsafe actions easier than the raw framework. |
| 7 | Not Started | P1 | Plugin validation and dogfood | Add plugin package checks, fixture-based behavior tests, fresh-session dogfood transcripts, and review prompts. | Plugin has repeatable evidence that it works as a product shell. |
| 8 | Not Started | P1 | Distribution and update workflow | Decide repo-local vs home-local install docs, marketplace entry, release artifact shape, update/uninstall instructions, and version compatibility policy. | A user can install, update, validate, and remove the plugin without hidden setup knowledge. |
| 9 | Not Started | P2 | Claude Code and other provider portability | Extract provider-neutral contract, Claude-specific notes, API/read-only mode notes, and remote-gateway handoff boundaries. | Codex remains v1, but portability is designed rather than bolted on. |
| 10 | Not Started | P2 | Product polish and adoption loop | Add first-success UX review fixes, examples, screenshots, support docs, and feedback capture. | Plugin is credible as the primary product entrypoint for new users. |

## Phase 0 - Product Contract And Plugin Boundary

### Objective

Lock the product promise and implementation boundary before scaffolding plugin
files.

### Owned Files

- `roadmaps/not_started_codex_plugin_product_roadmap.md`
- `roadmaps/README.md`
- optionally a short architecture decision record under docs

### Implementation Steps

1. Choose plugin name:
   - recommended: `async-research`
   - display name: `Async Research`
2. Define v1 supported environment:
   - Codex with repository file access
   - terminal access
   - workspace-write or explicit approval for writes
   - local framework checkout or installable package
3. Define v1 non-targets:
   - web-only ChatGPT/Claude operation
   - arbitrary remote command execution
   - hosted dashboard service
   - automatic global installs
   - public release/publishing automation
4. Decide canonical source layout:
   - root skill copied into plugin
   - plugin-owned skill source
   - generated dual layout with drift tests
5. Define first-run promise:
   - detect framework
   - detect workspace
   - explain setup gaps
   - ask before writes
   - run read-only checks
   - report next safe action
6. Define plugin safety policy:
   - source-of-truth hierarchy
   - dry-run/write policy
   - approval gates
   - dashboard as visibility, not truth
7. Define portability posture:
   - Codex plugin is v1 product
   - Claude Code support is a later export/port
   - API/remote agents require separate gateway safety contract

### Acceptance Criteria

- Product promise is one sentence and testable.
- Plugin boundary versus framework boundary is explicit.
- Canonical source layout is chosen.
- Codex v1 assumptions are listed.
- Claude/other portability is scoped without expanding v1.

### Non-Goals

- Do not scaffold plugin files in Phase 0.
- Do not build remote/API command tools.

## Phase 1 - Codex Plugin Skeleton

### Objective

Create the minimal Codex plugin package shape.

### Owned Files

- `plugins/async-research/.codex-plugin/plugin.json`
- optional `plugins/async-research/README.md` only if plugin packaging requires it
- `plugins/async-research/scripts/validate_plugin_pack.py`
- optional `.agents/plugins/marketplace.json`
- tests for plugin package shape

### Implementation Steps

1. Scaffold `plugins/async-research/`.
2. Add required `.codex-plugin/plugin.json` with:
   - name
   - display/interface metadata
   - description
   - version compatibility note
   - skill/resource declarations if supported by local plugin schema
3. Decide whether to add repo-local marketplace metadata:
   - keep out of v1 if plugin discovery is manual
   - add only when Codex UI ordering/install testing needs it
4. Add plugin validation script:
   - required manifest exists
   - plugin name matches folder name
   - required folders exist
   - no placeholder values remain when phase closes
   - root skill source and plugin skill bundle match expected layout
5. Add tests that validate plugin file shape without needing Codex UI.

### Acceptance Criteria

- Plugin folder has valid required structure.
- Validation fails on missing manifest or stale placeholders.
- No runtime behavior changes are introduced.

### Non-Goals

- Do not create MCP tools yet.
- Do not publish a plugin.

## Phase 2 - Skill Bundling And Drift Control

### Objective

Make the existing `async-research-operator` skill the plugin's operator brain
without creating divergent instructions.

### Owned Files

- `skills/async-research-operator/**`
- `plugins/async-research/skills/async-research-operator/**`
- plugin validation script
- skill validation tests

### Implementation Steps

1. Decide copy/link/generate mechanism.
2. Bundle `SKILL.md`, references, scripts, and metadata into the plugin.
3. Preserve progressive disclosure:
   - concise `SKILL.md`
   - detailed command recipes in references
   - scripts executable without loading all docs into context
4. Add drift validation:
   - root skill and plugin copy content hashes match, or
   - generated plugin skill has recorded source hash, or
   - root skill is removed and plugin skill becomes canonical
5. Extend existing skill tests to validate plugin-bundled skill.
6. Update docs to tell maintainers where to edit skill content.

### Acceptance Criteria

- Plugin contains a complete operator skill.
- Validation catches source drift.
- Existing skill-pack tests pass for the plugin-bundled copy.
- Maintainers know the canonical edit location.

### Non-Goals

- Do not fork the skill into Codex-only and Claude-only copies yet.

## Phase 3 - First-Run And Guided Setup UX

### Objective

Make the first interaction feel like "plug and start."

### Owned Files

- plugin skill references
- plugin scripts
- first-run prompt assets
- tests/fixtures

### Implementation Steps

1. Add a product-level first prompt:
   - "Use Async Research. Inspect this repo and tell me the next safe action."
2. Add first-run script or wrapper around `inspect_workspace.py`:
   - detect current directory
   - detect framework CLI
   - detect `.venv`
   - detect `research_ops/`
   - detect dashboard availability
   - probe CLI version/capabilities
   - emit concise JSON and human summary
3. Add guided setup branches:
   - framework missing
   - installed version drift
   - workspace missing
   - workspace exists but invalid
   - dashboard unavailable
4. Add approval checkpoints:
   - create `.venv`
   - install package
   - use network
   - initialize `research_ops/`
   - write derived surface files
5. Add post-setup checks:
   - `version`
   - `--help`
   - `schema-check`
   - `readiness --dry-run`
   - `health --dry-run`
   - `workflow next`
   - `console snapshot --json`

### Acceptance Criteria

- A new session can inspect and explain setup state without writing files.
- Missing setup produces clear next steps.
- Approved setup returns to read-only validation.
- Unsafe setup requests stop with a human-readable reason.

### Non-Goals

- Do not auto-install or auto-init without approval.

## Phase 4 - Navigation Commands And Action Recipes

### Objective

Let users ask product-level questions while the plugin maps them to safe CLI
recipes.

### Owned Files

- plugin skill references
- prompt assets
- optional wrapper scripts
- tests/fixtures

### Product-Level Intents

Support these intents:

| User Intent | Plugin Behavior |
| --- | --- |
| "Start async research here" | Run first-run inspection, then guided setup if needed. |
| "What should I do next?" | Run `workflow next`, summarize recommendation, safety, and exact command. |
| "Show me status" | Run health/readiness/queue/console snapshot and summarize. |
| "Run one task" | Dry-run worker start, explain write scope, ask or proceed based on autonomy. |
| "Review this task" | Prepare review context, submit review only with explicit decision. |
| "Advance workflow" | Dry-run or explain transition, then run guarded CLI command. |
| "Is this deliverable ready?" | Run deliverable checks and explain gates/gaps. |
| "Open dashboard" | Explain and run `async-research console <ops>` only when user wants local server. |

### Acceptance Criteria

- Each product-level intent maps to public CLI commands.
- Every mutating recipe includes dry-run or approval behavior.
- Plugin reports exact commands used and files touched.
- Unknown intent falls back to inspection, not improvisation.

### Non-Goals

- Do not add hidden state transitions outside the CLI.

## Phase 5 - Human-Readable Summaries And Dashboard Bridge

### Objective

Reduce JSON overload while keeping machine-readable outputs intact.

### Owned Files

- plugin reporting references
- optional CLI wrapper scripts
- dashboard launch docs
- tests

### Implementation Steps

1. Define concise summary formats:
   - workspace summary
   - next-action card
   - blocker card
   - task lifecycle card
   - deliverable maturity card
   - dashboard launch card
2. Add plugin-side summarization rules:
   - use JSON as source
   - summarize without hiding warnings
   - include exact command links/commands
   - disclose unavailable groups
3. Make dashboard launch discoverable:
   - command
   - URL
   - port conflict behavior
   - what actions dashboard can/cannot perform
4. Add examples for common states:
   - fresh workspace
   - ready task
   - human gate
   - failed deliverable maturity
   - source/data blocker

### Acceptance Criteria

- Users can understand state without reading raw JSON first.
- JSON remains available and authoritative.
- Dashboard launch path is obvious.

### Non-Goals

- Do not redesign the dashboard UI in this roadmap unless needed for launch UX.

## Phase 6 - Safety, Permission, And Failure-Mode Hardening

### Objective

Ensure plugin convenience does not weaken the framework's governance model.

### Owned Files

- plugin tests/fixtures
- skill safety references
- validation scripts
- dogfood logs

### Required Stop Fixtures

Add or reuse fixtures for:

- missing CLI
- version drift
- missing `research_ops/`
- public repo ambiguity
- requested global install
- requested network install
- credential requirement
- paid API/cloud/data request
- destructive file/git command
- active lock
- `needs_human` task
- acceptance/readiness contradiction
- accepted evidence but deliverable not ready
- dashboard/raw-state disagreement

### Acceptance Criteria

- Every stop fixture produces a clear stop reason and no unsafe writes.
- Plugin reports required approval in plain language.
- Plugin validator fails if critical stop text disappears.

### Non-Goals

- Do not rely on live external services for safety tests.

## Phase 7 - Plugin Validation And Dogfood

### Objective

Prove the plugin works as a product shell in fresh sessions.

### Owned Files

- plugin validation tests
- dogfood transcripts
- review prompts
- automation logs under `roadmaps/automation/`

### Implementation Steps

1. Add plugin validator to the standard verification path.
2. Add fixture tests for:
   - manifest validity
   - skill bundle completeness
   - source drift
   - first-run inspection
   - unsafe stop behavior
   - summary format
3. Run dogfood scenarios:
   - brand-new repo, no framework
   - framework repo, no workspace
   - initialized workspace, no task action needed
   - ready worker task
   - review/advance path
   - deliverable maturity gap
4. Record honest evidence:
   - commands run
   - files touched
   - what worked
   - what was confusing
   - whether this was installed-plugin dogfood or source-package replay
5. Run independent review of the delivered plugin branch.

### Acceptance Criteria

- Plugin behavior is validated without hidden local context.
- At least one fresh-session dogfood run is recorded.
- Known limitations are documented before any product claim.

### Non-Goals

- Do not publish externally from dogfood alone.

## Phase 8 - Distribution And Update Workflow

### Objective

Make the plugin installable, updatable, and removable without hidden knowledge.

### Owned Files

- plugin packaging docs
- marketplace metadata if used
- release checklist additions
- tests

### Implementation Steps

1. Document install modes:
   - repo-local development plugin
   - home-local plugin
   - copied plugin bundle
2. Document update modes:
   - pull repo and rerun validator
   - regenerate bundled skill
   - check supported framework version
3. Document uninstall:
   - remove plugin folder
   - remove marketplace entry if manually added
   - preserve `research_ops/`
4. Add compatibility policy:
   - plugin version
   - framework version
   - skill source hash
   - dashboard/API expectations
5. Decide whether plugin gets its own version separate from framework version.

### Acceptance Criteria

- A user can install, validate, update, and uninstall from docs alone.
- Plugin version compatibility is explicit.
- Distribution docs do not imply PyPI/GitHub release publication.

### Non-Goals

- Do not publish plugin to a marketplace unless explicitly requested.

## Phase 9 - Claude Code And Other Provider Portability

### Objective

Prepare portability without diluting the Codex plugin v1.

### Owned Files

- provider notes
- export scripts if needed
- portability fixtures
- follow-on roadmaps if needed

### Implementation Steps

1. Extract provider-neutral contract:
   - source of truth
   - public CLI recipes
   - stop conditions
   - reporting formats
   - setup boundaries
2. Define provider classes:
   - full local operator: file + terminal access
   - read-only reviewer: file read, no command execution
   - advisory chat: copied artifacts only
   - remote/API agent: gateway required for writes
3. Add Claude Code export notes:
   - `SKILL.md` compatibility
   - setup assumptions
   - terminal/file requirements
4. Add non-Codex guardrails:
   - never claim writes happened unless the provider can verify them
   - do not use copied chat context as state
   - remote writes require separate gateway roadmap
5. Create follow-on roadmaps only where there is real implementation work:
   - Claude package export
   - MCP/remote gateway
   - hosted dashboard

### Acceptance Criteria

- Codex-specific plugin files remain isolated from provider-neutral instructions.
- Claude/other provider notes are truthful about capability limits.
- Remote write capability remains blocked on the gateway roadmap.

### Non-Goals

- Do not make Claude or API agents equal v1 targets.

## Phase 10 - Product Polish And Adoption Loop

### Objective

Turn the plugin from a technical bundle into a pleasant first product entrypoint.

### Owned Files

- plugin docs/assets
- README pointers
- examples
- UX-review backlog
- tests

### Implementation Steps

1. Add first-success examples:
   - "new workspace"
   - "existing workspace"
   - "blocked workspace"
   - "deliverable gap"
2. Add screenshots or text captures:
   - dashboard launch
   - next-action report
   - human gate stop
   - deliverable maturity report
3. Add glossary links for:
   - `research_ops`
   - surface
   - accepted evidence
   - deliverable maturity
   - claim strength
   - anti-context
4. Add UX feedback loop:
   - capture friction reports
   - convert repeated friction into plugin fixes or framework CLI fixes
   - keep product copy aligned with actual capability
5. Run another UX review focused specifically on plugin onboarding.

### Acceptance Criteria

- New users are directed to the plugin as the easiest entrypoint.
- Plugin docs explain when to use raw CLI versus guided Codex operation.
- UX review findings are triaged into quick wins, plugin work, framework work,
  or non-goals.

### Non-Goals

- Do not hide the underlying framework from users who need auditability.

## Prioritized Improvement Table

| Priority | Improvement | Description | Impact | Status |
| --- | --- | --- | --- | --- |
| P0 | Plugin product contract | Define promise, boundaries, canonical source, and safety model. | Prevents plugin from becoming an unsafe second framework. | Not Started |
| P0 | Plugin skeleton | Add `.codex-plugin/plugin.json` and validation. | Makes async-research installable as a Codex product bundle. | Not Started |
| P0 | Skill bundling | Package existing operator skill inside plugin with drift checks. | Reuses delivered operator intelligence without duplication. | Not Started |
| P0 | First-run guided setup | Detect install/workspace state and guide setup safely. | Delivers "plug and start" value. | Not Started |
| P0 | Product-level navigation intents | Map natural requests to safe CLI recipes. | Reduces command memorization. | Not Started |
| P1 | Human-readable summaries | Translate JSON state into concise status cards. | Improves human UX while preserving agent JSON. | Not Started |
| P1 | Safety fixtures | Prove plugin stops at risky actions. | Protects framework governance. | Not Started |
| P1 | Dogfood evidence | Fresh-session product trials and review. | Builds confidence before distribution. | Not Started |
| P1 | Distribution docs | Install/update/uninstall and compatibility policy. | Makes plugin usable outside the author's machine. | Not Started |
| P2 | Provider portability notes | Claude/API/read-only modes and limits. | Keeps future expansion realistic. | Not Started |
| P2 | Product polish loop | Examples, glossary, screenshots, UX review. | Makes plugin credible as the primary entrypoint. | Not Started |

## Suggested Delivery Order

1. Phase 0 before any scaffold.
2. Phase 1 to create the plugin shell.
3. Phase 2 to bring in the existing operator skill.
4. Phase 3 and Phase 4 together if one implementation pass is desired; first
   run and navigation are tightly coupled.
5. Phase 5 once real plugin reports exist.
6. Phase 6 before dogfood broadens.
7. Phase 7 before any distribution claim.
8. Phase 8 when the plugin is installable by another user.
9. Phase 9 after Codex v1 is stable.
10. Phase 10 after first external UX feedback.

## Verification Strategy

For every phase:

```bash
git diff --check
.venv/bin/python -m unittest tests.test_doc_references
```

When plugin files exist:

```bash
python3 plugins/async-research/scripts/validate_plugin_pack.py
```

When skill bundle exists:

```bash
.venv/bin/python skills/async-research-operator/scripts/validate_skill_pack.py
```

When tests are added:

```bash
.venv/bin/python -m unittest discover -s tests
```

No verification path should require live credentials, paid APIs, network access,
or a marketplace publish.

## Open Decisions

- Should the plugin be named `async-research` or `async-research-operator`?
- Should the canonical skill source move into the plugin after v1?
- Should the plugin include only skills/scripts, or also a future MCP/action
  surface?
- Should plugin and framework versions move together or separately?
- Should repo-local marketplace metadata be committed, or should installation
  remain manual until distribution is clearer?
- What is the first external dogfood target for the plugin?

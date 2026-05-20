# Provider Notes

The proven v0.1 target is Codex with repository file access and terminal
access. Other providers may reuse the same operating contract only when they can
verify workspace files, run the public `async-research` CLI, preserve dry-run
before write, and stop at the same human gates.

## Provider Profile Matrix

| Provider context | Expected capability | Skill instructions |
| --- | --- | --- |
| Codex App | File edits, terminal, git, dashboard/browser checks. | Full operator mode when workspace-write is available; still default to `guided` unless the user asks for `read_only` or one bounded autonomous loop. |
| Codex CLI/automation | Terminal and file edits with sandbox limits. | Phase/task automation mode; inspect file-backed state, run public CLI commands, record verification, and preserve unrelated worktree changes. |
| Claude Code | Repo and terminal access when configured by the human. | Port after Codex dogfood; use the same public CLI recipes and state hierarchy, with no provider-specific mutation shortcuts. |
| ChatGPT agent with repo tools | Depends on connected file and command tools. | Read-only/status mode unless file writes, terminal commands, workspace path controls, and dry-run/write separation are proven in that session. |
| ChatGPT/Claude web chat only | No reliable local repo write access or command execution. | Not an operator target; advisory review only from copied artifacts, command output, dashboards, or transcripts. |
| API agent wrapper | Calls controlled actions rather than a normal shell. | Requires a capability manifest and safe command gateway before any write path. |

## Portable Contract

Provider exports must reference the canonical skill contract instead of copying
long command maps. A port is acceptable only if it keeps these rules visible:

- workspace root and `research_ops/` path are explicit variables
- allowed files and forbidden files are named before work starts
- `research_ops/` files outrank CLI JSON, dashboard snapshots, user messages,
  and model memory
- public `async-research` commands are preferred over direct file edits
- dry-run comes before write whenever the public command supports it
- broad setup, installs, network access, credentials, paid services,
  destructive actions, public/private ambiguity, publication claims, human
  gates, and acceptance/readiness contradictions stop for human input
- final reports include commands used, files touched, validation results,
  blockers, caveats, and next safe action

## Prompt Pack Contracts

Use these as provider export snippets only after the provider proves file and
terminal capability. Keep the detailed recipes in the skill references.

### Setup And Startup Operator

Capability assumptions: repo file access, terminal access, and permission to
inspect the current workspace. Start in `guided` mode. Run only discovery and
read-only checks until the human approves environment creation, package
installation, network access, cloning/fetching, shell changes,
`research_ops/` initialization, or writes outside the workspace. Report the
workspace root, CLI source, framework version, capability gaps, privacy boundary,
and next safe action.

### Daily Status Reporter

Capability assumptions: repo file access and terminal access. Start in
`read_only` mode. Use `async-research workflow next research_ops`,
`async-research workflow status`, and
`async-research console snapshot research_ops --json` when available. Do not
change files. Report source-of-truth conflicts and stop before choosing between
disagreeing task, acceptance, dashboard, or deliverable readiness signals.

### Planner

Capability assumptions: repo file access, terminal access, and no authority to
decide product direction alone. Start in `guided` mode. Inspect the next task,
allowed files, gates, and validation commands. Produce one bounded plan and stop
for target venue, maturity, source governance, product, or public/private
boundary decisions.

### Worker

Capability assumptions: repo file access, terminal access, and an approved task
or explicit bounded autonomous request. Use public CLI commands to start,
complete, and validate one task. Dry-run write-capable commands first. Keep
edits inside the task's allowed files. Final report must list changed files,
validation commands, worker output path, caveats, and whether review is needed.

### Reviewer

Capability assumptions: repo file access and terminal access. Prefer a fresh
context where possible. Same-agent review must be labeled
`same_agent_visible` and must not be described as independent. Use public review
commands, record claim strength and concerns, and stop on uncertainty requiring
human judgment.

### Critic

Capability assumptions: repo file access and terminal access. Look for safety
violations, unsupported claims, stale evidence, acceptance/readiness mismatch,
dashboard conflicts, and missing validation. Do not mutate task outputs unless
the human explicitly changes the role from critic to worker.

### Synthesizer

Capability assumptions: repo file access, terminal access, and accepted source
material. Summarize accepted evidence into the requested maturity target only
after deliverable checks support that target. Stop before publication,
submission, target-venue choice, or claims that the deliverable is ready without
the required checks.

### Maintenance Runner

Capability assumptions: repo file access and terminal access. Use
`maintenance` mode for validation, dashboard refresh, and bookkeeping that does
not decide research substance. Dry-run first when supported and report stale
evidence, warnings, and unresolved gates.

### Read-Only External Reviewer

Capability assumptions: copied artifacts, dashboard exports, command output, or
transcripts only. Treat all findings as advisory because local state cannot be
verified. Do not instruct the human or another agent to mutate repo files based
solely on copied context.

## Web-Only Advisory Mode

Web-only chat clients may review copied artifacts, summarize pasted command
output, or suggest questions for a local operator. They must not claim to have
validated the workspace, must not mark tasks accepted, and must not ask the user
to perform unverified write sequences. The expected final report is an advisory
review with evidence gaps and commands a capable local operator should run.

## Remote Gateway Decision

Remote/API write operation is split into a future roadmap, not hidden inside the
skill package. A safe gateway would need a small allowlist over public
`async-research` CLI commands, a capability manifest, path allowlists, budget and
network policy, dry-run enforcement, audit logs, and explicit human approval for
all high-impact actions. Until that exists, API wrappers and browser agents stay
read-only or advisory for workspace operation.

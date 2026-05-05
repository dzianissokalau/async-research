# Knowledge Library Roadmap

Created: 2026-05-05

## Summary

Build a trusted knowledge library before, during, and after research task
execution. The library should collect durable background context from books,
papers, articles, posts, user notes, and previously accepted evidence.

The goal is not to create an exhaustive literature review by default. The goal
is to create enough trusted context for the current research mission: key
concepts, claims, methods, debates, source quality, caveats, and open
questions.

## What It Does

The library feature gives the framework reusable research memory:

- source inventory with stable library source IDs
- key claims and caveats linked to sources
- important methods, assumptions, and definitions
- open questions and unresolved disagreements
- known weak sources, dead ends, and anti-context
- gaps that should become future tasks

It supports multiple starting points:

- user provides a curated reading list
- user provides rough notes or local documents
- accepted outputs already exist and can seed the library
- no library exists yet, so the planner creates a small `library_review` task

## Framework Integration

New workspace artifacts:

```text
research_ops/
  library/
    source_library.md
    knowledge_index.md
    claim_map.md
    method_index.md
    open_questions.md
    library_update_log.md
```

Recommended source namespace:

```text
LIT-0001
LIT-0002
LIT-0003
```

Integration points:

- Discovery reads `library/` before browsing.
- Planner uses `open_questions.md` and `claim_map.md` to create bounded tasks.
- Idea scoring can reference library support and knowledge gaps.
- Workers may cite `LIT-*` IDs as background, but final claims still need
  source-level citation.
- Reviewers check whether outputs overstate claims already marked weak,
  disputed, stale, or context-only.
- Accepted outputs can trigger reviewed library updates.

The library should complement `accepted_outputs_index.md`, not replace it.
Accepted outputs are task results. The library is background context and claim
memory that helps choose and review future work.

## Implementation Steps

### Slice 1: Starter Files

Add empty library files to the generic and real-estate templates.

Acceptance:

- `async-research init research_ops` creates `research_ops/library/`
- empty library files do not break `schema-check`, `readiness`, `health`, or
  `surface update`
- starter README explains that an empty library is valid during cold start

### Slice 2: Library File Contracts

Define lightweight Markdown table contracts.

Suggested files:

- `source_library.md`: source ID, title, author/publisher, type, location,
  trust tier, status, reviewed date, notes
- `knowledge_index.md`: topic, summary, source refs, confidence, caveats
- `claim_map.md`: claim, source refs, claim strength, caveats, disputed status
- `method_index.md`: method, use case, assumptions, source refs, risks
- `open_questions.md`: question, why it matters, source refs, next task
- `library_update_log.md`: date, task ID, files updated, reviewer/approver

Acceptance:

- each file has a schema/version marker or clear table header
- examples are domain-neutral
- contracts distinguish trusted source memory from accepted task results

### Slice 3: Task Template

Add a `library_review` task template.

The task should specify:

- topic or source set
- allowed source list
- whether browsing is allowed
- extraction fields
- claim-strength rules
- required caveats
- output update targets

Acceptance:

- a worker can complete one `library_review` task without writing outside the
  task folder unless explicitly asked to propose library updates
- reviewer can accept, revise, reject, or route to human
- accepted library updates are traceable to a reviewed task

### Slice 4: Validator

Add:

```bash
async-research library validate research_ops
```

The validator should check structure, not semantic truth.

Checks:

- duplicate `LIT-*` IDs
- malformed table rows
- missing source location or provenance
- missing trust/status fields
- claim rows without source refs
- disputed claims without caveats
- stale reviewed dates where configured

Acceptance:

- valid empty library passes or returns warning-only status
- duplicate IDs fail validation
- malformed claim rows are surfaced with file and row context

### Slice 5: Health, Readiness, And Surface

Add library signals to operational surfaces.

Examples:

- missing library: warning only
- stale high-priority topic: warning
- unsupported claim used by an active task: blocker or reviewer concern
- new open questions: weekly digest summary

Acceptance:

- `health` and `readiness` explain library warnings without blocking all work
- `weekly_digest.md` can summarize library coverage and open questions

### Slice 6: Dashboard Surface

Add read-only dashboard views.

Show:

- library coverage by topic
- recently reviewed sources
- stale or disputed claims
- open questions
- proposed library update tasks

Acceptance:

- operator can understand library state without opening raw Markdown files
- dashboard does not mutate library files in the first version

## Open Questions

- Should library source status mirror data source statuses, or use simpler
  statuses such as `candidate`, `trusted`, `context_only`, `disputed`, and
  `deprecated`?
- Should `LIT-*` IDs be globally unique across the workspace, or scoped to the
  library only?
- Should user-provided notes be treated as sources, or as annotations attached
  to other sources?
- Should the first implementation include import helpers, or only manual
  Markdown contracts?

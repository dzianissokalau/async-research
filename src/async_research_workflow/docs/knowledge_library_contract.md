# Knowledge Library Contract

Created: 2026-05-09

The knowledge library is the durable background-memory surface for a
`research_ops/` workspace. It records reviewed sources, topic summaries, claim
caveats, methods, open questions, and library-update provenance without
becoming a second accepted-results ledger.

## Scope

The canonical path is:

```text
research_ops/library/
```

V1 uses Markdown files as the source of truth:

```text
research_ops/library/source_library.md
research_ops/library/knowledge_index.md
research_ops/library/claim_map.md
research_ops/library/method_index.md
research_ops/library/open_questions.md
research_ops/library/library_update_log.md
```

Do not introduce `research_ops/knowledge/` as a parallel namespace. Library
source identifiers use the `LIT-0001` shape and resolve against
`research_ops/library/source_library.md`.

## Boundary With Accepted Outputs

The library stores background context. `accepted_outputs_index.md` stores
reviewed task outputs that have passed result acceptance. A library row can make
planning and review cheaper by preserving caveats or source status, but it does
not approve a final task claim by itself.

Workers may cite `LIT-*` IDs as background context. Final accepted claims still
need source-level citation, review, and the normal result-acceptance gates.

## Literature Extraction Tasks

V1 keeps the executable task type as `literature_extract`. A
`literature_extract` task may create or improve library state by proposing
generated-block rows, but worker writes stay inside the task folder by default.
Do not write directly to `research_ops/library/` unless the task's
`allowed_paths` explicitly grants those files.

The task guidance must specify the topic or source set, allowed source list,
whether browsing is allowed, extraction fields, source status and trust tier
rules, claim-strength rules, required caveats, anti-context and dead ends,
proposed update targets, and `async-research library validate research_ops`.

Worker output should include proposed `source_library.md`,
`knowledge_index.md`, `claim_map.md`, `method_index.md` when relevant,
`open_questions.md`, and `library_update_log.md` rows. It should also list the
exact files that would be updated and reviewer notes for weak, disputed,
deprecated, or context-only sources. Reviewers can accept, revise, reject, or
route proposed updates to a human. Accepted library updates must be traceable to
a reviewed task through `library_update_log.md`.

High-stakes claims and any proposed `strong` claim require human approval before
publication use.

For library-dependent planning support, only row-level `source_id` values parsed
from the generated `source_library.md` block satisfy `LIT-*` refs. Notes,
headings, examples, or other ad hoc text in `source_library.md` do not count as
resolved library support.

## Commands

Initialize or repair starter files:

```bash
async-research library init research_ops --dry-run
async-research library init research_ops --write
```

Without `--write`, `library init` is read-only and reports missing files. With
`--write`, it creates only missing library files and must preserve existing
manual notes.

Validate the library:

```bash
async-research library validate research_ops
```

Validation is read-only. It checks generated blocks, table shape, duplicate
`LIT-*` IDs, source refs, source metadata, caveats, reviewed dates, and update
provenance.

Exit codes:

| Code | Meaning |
| ---: | --- |
| 0 | Library contracts are clean. |
| 2 | Warning-only findings with usable state. |
| 3 | Invalid request flags such as malformed `--now`. |
| 4 | Malformed generated blocks, duplicate IDs, invalid vocabularies, or unresolved source refs. |

Cold-start workspaces are allowed. A missing or empty library warns or passes
depending on the state, but it must not block discovery, idea scoring, data
readiness, health, or surface validation in V1.

## Manual Notes

Each library file has one generated table block and a `## Notes` section.
Tooling owns only the generated block. Free-form notes are for humans and must
not be edited by tooling.

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

# Phase 6 Dependency Decision Record

Status: delivered
Roadmap: `roadmaps/in_progress_framework_simplification_strategy.md`
Date: 2026-05-25

## Phase Contract

Phase 6 makes dependency adoption intentional. It records explicit keep, defer,
or adopt decisions for Typer, jsonschema, and filelock without changing public
CLI behavior, JSON envelopes, exit codes, workspace file formats, or the
standard-library-only runtime posture.

## Decision Summary

| Candidate | Decision | Runtime posture | Rationale | Reopen trigger |
| --- | --- | --- | --- | --- |
| Typer | defer | Keep `argparse` in the default runtime. | The CLI already has broad public help, alias, wrapper-argv, JSON-envelope, and exit-code contracts. Replacing the parser before command normalization evidence would risk behavior drift for little immediate simplification. | Revisit only after command deprecations or aliases have golden help/error coverage and a migration plan proves that Typer reduces maintained surface without changing public behavior. |
| jsonschema | defer | Keep the current standard-library schema subset validator. | The validator is small, documented as incomplete, and fails closed for unsupported keywords. Adding jsonschema would change validation semantics and error text before schema contracts are mapped. | Revisit when schemas require unsupported JSON Schema features and the migration has fixtures for accepted and rejected artifacts plus documented error-envelope changes. |
| filelock | defer | Keep atomic-directory lock primitives. | Current locks use atomic directory creation, owner metadata, stale-lock handling, and task/workspace-specific semantics. Replacing them is a behavior change, not just a dependency swap. | Revisit after concurrency evidence shows the current lock primitive is insufficient, with cross-platform regression tests and lock metadata compatibility requirements. |

## Release Posture

The default package remains standard-library-only:

- `pyproject.toml` keeps `project.dependencies = []`.
- Typer, jsonschema, and filelock are not default runtime dependencies.
- Future adoption, if justified, should prefer an optional operator extra rather
  than a default runtime requirement.

An optional future shape could be:

```toml
[project.optional-dependencies]
operator = ["typer", "jsonschema", "filelock"]
```

That future shape is not adopted in Phase 6.

## Evidence Checked

- `README.md` states that runtime dependencies are standard-library-only.
- `pyproject.toml` has an empty `project.dependencies` list.
- `src/async_research_workflow/docs/schema_validation_protocol.md` documents
  the intentionally limited fail-closed schema validator.
- Phase 4 proposal consolidation used standard-library lock and atomic-write
  primitives instead of introducing a runtime dependency.

## Non-Goals

- Do not add Typer, jsonschema, filelock, or any other runtime dependency.
- Do not change public parser output, aliases, help shape, exit codes, or JSON
  envelopes.
- Do not change schema validation behavior or error text in this phase.
- Do not replace existing task, foundation, or proposal lock files.

## Follow-Up Requirements Before Any Future Adoption

Any future dependency adoption must include:

1. an updated decision record with the new evidence and a clear adopt decision;
2. public behavior goldens for any CLI, schema, or lock surface affected;
3. migration notes that say whether the package default remains
   standard-library-only or changes to optional extras;
4. targeted tests proving existing workspaces and file formats still work.

# Shareable Memo Polish Task Template

## Objective

Polish an internal draft for a declared non-academic audience without claiming
working-paper or submission-ready maturity.

## Required Inputs

- Deliverable id: `DELIV-0001`
- Target audience in `deliverable_manifest.json`
- Current draft artifact
- Open gaps and caveats

## Required Output

Produce a clean memo draft with reader-fit prose, embedded and narrated
figures/tables, reader-trust citations, and disclosed unresolved gaps.

## Acceptance Criteria

- `target_audience` is set.
- Shareable-memo manuscript gates are `passed`, `passed_with_caveats`, or
  `waived_by_human` with rationale.
- Internal workflow and source labels are removed from external-facing prose or
  explicitly disclosed where appropriate.
- `async-research deliverable check research_ops DELIV-0001 --target-maturity shareable_memo`
  passes before the output is called shareable.

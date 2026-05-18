# Internal Draft Assembly Task Template

## Objective

Assemble accepted source task outputs into a coherent internal draft. The output
may become source material for a deliverable, but this task does not certify
shareable, working-paper, or submission-ready maturity.

## Required Inputs

- Deliverable id: `DELIV-0001`
- Source task ids: `TASK-0001`
- Target output type and target maturity from `deliverable_manifest.json`

## Required Output

Write the draft under the task folder or the declared deliverable artifact path.
Include evidence links, caveats, unresolved gaps, and a short maturity note:
`accepted internal draft; external readiness requires deliverable gates`.

## Acceptance Criteria

- All cited source tasks are accepted.
- Claims remain within accepted evidence and caveats.
- Internal workflow labels are disclosed, not hidden.
- `async-research deliverable check research_ops DELIV-0001` is run and its
  blockers are copied into the task output.
- The task status or title does not use `final` or `submission-ready`.

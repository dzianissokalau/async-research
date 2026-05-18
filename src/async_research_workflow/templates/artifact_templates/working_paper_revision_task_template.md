# Working Paper Revision Task Template

## Objective

Revise a deliverable toward working-paper maturity after explicit manuscript
gates and adversarial critic findings are known.

## Required Inputs

- Deliverable id: `DELIV-0001`
- Latest critic review id and artifact
- Review-response matrix rows for material findings
- Current draft artifact and manuscript checklist

## Required Output

Produce revised manuscript sections and closure artifacts for each accepted or
modified response-matrix row.

## Acceptance Criteria

- Related work, contribution, methods, reproducibility, limitations, formal
  citations, and complete bibliography gates are satisfied or human-waived.
- A distinct critic review meets at least `separate_agent` independence.
- Critical and major response-matrix rows are closed or human-waived with
  rationale.
- `async-research deliverable check research_ops DELIV-0001 --target-maturity working_paper`
  passes before the output is called working-paper ready.

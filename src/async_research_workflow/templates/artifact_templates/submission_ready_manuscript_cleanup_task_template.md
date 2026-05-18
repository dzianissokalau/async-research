# Submission-Ready Manuscript Cleanup Task Template

## Objective

Prepare a venue-targeted manuscript only after working-paper gates, critic
review, and response-matrix closure are complete.

## Required Inputs

- Deliverable id: `DELIV-0001`
- Target venue and venue style profile
- Closed response matrix
- Bibliography, figure/table inventory, data availability, and code availability

## Required Output

Produce venue-compliant manuscript cleanup changes, final reference formatting,
data/code availability statements, figure/table requirement evidence, and final
editorial review notes.

## Acceptance Criteria

- `target_venue` and venue/style profile are declared.
- Formal references, data/code availability, venue figure/table requirements,
  response matrix closure, and independent final editorial review gates pass.
- Review independence is at least `different_model`, `human`, or `external`.
- `async-research deliverable check research_ops DELIV-0001 --target-maturity submission_ready_manuscript`
  passes before the output is called submission-ready.

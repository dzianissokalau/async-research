# Manuscript Readiness Checklist

Use this checklist before raising a deliverable above `internal_draft`.
Statuses must be one of `not_required`, `missing`, `partial`,
`passed_with_caveats`, `passed`, or `waived_by_human`. Human waivers require a
rationale and should remain visible in `deliverable check`.

| gate_id | minimum_maturity | status | evidence | rationale_or_waiver |
| --- | --- | --- | --- | --- |
| target_audience_declared | shareable_memo | missing |  |  |
| clean_prose_pass | shareable_memo | missing |  |  |
| figures_tables_embedded_and_narrated | shareable_memo | missing |  |  |
| reader_trust_citations | shareable_memo | missing |  |  |
| unresolved_gaps_disclosed | shareable_memo | missing |  |  |
| internal_workflow_source_label_cleanup | shareable_memo | missing |  |  |
| final_prose_pass | shareable_memo | missing |  |  |
| related_work_synthesis | working_paper | missing |  |  |
| contribution_statement | working_paper | missing |  |  |
| methods_detail | working_paper | missing |  |  |
| reproducibility_notes | working_paper | missing |  |  |
| formal_limitations | working_paper | missing |  |  |
| formal_citations | working_paper | missing |  |  |
| complete_bibliography | working_paper | missing |  |  |
| target_venue_declared | submission_ready_manuscript | missing |  |  |
| venue_style_compliance | submission_ready_manuscript | missing |  |  |
| formal_references | submission_ready_manuscript | missing |  |  |
| data_code_availability | submission_ready_manuscript | missing |  |  |
| figure_table_requirements | submission_ready_manuscript | missing |  |  |

Suggested CLI update:

```bash
async-research deliverable target research_ops DELIV-0001 \
  --manuscript-gate related_work_synthesis=passed \
  --gate-evidence related_work_synthesis="deliverables/DELIV-0001/related-work.md"
```

# Review-Response Matrix

Use one row per material critic issue. Critical and major rows must be closed
or explicitly human-waived before working-paper or submission-ready promotion.

| critique_id | source_review | severity | target_section | issue | decision | required_change | response_rationale | owner | status | closure_artifact |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RRM-0001 | CRITIC-0001 | major | Related work | Missing competing hypotheses. | accepted | Add related-work synthesis. |  | deliverable owner | open |  |

Allowed decisions: `accepted`, `modified`, `rejected_with_rationale`,
`deferred`, or `human_waived`.

Suggested CLI update:

```bash
async-research deliverable response research_ops DELIV-0001 \
  --critique-id RRM-0001 \
  --source-review CRITIC-0001 \
  --severity major \
  --target-section "Related work" \
  --issue "Missing competing hypotheses." \
  --decision accepted \
  --required-change "Add related-work synthesis." \
  --owner "deliverable owner" \
  --status closed \
  --closure-artifact deliverables/DELIV-0001/revisions/related-work.md
```

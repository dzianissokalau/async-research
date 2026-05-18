# Deliverable Manifest Template

Use this template when a paper, report, memo, or presentation needs a maturity
record before drafting or promotion. The durable file is
`research_ops/deliverables/deliverable_manifest.json`; the Markdown projection
is `research_ops/deliverables/deliverable_manifest.md`.

## Required Declaration

| field | value |
| --- | --- |
| deliverable_id | DELIV-0001 |
| title | Replace with deliverable title |
| output_type | research_note, internal_draft, memo, report, paper, working_paper, manuscript, presentation, or other |
| target_audience | Known reader or audience |
| target_venue | Venue, publication, client, or submission target; required for submission-ready manuscripts |
| venue_style_profile | Optional style or venue profile |
| target_maturity | research_note, internal_draft, shareable_memo, working_paper, or submission_ready_manuscript |
| current_maturity | Current declared maturity level |
| source_task_ids | Accepted task IDs used as source evidence |
| primary_artifact | Main artifact path relative to `research_ops/` |
| owner | Human or agent owner |

## Command Pattern

```bash
async-research deliverable init research_ops \
  --deliverable-id DELIV-0001 \
  --title "Replace with deliverable title" \
  --output-type working_paper \
  --target-maturity working_paper \
  --current-maturity internal_draft \
  --target-audience "public research readers" \
  --source-task TASK-0001 \
  --primary-artifact "deliverables/DELIV-0001/draft.md" \
  --owner "paper owner"
```

Run `async-research deliverable check research_ops DELIV-0001` before calling
the output shareable, working-paper-ready, final, or submission-ready.

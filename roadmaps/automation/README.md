# Roadmap Automation Artifacts

This folder keeps low-level Codex delivery machinery out of the roadmap root.

Use the roadmap root for human-facing roadmap documents:

- `delivered_*_roadmap.md`
- `in_progress_*_roadmap.md`
- `not_started_*_roadmap.md`
- `blocked_*_roadmap.md`
- `paused_*_roadmap.md`
- `superseded_*_roadmap.md`

Use this folder for automation templates, state, logs, and review outputs.

## Layout

```text
roadmaps/automation/
  codex_phase_gated_delivery_automation_template.md
  <roadmap_slug>/
    automation_guide.md
    delivery_state.json
    delivery_log.md
    review_fix_state.json
    review_fix_log.md
    reviews/
      ...
```

Do not place delivery state, automation logs, or review iteration files directly
in `roadmaps/`.

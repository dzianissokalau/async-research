# Roadmap Closeout Checklist

Use this checklist before marking a roadmap delivered, paused, superseded, or
otherwise complete.

## Checklist

- Update the roadmap header: `Status`, `Current phase`, `Last updated`,
  `Next action`, and `Blocked by`.
- Rename the roadmap file to the lifecycle prefix that matches the header:
  `delivered_`, `in_progress_`, `not_started_`, `blocked_`, `paused_`, or
  `superseded_`.
- Update `roadmaps/README.md` so the roadmap row points to the current filename
  and repeats the current status, phase, date, next action, and blocker.
- Update inbound links across documentation and roadmap files. Normal Markdown
  links must point to the current lifecycle filename.
- Move or repoint automation artifacts under
  `roadmaps/automation/<roadmap_slug>/`. Do not delete unique state, log, or
  review content while moving automation machinery.
- Run the stale-link scan with the documentation tests:
  `.venv/bin/python -m unittest tests.test_doc_references`.
- Run any roadmap-specific verification commands recorded in the delivery log
  before claiming closeout.
- Record backlog follow-ups in the relevant backlog or replacement roadmap
  instead of leaving them only in review notes.

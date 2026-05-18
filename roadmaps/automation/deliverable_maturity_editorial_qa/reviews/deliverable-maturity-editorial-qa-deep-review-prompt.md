# Deep Independent Review Prompt

Repository: `dzianissokalau/async-research`
Final branch: `codex/deliverable-maturity-editorial-qa-delivered`
Pre-delivery base branch: `origin/main`

Review these files and the delivered diff:

- Roadmap: `roadmaps/delivered_deliverable_maturity_editorial_qa_roadmap.md`
- Delivery log: `roadmaps/automation/deliverable_maturity_editorial_qa/delivery_log.md`
- Delivery state: `roadmaps/automation/deliverable_maturity_editorial_qa/delivery_state.json`
- Review files: `roadmaps/automation/deliverable_maturity_editorial_qa/reviews/`

Verification commands that passed on the delivery branch:

```bash
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest discover -s tests
.venv/bin/async-research acceptance-suite
.venv/bin/python -m unittest tests.test_deliverable_maturity
.venv/bin/python -m unittest tests.test_prompt_library
.venv/bin/python -m unittest tests.test_packaged_resources
.venv/bin/python -m unittest tests.test_cli_help
git diff --check
```

Inspect the full delivery diff against the pre-delivery base branch:

```bash
git fetch origin
git diff origin/main...codex/deliverable-maturity-editorial-qa-delivered
```

Review focus:

- Feature behavior: deliverable maturity must remain separate from task
  acceptance; accepted source tasks must never imply shareable, working-paper,
  final, or submission-ready maturity.
- Manuscript gates: target audience, output type, venue where required,
  bibliography, figure/table narration, data/code availability, critic review,
  and response-matrix closure must block promotion at the right maturity levels.
- Critic stage: review independence metadata, same-agent visibility, recommended
  maturity ceilings, severity distribution, required revision rows, and seeded
  response-matrix rows must behave consistently and fail closed.
- Response matrix: critical and major rows must remain blocking until closed
  with closure evidence or human-waived with rationale.
- Dashboard/read model honesty: labels must distinguish internal draft accepted
  from shareable memo, working-paper-ready, and submission-ready states.
- Tests and fixtures: confirm the coffee-pilot fixture proves the roadmap
  scenario and that regressions cover the new template, prompt, CLI, and
  packaged-resource paths.
- Security and path handling: inspect relative path validation for primary
  artifacts, critic artifacts, closure artifacts, and seeded response-matrix
  rows.
- Data integrity: check schema compatibility, manifest projection behavior,
  read-model derivation, and non-destructive handling of existing manifests.
- Roadmap claims: verify the roadmap, log, state, and review files match the
  actual delivered behavior.

Expected output:

- Findings by severity with file and line references.
- Missing tests, if any.
- Residual risks or follow-up recommendations.
- Final verdict: `delivered`, `needs-fix`, or `blocked`.

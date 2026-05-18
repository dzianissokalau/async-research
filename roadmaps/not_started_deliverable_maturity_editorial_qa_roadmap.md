# Deliverable Maturity And Editorial QA Roadmap

Status: Not Started
Current phase: Phase 4 - Dashboard visibility and honest labels
Last updated: 2026-05-18
Next action: Surface maturity/editorial QA status in dashboard/read models and rename misleading final-output labels
Blocked by: None

Created: 2026-05-17

## Summary

This roadmap turns the coffee-and-climate manuscript dogfood issue into a
dedicated feature track for deliverable maturity and editorial quality
assurance.

Source logs:

- `/Users/dzianissokalau/Documents/projects/open-researches/coffee/coffee-and-climate/FRAMEWORK_USAGE_ISSUES.md`
- `/Users/dzianissokalau/Documents/projects/open-researches/coffee/coffee-and-climate/HUMAN_FRAMEWORK_INTERACTION_LOG.md`
- `/Users/dzianissokalau/Documents/projects/open-researches/coffee/coffee-and-climate/LLM_FRAMEWORK_END_TO_END_LOG.md`

The core diagnosis is semantic: `accepted` currently means a task output is
internally valid enough to use under its caveats. It does not mean the final
paper is externally excellent, audience-fit, fully cited, publication-ready, or
independently challenged.

The framework should keep task acceptance strict and useful, but add a separate
deliverable-maturity layer for final outputs. A paper, memo, or report should
not be described as final or publication-ready unless it passes gates for its
declared target audience and maturity level.

## Product Problem

The coffee pilot produced a useful internal Markdown paper draft. The framework
source gates, library checks, review aggregation, accepted memory, and caveat
audit helped keep claims conservative. An external review still found the draft
was not journal-ready:

- related work was incomplete
- methods were under-formalized
- figures and tables were not fully embedded and narrated
- citations and bibliography were not publication-ready
- internal workflow/source labels leaked into prose
- the draft lacked an independent adversarial manuscript review
- `final paper production` overstated what the task actually produced

The missing concept is not another generic review. It is a deliverable-specific
quality system that distinguishes internal task validity from external
deliverable readiness.

## Design Principles

- Preserve `accepted` as a task-level workflow status, not a publication claim.
- Add maturity levels for deliverables instead of overloading task statuses.
- Require target audience and output type before high-stakes drafting.
- Make manuscript gates explicit, machine-checkable where possible, and
  human-reviewable where judgment is required.
- Require independent critical review before a draft can be called ready for an
  external audience.
- Convert critiques into a response matrix before revision work starts.
- Keep dashboards honest: show `internal draft accepted` separately from
  `shareable` or `submission-ready`.

## Deliverable Maturity Levels

| Level | Label | Meaning | Minimum Gates |
| ---: | --- | --- | --- |
| 0 | Research note | Bounded finding or evidence note for internal use. | Source/caveat checks, claim strength, task review. |
| 1 | Internal draft | Coherent internal synthesis assembled from accepted task outputs. | Accepted evidence linkage, caveat audit, internal-workflow disclosure, draft completeness check. |
| 2 | Shareable memo | Polished memo for a known non-academic audience. | Target audience, clean prose, figures/tables embedded and narrated, citations sufficient for reader trust, unresolved gaps disclosed. |
| 3 | Working paper | Public working paper or preprint-quality research artifact. | Related-work synthesis, contribution statement, methods detail, reproducibility notes, formal limitations, complete bibliography, adversarial review. |
| 4 | Submission-ready manuscript | Venue-targeted manuscript ready for journal/conference/submission workflow. | Venue fit, style compliance, formal references, data/code availability, figure/table requirements, response matrix closed, independent final editorial review. |

The exact labels can change, but the framework needs a durable distinction
between internal acceptance and external readiness.

## Phased Plan

| Phase | Focus | Scope | Exit Criteria |
| ---: | --- | --- | --- |
| 0 | Deliverable maturity contract | Define maturity taxonomy, output type, target audience, venue, status vocabulary, and durable manifest/read-model fields. | A deliverable can declare what it is trying to be, and the framework can represent that separately from task status. |
| 1 | Paper-specific quality gates | Add checklists for related work, contribution, methods, reproducibility, figures/tables, citations, data/code availability, limitations, and prose cleanup. | A manuscript-like deliverable cannot be marked above internal draft without satisfying explicit quality gates. |
| 2 | Adversarial reviewer stage | Add critic task type, independence metadata, role prompts, and critic-specific review output. | A working paper or submission-ready manuscript requires an independent critical review before final maturity promotion. |
| 3 | Review-response matrix | Add critique-to-action matrix with severity, target section, accepted/rejected/modified decision, required change, owner, and closure status. | Major critique cannot disappear into prose edits; every material issue is accepted, rejected with rationale, or resolved. |
| 4 | Dashboard visibility and honest labels | Surface maturity level, checklist status, critic review, response matrix, caveats, unresolved gaps, and independence status. Rename misleading final-paper task labels. | Humans can see whether an output is internally accepted, shareable, working-paper-ready, or submission-ready. |
| 5 | Templates, prompts, and fixtures | Add templates for deliverable targets, manuscript checklists, critic prompts, response matrices, and a coffee-pilot regression fixture. | LLMs and humans can create manuscript workflows without inventing the maturity model from scratch. |

## Prioritized Improvements

| Priority | Phase | Improvement | Description | Impact | Status |
| --- | ---: | --- | --- | --- | --- |
| P0 | 0 | Deliverable maturity taxonomy | Add canonical maturity levels and vocabulary for research note, internal draft, shareable memo, working paper, and submission-ready manuscript. | Prevents accepted task outputs from being mistaken for publication-ready deliverables. | Complete |
| P0 | 0 | Deliverable target manifest | Add a durable manifest, for example `research_ops/deliverables/deliverable_manifest.json`, with output type, target audience, intended venue, maturity target, owner, source task links, and current maturity. | Gives drafting and review tasks a declared target before prose is assembled. | Complete |
| P0 | 4 | Honest final-output naming | Rename or constrain labels like `final paper production` unless deliverable gates prove external readiness. Prefer `internal draft assembly` for TASK-0015-style work. | Removes the most misleading product signal from the coffee pilot. | Open |
| P1 | 1 | Manuscript-readiness checklist | Add structured checklist gates for related work, contribution, methods, reproducibility, figures/tables, citations, data/code availability, limitations, and final prose cleanup. | Turns editorial/product quality from tacit judgment into inspectable workflow state. | Complete |
| P1 | 1 | Venue and audience gate | Require target audience and optional venue/style profile before promoting a draft beyond internal maturity. | Aligns quality criteria with the intended reader instead of applying one generic paper standard. | Complete |
| P1 | 1 | Formal citation and bibliography requirement | Require complete bibliography artifacts and citation-style checks for working-paper and submission-ready levels. | Prevents internal source labels and informal citations from leaking into external drafts. | Complete |
| P1 | 1 | Figures and tables embedding gate | Require figures/tables to be embedded, captioned, numbered, referenced in prose, and interpreted in the narrative. | Makes exhibits part of the argument rather than loose artifacts. | Complete |
| P1 | 2 | Adversarial reviewer task type | Add a dedicated critic task with adversarial review prompts, target-output rubric, and required independence metadata. | Forces a separate challenge pass before a deliverable can claim external readiness. | Complete |
| P1 | 3 | Review-response matrix | Add a formal matrix for critique item, severity, target section, decision, required change, response rationale, and closure evidence. | Makes revision auditable and prevents major comments from being hand-waved away. | Complete |
| P1 | 4 | Dashboard maturity and editorial QA panel | Show maturity target/current level, checklist completion, critic result, response matrix status, unresolved gaps, caveats, confidence, and review independence. | Lets humans trust the deliverable status without opening raw review files. | Open |
| P2 | 1 | Related-work completeness rubric | Define coverage expectations, missing-schools checks, competing hypotheses, and source age/authority warnings by output type. | Improves scholarly positioning and reduces thin literature framing. | Complete |
| P2 | 1 | Reproducibility and data/code availability gate | Require methods detail, data availability, code availability, source manifests, and reproducibility limits for higher maturity levels. | Makes methods stronger before working-paper or submission-ready claims. | Complete |
| P2 | 2 | Review independence policy | Track whether critic review was same-agent, separate-agent, different model, human, panel, or external. Set minimum independence for each maturity level. | Makes review quality legible and prevents hidden same-agent self-approval. | Complete |
| P2 | 3 | Revision promotion blocker | Block maturity promotion when severe or critical response-matrix rows remain open unless a human explicitly accepts the risk. | Keeps adversarial review from becoming ceremonial. | Complete |
| P2 | 5 | Coffee-pilot regression fixture | Add a fixture where a task is accepted as an internal draft but fails working-paper readiness until related-work, citation, figure, and critic gates are completed. | Locks in the lesson from the coffee pilot. | Open |
| P3 | 5 | Citation-style adapters | Add optional adapters for common citation styles or external bibliography tools. | Improves publication polish, but should wait until the core maturity model exists. | Backlog |
| P3 | 5 | Venue profile library | Add reusable profiles for internal memo, consulting-style report, working paper, journal manuscript, and investor note. | Speeds setup for common deliverable types without blocking the core feature. | Backlog |

## Phase 0 Implementation Notes

Phase 0 should avoid UI first. The priority is the data contract that separates
task status from deliverable maturity.

Candidate artifacts:

- `research_ops/deliverables/deliverable_manifest.json`
- `research_ops/deliverables/deliverable_manifest.md`
- `research_ops/deliverables/readiness_checklist.json`
- `research_ops/deliverables/readiness_checklist.md`
- `research_ops/deliverables/review_response_matrix.md`
- task-level links from draft tasks to deliverable ids

Minimum manifest fields:

- `deliverable_id`
- `title`
- `output_type`
- `target_audience`
- `target_venue`
- `target_maturity`
- `current_maturity`
- `source_task_ids`
- `primary_artifact`
- `required_gates`
- `completed_gates`
- `review_independence`
- `open_gaps`
- `last_reviewed_at`

Candidate public commands:

```bash
async-research deliverable init <ops-dir> --title "<title>" --output-type working_paper --target-maturity internal_draft
async-research deliverable target <ops-dir> <DELIVERABLE-ID> --target-audience "<audience>" --target-maturity working_paper
async-research deliverable check <ops-dir> <DELIVERABLE-ID>
```

## Phase 1 Implementation Notes

Quality gates should be explicit but flexible by maturity level.

Minimum manuscript gates:

- related-work completeness
- contribution statement
- methods specification
- reproducibility and data/code availability
- figures and tables embedded, captioned, referenced, and narrated
- formal citations and bibliography
- limitations and caveats
- internal workflow/source-label cleanup
- final prose pass

Each gate should support:

- `not_required`
- `missing`
- `partial`
- `passed_with_caveats`
- `passed`
- `waived_by_human`

Waivers should require rationale and should be visible in the dashboard.

## Phase 2 Implementation Notes

The critic should be a distinct workflow role, not just another primary review.

Critic review should inspect:

- target audience and maturity fit
- novelty and contribution clarity
- related-work gaps
- methods and reproducibility weaknesses
- overclaims and unsupported causal language
- figure/table integration
- citation and bibliography quality
- prose clarity and external-reader readiness
- unresolved caveats that should block maturity promotion

Review metadata should record:

- reviewer role
- independence type
- model or human reviewer when available
- confidence
- severity distribution
- recommended maturity ceiling
- required revision rows

## Phase 3 Implementation Notes

The review-response matrix is the bridge between critique and revision.

Suggested columns:

- `critique_id`
- `source_review`
- `severity`
- `target_section`
- `issue`
- `decision`
- `required_change`
- `response_rationale`
- `owner`
- `status`
- `closure_artifact`

Allowed decisions:

- `accepted`
- `modified`
- `rejected_with_rationale`
- `deferred`
- `human_waived`

Higher maturity levels should require all critical and major rows to be closed
or explicitly waived by a human.

## Phase 4 Implementation Notes

The dashboard should make deliverable maturity impossible to misread.

Dashboard surfaces:

- deliverable maturity badge
- target audience and target maturity
- current maturity and maturity ceiling from latest critic review
- checklist status by gate
- critic review summary
- review-response matrix status
- open critical or major gaps
- citation/bibliography status
- figure/table integration status
- review independence status
- distinction between task acceptance and deliverable readiness

The dashboard should use honest labels:

- `internal draft accepted`
- `shareable memo ready`
- `working paper ready`
- `submission-ready manuscript`

It should avoid `final` unless the target maturity gates are complete.

## Phase 5 Implementation Notes

Templates should make the correct path easy for LLMs and humans.

Add templates for:

- deliverable manifest
- manuscript readiness checklist
- critic review prompt
- review-response matrix
- internal draft assembly task
- shareable memo polish task
- working paper revision task
- submission-ready manuscript cleanup task

The coffee-pilot fixture should prove this exact scenario:

1. A draft assembly task is accepted.
2. The deliverable remains `internal_draft`.
3. `deliverable check` refuses `working_paper` maturity because related work,
   citations, figure/table narration, and critic review are incomplete.
4. A critic review creates response-matrix rows.
5. The deliverable can advance only after required rows and gates close.

## Integration With Existing Roadmaps

- [Real Research Product Readiness Roadmap](./in_progress_real_research_product_readiness_roadmap.md)
  owns the immediate dashboard control-plane fixes. This roadmap owns the
  deliverable-maturity and editorial QA semantics that should be surfaced once
  artifact viewing and review visibility are reliable.
- [Knowledge Library Roadmap](./delivered_knowledge_library_roadmap.md)
  provides library/source structures that related-work completeness gates can
  reuse.
- [Hypothesis Testing Framework Roadmap](./delivered_hypothesis_testing_framework_roadmap.md)
  provides methods, experiment, and reproducibility concepts that manuscript
  gates should reference instead of duplicating.
- [Dashboard Delivery Roadmap](./delivered_dashboard_delivery_roadmap.md)
  delivered the console foundation. This roadmap adds new maturity panels and
  checklist views on top of that surface.

## Verification Plan

Every implementation slice should run:

```bash
.venv/bin/python -m unittest tests.test_doc_references
.venv/bin/python -m unittest discover -s tests
.venv/bin/async-research acceptance-suite
```

Feature-specific tests should cover:

- accepted task output does not imply deliverable readiness
- internal draft cannot be promoted to working paper with missing manuscript
  gates
- submission-ready maturity requires target venue/audience, bibliography,
  figure/table narration, data/code availability, critic review, and closed
  response matrix
- same-agent review is visible and capped below required independence where
  applicable
- dashboard read model exposes maturity, checklist, critic, and response-matrix
  status

## Open Decisions

- What exact maturity labels should ship in v1?
- Should `submission-ready manuscript` always require human approval?
- What counts as independent review: separate prompt, separate agent, separate
  model, human, or external reviewer?
- Should related-work completeness be measured from the knowledge library only,
  or allow ad hoc manuscript bibliography checks?
- How strict should citation-style validation be before external bibliography
  tooling exists?

# Roadmaps

This folder keeps project and feature roadmaps separate from packaged operator
docs. Roadmap filenames include their current lifecycle status so humans and LLM
implementers can quickly see what is live.

## Status Vocabulary

| Status | Meaning | Implementation Rule |
| --- | --- | --- |
| `Delivered` | Planned scope is implemented, tested, and pushed. | Only perform bug fixes, docs corrections, or explicitly requested follow-up work. |
| `In Progress` | The roadmap is the active execution track or umbrella track with unfinished child work. | Work one planned phase at a time and update progress before moving on. |
| `Not Started` | The roadmap is accepted but implementation has not begun. | Do not start unless the user explicitly chooses it as the next feature. |
| `Blocked` | Work should wait for a named dependency or decision. | Resolve the blocker first, or ask the user before starting implementation. |
| `Paused` | Work started but is intentionally stopped. | Resume only after the user explicitly reactivates it. |
| `Superseded` | The roadmap was replaced or merged into another track. | Do not implement from it; follow the replacement roadmap. |

Before implementing from any roadmap, read this index first. Prefer roadmaps
marked `In Progress`, or the exact roadmap the user names. Do not start
`Blocked`, `Superseded`, or `Delivered` roadmap work except bug fixes or
explicitly requested follow-ups.

## Folder Layout

Keep the root of this folder for human-facing roadmap documents and this index.
Low-level Codex automation machinery lives under
[`automation/`](./automation/README.md), including delivery templates, state
JSON, delivery logs, fix logs, and review iteration outputs.

When closing out or renaming a roadmap, follow the
[Roadmap Closeout Checklist](./automation/roadmap_closeout_checklist.md) before
marking the work delivered.

## Roadmap Index

| Roadmap | Status | Current Phase | Last Updated | Next Action | Blocked By |
| --- | --- | --- | --- | --- | --- |
| [Public Alpha Hardening Roadmap](./delivered_public_alpha_hardening_roadmap.md) | Delivered | Complete | 2026-05-09 | Maintenance fixes from dogfood and external review. | None |
| [Idea Catalog Roadmap](./delivered_idea_catalog_roadmap.md) | Delivered | V2.9 acceptance complete | 2026-05-09 | Monitor dogfood feedback and patch regressions. | None |
| [Data Foundations Roadmap](./delivered_data_foundations_roadmap.md) | Delivered | Dashboard surface complete | 2026-05-09 | Monitor workflow simulations and patch regressions. | None |
| [Research Foundations Roadmap](./delivered_research_foundations_roadmap.md) | Delivered | Complete | 2026-05-09 | Monitor foundation dogfood feedback and patch regressions. | None |
| [Knowledge Library Roadmap](./delivered_knowledge_library_roadmap.md) | Delivered | Complete | 2026-05-09 | Monitor dogfood feedback and patch regressions. | None |
| [Hypothesis Testing Framework Roadmap](./delivered_hypothesis_testing_framework_roadmap.md) | Delivered | Complete | 2026-05-10 | Monitor dogfood feedback and split adoption or V2 work from the Future Improvements Backlog when explicitly requested. | None |
| [Post-Review Operator Trust And Workflow Roadmap](./delivered_post_review_operator_trust_roadmap.md) | Delivered | Complete | 2026-05-16 | Use the Real Research Product Readiness roadmap for active dogfood issues. | None |
| [Real Research Product Readiness Roadmap](./delivered_real_research_product_readiness_roadmap.md) | Delivered | Complete | 2026-05-17 | Use the follow-on deliverable maturity/editorial QA roadmap for publication-readiness work. | None |
| [Deliverable Maturity And Editorial QA Roadmap](./delivered_deliverable_maturity_editorial_qa_roadmap.md) | Delivered | Complete | 2026-05-18 | Final branch push and automation pause. | None |
| [Autonomous Delivery Pivot Roadmap](./delivered_autonomous_delivery_pivot_roadmap.md) | Delivered | Complete | 2026-05-19 | Final branch push and automation pause. | None |
| [Future Improvements Backlog](./not_started_future_improvements_backlog_roadmap.md) | Not Started | Backlog | 2026-05-11 | Select one item and split it into a dedicated roadmap when explicitly requested. | None |
| [Operator UX And Workflow Ergonomics Roadmap](./delivered_operator_ux_workflow_ergonomics_roadmap.md) | Delivered | Complete | 2026-05-11 | Monitor operator dogfood feedback and patch regressions. | None |
| [Dashboard Delivery Roadmap](./delivered_dashboard_delivery_roadmap.md) | Delivered | Complete | 2026-05-13 | Monitor dashboard dogfood feedback and patch regressions. | None |

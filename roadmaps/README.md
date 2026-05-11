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

## Roadmap Index

| Roadmap | Status | Current Phase | Last Updated | Next Action | Blocked By |
| --- | --- | --- | --- | --- | --- |
| [Public Alpha Hardening Roadmap](./delivered_public_alpha_hardening_roadmap.md) | Delivered | Complete | 2026-05-09 | Maintenance fixes from dogfood and external review. | None |
| [Idea Catalog Roadmap](./delivered_idea_catalog_roadmap.md) | Delivered | V2.9 acceptance complete | 2026-05-09 | Monitor dogfood feedback and patch regressions. | None |
| [Data Foundations Roadmap](./delivered_data_foundations_roadmap.md) | Delivered | Dashboard surface complete | 2026-05-09 | Monitor workflow simulations and patch regressions. | None |
| [Research Foundations Roadmap](./delivered_research_foundations_roadmap.md) | Delivered | Complete | 2026-05-09 | Monitor foundation dogfood feedback and patch regressions. | None |
| [Knowledge Library Roadmap](./delivered_knowledge_library_roadmap.md) | Delivered | Complete | 2026-05-09 | Monitor dogfood feedback and patch regressions. | None |
| [Hypothesis Testing Framework Roadmap](./delivered_hypothesis_testing_framework_roadmap.md) | Delivered | Complete | 2026-05-10 | Monitor dogfood feedback and split adoption or V2 work from the Future Improvements Backlog when explicitly requested. | None |
| [Future Improvements Backlog](./not_started_future_improvements_backlog_roadmap.md) | Not Started | Backlog | 2026-05-10 | Select one item and split it into a dedicated roadmap when explicitly requested. | None |
| [Operator UX And Workflow Ergonomics Roadmap](./in_progress_operator_ux_workflow_ergonomics_roadmap.md) | In Progress | Phase 2 | 2026-05-11 | Add the one-page first-success quickstart. | None |
| [Dashboard Delivery Roadmap](./not_started_dashboard_delivery_roadmap.md) | Not Started | Slice 1 | 2026-05-09 | Start after explicit user request or dashboard track selection. | None |

# Research Foundations Roadmap

Status: Delivered
Current phase: Complete
Last updated: 2026-05-09
Next action: Monitor foundation dogfood feedback and patch regressions
Blocked by: None

Created: 2026-05-05

## Goal

Add three lightweight foundation tracks before task execution:

- build a trusted knowledge library
- build data foundations
- build and prioritize an idea catalog

These tracks should make the workflow better at choosing useful work before it
spends worker and reviewer time. They should feed the existing queue, task,
review, and accepted-evidence loop rather than replace it.

Target flow:

```text
mission
  -> knowledge library
  -> data foundations
  -> idea catalog
  -> prioritized queue
  -> worker output
  -> independent review
  -> accepted evidence / revision / rejection / human decision
```

The foundation tracks must support cold starts. A user should be able to begin
with no library, partial data notes, or a messy list of ideas. The framework
should turn missing foundations into small setup tasks rather than blocking all
progress.

## Feature Roadmaps

Implement these as separate, shippable features:

1. [Knowledge Library Roadmap](./delivered_knowledge_library_roadmap.md)
   - Create trusted source and claim memory from literature, posts, books,
     user notes, and accepted evidence.
   - Feeds discovery, planning, review, and future library update tasks.

2. [Data Foundations Roadmap](./delivered_data_foundations_roadmap.md)
   - Make data availability, access, readiness, joins, restrictions, and gaps
     explicit before expensive experiments start.
   - Extends `data_source_audit.md` with data catalog and source profiles.

3. [Idea Catalog Roadmap](./delivered_idea_catalog_roadmap.md)
   - Turn rough ideas into a managed research portfolio with scoring, dedupe,
     blockers, kill criteria, and next-task recommendations.
   - Bridges foundations into the existing queue and task loop.

## Design Rules

- Repo files remain the source of truth.
- Foundation work is reviewed before it becomes trusted memory.
- Missing foundation artifacts should warn, not fail, during early discovery.
- Experiment planning and accepted evidence should still fail closed when they
  depend on unaudited data or unsupported claims.
- Each foundation artifact should produce the next smallest useful task, not a
  large open-ended research program.
- Human-provided notes, source lists, local data paths, and rough ideas are
  first-class inputs.

## Delivered Overall Sequence

1. Delivered Knowledge Library post-MVP integrations.
2. Kept delivered data foundations and idea catalog behavior aligned with
   library references.
3. Preserved warning-only foundation gaps so missing foundations can become
   small setup tasks rather than blocking all cold starts.
4. Added dashboard surfaces for library coverage, data readiness, and idea
   backlog.

The planned foundation tracks are now delivered. Future planner, importer, or
strict gating work should start from a new roadmap or an explicit follow-up
request.

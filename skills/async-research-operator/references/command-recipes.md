# Command Recipes

Use this reference to keep command handling conservative until the full Phase 3
recipe table exists.

## Current Contract

- Prefer public `async-research` CLI commands.
- Run read-only checks before write-capable commands.
- Run dry-run before writes whenever the command supports it.
- Do not call internal helper modules unless a future reference labels the route
  as advanced and explains why no public command exists.
- Stop on missing commands, failed validators, lock conflicts, stale preflight
  hashes, human gates, credentials, paid services, network needs, or ambiguous
  public/private boundaries.

## Recipe Areas Reserved For Phase 3

- Status-only check.
- Guided framework setup.
- New workspace setup.
- Idea capture and promotion.
- Manual or LLM task creation.
- Worker loop.
- Review loop.
- Human gate handling.
- Foundation proposal loop.
- Deliverable maturity loop.
- Maintenance loop.

Do not improvise write ordering for these areas before Phase 3 documents the
exact sequence.

# Dogfood In ideas_ai

Install this package next to `ideas_ai`:

```bash
cd /Users/dzianissokalau/Documents/projects/async-research-workflow
pip install -e .
cd /Users/dzianissokalau/Documents/projects/ideas_ai
async-research schema-check research_ops
async-research readiness research_ops --dry-run
async-research health research_ops --dry-run
async-research surface validate research_ops
async-research result-acceptance research_ops/tasks/TASK-0002-idea-discovery --ops-dir research_ops
```

Do not delete the old `ideas_ai/async_research_workflow` folder until the
packaged CLI passes against live `ideas_ai/research_ops` state.

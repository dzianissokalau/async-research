# Data Source Audit Register Protocol

Created: 2026-05-02

This document implements P3-4 data source audit register and Phase 5 source
governance for the async research workflow.

## Purpose

Discovery can use plausible data paths, but experiment planning needs stronger
evidence that the data exists, can be accessed, and has known limitations. The
data source audit register keeps that readiness state separate from idea
discovery so interesting ideas do not silently become executable experiments.

## Register

The operational register lives at:

```text
research_ops/data_source_audit.md
```

Initialize it with:

```bash
python -m async_research_workflow.scripts.data_source_audit init research_ops
```

The register is a markdown table with schema version `1.0` and these fields:

| Field | Meaning |
| --- | --- |
| `source_id` | Stable identifier such as `DS-0001` |
| `source_name` | Human-readable source name |
| `url_or_domain` | File path, table, bucket, API, URL, or domain |
| `publisher_owner` | Publisher, owner, or responsible system/team |
| `source_tier` | Governance tier |
| `approval_status` | Current approval state |
| `approved_use_cases` | Uses the workflow may rely on |
| `blocked_use_cases` | Uses the workflow must not rely on |
| `freshness_window_days` | Number of days before review is stale |
| `known_limitations` | Caveats, data limits, and known failure modes |
| `citation_requirements` | Required source citation details |
| `last_reviewed` | Date in `YYYY-MM-DD` format |
| `approved_by` | Human, task, or review that approved the record |
| `review_notes` | Operational notes from the latest review |

Source tiers:

```text
tier_1_official
tier_2_institutional
tier_3_media
tier_4_untrusted
```

Approval statuses:

```text
unknown
candidate
approved
approved_with_caveats
explicitly_approved
blocked
restricted
deprecated
```

Experiment-ready statuses:

```text
approved
approved_with_caveats
```

`approved_with_caveats` is allowed for experiments only when the caveat is
explicit in the plan, leakage checks, or claim limits.

Tier rules:

- experiment planning cannot use unaudited or unapproved sources
- high-impact claims require at least one `tier_1_official` or
  `tier_2_institutional` source
- `tier_3_media` sources may provide context but cannot independently justify
  promotion or accepted evidence
- `tier_4_untrusted` sources are blocked from accepted evidence unless a human
  explicitly approves the exact use
- stale sources warn for low/context use and block experiment planning or
  accepted evidence until refreshed or explicitly approved

## Helper Commands

Add or update an entry:

```bash
python -m async_research_workflow.scripts.data_source_audit upsert \
  research_ops \
  --source-id DS-0001 \
  --approval-status approved \
  --name "UK Price Paid Data" \
  --location "bigquery:re_trends.fact_transaction" \
  --owner "research_ops" \
  --source-tier tier_1_official \
  --approved-use-cases "experiment_planning; accepted_evidence" \
  --blocked-use-cases "borrower-level mortgage terms" \
  --freshness-window-days 45 \
  --known-limitations "latest months incomplete because of registration lag" \
  --citation-requirements "cite DS-0001, source URL, extract date, and caveats" \
  --last-reviewed 2026-05-02 \
  --approved-by "source-governance review" \
  --review-notes "Loaded monthly; transaction date and price fields present."
```

Validate the register:

```bash
async-research source validate research_ops
```

Check an experiment plan or task output:

```bash
python -m async_research_workflow.scripts.data_source_audit check-experiment \
  research_ops \
  research_ops/tasks/TASK-0007-experiment-plan/worker_output.md
```

Check an accepted-evidence claim:

```bash
python -m async_research_workflow.scripts.data_source_audit check-claim \
  research_ops \
  research_ops/tasks/TASK-0007/worker_output.md \
  --use-case accepted_evidence \
  --claim-impact high
```

Explain one source decision:

```bash
python -m async_research_workflow.scripts.data_source_audit explain \
  research_ops \
  DS-0001 \
  --use-case experiment_planning
```

Report freshness warnings:

```bash
async-research source freshness research_ops
```

The check fails closed when:

- the register is missing or malformed
- the plan references no `DS-0000` style source IDs
- a referenced source ID is missing from the register
- a referenced source is not `approved` or `approved_with_caveats`
- only Tier 3 contextual sources support an experiment or accepted-evidence
  claim
- a source is stale for experiment planning or accepted evidence
- a high-impact claim lacks Tier 1 or Tier 2 support

## Workflow Rule

Ideas may enter discovery with plausible data paths:

```text
required_data = ["EPC certificates", "Price Paid Data", "postcode geography"]
```

But experiment plans must reference audited entries:

```text
Data audit refs: DS-0001, DS-0004
```

If the data path is plausible but unaudited, the planner should create a
`data_readiness` task before an `experiment_plan` task. A data-readiness worker
may update `data_source_audit.md` with `candidate`, `approved`,
`approved_with_caveats`, `blocked`, `restricted`, or `deprecated`. Automation
uses exact use-case tokens such as `experiment_planning`, `accepted_evidence`,
and `context`, so human-readable caveats should be added after those tokens
rather than replacing them.

## Acceptance Checks

P3-4 and Phase 5 are implemented when:

- `research_ops/data_source_audit.md` can be initialized and validated
- invalid audit statuses fail validation
- experiment plans without data audit refs fail closed
- experiment plans referencing missing or blocked data fail closed
- experiment plans referencing ready audit entries pass
- planner, worker, and reviewer prompts require the experiment audit check
- unapproved sources block promotion to experiment planning
- source freshness warnings appear in health reports and weekly digests
- accepted evidence records cite audited source IDs
- the system can explain why a source was allowed or blocked

# Data Profile Contract

Dataset profiles live in this directory and use filenames such as `DS-0001.md`.
`DS-0000.md` is the template shape; do not treat it as an active source profile.

Each active profile must point to exactly one row in `../../data_source_audit.md`.
The canonical profile ID comes from both the filename and the internal
`source_id` line. They must match.

## Required Shape

```markdown
# DS-0000: Source Name

source_id: DS-0000
source_name: Source Name
profile_status: draft
audit_register: ../../data_source_audit.md
audit_status: candidate
reviewed_date: YYYY-MM-DD
reviewer: name-or-task-id

## Location And Access

- location:
- access_method:
- access_notes:

## Owner Or Publisher

- owner_or_publisher:
- contact_or_docs:

## Use Policy

- approved_use_cases:
- blocked_use_cases:
- privacy_or_licensing_restrictions:

## Coverage And Grain

- fields:
- grain:
- geography:
- time_coverage:
- refresh_cadence:

## Quality And Limitations

- known_limitations:
- missingness_or_bias_risks:
- freshness_notes:

## Join Keys And Risks

- join_keys:
- plausible_joins:
- join_risks:

## Review Notes

- readiness_summary:
- recommended_next_task:
- kill_reason_if_unusable:
```

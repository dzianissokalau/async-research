# Reviewer Registry

| reviewer_role | default_model_or_tool | prompt_version | framework_versions | isolation_required | notes |
| --- | --- | --- | --- | --- | --- |
| primary | Codex or frontier/standard model | primary_reviewer_v1.0 | result_acceptance_v1.0 | no | First-pass review for low-risk outputs. |
| methodology | Claude, Codex, or comparable methodology reviewer | methodology_reviewer_v1.0 | result_acceptance_v1.0 | yes | Use for experiment plans and methodology-sensitive outputs. |
| skeptic | Gemini, Claude, Codex, or comparable independent skeptic | skeptic_reviewer_v1.0 | result_acceptance_v1.0 | yes | Use for adversarial source/claim checks. |
| aggregator | deterministic script plus optional narrative model | review_aggregator_v1.0 | review_aggregation_v1.0, result_acceptance_v1.0 | yes | Deterministic aggregation computes route; narrative model may only summarize. |

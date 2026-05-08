# Join Map

Record plausible joins between governed datasets and the caveats that make each
join safe or unsafe.

| join_id | left_source_id | right_source_id | join_keys | grain_after_join | status | caveats |
| --- | --- | --- | --- | --- | --- | --- |

## Notes

Use one row per join path. Every join should state caveats before it is used in
an experiment plan.

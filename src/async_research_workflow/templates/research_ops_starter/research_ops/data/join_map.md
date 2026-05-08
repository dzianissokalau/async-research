# Join Map

Plausible joins and caveats for the real-estate worked example.

| join_id | left_source_id | right_source_id | join_keys | grain_after_join | status | caveats |
| --- | --- | --- | --- | --- | --- | --- |
| JOIN-0001 | DS-0001 | DS-0002 | transaction month to monthly rate period | transaction with monthly macro context | plausible_with_caveats | mortgage-rate series are aggregate context, not borrower-level terms |
| JOIN-0002 | DS-0001 | DS-0003 | geography and period, after documented aggregation | geography-period context | plausible_with_caveats | ONS local estimates and HPI/rent series are contextual; avoid transaction-level causal claims without a separate design |

## Notes

Every experiment plan should restate join caveats and leakage controls before
using these paths.

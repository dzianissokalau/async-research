# Data Catalog

Human-readable inventory of governed datasets in the real-estate worked example.
The governance source of truth stays in `../data_source_audit.md`.

| source_id | source_name | approval_status | profile_path | grain | geography | time_coverage | access_summary | limitations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DS-0001 | HM Land Registry Price Paid Data | approved_with_caveats | data/profiles/DS-0001.md | transaction | England and Wales | sale records with publication lag | public download and linked data page | latest periods incomplete; address matching and licensing need care |
| DS-0002 | Bank of England Bank Rate, effective mortgage rates, and quoted household mortgage rates | approved_with_caveats | data/profiles/DS-0002.md | monthly aggregate series | UK | monthly series and official rate history | public statistics page | aggregate rates only; exact series IDs must be fixed before analysis |
| DS-0003 | ONS private rent and house price statistics | approved_with_caveats | data/profiles/DS-0003.md | official statistics release and dataset series | UK with local breakdowns where published | latest official release and historical series | public bulletin and data links | provisional/revised periods and local volatility require caveats |

## Notes

Treat this catalog as planning context. Experiment plans must still cite approved
`DS-*` references and run source-governance checks.

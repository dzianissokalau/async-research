# Climate Coffee Economics Source Policy

This policy governs the packaged climate/coffee economics benchmark. Default
fixtures are offline and mocked. Live API calls, browsing, credentials, paid
services, publication claims, and private buyer data require explicit
task-contract permission plus a human gate.

## Allowed Source Classes

| Source class | Default benchmark use | Examples |
| --- | --- | --- |
| `official_api` | Mocked fixture only | ICO indicator endpoint, World Bank Climate API, FAOSTAT tables |
| `authoritative_downloadable_data` | Fixture snapshot only | ICO monthly prices, USDA coffee production reports, NOAA climate summaries |
| `institutional_report` | Fixture snapshot only | International Coffee Organization reports, national agriculture agency reports |
| `private_local_file` | Redacted local fixture only | Buyer memo, internal sourcing note, local CSV |
| `computed_artifact` | Local deterministic computation | Yield-stress table, price-sensitivity check |

## Preferred Source Order

1. Official APIs or downloadable tables when the task contract allows that
   source class.
2. Institutional reports with named publisher, retrieval date, license/use
   metadata, and freshness window.
3. Private/local files only when the brief permits private data and the output
   marks any public-claim limits.
4. Web pages only when a structured source is unavailable and browser fallback
   is allowed with snapshots.

## Fail-Closed Rules

- Missing license/use metadata caps claim strength and blocks acceptance for
  material claims.
- Missing source date, retrieval date, or freshness window makes the evidence
  stale until reviewed.
- Private/local evidence cannot support public claims unless the brief records
  an explicit publication permission.
- External Deep Research-style outputs cannot be used in a head-to-head report
  unless the artifact stores product name, model/version where available,
  prompt, capture date, allowed-use basis, and redaction status.
- A benchmark report may say the candidate wins only on metrics backed by the
  packaged run artifacts. All other comparisons remain unproven.

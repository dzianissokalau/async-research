# Claim And Citation Verification

Created: 2026-05-20

Claim and citation verification is the Phase 4 gate between runtime evidence
objects and accepted or publication-oriented outputs. It is deterministic and
offline by default: it reads explicit claim objects, runtime evidence objects,
and local snapshots under `research_ops/`.

## Claim Object

Each claim object records:

- `claim_id`
- `text`
- `claim_type`
- `strength`
- `required_support_level`
- `evidence_refs`
- `citation_refs`
- `verification_status`
- `failure_reason`

Supported verifier outcomes are `supported`, `weakly_supported`,
`unsupported`, `contradicted`, `stale`, and `unverifiable`.

## Evidence Mapping

Evidence and citation refs map claims to runtime evidence objects by evidence
ID, source URI, span reference, quote or paraphrase status, source freshness
status, and optional computation-artifact status. Quoted support must appear in
the local evidence snapshot. Numeric claims require a computation artifact such
as a `code_execute` runtime evidence object.

The verifier does not fetch live sources. Missing evidence, missing snapshots,
stale source status, contradicted support, and absent computation artifacts are
recorded as local verifier outcomes.

## Result Acceptance

`result_acceptance.json` now includes a `claim_verification` report when
explicit claim objects are present or when a task requires claim verification.
Accepted outputs fail closed for unsupported, contradicted, or unverifiable
material claims. Weakly supported and stale claims cap maximum claim strength,
and contradictions create a skeptic-review follow-up.

When ledgers are updated, claim status rows are written to:

```text
research_ops/claim_verification_ledger.md
```

## Deliverable Maturity

Working-paper and submission-ready deliverables require claim and citation
verification. Unresolved citation gaps block readiness, and the deliverable
read model surfaces claim-verification status, unresolved counts, and the
maximum supported claim strength. Accepted source tasks remain evidence only;
they do not make a publication-oriented draft ready without verified citations.

## Offline Fixture Shape

A minimal task claim artifact can live at:

```text
research_ops/tasks/TASK-0001-example/artifacts/claim_verification.json
```

Example:

```json
{
  "claims": [
    {
      "claim_id": "CLM-0001",
      "text": "The fixture source reports a 12 percent increase.",
      "claim_type": "empirical",
      "strength": "moderate",
      "required_support_level": "direct",
      "evidence_refs": [
        {
          "evidence_id": "EVID-000001",
          "span_ref": "SPAN-0001",
          "quote_or_paraphrase_status": "quote",
          "quote": "12 percent increase"
        }
      ],
      "citation_refs": [
        "EVID-000001#SPAN-0001"
      ]
    }
  ]
}
```

The referenced evidence object must already exist in
`research_ops/runtime/evidence_objects.jsonl` with a valid local snapshot.

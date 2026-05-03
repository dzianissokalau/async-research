#!/usr/bin/env python3
"""Emit reviewer JSON templates with required version metadata."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Iterable


SUCCESS = 0
ROLE_PROMPT_VERSIONS = {
    "primary": "primary_reviewer_v1.0",
    "methodology": "methodology_reviewer_v1.0",
    "skeptic": "skeptic_reviewer_v1.0",
}
DECISIONS = {"accept", "accept_with_caveats", "needs_revision", "needs_human", "reject"}
CLAIM_STRENGTHS = {"none", "weak", "suggestive", "moderate", "strong"}


def review_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "reviewer_role": args.role,
        "decision": args.decision,
        "claim_strength": args.claim_strength,
        "confidence": args.confidence,
        "prompt_version": ROLE_PROMPT_VERSIONS[args.role],
        "framework_versions": {
            "result_acceptance": "result_acceptance_v1.0",
        },
        "main_concerns": args.concern or [],
        "required_followups": args.followup or [],
        "evidence_gaps": args.evidence_gap or [],
    }


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a fenced JSON review template.")
    parser.add_argument("role", choices=sorted(ROLE_PROMPT_VERSIONS))
    parser.add_argument("--decision", choices=sorted(DECISIONS), default="accept_with_caveats")
    parser.add_argument("--claim-strength", choices=sorted(CLAIM_STRENGTHS), default="suggestive")
    parser.add_argument("--confidence", type=float, default=0.8)
    parser.add_argument("--concern", action="append", help="Main concern. Repeat for multiple concerns.")
    parser.add_argument("--followup", action="append", help="Required follow-up. Repeat for multiple follow-ups.")
    parser.add_argument("--evidence-gap", action="append", help="Evidence gap. Repeat for multiple gaps.")
    parser.add_argument("--raw-json", action="store_true", help="Emit JSON only, without Markdown fence.")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    payload = review_payload(args)
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.raw_json:
        print(text)
    else:
        print("```json")
        print(text)
        print("```")
    return SUCCESS


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

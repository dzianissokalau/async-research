#!/usr/bin/env python3
"""Evaluate claim gates for completed analysis-run artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Optional

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.validate_json_artifact import load_json, validate


SUCCESS = 0
VALIDATION_FAILED = 2
MALFORMED = 4

SCHEMA_VERSION = "1.0"
FRAMEWORK_VERSION = "analysis_claim_gates_v1.0"
CLAIM_GATE_SCHEMA = schema_path("analysis_claim_gates.schema.json")

CLAIM_ORDER = {
    "none": 0,
    "weak": 1,
    "suggestive": 2,
    "moderate": 3,
    "strong": 4,
}
CLAIM_BY_SCORE = {score: claim for claim, score in CLAIM_ORDER.items()}
CLAIM_TYPES = {
    "descriptive",
    "associative",
    "predictive",
    "causal",
    "probabilistic",
    "other",
}
CLAIM_TYPE_ALIASES = {
    "association": "associative",
    "correlational": "associative",
    "forecast": "predictive",
    "forecasting": "predictive",
    "prediction": "predictive",
    "probability": "probabilistic",
    "calibrated_risk": "probabilistic",
    "calibrated-risk": "probabilistic",
    "risk": "probabilistic",
}
IDENTITY_FIELDS = ["run_id", "experiment_plan_id", "task_id"]
IDENTITY_SENTINELS = {
    "run_id": "RUN-0000",
    "experiment_plan_id": "EXP-0000",
    "task_id": "TASK-0000",
}
ARTIFACT_SCHEMAS = {
    "metrics": "analysis_metrics.schema.json",
    "diagnostics": "analysis_diagnostics.schema.json",
    "robustness": "analysis_robustness_checks.schema.json",
    "claim_gates": "analysis_claim_gates.schema.json",
}
DIAGNOSTIC_SECTIONS = [
    "missingness_checks",
    "join_quality_checks",
    "leakage_checks",
    "segment_diagnostics",
    "calibration_checks",
    "uncertainty_checks",
]
OUT_OF_SAMPLE_SPLIT_ROLES = {"validation", "test", "holdout", "backtest"}
CAUSAL_CHECK_FAMILIES = {"placebo", "falsification", "sensitivity", "alternative_specification"}
CAUSAL_LANGUAGE_PATTERNS = [
    r"\bcaus(?:e|es|ed|al|ation)\b",
    r"\bimpact(?:s|ed|ing)?\b",
    r"\beffect(?:s)?\b",
    r"\bdriv(?:e|es|en|ing)\b",
    r"\bleads? to\b",
    r"\battribut(?:e|es|ed|ion)\b",
]
PROBABILITY_LANGUAGE_PATTERNS = [
    r"\bprobab",
    r"\bcalibrat",
    r"\brisk\b",
    r"\buncertain",
    r"\bconfidence interval\b",
    r"\bcredible interval\b",
    r"\bchance\b",
]


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


def text_blob(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(f"{key} {text_blob(item)}" for key, item in value.items())
    if isinstance(value, list):
        return " ".join(text_blob(item) for item in value)
    if value is None:
        return ""
    return str(value)


def claim_text(summary: dict[str, Any]) -> str:
    return " ".join(
        str(summary.get(field, ""))
        for field in ["claim", "claim_type", "primary_metric", "candidate_results"]
        if summary.get(field) is not None
    )


def matches_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) is not None for pattern in patterns)


def has_causal_language(summary: dict[str, Any]) -> bool:
    return matches_any(claim_text(summary), CAUSAL_LANGUAGE_PATTERNS)


def has_probability_language(summary: dict[str, Any]) -> bool:
    return matches_any(claim_text(summary), PROBABILITY_LANGUAGE_PATTERNS)


def read_json_object(path: Path) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"JSON artifact is not an object: {path}")
    return payload


def extract_fenced_json(text: str) -> dict[str, Any]:
    for match in re.finditer(r"```(?:json|[a-z_]+)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE):
        candidate = match.group(1).strip()
        if not candidate.startswith("{"):
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("no JSON object or fenced JSON block found")


def load_artifact(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        return read_json_object(path)
    try:
        return extract_fenced_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read artifact {path}: {exc}") from exc


def schema_errors(payload: dict[str, Any], schema_name: str) -> list[dict[str, str]]:
    schema = load_json(schema_path(schema_name))
    if not isinstance(schema, dict):
        return [{"path": "$", "message": f"schema is not an object: {schema_name}"}]
    return [error.to_dict() for error in validate(payload, schema)]


def normalize_claim_type(summary: dict[str, Any]) -> str:
    raw = str(summary.get("claim_type", "")).strip().lower().replace(" ", "_")
    if raw in CLAIM_TYPES:
        return raw
    if raw in CLAIM_TYPE_ALIASES:
        return CLAIM_TYPE_ALIASES[raw]
    if has_causal_language(summary):
        return "causal"
    if has_probability_language(summary):
        return "probabilistic"
    return "other"


def claim_type_gate(summary: dict[str, Any], claim_type: str) -> dict[str, Any]:
    raw = str(summary.get("claim_type", "")).strip().lower().replace(" ", "_")
    if not raw:
        return gate_result(
            "claim_type_classified",
            "reject",
            "none",
            "result summary claim_type is required for claim gates",
        )
    if raw in CLAIM_TYPES or raw in CLAIM_TYPE_ALIASES:
        if claim_type == "other":
            return gate_result(
                "claim_type_classified",
                "cap",
                "weak",
                "other claims require reviewer classification before stronger evidence can be accepted",
            )
        return gate_result("claim_type_classified", "pass", "strong", f"claim_type is classified as {claim_type}")
    return gate_result(
        "claim_type_classified",
        "reject",
        "none",
        f"unknown claim_type {summary.get('claim_type')!r}; claim gates fail closed",
        [f"allowed claim types: {', '.join(sorted(CLAIM_TYPES))}"],
    )


def canonical_identity(summary: dict[str, Any], trusted_identity: Optional[dict[str, str]] = None) -> dict[str, str]:
    trusted_identity = trusted_identity or {}
    identity: dict[str, str] = {}
    for field in IDENTITY_FIELDS:
        value = trusted_identity.get(field) if nonempty_text(trusted_identity.get(field)) else summary.get(field)
        identity[field] = str(value) if nonempty_text(value) else IDENTITY_SENTINELS[field]
    return identity


def identity_gates(
    summary: dict[str, Any],
    artifacts: dict[str, Optional[dict[str, Any]]],
    trusted_identity: Optional[dict[str, str]] = None,
) -> list[dict[str, Any]]:
    trusted_identity = trusted_identity or {}
    gates: list[dict[str, Any]] = []
    missing_summary = [
        field for field in IDENTITY_FIELDS if not nonempty_text(summary.get(field)) and not nonempty_text(trusted_identity.get(field))
    ]
    if missing_summary:
        gates.append(
            gate_result(
                "claim_identity_present",
                "reject",
                "none",
                "result summary is missing required provenance identifiers",
                [f"missing fields: {', '.join(missing_summary)}"],
            )
        )
    else:
        gates.append(gate_result("claim_identity_present", "pass", "strong", "result summary provenance identifiers are present"))

    identity = canonical_identity(summary, trusted_identity)
    for field, trusted_value in trusted_identity.items():
        if (
            field in IDENTITY_FIELDS
            and nonempty_text(trusted_value)
            and nonempty_text(summary.get(field))
            and str(summary[field]) != str(trusted_value)
        ):
            gates.append(
                gate_result(
                    "claim_identity_matches_context",
                    "reject",
                    "none",
                    "result summary provenance does not match trusted caller context",
                    [f"{field}: summary={summary[field]!r}, trusted={trusted_value!r}"],
                )
            )

    mismatches: list[str] = []
    for name, payload in artifacts.items():
        if payload is None:
            continue
        for field in IDENTITY_FIELDS:
            artifact_value = payload.get(field)
            if not nonempty_text(artifact_value):
                mismatches.append(f"{name}.{field} is missing")
            elif str(artifact_value) != identity[field]:
                mismatches.append(f"{name}.{field}={artifact_value!r} does not match {identity[field]!r}")
    if mismatches:
        gates.append(
            gate_result(
                "artifact_identity_matches_claim",
                "reject",
                "none",
                "analysis artifacts must share run_id, experiment_plan_id, and task_id with the claim summary",
                mismatches,
            )
        )
    else:
        gates.append(gate_result("artifact_identity_matches_claim", "pass", "strong", "artifact identities match the claim summary"))
    return gates


def requested_claim_strength(summary: dict[str, Any]) -> str:
    value = str(summary.get("claim_strength", "none")).strip().lower()
    return value if value in CLAIM_ORDER else "none"


def gate_result(
    gate: str,
    status: str,
    max_claim_strength: str,
    reason: str,
    evidence: Optional[list[str]] = None,
) -> dict[str, Any]:
    return {
        "gate": gate,
        "status": status,
        "max_claim_strength": max_claim_strength,
        "reason": reason,
        "evidence": evidence or [],
    }


def artifact_schema_gates(artifacts: dict[str, Optional[dict[str, Any]]]) -> list[dict[str, Any]]:
    gates: list[dict[str, Any]] = []
    for name, payload in artifacts.items():
        if payload is None:
            continue
        errors = schema_errors(payload, ARTIFACT_SCHEMAS[name])
        if errors:
            gates.append(
                gate_result(
                    f"{name}_schema_valid",
                    "reject",
                    "none",
                    f"{name} artifact fails its schema",
                    [f"{error['path']}: {error['message']}" for error in errors],
                )
            )
        else:
            gates.append(gate_result(f"{name}_schema_valid", "pass", "strong", f"{name} artifact schema is valid"))
    return gates


def predictive_gate(metrics: Optional[dict[str, Any]]) -> dict[str, Any]:
    if metrics is None:
        return gate_result(
            "predictive_validation_and_baseline",
            "reject",
            "none",
            "predictive claims require metrics with validation splits and baseline comparison",
            ["metrics artifact missing"],
        )

    missing: list[str] = []
    for field in ["baseline_metrics", "candidate_metrics", "validation_metrics", "baseline_comparisons", "validation_splits"]:
        if not nonempty_list(metrics.get(field)):
            missing.append(field)

    passed_baselines = [
        item
        for item in metrics.get("baseline_comparisons", [])
        if isinstance(item, dict) and item.get("passed") is True
    ]
    validation_splits = [
        item
        for item in metrics.get("validation_splits", [])
        if isinstance(item, dict) and str(item.get("split_role", "")).lower() in OUT_OF_SAMPLE_SPLIT_ROLES
    ]

    if missing or not passed_baselines or not validation_splits:
        evidence = []
        if missing:
            evidence.append(f"missing or empty fields: {', '.join(missing)}")
        if not passed_baselines:
            evidence.append("no passed baseline comparison")
        if not validation_splits:
            evidence.append("no out-of-sample validation/test/holdout/backtest split")
        return gate_result(
            "predictive_validation_and_baseline",
            "reject",
            "none",
            "predictive claims are blocked without out-of-sample validation and baseline comparison",
            evidence,
        )

    return gate_result(
        "predictive_validation_and_baseline",
        "pass",
        "moderate",
        "predictive validation and baseline comparison are present; predictive claims remain capped at moderate",
        [
            f"passed baseline comparisons: {len(passed_baselines)}",
            f"out-of-sample splits: {len(validation_splits)}",
        ],
    )


def predictive_leakage_gate(diagnostics: Optional[dict[str, Any]]) -> dict[str, Any]:
    if diagnostics is None:
        return gate_result(
            "predictive_leakage_checks",
            "reject",
            "none",
            "predictive claims require diagnostics with leakage checks",
            ["diagnostics artifact missing"],
        )

    rows = [item for item in diagnostics.get("leakage_checks", []) if isinstance(item, dict)]
    if not rows:
        return gate_result(
            "predictive_leakage_checks",
            "reject",
            "none",
            "predictive claims require at least one leakage check row",
        )

    statuses = [str(row.get("status", "")).lower() for row in rows]
    if "fail" in statuses:
        return gate_result(
            "predictive_leakage_checks",
            "reject",
            "none",
            "failed leakage checks block predictive claims",
            [f"statuses: {', '.join(statuses)}"],
        )
    if "pass" not in statuses:
        if "warn" in statuses:
            return gate_result(
                "predictive_leakage_checks",
                "cap",
                "suggestive",
                "warning-only leakage checks cap predictive claims at suggestive",
                [f"statuses: {', '.join(statuses)}"],
            )
        return gate_result(
            "predictive_leakage_checks",
            "reject",
            "none",
            "predictive claims require an applicable passing leakage check",
            [f"statuses: {', '.join(statuses)}"],
        )
    return gate_result(
        "predictive_leakage_checks",
        "pass",
        "moderate",
        "predictive leakage checks include a passing row",
        [f"statuses: {', '.join(statuses)}"],
    )


def associative_gate(summary: dict[str, Any], metrics: Optional[dict[str, Any]]) -> dict[str, Any]:
    has_metrics_comparison = isinstance(metrics, dict) and nonempty_list(metrics.get("baseline_comparisons"))
    has_summary_comparison = nonempty_text(summary.get("baseline_results"))
    if has_metrics_comparison or has_summary_comparison:
        return gate_result("associative_comparison_context", "pass", "strong", "comparison context is present")
    return gate_result(
        "associative_comparison_context",
        "cap",
        "weak",
        "associative claims without comparison context are capped at weak",
    )


def summary_limitations_gate(summary: dict[str, Any]) -> dict[str, Any]:
    if nonempty_list(summary.get("limitations")):
        return gate_result("claim_limitations_declared", "pass", "strong", "claim limitations are declared")
    return gate_result(
        "claim_limitations_declared",
        "cap",
        "weak",
        "claims without explicit limitations are capped at weak",
    )


def diagnostic_quality_gate(diagnostics: Optional[dict[str, Any]]) -> dict[str, Any]:
    if diagnostics is None:
        return gate_result(
            "diagnostic_quality",
            "cap",
            "weak",
            "diagnostics artifact is missing; claim strength is capped at weak",
        )

    statuses: list[str] = []
    for section in DIAGNOSTIC_SECTIONS:
        for item in diagnostics.get(section, []):
            if isinstance(item, dict):
                status = str(item.get("status", "")).lower()
                if status:
                    statuses.append(status)

    if "fail" in statuses:
        return gate_result(
            "diagnostic_quality",
            "cap",
            "weak",
            "failed diagnostics cap the claim at weak",
            [f"statuses: {', '.join(statuses)}"],
        )
    if "warn" in statuses:
        return gate_result(
            "diagnostic_quality",
            "cap",
            "suggestive",
            "warning diagnostics cap the claim at suggestive",
            [f"statuses: {', '.join(statuses)}"],
        )
    return gate_result("diagnostic_quality", "pass", "strong", "diagnostics do not cap the claim")


def probability_gate(diagnostics: Optional[dict[str, Any]]) -> dict[str, Any]:
    if diagnostics is None:
        return gate_result(
            "probability_calibration_or_uncertainty",
            "reject",
            "none",
            "probability claims require calibration or uncertainty diagnostics",
            ["diagnostics artifact missing"],
        )

    rows: list[dict[str, Any]] = []
    for section in ["calibration_checks", "uncertainty_checks"]:
        rows.extend(item for item in diagnostics.get(section, []) if isinstance(item, dict))

    applicable = [row for row in rows if row.get("applicable") is True]
    if not applicable:
        return gate_result(
            "probability_calibration_or_uncertainty",
            "reject",
            "none",
            "probability claims are blocked without applicable calibration or uncertainty checks",
        )

    statuses = {str(row.get("status", "")).lower() for row in applicable}
    if not statuses or "not_applicable" in statuses:
        return gate_result(
            "probability_calibration_or_uncertainty",
            "reject",
            "none",
            "applicable calibration or uncertainty checks cannot be marked not_applicable",
            [f"statuses: {', '.join(sorted(statuses))}"],
        )
    if "fail" in statuses:
        return gate_result(
            "probability_calibration_or_uncertainty",
            "reject",
            "none",
            "failed calibration or uncertainty diagnostics block probability claims",
            [f"statuses: {', '.join(sorted(statuses))}"],
        )
    if "warn" in statuses:
        return gate_result(
            "probability_calibration_or_uncertainty",
            "cap",
            "suggestive",
            "warning calibration or uncertainty diagnostics cap probability claims at suggestive",
            [f"statuses: {', '.join(sorted(statuses))}"],
        )
    return gate_result(
        "probability_calibration_or_uncertainty",
        "pass",
        "strong",
        "applicable calibration or uncertainty diagnostics support the probability claim",
    )


def causal_identification_gate(summary: dict[str, Any], robustness: Optional[dict[str, Any]]) -> dict[str, Any]:
    summary_tests = nonempty_list(summary.get("identification_tests"))
    checks = []
    if isinstance(robustness, dict):
        checks = [
            item
            for item in robustness.get("planned_checks", [])
            if isinstance(item, dict)
            and str(item.get("check_family", "")).lower() in CAUSAL_CHECK_FAMILIES
        ]
    blocking = [
        item
        for item in checks
        if str(item.get("status", "")).lower() == "fail"
        or str(item.get("decision_impact", "")).lower() == "blocks_claim"
    ]
    requires_human = [
        item
        for item in checks
        if str(item.get("decision_impact", "")).lower() == "requires_human"
    ]
    supporting = [
        item
        for item in checks
        if str(item.get("status", "")).lower() in {"pass", "warn"}
        and str(item.get("decision_impact", "")).lower() != "blocks_claim"
    ]

    assumption_text = text_blob(
        [
            summary.get("identification_assumptions"),
            summary.get("limitations"),
            robustness.get("summary") if isinstance(robustness, dict) else "",
            robustness.get("limitations") if isinstance(robustness, dict) else "",
        ]
    ).lower()
    has_assumptions = nonempty_list(summary.get("identification_assumptions")) or any(
        token in assumption_text for token in ["assumption", "identification", "ignorability", "parallel trends", "exclusion"]
    )

    if blocking:
        return gate_result(
            "causal_identification_tests",
            "reject",
            "none",
            "failed or blocking causal identification checks block causal claims",
            [
                f"{item.get('name', 'causal check')}: status={item.get('status')}, decision_impact={item.get('decision_impact')}"
                for item in blocking
            ],
        )
    if requires_human:
        return gate_result(
            "causal_identification_tests",
            "needs_human",
            "strong",
            "causal identification checks require human review",
            [
                f"{item.get('name', 'causal check')}: decision_impact={item.get('decision_impact')}"
                for item in requires_human
            ],
        )
    if not summary_tests and not supporting:
        return gate_result(
            "causal_identification_tests",
            "reject",
            "none",
            "causal language is blocked without identification, placebo, or falsification tests",
        )
    if not has_assumptions:
        return gate_result(
            "causal_identification_tests",
            "reject",
            "none",
            "causal claims require explicit identification assumptions",
        )
    if any(str(item.get("status", "")).lower() == "warn" for item in supporting):
        return gate_result(
            "causal_identification_tests",
            "cap",
            "moderate",
            "warning identification checks cap causal claims at moderate",
            [f"supporting checks: {len(supporting)}"],
        )
    return gate_result(
        "causal_identification_tests",
        "pass",
        "strong",
        "causal identification tests and assumptions are present",
        [f"supporting checks: {len(supporting)}", f"summary tests declared: {summary_tests}"],
    )


def robustness_decision_impact_gate(robustness: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not isinstance(robustness, dict):
        return None
    checks = [item for item in robustness.get("planned_checks", []) if isinstance(item, dict)]
    blockers = [item for item in checks if str(item.get("decision_impact", "")).lower() == "blocks_claim"]
    if blockers:
        return gate_result(
            "robustness_decision_impact",
            "reject",
            "none",
            "robustness checks marked blocks_claim block result acceptance",
            [f"{item.get('name', 'robustness check')}: {item.get('result', '')}" for item in blockers],
        )
    human_required = [item for item in checks if str(item.get("decision_impact", "")).lower() == "requires_human"]
    if human_required:
        return gate_result(
            "robustness_decision_impact",
            "needs_human",
            "strong",
            "robustness checks require human review",
            [f"{item.get('name', 'robustness check')}: {item.get('result', '')}" for item in human_required],
        )
    return gate_result("robustness_decision_impact", "pass", "strong", "no robustness decision impacts block the claim")


def robustness_support_gate(requested_strength: str, robustness: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if requested_strength != "strong":
        return None

    if not isinstance(robustness, dict):
        return gate_result(
            "strong_claim_robustness",
            "cap",
            "moderate",
            "strong claims require clear robustness evidence",
            ["robustness artifact missing"],
        )

    summary = robustness.get("summary") if isinstance(robustness.get("summary"), dict) else {}
    supporting = [
        item
        for item in robustness.get("planned_checks", [])
        if isinstance(item, dict)
        and str(item.get("status", "")).lower() == "pass"
        and str(item.get("decision_impact", "")).lower() == "supports_claim"
    ]
    if summary.get("overall_status") == "pass" and supporting:
        return gate_result(
            "strong_claim_robustness",
            "pass",
            "strong",
            "clear robustness evidence supports a strong claim",
            [f"supporting robustness checks: {len(supporting)}"],
        )
    return gate_result(
        "strong_claim_robustness",
        "cap",
        "moderate",
        "strong claims require pass-status robustness checks that support the claim",
    )


def human_gate(summary: dict[str, Any], requested_strength: str) -> tuple[dict[str, Any], dict[str, Any]]:
    public_or_high_stakes = (
        summary.get("public_or_high_stakes") is True
        or summary.get("public_use") is True
        or summary.get("high_stakes") is True
    )
    strong_claim = requested_strength == "strong"
    methodology_review_present = (
        summary.get("methodology_review_present") is True
        or nonempty_text(summary.get("methodology_review_id"))
    )
    required = public_or_high_stakes or strong_claim
    satisfied = bool(summary.get("human_approval_present") is True or nonempty_text(summary.get("human_approval_id")))

    if strong_claim and not methodology_review_present:
        gate = gate_result(
            "human_approval_required",
            "needs_human",
            "strong",
            "strong claims require human approval and methodology review",
        )
        return gate, {"required": True, "satisfied": False, "reason": gate["reason"]}

    if not required:
        gate = gate_result("human_approval_required", "pass", "strong", "human approval is not required")
        return gate, {"required": False, "satisfied": True, "reason": "not required"}
    if satisfied:
        gate = gate_result("human_approval_required", "pass", "strong", "human approval is recorded")
        return gate, {"required": True, "satisfied": True, "reason": "human approval recorded"}

    reason = (
        "public or high-stakes claims require human approval"
        if public_or_high_stakes
        else "strong claims require human approval"
    )
    gate = gate_result("human_approval_required", "needs_human", "strong", reason)
    return gate, {"required": True, "satisfied": False, "reason": reason}


def choose_decision(
    requested_strength: str,
    gates: list[dict[str, Any]],
) -> tuple[str, str, str, list[str]]:
    cap_score = CLAIM_ORDER["strong"]
    reasons: list[str] = []
    rejected = False
    needs_human = False

    for gate in gates:
        max_strength = str(gate.get("max_claim_strength", "strong"))
        if max_strength in CLAIM_ORDER:
            cap_score = min(cap_score, CLAIM_ORDER[max_strength])
        status = gate.get("status")
        if status == "reject":
            rejected = True
            reasons.append(str(gate.get("reason", "")))
        elif status == "needs_human":
            needs_human = True
            reasons.append(str(gate.get("reason", "")))
        elif status == "cap":
            reasons.append(str(gate.get("reason", "")))

    max_strength = CLAIM_BY_SCORE[cap_score]
    if rejected:
        return "rejected", "reject", max_strength, [reason for reason in reasons if reason]
    if needs_human:
        return "needs_human", "needs_human", max_strength, [reason for reason in reasons if reason]
    if CLAIM_ORDER[requested_strength] > cap_score:
        cap_reason = f"requested claim strength {requested_strength} exceeds max supported strength {max_strength}"
        return "capped", "accept_as_evidence", max_strength, [*reasons, cap_reason]
    return "accepted", "accept_as_evidence", max_strength, [reason for reason in reasons if reason]


def review_notes_for(decision: str, reasons: list[str]) -> list[str]:
    if decision == "accepted":
        return ["Claim gates accepted the requested claim strength."]
    if decision == "capped":
        return [f"Claim was capped: {'; '.join(reasons)}"]
    if decision == "needs_human":
        return [f"Human review is required: {'; '.join(reasons)}"]
    return [f"Claim was rejected: {'; '.join(reasons)}"]


def evaluate_claim_gates(
    summary: dict[str, Any],
    metrics: Optional[dict[str, Any]] = None,
    diagnostics: Optional[dict[str, Any]] = None,
    robustness: Optional[dict[str, Any]] = None,
    generated_at: Optional[str] = None,
    trusted_identity: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    claim_type = normalize_claim_type(summary)
    requested_strength = requested_claim_strength(summary)
    gates = artifact_schema_gates({"metrics": metrics, "diagnostics": diagnostics, "robustness": robustness})
    gates.extend(identity_gates(summary, {"metrics": metrics, "diagnostics": diagnostics, "robustness": robustness}, trusted_identity))

    gates.append(claim_type_gate(summary, claim_type))
    gates.append(summary_limitations_gate(summary))
    gates.append(diagnostic_quality_gate(diagnostics))

    if claim_type == "associative":
        gates.append(associative_gate(summary, metrics))
    if claim_type == "predictive":
        gates.append(predictive_gate(metrics))
        gates.append(predictive_leakage_gate(diagnostics))
    if claim_type == "causal" or has_causal_language(summary):
        gates.append(causal_identification_gate(summary, robustness))
    if claim_type == "probabilistic" or has_probability_language(summary):
        gates.append(probability_gate(diagnostics))

    robustness_gate = robustness_support_gate(requested_strength, robustness)
    if robustness_gate is not None:
        gates.append(robustness_gate)
    robustness_impact_gate = robustness_decision_impact_gate(robustness)
    if robustness_impact_gate is not None:
        gates.append(robustness_impact_gate)

    human_gate_result, human_gate_payload = human_gate(summary, requested_strength)
    gates.append(human_gate_result)

    decision, route, max_strength, reasons = choose_decision(requested_strength, gates)
    identity = canonical_identity(summary, trusted_identity)
    return {
        "schema_version": SCHEMA_VERSION,
        "framework_version": FRAMEWORK_VERSION,
        "generated_at": generated_at or utc_now(),
        "run_id": identity["run_id"],
        "experiment_plan_id": identity["experiment_plan_id"],
        "task_id": identity["task_id"],
        "claim": str(summary.get("claim") or ""),
        "claim_type": claim_type,
        "requested_claim_strength": requested_strength,
        "max_claim_strength": max_strength,
        "claim_decision": decision,
        "recommended_route": route,
        "cap_reasons": reasons,
        "human_gate": human_gate_payload,
        "claim_gate_results": gates,
        "review_notes": review_notes_for(decision, reasons),
    }


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate analysis claim gates from structured run artifacts.")
    parser.add_argument("--summary", required=True, type=Path, help="Result summary JSON or markdown with fenced JSON")
    parser.add_argument("--metrics", type=Path, help="analysis_metrics_v1.0 JSON artifact")
    parser.add_argument("--diagnostics", type=Path, help="analysis_diagnostics_v1.0 JSON artifact")
    parser.add_argument("--robustness", type=Path, help="analysis_robustness_v1.0 JSON artifact")
    parser.add_argument("--run-id", help="Trusted run_id from caller context when the summary omits it")
    parser.add_argument("--experiment-plan-id", help="Trusted experiment_plan_id from caller context when the summary omits it")
    parser.add_argument("--task-id", help="Trusted task_id from caller context when the summary omits it")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    try:
        summary = load_artifact(args.summary)
        metrics = load_artifact(args.metrics) if args.metrics is not None else None
        diagnostics = load_artifact(args.diagnostics) if args.diagnostics is not None else None
        robustness = load_artifact(args.robustness) if args.robustness is not None else None
    except ValueError as exc:
        print_json({"ok": False, "reason": "malformed_or_missing", "error": str(exc)})
        return MALFORMED

    trusted_identity = {
        "run_id": args.run_id,
        "experiment_plan_id": args.experiment_plan_id,
        "task_id": args.task_id,
    }
    report = evaluate_claim_gates(summary, metrics, diagnostics, robustness, trusted_identity=trusted_identity)
    report_schema_errors = schema_errors(report, ARTIFACT_SCHEMAS["claim_gates"])
    if report_schema_errors:
        print_json(
            {
                "ok": False,
                "reason": "internal_report_schema_validation_failed",
                "errors": report_schema_errors,
                "report": report,
            }
        )
        return MALFORMED

    print_json(report)
    if report["claim_decision"] in {"rejected", "needs_human"}:
        return VALIDATION_FAILED
    return SUCCESS


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

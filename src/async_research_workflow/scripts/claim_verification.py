#!/usr/bin/env python3
"""Extract and verify explicit claims against runtime evidence snapshots."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SUCCESS = 0
VALIDATION_FAILED = 2
INVALID_REQUEST = 3
MALFORMED = 4

SCHEMA_VERSION = "1.0"
FRAMEWORK_VERSION = "claim_verification_v1.0"
CLAIM_ID_RE = re.compile(r"^CLM-[0-9]{4,6}$")
EVIDENCE_ID_RE = re.compile(r"^EVID-[0-9]{6}$")
TASK_ID_RE = re.compile(r"^TASK-[0-9]{4}$")

CLAIM_OUTCOMES = {
    "supported",
    "weakly_supported",
    "unsupported",
    "contradicted",
    "stale",
    "unverifiable",
}
CLAIM_ORDER = {"none": 0, "weak": 1, "suggestive": 2, "moderate": 3, "strong": 4}
CLAIM_BY_SCORE = {score: claim for claim, score in CLAIM_ORDER.items()}
OUTCOME_CAPS = {
    "supported": "strong",
    "weakly_supported": "suggestive",
    "stale": "weak",
    "unsupported": "none",
    "contradicted": "none",
    "unverifiable": "none",
}
MATERIAL_CLAIM_TYPES = {
    "causal",
    "comparative",
    "empirical",
    "forecast",
    "numeric",
    "predictive",
    "source_grounded",
}
HARD_ACCEPTANCE_OUTCOMES = {"unsupported", "contradicted", "unverifiable"}
READINESS_BLOCKING_OUTCOMES = {"unsupported", "contradicted", "stale", "unverifiable"}
QUOTE_MARKERS = {"quote", "quoted", "direct_quote"}
PARAPHRASE_MARKERS = {"paraphrase", "paraphrased", "summary"}
NO_VALUE_MARKERS = {"", "none", "n/a", "na", "unknown", "todo", "tbd"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def markdown_escape(value: Any) -> str:
    return normalize_text(value).replace("|", "\\|") or "none"


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def load_json_optional(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def extract_json_objects(text: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE):
        candidate = match.group(1).strip()
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            objects.append(payload)
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{") or not stripped.endswith("}"):
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            objects.append(payload)
    return objects


def workspace_path(ops_dir: Path, path_text: Any) -> Path | None:
    if not isinstance(path_text, str):
        return None
    posix = PurePosixPath(path_text)
    if posix.is_absolute() or not posix.parts:
        return None
    if posix.parts[0] != "research_ops":
        return None
    if any(part in {"", ".", ".."} for part in posix.parts):
        return None
    candidate = (ops_dir.parent / Path(*posix.parts)).resolve(strict=False)
    try:
        candidate.relative_to(ops_dir.resolve(strict=False))
    except ValueError:
        return None
    return candidate


def ops_relative_path(ops_dir: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(ops_dir.parent.resolve(strict=False)).as_posix()
    except ValueError:
        try:
            return path.resolve(strict=False).relative_to(ops_dir.resolve(strict=False)).as_posix()
        except ValueError:
            return path.as_posix()


def task_dir_for_id(ops_dir: Path, task_id: str) -> Path | None:
    direct = ops_dir / "tasks" / task_id
    if direct.is_dir():
        return direct
    matches = sorted(path for path in (ops_dir / "tasks").glob(f"{task_id}-*") if path.is_dir())
    return matches[0] if matches else None


def read_runtime_evidence(ops_dir: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    ledger = ops_dir / "runtime" / "evidence_objects.jsonl"
    evidence: dict[str, dict[str, Any]] = {}
    warnings: list[dict[str, Any]] = []
    if not ledger.exists():
        return evidence, warnings
    try:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        warnings.append({"reason": "runtime_evidence_read_failed", "path": str(ledger), "message": str(exc)})
        return evidence, warnings
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            warnings.append(
                {
                    "reason": "runtime_evidence_malformed",
                    "path": str(ledger),
                    "line_number": line_number,
                    "message": exc.msg,
                }
            )
            continue
        if not isinstance(payload, dict):
            continue
        evidence_id = payload.get("evidence_id")
        if isinstance(evidence_id, str):
            evidence[evidence_id] = payload
    return evidence, warnings


def snapshot_text(ops_dir: Path, evidence: dict[str, Any]) -> tuple[str, str | None]:
    path = workspace_path(ops_dir, evidence.get("snapshot_path"))
    if path is None:
        return "", "snapshot_path_invalid"
    try:
        return path.read_text(encoding="utf-8"), None
    except OSError:
        return "", "snapshot_missing"


def parse_ref_string(value: str) -> dict[str, Any]:
    text = value.strip()
    evidence_id = text
    span_ref = ""
    if "#" in text:
        evidence_id, span_ref = text.split("#", 1)
    return {
        "evidence_id": evidence_id.strip(),
        "span_ref": span_ref.strip(),
        "quote": "",
        "quote_or_paraphrase_status": "unspecified",
        "support_status": "supports",
        "computation_artifact": False,
    }


def normalize_evidence_ref(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str):
        if not value.strip():
            return None
        return parse_ref_string(value)
    if not isinstance(value, dict):
        return None
    evidence_id = normalize_text(value.get("evidence_id") or value.get("id") or value.get("source_id"))
    if not evidence_id:
        return None
    span_ref = normalize_text(value.get("span_ref") or value.get("span_id") or value.get("selector"))
    status = normalize_text(
        value.get("quote_or_paraphrase_status")
        or value.get("quote_status")
        or value.get("citation_mode")
        or value.get("mode")
        or "unspecified"
    ).lower()
    support_status = normalize_text(value.get("support_status") or value.get("support") or "supports").lower()
    return {
        "evidence_id": evidence_id,
        "span_ref": span_ref,
        "quote": normalize_text(value.get("quote") or value.get("supporting_quote")),
        "quote_or_paraphrase_status": status,
        "support_status": support_status,
        "computation_artifact": value.get("computation_artifact") is True,
    }


def default_support_level(claim_type: str) -> str:
    if claim_type == "numeric":
        return "computation"
    if claim_type in {"causal", "comparative", "empirical", "predictive"}:
        return "direct"
    return "citation"


def normalize_claim(value: dict[str, Any], *, source: str, index: int) -> dict[str, Any] | None:
    text = normalize_text(value.get("text") or value.get("claim") or value.get("key_finding"))
    if not text:
        return None
    claim_type = normalize_text(value.get("claim_type") or value.get("type") or "general").lower() or "general"
    strength = normalize_text(value.get("strength") or value.get("claim_strength") or "none").lower()
    if strength not in CLAIM_ORDER:
        strength = "none"
    claim_id = normalize_text(value.get("claim_id") or value.get("id"))
    if not CLAIM_ID_RE.match(claim_id):
        claim_id = f"CLM-{index:04d}"
    evidence_refs = [item for item in (normalize_evidence_ref(ref) for ref in as_list(value.get("evidence_refs"))) if item]
    citation_refs = [item for item in (normalize_evidence_ref(ref) for ref in as_list(value.get("citation_refs"))) if item]
    if not citation_refs and evidence_refs:
        citation_refs = [dict(item) for item in evidence_refs]
    if not evidence_refs and citation_refs:
        evidence_refs = [dict(item) for item in citation_refs]
    required_support_level = normalize_text(value.get("required_support_level") or default_support_level(claim_type)).lower()
    return {
        "claim_id": claim_id,
        "text": text,
        "claim_type": claim_type,
        "strength": strength,
        "required_support_level": required_support_level,
        "evidence_refs": evidence_refs,
        "citation_refs": citation_refs,
        "verification_status": "unverified",
        "failure_reason": "",
        "source": source,
    }


def claims_from_payload(payload: dict[str, Any], *, source: str, start_index: int) -> list[dict[str, Any]]:
    candidates: list[Any] = []
    if isinstance(payload.get("claims"), list):
        candidates.extend(payload["claims"])
    claim_verification = payload.get("claim_verification")
    if isinstance(claim_verification, dict) and isinstance(claim_verification.get("claims"), list):
        candidates.extend(claim_verification["claims"])
    if "claim_id" in payload or ("claim" in payload and ("evidence_refs" in payload or "citation_refs" in payload)):
        candidates.append(payload)
    claims: list[dict[str, Any]] = []
    for offset, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue
        claim = normalize_claim(candidate, source=source, index=start_index + offset)
        if claim is not None:
            claims.append(claim)
    return claims


def task_claim_artifact_paths(task_dir: Path) -> list[Path]:
    return [
        task_dir / "artifacts" / "claim_verification.json",
        task_dir / "artifacts" / "claim_verification" / "claims.json",
    ]


def extract_task_claims(task_dir: Path, summary: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[str], bool]:
    claims: list[dict[str, Any]] = []
    artifact_paths: list[str] = []
    explicit_artifact = False

    for path in task_claim_artifact_paths(task_dir):
        payload = load_json_optional(path)
        if payload is None:
            continue
        explicit_artifact = True
        artifact_paths.append(str(path))
        claims.extend(claims_from_payload(payload, source=path.as_posix(), start_index=len(claims) + 1))

    if isinstance(summary, dict):
        extracted = claims_from_payload(summary, source="result_summary", start_index=len(claims) + 1)
        if extracted:
            claims.extend(extracted)

    worker_output = task_dir / "worker_output.md"
    if worker_output.exists():
        for payload in extract_json_objects(worker_output.read_text(encoding="utf-8")):
            extracted = claims_from_payload(payload, source=worker_output.as_posix(), start_index=len(claims) + 1)
            if extracted:
                claims.extend(extracted)

    return dedupe_claims(claims), artifact_paths, explicit_artifact


def deliverable_claim_artifact_paths(ops_dir: Path, deliverable: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for value in (
        deliverable.get("claim_verification_path"),
        deliverable.get("citation_verification_path"),
        deliverable.get("primary_artifact"),
    ):
        resolved = workspace_path(ops_dir, value)
        if resolved is not None and resolved.is_file():
            paths.append(resolved)
    default_path = ops_dir / "deliverables" / "claim_verification" / f"{deliverable.get('deliverable_id')}.json"
    if default_path.is_file():
        paths.append(default_path)
    return sorted({path.resolve(strict=False) for path in paths})


def extract_deliverable_claims(ops_dir: Path, deliverable: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], bool]:
    claims: list[dict[str, Any]] = []
    paths = deliverable_claim_artifact_paths(ops_dir, deliverable)
    for path in paths:
        if path.suffix.lower() == ".json":
            payload = load_json_optional(path)
            if payload is not None:
                claims.extend(claims_from_payload(payload, source=path.as_posix(), start_index=len(claims) + 1))
                continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for payload in extract_json_objects(text):
            claims.extend(claims_from_payload(payload, source=path.as_posix(), start_index=len(claims) + 1))
    return dedupe_claims(claims), [path.as_posix() for path in paths], bool(paths)


def dedupe_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for claim in claims:
        key = (claim.get("claim_id", ""), claim.get("text", "").lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(claim)
    return result


def merged_refs(claim: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for ref in claim.get("evidence_refs", []) + claim.get("citation_refs", []):
        if not isinstance(ref, dict):
            continue
        key = (
            normalize_text(ref.get("evidence_id")),
            normalize_text(ref.get("span_ref")),
            normalize_text(ref.get("quote")),
        )
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return refs


def evidence_span_ref(evidence: dict[str, Any], requested: str) -> str:
    if requested:
        return requested
    spans = evidence.get("span_refs") if isinstance(evidence.get("span_refs"), list) else []
    for span in spans:
        if isinstance(span, dict) and normalize_text(span.get("span_id")):
            return normalize_text(span.get("span_id"))
    return ""


def evidence_freshness(evidence: dict[str, Any]) -> str:
    freshness = evidence.get("freshness_status") if isinstance(evidence.get("freshness_status"), dict) else {}
    status = normalize_text(freshness.get("status") if freshness else "").lower()
    return status or "unknown"


def ref_is_quote(ref: dict[str, Any]) -> bool:
    status = normalize_text(ref.get("quote_or_paraphrase_status")).lower()
    return status in QUOTE_MARKERS or bool(normalize_text(ref.get("quote")))


def ref_is_paraphrase(ref: dict[str, Any]) -> bool:
    return normalize_text(ref.get("quote_or_paraphrase_status")).lower() in PARAPHRASE_MARKERS


def evidence_is_computation(evidence: dict[str, Any], ref: dict[str, Any]) -> bool:
    adapter_type = normalize_text(evidence.get("adapter_type")).lower()
    if adapter_type == "code_execute":
        return True
    source_uri = normalize_text(evidence.get("source_uri")).lower()
    return ref.get("computation_artifact") is True or source_uri.startswith(("computed://", "artifact://analysis", "analysis://"))


def map_ref(ref: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]], ops_dir: Path) -> dict[str, Any]:
    evidence_id = normalize_text(ref.get("evidence_id"))
    evidence = evidence_by_id.get(evidence_id)
    mapping: dict[str, Any] = {
        "evidence_id": evidence_id,
        "source_uri": "",
        "span_ref": normalize_text(ref.get("span_ref")),
        "quote_or_paraphrase_status": normalize_text(ref.get("quote_or_paraphrase_status") or "unspecified"),
        "source_freshness_status": "unknown",
        "support_status": normalize_text(ref.get("support_status") or "supports").lower(),
        "found": evidence is not None,
        "quote_found": None,
        "computation_artifact": False,
        "failure_reason": "",
    }
    if evidence is None:
        mapping["failure_reason"] = "evidence_object_missing"
        return mapping
    mapping["source_uri"] = normalize_text(evidence.get("source_uri"))
    mapping["span_ref"] = evidence_span_ref(evidence, mapping["span_ref"])
    mapping["source_freshness_status"] = evidence_freshness(evidence)
    mapping["computation_artifact"] = evidence_is_computation(evidence, ref)
    if ref_is_quote(ref):
        text, error = snapshot_text(ops_dir, evidence)
        quote = normalize_text(ref.get("quote"))
        if error:
            mapping["quote_found"] = False
            mapping["failure_reason"] = error
        elif quote:
            mapping["quote_found"] = quote in normalize_text(text)
            if not mapping["quote_found"]:
                mapping["failure_reason"] = "quote_not_found_in_snapshot"
        else:
            mapping["quote_found"] = True
    elif ref_is_paraphrase(ref):
        mapping["quote_or_paraphrase_status"] = "paraphrase"
    return mapping


def claim_is_material(claim: dict[str, Any]) -> bool:
    claim_type = normalize_text(claim.get("claim_type")).lower()
    strength = normalize_text(claim.get("strength")).lower()
    return claim_type in MATERIAL_CLAIM_TYPES or CLAIM_ORDER.get(strength, 0) >= CLAIM_ORDER["moderate"]


def status_for_claim(claim: dict[str, Any], mappings: list[dict[str, Any]]) -> tuple[str, str]:
    if not mappings:
        return "unsupported", "missing_citation"
    if any(mapping.get("support_status") in {"contradict", "contradicted", "contradicts"} for mapping in mappings):
        return "contradicted", "mapped evidence is marked as contradicting the claim"
    missing = [mapping for mapping in mappings if not mapping.get("found")]
    if missing:
        return "unverifiable", "referenced evidence object is missing"
    quote_missing = [mapping for mapping in mappings if mapping.get("quote_found") is False]
    if quote_missing:
        return "unsupported", "quoted support was not found in the evidence snapshot"
    if claim.get("required_support_level") == "computation" and not any(mapping.get("computation_artifact") for mapping in mappings):
        return "unverifiable", "numeric claims require a computation artifact"
    if any(mapping.get("source_freshness_status") == "stale" for mapping in mappings):
        return "stale", "one or more supporting evidence objects are stale"
    if any(mapping.get("quote_found") is True for mapping in mappings):
        return "supported", "quoted support found in runtime evidence snapshot"
    return "weakly_supported", "evidence object exists, but support is paraphrased or span-level only"


def verify_claims(
    claims: list[dict[str, Any]],
    *,
    ops_dir: Path,
    evidence_by_id: dict[str, dict[str, Any]],
    target_type: str,
    target_id: str,
    required: bool,
    artifact_paths: list[str],
    warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    verified: list[dict[str, Any]] = []
    counts = {outcome: 0 for outcome in sorted(CLAIM_OUTCOMES)}
    max_cap = CLAIM_ORDER["strong"]
    acceptance_blockers: list[dict[str, Any]] = []
    readiness_blockers: list[dict[str, Any]] = []
    cap_reasons: list[str] = []
    skeptic_review_required = False

    if required and not claims:
        acceptance_blockers.append(
            {
                "claim_id": "none",
                "reason": "claim_verification_missing",
                "message": "claim verification is required, but no explicit claim objects were found",
            }
        )
        readiness_blockers.append(acceptance_blockers[0])
        max_cap = min(max_cap, CLAIM_ORDER["none"])

    for claim in claims:
        mappings = [map_ref(ref, evidence_by_id, ops_dir) for ref in merged_refs(claim)]
        status, failure_reason = status_for_claim(claim, mappings)
        counts[status] += 1
        claim["verification_status"] = status
        claim["failure_reason"] = failure_reason
        claim["citation_mappings"] = mappings
        outcome_cap = OUTCOME_CAPS[status]
        max_cap = min(max_cap, CLAIM_ORDER[outcome_cap])
        if outcome_cap != "strong":
            cap_reasons.append(f"{claim['claim_id']} is {status}; cap claim strength at {outcome_cap}")
        material = claim_is_material(claim)
        if material and status in HARD_ACCEPTANCE_OUTCOMES:
            acceptance_blockers.append(
                {
                    "claim_id": claim["claim_id"],
                    "reason": status,
                    "message": failure_reason,
                    "claim_type": claim["claim_type"],
                }
            )
        if material and status in READINESS_BLOCKING_OUTCOMES:
            readiness_blockers.append(
                {
                    "claim_id": claim["claim_id"],
                    "reason": status,
                    "message": failure_reason,
                    "claim_type": claim["claim_type"],
                }
            )
        if status == "contradicted":
            skeptic_review_required = True
        verified.append(claim)

    claim_count = len(verified)
    supported_count = counts.get("supported", 0)
    weak_count = counts.get("weakly_supported", 0)
    unresolved_count = sum(counts[outcome] for outcome in READINESS_BLOCKING_OUTCOMES)
    report_warnings = list(warnings or [])
    if not required and not claims:
        status = "not_required"
    elif not acceptance_blockers:
        status = "pass"
    else:
        status = "blocked"
    return {
        "schema_version": SCHEMA_VERSION,
        "framework_version": FRAMEWORK_VERSION,
        "target_type": target_type,
        "target_id": target_id,
        "evaluated_at": utc_now(),
        "required": required,
        "status": status,
        "acceptance_ok": not acceptance_blockers,
        "readiness_ok": not readiness_blockers,
        "claim_count": claim_count,
        "supported_claim_count": supported_count,
        "weakly_supported_claim_count": weak_count,
        "unresolved_claim_count": unresolved_count,
        "outcome_counts": counts,
        "max_claim_strength": CLAIM_BY_SCORE[max_cap],
        "cap_reasons": cap_reasons,
        "skeptic_review_required": skeptic_review_required,
        "acceptance_blockers": acceptance_blockers,
        "readiness_blockers": readiness_blockers,
        "artifact_paths": artifact_paths,
        "claims": verified,
        "warnings": report_warnings,
    }


def task_requires_claim_verification(status: dict[str, Any] | None, explicit_artifact: bool, claims: list[dict[str, Any]]) -> bool:
    if explicit_artifact or claims:
        return True
    if not isinstance(status, dict):
        return False
    result = status.get("result") if isinstance(status.get("result"), dict) else {}
    for key in ("claim_verification_required", "requires_claim_verification", "runtime_claim_verification_required"):
        if status.get(key) is True or result.get(key) is True:
            return True
    return False


def verify_task_claims(
    task_dir: Path,
    ops_dir: Path | None = None,
    *,
    summary: dict[str, Any] | None = None,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ops = ops_dir or infer_ops_dir(task_dir)
    if ops is None:
        return empty_report("task", task_dir.name, required=False, warning="could not infer research_ops directory")
    evidence_by_id, warnings = read_runtime_evidence(ops)
    claims, artifact_paths, explicit_artifact = extract_task_claims(task_dir, summary)
    required = task_requires_claim_verification(status, explicit_artifact, claims)
    task_id = normalize_text(status.get("id") if isinstance(status, dict) else "") or task_dir.name
    return verify_claims(
        claims,
        ops_dir=ops,
        evidence_by_id=evidence_by_id,
        target_type="task",
        target_id=task_id,
        required=required,
        artifact_paths=artifact_paths,
        warnings=warnings,
    )


def target_maturity_requires_claim_verification(target_maturity: str) -> bool:
    return target_maturity in {"working_paper", "submission_ready_manuscript"}


def verify_deliverable_claims(
    ops_dir: Path,
    deliverable: dict[str, Any],
    *,
    target_maturity: str | None = None,
) -> dict[str, Any]:
    evidence_by_id, warnings = read_runtime_evidence(ops_dir)
    claims, artifact_paths, explicit_artifact = extract_deliverable_claims(ops_dir, deliverable)
    target = target_maturity or normalize_text(deliverable.get("target_maturity")) or "research_note"
    required = (
        target_maturity_requires_claim_verification(target)
        or deliverable.get("claim_verification_required") is True
        or explicit_artifact
        or bool(claims)
    )
    return verify_claims(
        claims,
        ops_dir=ops_dir,
        evidence_by_id=evidence_by_id,
        target_type="deliverable",
        target_id=normalize_text(deliverable.get("deliverable_id")) or "unknown",
        required=required,
        artifact_paths=artifact_paths,
        warnings=warnings,
    )


def empty_report(target_type: str, target_id: str, *, required: bool, warning: str = "") -> dict[str, Any]:
    warnings = [{"reason": "claim_verification_unavailable", "message": warning}] if warning else []
    return verify_claims(
        [],
        ops_dir=Path("research_ops"),
        evidence_by_id={},
        target_type=target_type,
        target_id=target_id,
        required=required,
        artifact_paths=[],
        warnings=warnings,
    )


def infer_ops_dir(task_dir: Path) -> Path | None:
    if task_dir.parent.name == "tasks":
        return task_dir.parent.parent
    for parent in task_dir.parents:
        if parent.name == "research_ops":
            return parent
    return None


def claim_followups(report: dict[str, Any]) -> list[dict[str, Any]]:
    followups: list[dict[str, Any]] = []
    for blocker in report.get("acceptance_blockers", []):
        if not isinstance(blocker, dict):
            continue
        followups.append(
            {
                "reason": f"Resolve claim {blocker.get('claim_id', 'unknown')}: {blocker.get('message', blocker.get('reason', 'unsupported claim'))}",
                "required_artifact": "research_ops/claim_verification_ledger.md",
                "priority": 1 if blocker.get("reason") == "contradicted" else 2,
                "human_approval_needed": blocker.get("reason") == "contradicted",
                "required_before_memo_use": True,
            }
        )
    if report.get("skeptic_review_required") is True:
        followups.append(
            {
                "reason": "Route contradicted claim evidence to skeptic review before acceptance.",
                "required_artifact": "research_ops/review_panel/",
                "priority": 1,
                "human_approval_needed": False,
                "required_before_memo_use": True,
            }
        )
    return followups


def claim_verification_ceiling(report: dict[str, Any], *, target_maturity: str) -> str:
    if not report.get("required"):
        return target_maturity
    if report.get("readiness_ok") is True:
        return target_maturity
    return "shareable_memo"


def write_claim_ledger(ops_dir: Path, report: dict[str, Any]) -> None:
    if not report.get("required") and not report.get("claims"):
        return
    path = ops_dir / "claim_verification_ledger.md"
    existing_rows: list[list[str]] = []
    header = [
        "date",
        "target_type",
        "target_id",
        "claim_id",
        "claim_type",
        "verification_status",
        "max_claim_strength",
        "evidence_refs",
        "failure_reason",
        "claim",
    ]
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip().startswith("|") or "---" in line:
                continue
            cells = [cell.strip().replace("\\|", "|") for cell in line.strip().strip("|").split("|")]
            if [cell.lower() for cell in cells] == header:
                continue
            if len(cells) == len(header):
                existing_rows.append(cells)
    rows_by_key = {(row[1], row[2], row[3]): row for row in existing_rows}
    claims = report.get("claims") if isinstance(report.get("claims"), list) else []
    if not claims and report.get("required"):
        claims = [
            {
                "claim_id": "none",
                "claim_type": "unknown",
                "verification_status": "unverifiable",
                "failure_reason": "claim verification required but no explicit claim objects were found",
                "text": "missing claim verification",
                "evidence_refs": [],
            }
        ]
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        refs = ", ".join(
            str(ref.get("evidence_id"))
            for ref in claim.get("evidence_refs", [])
            if isinstance(ref, dict) and ref.get("evidence_id")
        )
        row = [
            today(),
            str(report.get("target_type") or "unknown"),
            str(report.get("target_id") or "unknown"),
            str(claim.get("claim_id") or "unknown"),
            str(claim.get("claim_type") or "unknown"),
            str(claim.get("verification_status") or "unverified"),
            str(report.get("max_claim_strength") or "none"),
            refs or "none",
            str(claim.get("failure_reason") or "none"),
            str(claim.get("text") or "missing claim text"),
        ]
        rows_by_key[(row[1], row[2], row[3])] = [markdown_escape(cell) for cell in row]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in sorted(rows_by_key.values(), key=lambda item: (item[1], item[2], item[3])))
    atomic_write_text(path, "\n".join(lines) + "\n")


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify explicit claim objects against runtime evidence snapshots.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    task = subparsers.add_parser("verify-task", help="Verify task claim artifacts.")
    task.add_argument("task_dir", type=Path)
    task.add_argument("--ops-dir", type=Path)
    deliverable = subparsers.add_parser("verify-deliverable", help="Verify deliverable claim artifacts.")
    deliverable.add_argument("ops_dir", type=Path)
    deliverable.add_argument("deliverable_id")
    deliverable.add_argument("--target-maturity")
    return parser.parse_args(list(argv))


def load_deliverable(ops_dir: Path, deliverable_id: str) -> dict[str, Any] | None:
    manifest = load_json_optional(ops_dir / "deliverables" / "deliverable_manifest.json")
    if not isinstance(manifest, dict):
        return None
    deliverables = manifest.get("deliverables") if isinstance(manifest.get("deliverables"), list) else []
    for deliverable in deliverables:
        if isinstance(deliverable, dict) and deliverable.get("deliverable_id") == deliverable_id:
            return deliverable
    return None


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    try:
        if args.command == "verify-task":
            report = verify_task_claims(args.task_dir, args.ops_dir)
        else:
            deliverable = load_deliverable(args.ops_dir, args.deliverable_id)
            if deliverable is None:
                print_json({"ok": False, "reason": "deliverable_not_found", "deliverable_id": args.deliverable_id})
                return INVALID_REQUEST
            report = verify_deliverable_claims(args.ops_dir, deliverable, target_maturity=args.target_maturity)
    except Exception as exc:
        print_json({"ok": False, "reason": "claim_verification_failed", "error": str(exc)})
        return MALFORMED
    print_json({"ok": report.get("acceptance_ok") is True, "report": report})
    return SUCCESS if report.get("acceptance_ok") is True else VALIDATION_FAILED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

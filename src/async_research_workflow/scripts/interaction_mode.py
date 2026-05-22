#!/usr/bin/env python3
"""Inspect and manage durable research_ops interaction mode config."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable

from async_research_workflow.resources import schema_path
from async_research_workflow.scripts.validate_json_artifact import load_json
from async_research_workflow.scripts.validate_json_artifact import validate


SUCCESS = 0
INVALID = 4
CONFIG_FILENAME = "interaction_mode.json"
SCHEMA_NAME = "interaction_mode.schema.json"
SCHEMA_VERSION = "1.0"
INTERACTION_MODES = (
    "manual",
    "guided",
    "supervised",
    "autonomous",
    "publication_guarded",
)
ALL_INTERRUPT_CATEGORIES = (
    "quality_uncertainty",
    "source_freshness_or_approval",
    "review_disagreement",
    "revision_limit_reached",
    "idea_prioritization_ambiguity",
    "budget_warning",
    "hard_budget_breach",
    "credentials_missing",
    "destructive_operation",
    "private_data_approval",
    "legal_policy_sensitive_claim",
    "external_publication_approval",
    "source_governance_missing",
    "result_acceptance_missing",
    "deliverable_maturity_missing",
)
HARD_STOP_INTERRUPT_CATEGORIES = (
    "hard_budget_breach",
    "credentials_missing",
    "destructive_operation",
    "private_data_approval",
    "legal_policy_sensitive_claim",
    "external_publication_approval",
)
AUTO_DECISION_KEYS = (
    "allow_resume",
    "allow_revision",
    "allow_reject",
    "allow_claim_downgrade",
    "allow_source_substitution",
    "allow_idea_prioritization",
)
AUTONOMOUS_DEFAULT_MODES = {"supervised", "autonomous", "publication_guarded"}


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def mode_config_path(ops_dir: Path) -> Path:
    return ops_dir / CONFIG_FILENAME


def default_config_for_mode(mode: str) -> dict[str, Any]:
    auto_allowed = mode in AUTONOMOUS_DEFAULT_MODES
    interrupt_only_for = HARD_STOP_INTERRUPT_CATEGORIES if auto_allowed else ALL_INTERRUPT_CATEGORIES
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "risk_tolerance": "conservative",
        "interrupt_policy": {
            "allow_interrupts": True,
            "interrupt_only_for": list(interrupt_only_for),
        },
        "auto_decisions": {key: auto_allowed for key in AUTO_DECISION_KEYS},
        "audit": {
            "write_decisions": True,
            "write_auto_decisions": auto_allowed,
            "explain_auto_decisions": True,
        },
    }


def starter_default_config() -> dict[str, Any]:
    return default_config_for_mode("supervised")


def missing_config_default() -> dict[str, Any]:
    return default_config_for_mode("manual")


def issue(path: str, message: str, hint: str | None = None) -> dict[str, str]:
    payload = {"path": path, "message": message}
    if hint:
        payload["hint"] = hint
    return payload


def validation_errors(config: dict[str, Any]) -> list[dict[str, str]]:
    schema = load_json(schema_path(SCHEMA_NAME))
    errors = [error.to_dict() for error in validate(config, schema)]
    if errors:
        return errors

    semantic: list[dict[str, str]] = []
    mode = config.get("mode")
    interrupt_policy = config.get("interrupt_policy") if isinstance(config.get("interrupt_policy"), dict) else {}
    interrupt_only_for = interrupt_policy.get("interrupt_only_for")
    interrupt_categories = set(interrupt_only_for if isinstance(interrupt_only_for, list) else [])
    auto_decisions = config.get("auto_decisions") if isinstance(config.get("auto_decisions"), dict) else {}
    audit = config.get("audit") if isinstance(config.get("audit"), dict) else {}

    if interrupt_policy.get("allow_interrupts") is not True:
        semantic.append(
            issue(
                "$.interrupt_policy.allow_interrupts",
                "interaction modes must allow human interrupts for hard stops",
                "Set allow_interrupts to true; autonomous mode still stops for credentials, budget breaches, private data, destructive operations, legal or publication approval.",
            )
        )

    missing_hard_stops = sorted(set(HARD_STOP_INTERRUPT_CATEGORIES) - interrupt_categories)
    if missing_hard_stops:
        semantic.append(
            issue(
                "$.interrupt_policy.interrupt_only_for",
                f"hard-stop categories are missing: {', '.join(missing_hard_stops)}",
                "Include every hard-stop category so autonomy cannot bypass human approval.",
            )
        )

    if mode in {"manual", "guided"}:
        missing_manual_interrupts = sorted(set(ALL_INTERRUPT_CATEGORIES) - interrupt_categories)
        if missing_manual_interrupts:
            semantic.append(
                issue(
                    "$.interrupt_policy.interrupt_only_for",
                    f"{mode} mode must keep manual-compatible interrupts: {', '.join(missing_manual_interrupts)}",
                    "Use `async-research mode set research_ops --mode manual` or guided to rewrite a safe policy.",
                )
            )

    enabled_auto_decisions = sorted(key for key, value in auto_decisions.items() if value is True)
    if mode in {"manual", "guided"} and enabled_auto_decisions:
        semantic.append(
            issue(
                "$.auto_decisions",
                f"{mode} mode cannot enable automatic decisions: {', '.join(enabled_auto_decisions)}",
                "Disable automatic decisions or select supervised/autonomous mode explicitly.",
            )
        )

    if enabled_auto_decisions:
        missing_audit = [
            key
            for key in ("write_decisions", "write_auto_decisions", "explain_auto_decisions")
            if audit.get(key) is not True
        ]
        if missing_audit:
            semantic.append(
                issue(
                    "$.audit",
                    f"automatic decisions require audit fields to be true: {', '.join(missing_audit)}",
                    "Autonomy must remain inspectable through durable decision logs.",
                )
            )

    return semantic


def summary_for_config(config: dict[str, Any]) -> dict[str, Any]:
    auto_decisions = config.get("auto_decisions") if isinstance(config.get("auto_decisions"), dict) else {}
    interrupt_policy = config.get("interrupt_policy") if isinstance(config.get("interrupt_policy"), dict) else {}
    enabled_auto_decisions = sorted(key for key, value in auto_decisions.items() if value is True)
    return {
        "mode": config.get("mode"),
        "risk_tolerance": config.get("risk_tolerance"),
        "allow_interrupts": interrupt_policy.get("allow_interrupts"),
        "interrupt_only_for": interrupt_policy.get("interrupt_only_for", []),
        "auto_decisions_enabled": enabled_auto_decisions,
        "auto_decision_count": len(enabled_auto_decisions),
        "audit": config.get("audit", {}),
    }


def inspect_mode_config(ops_dir: Path) -> dict[str, Any]:
    path = mode_config_path(ops_dir)
    if not ops_dir.exists():
        return {
            "ok": False,
            "reason": "ops_dir_missing",
            "ops_dir": str(ops_dir),
            "path": str(path),
            "config_present": False,
            "read_only": True,
            "changed": False,
            "errors": [
                issue("$", "research_ops workspace does not exist", "Initialize or choose an existing research_ops directory.")
            ],
            "warnings": [],
        }
    if not ops_dir.is_dir():
        return {
            "ok": False,
            "reason": "ops_dir_not_directory",
            "ops_dir": str(ops_dir),
            "path": str(path),
            "config_present": False,
            "read_only": True,
            "changed": False,
            "errors": [issue("$", "research_ops path is not a directory")],
            "warnings": [],
        }

    if not path.exists():
        config = missing_config_default()
        return {
            "ok": True,
            "reason": "missing_config_default",
            "ops_dir": str(ops_dir),
            "path": str(path),
            "config_present": False,
            "source": "missing_config_default",
            "defaulted": True,
            "read_only": True,
            "changed": False,
            "config": config,
            "summary": summary_for_config(config),
            "errors": [],
            "warnings": [
                issue(
                    "$",
                    "interaction_mode.json is missing; manual-compatible default is in effect",
                    "Run `async-research mode set research_ops --mode supervised` to opt in explicitly.",
                )
            ],
        }

    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "reason": "malformed_mode_config",
            "ops_dir": str(ops_dir),
            "path": str(path),
            "config_present": True,
            "read_only": True,
            "changed": False,
            "errors": [issue("$", f"malformed JSON: {exc}", "Repair JSON before mode-aware commands continue.")],
            "warnings": [],
        }
    except OSError as exc:
        return {
            "ok": False,
            "reason": "mode_config_read_failed",
            "ops_dir": str(ops_dir),
            "path": str(path),
            "config_present": True,
            "read_only": True,
            "changed": False,
            "errors": [issue("$", f"could not read interaction mode config: {exc}")],
            "warnings": [],
        }

    if not isinstance(config, dict):
        return {
            "ok": False,
            "reason": "invalid_mode_config",
            "ops_dir": str(ops_dir),
            "path": str(path),
            "config_present": True,
            "read_only": True,
            "changed": False,
            "errors": [issue("$", "interaction mode config must be a JSON object")],
            "warnings": [],
        }

    errors = validation_errors(config)
    if errors:
        return {
            "ok": False,
            "reason": "invalid_mode_config",
            "ops_dir": str(ops_dir),
            "path": str(path),
            "config_present": True,
            "read_only": True,
            "changed": False,
            "config": config,
            "errors": errors,
            "warnings": [],
        }

    return {
        "ok": True,
        "reason": "mode_config_loaded",
        "ops_dir": str(ops_dir),
        "path": str(path),
        "config_present": True,
        "source": "config_file",
        "defaulted": False,
        "read_only": True,
        "changed": False,
        "config": config,
        "summary": summary_for_config(config),
        "errors": [],
        "warnings": [],
    }


def mode_show(ops_dir: Path) -> tuple[int, dict[str, Any]]:
    result = inspect_mode_config(ops_dir)
    payload = {"action": "mode_show", **result}
    return (SUCCESS if result["ok"] else INVALID), payload


def mode_validate(ops_dir: Path) -> tuple[int, dict[str, Any]]:
    result = inspect_mode_config(ops_dir)
    payload = {"action": "mode_validated", **result}
    return (SUCCESS if result["ok"] else INVALID), payload


def mode_set(ops_dir: Path, mode: str) -> tuple[int, dict[str, Any]]:
    before = inspect_mode_config(ops_dir)
    if not ops_dir.exists() or not ops_dir.is_dir():
        return INVALID, {
            "action": "mode_set",
            "ok": False,
            "reason": before.get("reason", "ops_dir_missing_or_invalid"),
            "ops_dir": str(ops_dir),
            "path": str(mode_config_path(ops_dir)),
            "mode": mode,
            "changed": False,
            "errors": before.get("errors", []),
            "warnings": before.get("warnings", []),
        }

    if not before["ok"]:
        return INVALID, {
            "action": "mode_set",
            "ok": False,
            "reason": "existing_mode_config_invalid",
            "ops_dir": str(ops_dir),
            "path": str(mode_config_path(ops_dir)),
            "mode": mode,
            "changed": False,
            "errors": before.get("errors", []),
            "warnings": before.get("warnings", []),
        }

    previous_config = before.get("config") if isinstance(before.get("config"), dict) else {}
    new_config = default_config_for_mode(mode)
    if previous_config.get("risk_tolerance") in {"conservative", "moderate"}:
        new_config["risk_tolerance"] = previous_config["risk_tolerance"]
    errors = validation_errors(new_config)
    if errors:
        return INVALID, {
            "action": "mode_set",
            "ok": False,
            "reason": "generated_mode_config_invalid",
            "ops_dir": str(ops_dir),
            "path": str(mode_config_path(ops_dir)),
            "mode": mode,
            "changed": False,
            "errors": errors,
            "warnings": [],
        }

    path = mode_config_path(ops_dir)
    changed = previous_config != new_config or not path.exists()
    try:
        path.write_text(json.dumps(new_config, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return INVALID, {
            "action": "mode_set",
            "ok": False,
            "reason": "mode_config_write_failed",
            "ops_dir": str(ops_dir),
            "path": str(path),
            "mode": mode,
            "changed": False,
            "errors": [issue("$", f"could not write interaction mode config: {exc}")],
            "warnings": [],
        }

    return SUCCESS, {
        "action": "mode_set",
        "ok": True,
        "ops_dir": str(ops_dir),
        "path": str(path),
        "previous_mode": previous_config.get("mode"),
        "mode": mode,
        "changed": changed,
        "config_present": True,
        "source": "config_file",
        "defaulted": False,
        "config": new_config,
        "summary": summary_for_config(new_config),
        "errors": [],
        "warnings": [],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and manage research_ops interaction mode config.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    show = subparsers.add_parser("show", help="Show the effective interaction mode as JSON.")
    show.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"), help="Path to the research_ops workspace.")

    validate_cmd = subparsers.add_parser("validate", help="Validate interaction_mode.json or the deterministic missing-config default.")
    validate_cmd.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"), help="Path to the research_ops workspace.")

    set_cmd = subparsers.add_parser("set", help="Write a safe interaction mode config.")
    set_cmd.add_argument("ops_dir", nargs="?", type=Path, default=Path("research_ops"), help="Path to the research_ops workspace.")
    set_cmd.add_argument("--mode", required=True, choices=INTERACTION_MODES, help="Interaction mode to write.")

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv or []))
    if args.command == "show":
        code, payload = mode_show(args.ops_dir)
    elif args.command == "validate":
        code, payload = mode_validate(args.ops_dir)
    else:
        code, payload = mode_set(args.ops_dir, args.mode)
    print_json(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

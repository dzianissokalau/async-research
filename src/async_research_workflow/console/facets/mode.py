"""Console snapshot facet helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from async_research_workflow.console.facets.base import unavailable
from async_research_workflow.scripts import interaction_mode
from async_research_workflow.scripts import prompt_library
from async_research_workflow.scripts import schedule_manifest

def interaction_mode_snapshot(ops_dir: Path) -> dict[str, Any]:
    result = interaction_mode.inspect_mode_config(ops_dir)
    config = result.get("config") if isinstance(result.get("config"), dict) else {}
    interrupt_policy = config.get("interrupt_policy") if isinstance(config.get("interrupt_policy"), dict) else {}
    auto_decisions = config.get("auto_decisions") if isinstance(config.get("auto_decisions"), dict) else {}
    audit = config.get("audit") if isinstance(config.get("audit"), dict) else {}
    interrupt_only_for = interrupt_policy.get("interrupt_only_for") if isinstance(interrupt_policy.get("interrupt_only_for"), list) else []
    hard_stops = list(interaction_mode.HARD_STOP_INTERRUPT_CATEGORIES)
    routine_interrupts = [category for category in interrupt_only_for if category not in hard_stops]
    enabled_auto_decisions = sorted(key for key, value in auto_decisions.items() if value is True)
    payload = {
        "available": result.get("ok") is True,
        "status": "available" if result.get("ok") is True else "invalid",
        "mode": (result.get("summary") or {}).get("mode"),
        "risk_tolerance": (result.get("summary") or {}).get("risk_tolerance"),
        "config_present": result.get("config_present", False),
        "defaulted": result.get("defaulted", False),
        "source": result.get("source", result.get("reason")),
        "path": result.get("path"),
        "summary": result.get("summary", {}),
        "interrupt_policy": {
            "allow_interrupts": interrupt_policy.get("allow_interrupts"),
            "interrupt_only_for": interrupt_only_for,
            "hard_stops": hard_stops,
            "routine_interrupts": routine_interrupts,
            "hard_stop_count": len(hard_stops),
            "routine_interrupt_count": len(routine_interrupts),
        },
        "auto_decision_policy": {
            "enabled": enabled_auto_decisions,
            "enabled_count": len(enabled_auto_decisions),
            "audit": audit,
            "write_decisions": audit.get("write_decisions"),
            "write_auto_decisions": audit.get("write_auto_decisions"),
            "explain_auto_decisions": audit.get("explain_auto_decisions"),
        },
        "controls": {
            "available_modes": list(interaction_mode.INTERACTION_MODES),
            "validate_action": "mode_validate",
            "switch_action": "mode_set",
        },
        "warnings": result.get("warnings", []),
        "errors": result.get("errors", []),
    }
    if result.get("ok") is not True:
        payload["reason"] = result.get("reason", "invalid_mode_config")
        payload["message"] = "interaction mode config is invalid; mode-aware automation must fail closed"
    return payload

def prompts_snapshot(ops_dir: Path) -> dict[str, Any]:
    try:
        return prompt_library.library_snapshot(ops_dir)
    except Exception as exc:
        return unavailable(
            "prompts_unavailable",
            "prompt library could not be read",
            ops_dir / "prompts",
            str(exc),
        )

def schedules_snapshot(ops_dir: Path) -> dict[str, Any]:
    try:
        return schedule_manifest.schedule_snapshot(ops_dir)
    except Exception as exc:
        return unavailable(
            "schedules_unavailable",
            "schedule manifest could not be read",
            ops_dir / "schedules.json",
            str(exc),
        )

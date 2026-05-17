"""Human-oriented diagnostics for common workflow schema failures."""

from __future__ import annotations

from typing import Any, Iterable


def status_schema_diagnostics(payload: Any, errors: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return targeted repair hints for common task status authoring mistakes."""

    if not isinstance(payload, dict):
        return []

    diagnostics: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(path: str, reason: str, message: str, suggested_value: Any) -> None:
        key = f"{path}:{reason}"
        if key in seen:
            return
        seen.add(key)
        diagnostics.append(
            {
                "path": path,
                "reason": reason,
                "message": message,
                "suggested_value": suggested_value,
            }
        )

    if payload.get("last_transition_reason") is None and "last_transition_reason" in payload:
        add(
            "$.last_transition_reason",
            "last_transition_reason_null",
            "last_transition_reason must be a non-empty string; null is not valid task status.",
            "manual_task_created",
        )
    if payload.get("result") is None and "result" in payload:
        add(
            "$.result",
            "result_null",
            "result must be an object when present; use placeholder fields instead of null.",
            {
                "recommendation": None,
                "claim_strength": "none",
                "followup_count": 0,
            },
        )

    for error in errors:
        path = str(error.get("path") or "")
        message = str(error.get("message") or "")
        if path == "$.last_transition_reason" and "required field missing" in message:
            add(
                path,
                "last_transition_reason_missing",
                "new tasks still need a transition reason explaining how the initial state was created.",
                "manual_task_created",
            )
        if path == "$.result" and "expected type" in message:
            add(
                path,
                "result_must_be_object",
                "omit result or set it to a placeholder object; result: null fails the task schema.",
                {
                    "recommendation": None,
                    "claim_strength": "none",
                    "followup_count": 0,
                },
            )
    return diagnostics

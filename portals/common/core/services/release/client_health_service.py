# -*- coding: utf-8 -*-
"""Client health panel data: verify smoke checks + bootstrap gate log."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.client_telemetry import list_gate_log_recent


def _verify_checks_from_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for event in events or []:
        if not isinstance(event, dict):
            continue
        if str(event.get("event_type") or "") not in {"verified", "verify_failed"}:
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        smoke = payload.get("smoke") if isinstance(payload.get("smoke"), dict) else {}
        checks = smoke.get("checks")
        if isinstance(checks, list):
            return [dict(x) for x in checks if isinstance(x, dict)]
    return []


def build_client_health_panel(
    *,
    events: Optional[List[Dict[str, Any]]] = None,
    scope_id: str = "",
    gate_limit: int = 8,
) -> Dict[str, Any]:
    verify_checks = _verify_checks_from_events(events or [])
    gate_rows = list_gate_log_recent(limit=gate_limit)
    gate_results = []
    for row in gate_rows:
        gate_results.append(
            {
                "gate": str(row.get("gate") or ""),
                "passed": bool(row.get("passed")),
                "at": str(row.get("at") or ""),
                "scope_id": str(row.get("scope_id") or scope_id or ""),
                "detail": {k: v for k, v in row.items() if k not in {"gate", "passed", "at", "scope_id"}},
            }
        )
    verify_ok = bool(verify_checks) and all(bool(item.get("ok")) for item in verify_checks)
    latest_gate = gate_results[0] if gate_results else {}
    return {
        "verify_checks": verify_checks,
        "verify_ok": verify_ok,
        "gate_results": gate_results,
        "gate_ok": bool(latest_gate.get("passed")) if latest_gate else None,
        "scope_id": str(scope_id or ""),
    }

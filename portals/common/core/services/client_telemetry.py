# -*- coding: utf-8 -*-
"""In-memory client telemetry ring buffer with optional JSON persistence."""

from __future__ import annotations

import os
from collections import deque
from datetime import datetime
from threading import Lock
from typing import Any, Deque, Dict, List

from data._store import CLIENT_TELEMETRY_FILE, load_document, save_document

_lock = Lock()
_buffer: Deque[Dict[str, Any]] = deque(maxlen=500)
_gate_log: Deque[Dict[str, Any]] = deque(maxlen=200)
_loaded = False


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    rows = load_document(CLIENT_TELEMETRY_FILE, [])
    if isinstance(rows, dict):
        telemetry_rows = rows.get("telemetry") if isinstance(rows.get("telemetry"), list) else []
        gate_rows = rows.get("gate_log") if isinstance(rows.get("gate_log"), list) else []
    elif isinstance(rows, list):
        telemetry_rows = rows
        gate_rows = []
    else:
        telemetry_rows = []
        gate_rows = []
    for row in telemetry_rows[-500:]:
        if isinstance(row, dict):
            _buffer.append(row)
    for row in gate_rows[-200:]:
        if isinstance(row, dict):
            _gate_log.append(row)
    _loaded = True


def _persist() -> None:
    save_document(
        CLIENT_TELEMETRY_FILE,
        {
            "telemetry": list(_buffer),
            "gate_log": list(_gate_log),
        },
    )


def ingest(payload: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_loaded()
    now = datetime.utcnow().isoformat() + "Z"
    row = {
        "id": f"tel-{int(datetime.utcnow().timestamp() * 1000)}",
        "received_at": now,
        "kind": str(payload.get("kind") or payload.get("type") or payload.get("event_type") or "performance").strip(),
        "project_id": str(payload.get("project_id") or "").strip(),
        "device_id": str(payload.get("device_id") or "").strip(),
        "session_id": str(payload.get("session_id") or "").strip(),
        "sample_id": str(payload.get("sample_id") or "").strip(),
        "fps": payload.get("fps"),
        "rtt_ms": payload.get("rtt_ms"),
        "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else payload,
    }
    with _lock:
        _buffer.appendleft(row)
        if str(os.getenv("CLIENT_TELEMETRY_PERSIST", "true")).lower() in ("true", "1", "yes"):
            _persist()
    from services.metrics import increment_telemetry_ingest

    increment_telemetry_ingest()
    return row


def list_recent(limit: int = 50) -> List[Dict[str, Any]]:
    _ensure_loaded()
    cap = max(1, min(int(limit or 50), 300))
    with _lock:
        return [dict(x) for x in list(_buffer)[:cap]]


def record_gate_pass(gate_name: str, passed: bool = True, **extra: Any) -> None:
    from services.metrics import increment_gate_pass

    increment_gate_pass(gate_name, passed=passed)
    _ensure_loaded()
    now = datetime.utcnow().isoformat() + "Z"
    row = {
        "gate": str(gate_name or "unknown").strip() or "unknown",
        "passed": bool(passed),
        "at": now,
        **({k: v for k, v in extra.items() if v is not None}),
    }
    with _lock:
        _gate_log.appendleft(row)
        if str(os.getenv("CLIENT_TELEMETRY_PERSIST", "true")).lower() in ("true", "1", "yes"):
            _persist()


def list_gate_log_recent(limit: int = 20, gate_name: str = "") -> List[Dict[str, Any]]:
    _ensure_loaded()
    cap = max(1, min(int(limit or 20), 100))
    needle = str(gate_name or "").strip()
    with _lock:
        rows = [dict(x) for x in list(_gate_log)]
    if needle:
        rows = [row for row in rows if str(row.get("gate") or "") == needle]
    return rows[:cap]

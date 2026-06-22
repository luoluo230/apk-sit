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
_loaded = False


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    rows = load_document(CLIENT_TELEMETRY_FILE, [])
    if isinstance(rows, list):
        for row in rows[-500:]:
            if isinstance(row, dict):
                _buffer.append(row)
    _loaded = True


def _persist() -> None:
    save_document(CLIENT_TELEMETRY_FILE, list(_buffer))


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


def record_gate_pass(gate_name: str, passed: bool = True) -> None:
    from services.metrics import increment_gate_pass

    increment_gate_pass(gate_name, passed=passed)

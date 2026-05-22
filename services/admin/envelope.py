"""API response envelope helpers."""

from __future__ import annotations

from typing import Any, Dict


def ok(data: Any = None, *, meta: Dict[str, Any] | None = None, legacy: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = {
        "ok": True,
        "data": data if data is not None else {},
        "error": None,
        "meta": meta or {},
    }
    if legacy:
        payload.update(legacy)
    return payload


def fail(message: str, *, code: str = "bad_request", meta: Dict[str, Any] | None = None, legacy: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = {
        "ok": False,
        "data": {},
        "error": {
            "code": code,
            "message": message,
        },
        "meta": meta or {},
    }
    # backward compatible flat error field
    payload["error_message"] = message
    payload["error"] = payload["error"]
    if legacy:
        payload.update(legacy)
    # keep legacy callers that read data.error as string
    payload["error_text"] = message
    payload["error_legacy"] = message
    return payload


def attach_legacy_error(payload: Dict[str, Any]) -> Dict[str, Any]:
    err = payload.get("error")
    if isinstance(err, dict):
        payload["error"] = err.get("message") or "unknown error"
    return payload

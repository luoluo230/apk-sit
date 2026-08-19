# -*- coding: utf-8 -*-
"""BaaS unified error codes loaded from packages/baas_shared/error_codes.json."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
_ERROR_CODES_PATH = os.path.join(_REPO_ROOT, "packages", "baas_shared", "error_codes.json")

_CATALOG: Optional[Dict[str, Any]] = None


def _load_catalog() -> Dict[str, Any]:
    global _CATALOG
    if _CATALOG is not None:
        return _CATALOG
    with open(_ERROR_CODES_PATH, "r", encoding="utf-8") as fh:
        _CATALOG = json.load(fh)
    return _CATALOG


def reload_error_catalog() -> None:
    global _CATALOG
    _CATALOG = None
    _load_catalog()


def error_codes_path() -> str:
    return _ERROR_CODES_PATH


def list_error_codes() -> Mapping[str, Any]:
    return dict(_load_catalog().get("codes") or {})


def list_transport_codes() -> Mapping[str, Any]:
    return dict(_load_catalog().get("transport_codes") or {})


def resolve_code(code_or_message: str) -> str:
    raw = str(code_or_message or "").strip()
    if not raw:
        return "BAAS_UNKNOWN"
    catalog = _load_catalog()
    codes = catalog.get("codes") or {}
    if raw in codes:
        return raw
    aliases = catalog.get("message_aliases") or {}
    return str(aliases.get(raw) or "BAAS_UNKNOWN")


def code_meta(code: str) -> Dict[str, Any]:
    catalog = _load_catalog()
    resolved = resolve_code(code)
    meta = dict((catalog.get("codes") or {}).get(resolved) or {})
    if not meta:
        meta = dict((catalog.get("codes") or {}).get("BAAS_UNKNOWN") or {})
    meta.setdefault("message_zh", "未知错误")
    meta.setdefault("http_status", 400)
    return meta


@dataclass
class BaasError(Exception):
    code: str
    message: str = ""
    http_status: int = 400
    details: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.code = resolve_code(self.code)
        meta = code_meta(self.code)
        if not self.message:
            self.message = str(meta.get("message_zh") or self.code)
        if not self.http_status or self.http_status == 400:
            self.http_status = int(meta.get("http_status") or 400)

    def to_body(self) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "ok": False,
            "error_code": self.code,
            "error": self.message,
        }
        if self.details:
            body["details"] = self.details
        return body


def baas_error(code: str, *, message: str = "", details: Optional[Dict[str, Any]] = None, http_status: int = 0) -> BaasError:
    meta = code_meta(resolve_code(code))
    status = int(http_status or meta.get("http_status") or 400)
    msg = message or str(meta.get("message_zh") or code)
    return BaasError(code=resolve_code(code), message=msg, http_status=status, details=dict(details or {}))


def baas_error_from_message(message: str, *, details: Optional[Dict[str, Any]] = None) -> BaasError:
    code = resolve_code(str(message or ""))
    meta = code_meta(code)
    return BaasError(
        code=code,
        message=str(message or meta.get("message_zh") or code),
        http_status=int(meta.get("http_status") or 400),
        details=dict(details or {}),
    )


def baas_error_from_exception(exc: BaseException) -> BaasError:
    if isinstance(exc, BaasError):
        return exc
    return baas_error_from_message(str(exc))


def baas_success(data: Any, *, status: int = 200) -> Tuple[Any, int]:
    from flask import jsonify

    return jsonify({"ok": True, "data": data}), status


def baas_fail(code: str, *, message: str = "", details: Optional[Dict[str, Any]] = None, http_status: int = 0) -> Tuple[Any, int]:
    from flask import jsonify

    err = baas_error(code, message=message, details=details, http_status=http_status)
    return jsonify(err.to_body()), err.http_status


def baas_fail_exc(exc: BaseException, *, http_status: int = 0) -> Tuple[Any, int]:
    from flask import jsonify

    err = baas_error_from_exception(exc)
    if http_status:
        err.http_status = int(http_status)
    return jsonify(err.to_body()), err.http_status


def baas_handle(callable_fn):
    """Wrap a zero-arg service call returning serializable data."""

    def _wrapped(*args, **kwargs):
        try:
            return baas_success(callable_fn(*args, **kwargs))
        except Exception as exc:
            return baas_fail_exc(exc)

    return _wrapped

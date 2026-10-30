# -*- coding: utf-8 -*-
"""Probe patch manifests for non-empty files[] and optional first-file download."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _fetch_text(url: str, *, timeout: float = 15.0) -> tuple[int, str]:
    text_url = str(url or "").strip()
    if not text_url:
        return 0, ""
    try:
        req = Request(text_url, method="GET")
        with urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            body = resp.read().decode("utf-8", "replace")
            return status, body
    except HTTPError as exc:
        return int(getattr(exc, "code", 0) or 0), ""
    except (URLError, Exception):
        return 0, ""


def _fetch_bytes(url: str, *, timeout: float = 30.0) -> tuple[int, bytes]:
    text_url = str(url or "").strip()
    if not text_url:
        return 0, b""
    try:
        req = Request(text_url, method="GET")
        with urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            return status, resp.read() or b""
    except HTTPError as exc:
        return int(getattr(exc, "code", 0) or 0), b""
    except (URLError, Exception):
        return 0, b""


def parse_manifest_files(manifest_text: str) -> List[Dict[str, Any]]:
    try:
        payload = json.loads(manifest_text or "{}")
    except json.JSONDecodeError:
        return []
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list):
        return []
    return [row for row in files if isinstance(row, dict)]


def allow_empty_manifest(*, is_gate_fixture: bool = False) -> bool:
    if not is_gate_fixture:
        return False
    return str(os.environ.get("RELEASE_GATE_ALLOW_EMPTY_MANIFEST") or "").strip() in {
        "1",
        "true",
        "yes",
        "on",
    }


def probe_patch_manifest(
    url: str,
    *,
    label: str,
    is_gate_fixture: bool = False,
    download_first_file: bool = True,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    """Return ok=False when manifest is missing, empty files[], or first file fails."""
    status, text = _fetch_text(url, timeout=timeout)
    result: Dict[str, Any] = {
        "key": label,
        "url": str(url or "")[:160],
        "http_status": status,
        "ok": False,
        "file_count": 0,
    }
    if status < 200 or status >= 400 or not text.strip():
        result["error"] = f"manifest HTTP {status} or empty body"
        return result

    files = parse_manifest_files(text)
    result["file_count"] = len(files)
    if not files:
        if allow_empty_manifest(is_gate_fixture=is_gate_fixture):
            result["ok"] = True
            result["warning"] = "empty files[] allowed for gate-fixture"
            return result
        result["error"] = "manifest files[] empty"
        return result

    if not download_first_file:
        result["ok"] = True
        return result

    entry = files[0]
    relative = str(entry.get("relativePath") or entry.get("path") or "").replace("\\", "/").lstrip("/")
    download_url = str(entry.get("downloadUrl") or "").strip()
    if not download_url and relative:
        base = url.rsplit("/", 1)[0] + "/"
        download_url = base + relative
    file_status, blob = _fetch_bytes(download_url, timeout=max(timeout, 30.0))
    result["first_file"] = relative or download_url[:120]
    result["first_file_status"] = file_status
    result["first_file_bytes"] = len(blob)
    if file_status < 200 or file_status >= 400 or not blob:
        result["error"] = f"first file download failed HTTP {file_status}"
        return result

    expected_md5 = str(entry.get("md5") or entry.get("Md5") or "").strip().lower()
    if expected_md5:
        digest = hashlib.md5(blob).hexdigest()
        if digest != expected_md5:
            result["error"] = f"md5 mismatch {relative}"
            return result
    result["ok"] = True
    return result


def probe_catalog(url: str, *, timeout: float = 15.0) -> Dict[str, Any]:
    status, blob = _fetch_bytes(url, timeout=timeout)
    ok = 200 <= status < 400 and bool(blob)
    return {
        "key": "catalog",
        "url": str(url or "")[:160],
        "http_status": status,
        "bytes": len(blob),
        "ok": ok,
        "error": None if ok else f"catalog HTTP {status} or empty",
    }

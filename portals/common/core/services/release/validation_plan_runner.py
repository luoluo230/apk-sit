# -*- coding: utf-8 -*-
"""Run release-order validation_items against bundle artifact URLs and optional business hook."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.release.bundle_service import _check_remote_artifact


def parse_validation_items(plan: Dict[str, Any]) -> List[str]:
    raw = (plan or {}).get("validation_items")
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.replace("，", ",").split(",") if part.strip()]


def _artifact_probe_targets(client: Dict[str, Any]) -> Dict[str, str]:
    keys = ("catalog_url", "config_manifest_url", "code_manifest_url", "apk_url", "resource_url", "config_url")
    out: Dict[str, str] = {}
    for key in keys:
        val = str(client.get(key) or "").strip()
        if val:
            out[key] = val
    return out


def _looks_like_url(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


def _call_business_hook(hook_url: str, items: List[str], order: Dict[str, Any], plan: Dict[str, Any]) -> Dict[str, Any]:
    url = str(hook_url or "").strip()
    if not url:
        return {"ok": True, "skipped": True}
    payload = {
        "validation_items": items,
        "validation_task": str(plan.get("validation_task") or "").strip(),
        "release_order_id": str(order.get("release_order_id") or order.get("order_id") or ""),
        "project_id": str(order.get("project_id") or ""),
        "scope_id": str(order.get("scope_id") or ""),
    }
    try:
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=8.0) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(body) if body.strip().startswith("{") else {}
            ok = bool(parsed.get("ok", resp.status < 400))
            return {"ok": ok, "status": int(getattr(resp, "status", 200) or 200), "response": parsed or body[:500]}
    except HTTPError as exc:
        return {"ok": False, "status": int(getattr(exc, "code", 0) or 0), "error": str(exc)}
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "status": 0, "error": str(exc)}


def run_validation_plan(
    order: Dict[str, Any],
    *,
    client_snapshot: Dict[str, Any] | None = None,
    phase: str = "precheck",
) -> Dict[str, Any]:
    """Execute validation_items HTTP probes and optional business test hook."""
    plan = dict(order.get("payload") or {})
    items = parse_validation_items(plan)
    if not items:
        return {"ok": True, "skipped": True, "phase": phase, "items": [], "url_checks": []}

    client = dict(client_snapshot or {})
    if not client and order.get("bundle_id"):
        from services.release.bundle_service import find_active_bundle, get_bundle

        bundle = get_bundle(str(order.get("bundle_id") or "")) or find_active_bundle(
            str(order.get("scope_id") or ""),
            platform=str(order.get("platform") or "").lower(),
        )
        client = dict((bundle or {}).get("client") or {})

    url_checks: List[Dict[str, Any]] = []
    for key, url in _artifact_probe_targets(client).items():
        probe = _check_remote_artifact(url)
        url_checks.append({"key": key, "url": url[:160], "ok": bool(probe.get("ok")), "probe": probe})

    item_rows: List[Dict[str, Any]] = []
    bundle_ok = all(row.get("ok") for row in url_checks) if url_checks else True
    for item in items:
        if _looks_like_url(item):
            probe = _check_remote_artifact(item)
            item_rows.append({"item": item, "ok": bool(probe.get("ok")), "kind": "url", "probe": probe})
        else:
            item_rows.append({"item": item, "ok": bundle_ok, "kind": "bundle_smoke"})

    hook_url = str(plan.get("validation_hook_url") or os.getenv("RELEASE_VALIDATION_HOOK_URL") or "").strip()
    hook_result = _call_business_hook(hook_url, items, order, plan) if hook_url else {"ok": True, "skipped": True}
    hook_ok = bool(hook_result.get("ok", True))
    items_ok = all(row.get("ok") for row in item_rows) if item_rows else True
    ok = bundle_ok and items_ok and hook_ok
    return {
        "ok": ok,
        "phase": phase,
        "items": item_rows,
        "url_checks": url_checks,
        "hook": hook_result,
        "validation_task": str(plan.get("validation_task") or "").strip(),
    }

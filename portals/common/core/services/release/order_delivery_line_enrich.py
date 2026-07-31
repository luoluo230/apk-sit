# -*- coding: utf-8 -*-
"""Attach delivery action BFF payload to environment delivery lines."""

from __future__ import annotations

from typing import Any, Dict


def enrich_delivery_line_actions(project_id: str, line: Dict[str, Any]) -> Dict[str, Any]:
    from services.release.order_build_sync import resolve_delivery_actions

    out = dict(line or {})
    version_id = str(out.get("version_id") or "").strip()
    if not version_id:
        status_hint = "未配置 VersionCode · 请先新建 VC"
        out.update({
            "release_order_id": "",
            "release_order_status": "",
            "pipeline_ready": False,
            "artifact_ready": False,
            "status_hint": status_hint,
            "delivery_actions": {
                "primary": {"action": "create_vc", "label": "新建 VC", "href": ""},
                "secondary": [],
                "status_hint": status_hint,
            },
        })
        return out
    try:
        actions = resolve_delivery_actions(project_id, version_id)
    except ValueError:
        actions = {
            "release_order_id": "",
            "release_order_status": "",
            "pipeline_ready": False,
            "artifact_ready": False,
            "status_hint": "交付动作暂不可用",
            "primary": {"action": "versions", "label": "去版本代码", "href": ""},
            "secondary": [],
        }
    out["release_order_id"] = actions.get("release_order_id") or ""
    out["release_order_status"] = actions.get("release_order_status") or ""
    out["pipeline_ready"] = bool(actions.get("pipeline_ready"))
    out["artifact_ready"] = bool(actions.get("artifact_ready"))
    out["status_hint"] = actions.get("status_hint") or ""
    out["delivery_actions"] = {
        "primary": actions.get("primary") or {},
        "secondary": actions.get("secondary") or [],
        "status_hint": out["status_hint"],
        "scope": actions.get("scope") or {},
        "links": actions.get("links") or {},
    }
    return out

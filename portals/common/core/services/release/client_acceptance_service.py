# -*- coding: utf-8 -*-
"""Client release pipeline — mark VersionCode acceptance (验收)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Tuple

from models.data import project_versions_db, save_project_versions

ALLOWED = {"pending", "passed", "failed"}


def get_client_acceptance(row: Dict[str, Any] | None) -> Dict[str, Any]:
    raw = (row or {}).get("client_acceptance")
    if not isinstance(raw, dict):
        return {"status": "pending", "updated_at": "", "updated_by": ""}
    status = str(raw.get("status") or "pending").strip().lower()
    if status not in ALLOWED:
        status = "pending"
    return {
        "status": status,
        "updated_at": str(raw.get("updated_at") or ""),
        "updated_by": str(raw.get("updated_by") or ""),
        "note": str(raw.get("note") or ""),
    }


def set_client_acceptance(
    project_id: str,
    version_id: str,
    *,
    status: str,
    username: str = "admin",
    note: str = "",
) -> Tuple[Dict[str, Any], int]:
    vid = str(version_id or "").strip()
    st = str(status or "").strip().lower()
    if st not in ALLOWED:
        return {"ok": False, "error": "验收状态无效，仅支持 pending / passed / failed"}, 400
    versions = project_versions_db.get(project_id)
    if not isinstance(versions, list):
        return {"ok": False, "error": "项目版本不存在"}, 404
    target = None
    for row in versions:
        if str((row or {}).get("id") or "").strip() == vid:
            target = row
            break
    if not isinstance(target, dict):
        return {"ok": False, "error": "VersionCode 不存在"}, 404
    if st in {"passed", "failed"} and str(target.get("apk_status") or "") != "found":
        # 允许已发布记录补标；无产物时拒绝通过
        if st == "passed" and not target.get("active_bundle_id"):
            return {"ok": False, "error": "尚无打包产物，不能标记验收通过"}, 400
    payload = {
        "status": st,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "updated_by": str(username or "admin"),
        "note": str(note or "").strip()[:500],
    }
    target["client_acceptance"] = payload
    save_project_versions()
    return {"ok": True, "data": {"version_id": vid, "client_acceptance": payload}}, 200

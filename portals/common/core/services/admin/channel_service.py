"""Channel management service."""

from __future__ import annotations

import re
from typing import Any, Dict, Tuple

from repositories.admin import channels_repo
from services.admin.envelope import ok, fail, attach_legacy_error


def list_channels() -> Tuple[Dict[str, Any], int]:
    rows = []
    for ch in channels_repo.list_channels():
        cid = (ch.get("id") or "").strip()
        if not cid:
            continue
        rows.append(
            {
                "id": cid,
                "name": (ch.get("name") or cid).strip(),
                "description": (ch.get("description") or "").strip(),
                "order": int(ch.get("order") or 0),
                "apk_subdir": (ch.get("apk_subdir") or "").strip(),
                "build_param": (ch.get("build_param") or "").strip(),
            }
        )
    rows.sort(key=lambda x: (x["order"], x["id"]))
    return ok({"channels": rows}, legacy={"channels": rows}), 200


def create_channel(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    cid = (data.get("id") or "").strip()
    name = (data.get("name") or "").strip()
    desc = (data.get("description") or "").strip()
    order = int(data.get("order") or 0)
    apk_subdir = (data.get("apk_subdir") or "").strip()
    build_param = (data.get("build_param") or "").strip()

    if not cid or not name:
        return attach_legacy_error(fail("渠道 ID 与名称不能为空", code="validation_error", legacy={"error": "渠道 ID 与名称不能为空"})), 400
    if not re.match(r"^[a-zA-Z0-9_-]+$", cid):
        return attach_legacy_error(fail("渠道 ID 只能包含字母、数字、下划线和中划线", code="validation_error", legacy={"error": "渠道 ID 只能包含字母、数字、下划线和中划线"})), 400

    existing_ids = {(c.get("id") or "").strip() for c in channels_repo.list_channels()}
    if cid in existing_ids:
        return attach_legacy_error(fail("渠道 ID 已存在", code="conflict", legacy={"error": "渠道 ID 已存在"})), 409

    ch = {
        "id": cid,
        "name": name,
        "description": desc,
        "order": order,
        "apk_subdir": apk_subdir,
        "build_param": build_param,
    }
    rows = channels_repo.list_channels()
    rows.append(ch)
    channels_repo.save()
    channels_repo.audit("channel_create", cid)
    return ok({"channel": ch}, legacy={"ok": True, "channel": ch}), 200


def update_channel(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    cid = (data.get("id") or "").strip()
    if not cid:
        return attach_legacy_error(fail("缺少渠道 ID", code="validation_error", legacy={"error": "缺少渠道 ID"})), 400

    name = (data.get("name") or "").strip()
    desc = (data.get("description") or "").strip()
    order = data.get("order")
    updated = None

    rows = channels_repo.list_channels()
    for ch in rows:
        if (ch.get("id") or "").strip() == cid:
            if name:
                ch["name"] = name
            ch["description"] = desc
            if order is not None:
                try:
                    ch["order"] = int(order)
                except (TypeError, ValueError):
                    ch["order"] = ch.get("order", 0)
            if "apk_subdir" in data:
                ch["apk_subdir"] = (data.get("apk_subdir") or "").strip()
            if "build_param" in data:
                ch["build_param"] = (data.get("build_param") or "").strip()
            updated = {
                "id": cid,
                "name": ch.get("name", cid),
                "description": ch.get("description", ""),
                "order": ch.get("order", 0),
                "apk_subdir": ch.get("apk_subdir", ""),
                "build_param": ch.get("build_param", ""),
            }
            break

    if not updated:
        return attach_legacy_error(fail("渠道不存在", code="not_found", legacy={"error": "渠道不存在"})), 404

    channels_repo.save()
    channels_repo.audit("channel_update", cid)
    return ok({"channel": updated}, legacy={"ok": True, "channel": updated}), 200


def delete_channel(channel_id: str) -> Tuple[Dict[str, Any], int]:
    cid = (channel_id or "").strip()
    if not cid:
        return attach_legacy_error(fail("缺少渠道 ID", code="validation_error", legacy={"error": "缺少渠道 ID"})), 400

    used_in = channels_repo.version_project_ids_using_channel(cid)
    if used_in:
        msg = "已有版本使用该渠道，无法删除（涉及项目：%s）" % ", ".join(sorted(set(used_in)))
        return attach_legacy_error(fail(msg, code="conflict", legacy={"error": msg})), 409

    rows = channels_repo.list_channels()
    before = len(rows)
    rows[:] = [c for c in rows if (c.get("id") or "").strip() != cid]
    if len(rows) == before:
        return attach_legacy_error(fail("渠道不存在", code="not_found", legacy={"error": "渠道不存在"})), 404

    channels_repo.save()
    channels_repo.audit("channel_delete", cid)
    return ok({}, legacy={"ok": True}), 200

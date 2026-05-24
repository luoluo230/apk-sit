# -*- coding: utf-8 -*-
"""项目测试设备：按阶段（开发/测试/线上）绑定 device_id，供 version-resolve 选版。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from models.data import DATA_DIR, load_json, save_json

TEST_DEVICES_FILE = DATA_DIR + "/project_test_devices.json"
VALID_STAGES = ("dev", "test", "production")


def _load_all() -> Dict[str, List[Dict[str, Any]]]:
    raw = load_json(TEST_DEVICES_FILE, {})
    return raw if isinstance(raw, dict) else {}


def _save_all(data: Dict[str, List[Dict[str, Any]]]) -> None:
    save_json(TEST_DEVICES_FILE, data)


def list_devices(project_id: str) -> List[Dict[str, Any]]:
    pid = (project_id or "").strip()
    if not pid:
        return []
    rows = _load_all().get(pid) or []
    return [dict(x) for x in rows if isinstance(x, dict)]


def find_device(project_id: str, device_id: str) -> Optional[Dict[str, Any]]:
    needle = (device_id or "").strip()
    if not needle:
        return None
    for row in list_devices(project_id):
        if (row.get("device_id") or "").strip() == needle:
            return row
    return None


def resolve_stage_for_device(project_id: str, device_id: str) -> Optional[str]:
    row = find_device(project_id, device_id)
    if not row:
        return None
    stage = (row.get("stage") or "dev").strip() or "dev"
    return stage if stage in VALID_STAGES else "dev"


def save_device(project_id: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    pid = (project_id or "").strip()
    if not pid:
        return {}, "缺少 project_id"
    device_id = (payload.get("device_id") or "").strip()
    if not device_id:
        return {}, "设备 ID 不能为空"
    stage = (payload.get("stage") or "dev").strip() or "dev"
    if stage not in VALID_STAGES:
        return {}, "阶段无效"
    platform = (payload.get("platform") or "android").strip().lower()
    if platform not in ("android", "ios"):
        platform = "android"
    label = (payload.get("label") or "").strip()
    notes = (payload.get("notes") or "").strip()
    record_id = (payload.get("id") or "").strip()

    data = _load_all()
    rows = data.get(pid) or []
    if not isinstance(rows, list):
        rows = []
    now = datetime.now().isoformat()
    out: Dict[str, Any]

    if record_id:
        idx = next((i for i, x in enumerate(rows) if (x.get("id") or "") == record_id), -1)
        if idx < 0:
            return {}, "设备记录不存在"
        dup = next(
            (
                x
                for x in rows
                if (x.get("device_id") or "").strip() == device_id and (x.get("id") or "") != record_id
            ),
            None,
        )
        if dup:
            return {}, "设备 ID 已存在"
        rows[idx].update(
            {
                "device_id": device_id,
                "platform": platform,
                "stage": stage,
                "label": label,
                "notes": notes,
                "updated_at": now,
            }
        )
        out = dict(rows[idx])
    else:
        if any((x.get("device_id") or "").strip() == device_id for x in rows):
            return {}, "设备 ID 已存在"
        out = {
            "id": str(uuid.uuid4())[:8],
            "device_id": device_id,
            "platform": platform,
            "stage": stage,
            "label": label,
            "notes": notes,
            "created_at": now,
            "updated_at": now,
        }
        rows.append(out)

    data[pid] = rows
    _save_all(data)
    return out, None


def delete_device(project_id: str, record_id: str) -> Optional[str]:
    pid = (project_id or "").strip()
    rid = (record_id or "").strip()
    if not pid or not rid:
        return "参数无效"
    data = _load_all()
    rows = data.get(pid) or []
    if not isinstance(rows, list):
        return "设备记录不存在"
    new_rows = [x for x in rows if (x.get("id") or "") != rid]
    if len(new_rows) == len(rows):
        return "设备记录不存在"
    data[pid] = new_rows
    _save_all(data)
    return None

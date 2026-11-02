# -*- coding: utf-8 -*-
"""Persist Jenkins packaging step push events (Android / iOS)."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import DATA_DIR

_LOCK = threading.RLock()

# stage_key from pipeline scripts → detection step id
STAGE_KEY_TO_STEP_ID = {
    "0": "env_prep",
    "0a": "apk_prebuild",
    "1": "config_export",
    "2": "resource_build",
    "3": "hot_release",
    "4": "apk_build",
    "5": "ios_xcode_export",
    "6": "ios_ipa_archive",
    "7": "ios_artifact_land",
    "8": "ios_testflight",
    "end": "pipeline_end",
}

_STATUS_OK = {"success", "failed", "running", "stopped", "pending", "skipped"}


def _store_root() -> str:
    root = os.path.join(str(DATA_DIR), "jenkins_step_push")
    os.makedirs(root, exist_ok=True)
    return root


def _path(instance_id: str, build_number: int) -> str:
    safe_iid = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in str(instance_id or "unknown"))
    return os.path.join(_store_root(), safe_iid, f"{int(build_number)}.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_step_id(stage_key: str = "", step_id: str = "") -> str:
    sid = str(step_id or "").strip()
    if sid:
        return sid
    key = str(stage_key or "").strip().lower()
    return STAGE_KEY_TO_STEP_ID.get(key, key)


def load_push_snapshot(instance_id: str, build_number: int) -> Dict[str, Any]:
    path = _path(instance_id, build_number)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def record_step_push(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Upsert one step event. Auto-complete previous running steps when a new step starts."""
    instance_id = str(payload.get("instance_id") or "").strip()
    try:
        build_number = int(payload.get("build_number"))
    except (TypeError, ValueError):
        raise ValueError("build_number required")
    if not instance_id:
        raise ValueError("instance_id required")

    step_id = resolve_step_id(
        str(payload.get("stage_key") or ""),
        str(payload.get("step_id") or ""),
    )
    if not step_id or step_id == "pipeline_end":
        # END marker: mark all running as success
        status = "success"
        step_id = ""
    else:
        status = str(payload.get("status") or "running").strip().lower()
        if status not in _STATUS_OK:
            status = "running"

    label = str(payload.get("label") or payload.get("title") or step_id or "").strip()
    detail = str(payload.get("detail") or "").strip()
    platform = str(payload.get("platform") or "").strip().lower()
    at = str(payload.get("at") or _now_iso())

    with _LOCK:
        snap = load_push_snapshot(instance_id, build_number) or {
            "instance_id": instance_id,
            "build_number": build_number,
            "platform": platform,
            "steps": {},
            "events": [],
            "updated_at": at,
        }
        steps = snap.get("steps") if isinstance(snap.get("steps"), dict) else {}
        events = snap.get("events") if isinstance(snap.get("events"), list) else []

        if platform:
            snap["platform"] = platform

        # Starting a new step → previous running become success (unless already failed/stopped)
        if status == "running" and step_id:
            for sid, row in list(steps.items()):
                if not isinstance(row, dict):
                    continue
                if sid == step_id:
                    continue
                if str(row.get("status") or "") == "running":
                    row = dict(row)
                    row["status"] = "success"
                    row["status_label"] = "完成"
                    row["closed_by"] = step_id
                    row["updated_at"] = at
                    steps[sid] = row

        if step_id:
            prev = steps.get(step_id) if isinstance(steps.get(step_id), dict) else {}
            steps[step_id] = {
                **prev,
                "id": step_id,
                "stage_key": str(payload.get("stage_key") or prev.get("stage_key") or ""),
                "label": label or prev.get("label") or step_id,
                "status": status,
                "status_label": {
                    "success": "完成",
                    "failed": "失败",
                    "running": "进行中",
                    "stopped": "停止",
                    "pending": "待开始",
                    "skipped": "未启用",
                }.get(status, status),
                "detail": detail or prev.get("detail") or "",
                "updated_at": at,
                "source": "jenkins_push",
            }

        if str(payload.get("stage_key") or "").strip().upper() == "END" or str(payload.get("step_id") or "") == "pipeline_end":
            for sid, row in list(steps.items()):
                if isinstance(row, dict) and str(row.get("status") or "") == "running":
                    row = dict(row)
                    row["status"] = "success"
                    row["status_label"] = "完成"
                    row["updated_at"] = at
                    steps[sid] = row

        event = {
            "at": at,
            "step_id": step_id or "pipeline_end",
            "stage_key": str(payload.get("stage_key") or ""),
            "status": status if step_id else "success",
            "label": label,
            "detail": detail,
        }
        events.append(event)
        if len(events) > 200:
            events = events[-200:]

        snap["steps"] = steps
        snap["events"] = events
        snap["updated_at"] = at
        snap["instance_id"] = instance_id
        snap["build_number"] = build_number

        path = _path(instance_id, build_number)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + f".{os.getpid()}.{int(time.time() * 1000)}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(snap, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return snap


def list_pushed_steps(instance_id: str, build_number: int) -> List[Dict[str, Any]]:
    snap = load_push_snapshot(instance_id, build_number)
    steps = snap.get("steps") if isinstance(snap.get("steps"), dict) else {}
    rows = [dict(v) for v in steps.values() if isinstance(v, dict)]
    rows.sort(key=lambda r: str(r.get("updated_at") or ""))
    return rows

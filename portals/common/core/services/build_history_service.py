# -*- coding: utf-8 -*-
"""构建历史：记录、查询、详情、删除（含 Jenkins 构建目录）。"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from models.data import BUILD_VERSION_RECORDS_FILE, load_json, project_versions_db, save_json
from services import jenkins as jenkins_svc
from services import jenkins_manager as jm

MAX_RECORDS = 2000
DEFAULT_VERSION_LIMIT = 50


def _load_records() -> list:
    records = load_json(BUILD_VERSION_RECORDS_FILE, [])
    return records if isinstance(records, list) else []


def _save_records(records: list) -> None:
    if len(records) > MAX_RECORDS:
        records = records[-MAX_RECORDS:]
    save_json(BUILD_VERSION_RECORDS_FILE, records)


def _version_meta(project_id: str, version_id: str) -> dict:
    versions = project_versions_db.get(project_id) or []
    if not isinstance(versions, list):
        return {}
    row = next((x for x in versions if (x.get("id") or "") == version_id), None)
    return row if isinstance(row, dict) else {}


def record_build(
    instance_id: str,
    build_number: int,
    version_id: str,
    project_id: str,
    *,
    triggered_by: str = "",
    version_name: str = "",
    version_code: str = "",
) -> None:
    meta = _version_meta(project_id, version_id) if project_id and version_id else {}
    records = _load_records()
    entry = {
        "instance_id": (instance_id or "").strip(),
        "build_number": int(build_number),
        "version_id": (version_id or "").strip(),
        "project_id": (project_id or "").strip(),
        "version_name": (version_name or meta.get("version_name") or "").strip(),
        "version_code": str(version_code or meta.get("version_code") or "").strip(),
        "triggered_by": (triggered_by or "").strip(),
        "created_at": datetime.now().isoformat(),
        "stopped_by": "",
    }
    records.append(entry)
    _save_records(records)


def mark_build_stopped(instance_id: str, build_number: int, username: str) -> None:
    iid = (instance_id or "").strip()
    bn = int(build_number)
    user = (username or "").strip()
    if not iid or not user:
        return
    records = _load_records()
    for row in records:
        if (row.get("instance_id") or "").strip() == iid and int(row.get("build_number") or 0) == bn:
            row["stopped_by"] = user
            row["stop_requested_at"] = datetime.now().isoformat()
            break
    _save_records(records)


def find_record(
    instance_id: str,
    build_number: int,
    version_id: str = "",
    project_id: str = "",
) -> Optional[dict]:
    iid = (instance_id or "").strip()
    bn = int(build_number)
    vid = (version_id or "").strip()
    pid = (project_id or "").strip()
    for row in reversed(_load_records()):
        if (row.get("instance_id") or "").strip() != iid:
            continue
        if int(row.get("build_number") or 0) != bn:
            continue
        if vid and (row.get("version_id") or "").strip() != vid:
            continue
        if pid and (row.get("project_id") or "").strip() != pid:
            continue
        return dict(row)
    return None


def remove_record(
    instance_id: str,
    build_number: int,
    version_id: str = "",
    project_id: str = "",
) -> Tuple[bool, Optional[str]]:
    iid = (instance_id or "").strip()
    bn = int(build_number)
    vid = (version_id or "").strip()
    pid = (project_id or "").strip()
    records = _load_records()
    kept = []
    removed = False
    for row in records:
        match = (
            (row.get("instance_id") or "").strip() == iid
            and int(row.get("build_number") or 0) == bn
        )
        if match and vid and (row.get("version_id") or "").strip() != vid:
            match = False
        if match and pid and (row.get("project_id") or "").strip() != pid:
            match = False
        if match:
            removed = True
            continue
        kept.append(row)
    if removed:
        _save_records(kept)
    return removed, None if removed else "未找到构建记录"


def list_records_for_version(version_id: str, instance_id: str = "", limit: int = DEFAULT_VERSION_LIMIT) -> list:
    vid = (version_id or "").strip()
    if not vid:
        return []
    iid = (instance_id or "").strip()
    out = [r for r in _load_records() if (r.get("version_id") or "").strip() == vid]
    if iid:
        out = [r for r in out if (r.get("instance_id") or "").strip() == iid]
    out.sort(key=lambda x: int(x.get("build_number") or 0), reverse=True)
    return out[:limit]


def list_records_for_project(project_id: str, limit: int = 500) -> list:
    pid = (project_id or "").strip()
    if not pid:
        return []
    out = [r for r in _load_records() if (r.get("project_id") or "").strip() == pid]
    out.sort(key=lambda x: (x.get("created_at") or "", int(x.get("build_number") or 0)), reverse=True)
    return out[:limit]


def _instance_console_url(instance_id: str, build_number: Optional[int] = None) -> str:
    inst = jm.get_instance_by_id(instance_id) if instance_id else None
    port = (inst or {}).get("port")
    if not port:
        return ""
    url = f"http://127.0.0.1:{port}/job/Android/"
    if build_number:
        url += f"{int(build_number)}/console"
    return url


def _recent_numbers_for_instance(instance_id: str, cache: dict) -> set:
    if not instance_id:
        return set()
    if instance_id in cache:
        return cache[instance_id]
    nums: set = set()
    try:
        iurl = jm.get_jenkins_url_for_instance(instance_id=instance_id)
        bdir = jm.get_builds_dir_for_instance(instance_id=instance_id)
        st = jenkins_svc.fetch_jenkins_status(base_url=iurl, builds_dir=bdir, instance_id=instance_id)
        for b in (st.get("recent") or []):
            try:
                n = int(b.get("number") or 0)
            except Exception:
                n = 0
            if n > 0:
                nums.add(n)
    except Exception:
        nums = set()
    cache[instance_id] = nums
    return nums


def _extract_failure_summary(log_text: str, max_lines: int = 8) -> str:
    if not log_text:
        return "构建失败，请查看完整日志"
    lines = [ln.strip() for ln in log_text.splitlines() if ln.strip()]
    keys = ("error", "exception", "failed", "failure", "fatal", "错误", "失败")
    hits = [ln for ln in reversed(lines) if any(k in ln.lower() for k in keys)]
    if not hits:
        hits = lines[-max_lines:]
    return "\n".join(hits[:max_lines])


def _resolve_build_status(record: dict, recent_cache: Optional[dict] = None) -> dict:
    recent_cache = recent_cache if recent_cache is not None else {}
    bn = int(record.get("build_number") or 0)
    iid = (record.get("instance_id") or "").strip()
    item = {
        "number": bn,
        "build_number": bn,
        "instance_id": iid,
        "version_id": (record.get("version_id") or "").strip(),
        "project_id": (record.get("project_id") or "").strip(),
        "version_name": (record.get("version_name") or "").strip(),
        "version_code": str(record.get("version_code") or "").strip(),
        "triggered_by": (record.get("triggered_by") or "").strip(),
        "stopped_by": (record.get("stopped_by") or "").strip(),
        "started_at": (record.get("created_at") or "").strip(),
        "ended_at": "",
        "duration": "",
        "duration_seconds": None,
        "result": "",
        "building": False,
        "status_label": "未知",
        "console_url": _instance_console_url(iid, bn),
        "failure_summary": "",
    }
    vid0 = (record.get("version_id") or "").strip()
    pid0 = (record.get("project_id") or "").strip()
    if vid0 and pid0 and not item["version_name"]:
        meta0 = _version_meta(pid0, vid0)
        if meta0:
            item["version_name"] = (meta0.get("version_name") or item["version_name"] or "").strip()
            item["version_code"] = str(meta0.get("version_code") or item["version_code"] or "").strip()
    if not iid or not bn:
        return item
    iurl = jm.get_jenkins_url_for_instance(instance_id=iid)
    bdir = jm.get_builds_dir_for_instance(instance_id=iid)
    if not (bdir or iurl):
        return item
    st = jenkins_svc.get_build_status(bn, base_url=iurl, builds_dir=bdir, instance_id=iid)
    status = (st.get("status") or "").strip()
    is_building = bool(st.get("building"))
    local_exists = bool(bdir and os.path.isdir(os.path.join(bdir, str(bn))))
    recent_nums = _recent_numbers_for_instance(iid, recent_cache)
    if is_building and status in ("BUILDING", "QUEUED", "UNKNOWN"):
        if (not local_exists) and (bn not in recent_nums):
            is_building = False
            status = "UNKNOWN"
    item["building"] = is_building
    if not is_building and status not in ("BUILDING", "QUEUED", "UNKNOWN", ""):
        item["result"] = status
    detail = jenkins_svc.get_build_detail(bn, base_url=iurl, builds_dir=bdir) or {}
    if detail.get("timestamp"):
        item["ended_at"] = detail.get("timestamp") or ""
    if detail.get("duration"):
        item["duration"] = detail.get("duration") or ""
        m = re.match(r"^([\d.]+)s$", item["duration"])
        if m:
            try:
                item["duration_seconds"] = float(m.group(1))
            except Exception:
                pass
    if is_building:
        item["status_label"] = "构建中"
    elif status == "SUCCESS":
        item["status_label"] = "成功"
    elif status == "FAILURE":
        item["status_label"] = "失败"
        item["failure_summary"] = _extract_failure_summary(detail.get("log") or "")
    elif status == "ABORTED":
        item["status_label"] = "已中断"
        if item["stopped_by"]:
            item["failure_summary"] = f"由用户 {item['stopped_by']} 停止"
        else:
            item["failure_summary"] = "构建被中断"
    elif status == "UNSTABLE":
        item["status_label"] = "不稳定"
    else:
        item["status_label"] = status or "未知"
    return item


def builds_for_version_enriched(version_id: str, instance_id: str = "") -> list:
    records = list_records_for_version(version_id, instance_id=instance_id)
    cache: dict = {}
    return [_resolve_build_status(r, cache) for r in records]


def builds_grouped_by_project(project_id: str) -> dict:
    versions = project_versions_db.get(project_id) or []
    if not isinstance(versions, list):
        versions = []
    version_map = {(v.get("id") or ""): v for v in versions if isinstance(v, dict)}
    records = list_records_for_project(project_id)
    cache: dict = {}
    by_vid: Dict[str, list] = {}
    for rec in records:
        vid = (rec.get("version_id") or "").strip()
        if not vid:
            continue
        by_vid.setdefault(vid, []).append(_resolve_build_status(rec, cache))
    groups: Dict[str, dict] = {}
    for vid, builds in by_vid.items():
        meta = version_map.get(vid) or {}
        vn = (meta.get("version_name") or (builds[0].get("version_name") if builds else "") or "").strip()
        if not vn:
            vn = ("版本 " + vid[:8]) if vid else "未命名"
        vc = str(meta.get("version_code") or (builds[0].get("version_code") if builds else "") or "").strip()
        if not vc and vid:
            vc = vid[:8]
        ch = (meta.get("channel") or "").strip()
        st = (meta.get("stage") or "dev").strip()
        g = groups.setdefault(vn, {"version_name": vn, "version_codes": []})
        g["version_codes"].append({
            "version_id": vid,
            "version_code": vc,
            "channel": ch,
            "stage": st,
            "platform": meta.get("platform") or "",
            "builds": sorted(builds, key=lambda x: int(x.get("build_number") or 0), reverse=True),
        })
    grouped = []
    for vn in sorted(groups.keys(), reverse=True):
        entry = groups[vn]
        entry["version_codes"].sort(key=lambda x: str(x.get("version_code") or ""), reverse=True)
        grouped.append(entry)
    return {"ok": True, "project_id": project_id, "groups": grouped}


def history_by_project(project_id: str) -> dict:
    return builds_grouped_by_project(project_id)


def build_detail_enriched(
    instance_id: str,
    build_number: int,
    version_id: str = "",
    project_id: str = "",
) -> Optional[dict]:
    record = find_record(instance_id, build_number, version_id=version_id, project_id=project_id)
    if not record and version_id:
        records = list_records_for_version(version_id, instance_id=instance_id)
        record = next((r for r in records if int(r.get("build_number") or 0) == int(build_number)), None)
    summary = _resolve_build_status(record or {"instance_id": instance_id, "build_number": build_number}, {})
    if version_id and project_id and not summary.get("version_name"):
        meta = _version_meta(project_id, version_id)
        if meta:
            summary["version_name"] = (meta.get("version_name") or "").strip()
            summary["version_code"] = str(meta.get("version_code") or "").strip()
            summary["version_id"] = version_id
    iurl = jm.get_jenkins_url_for_instance(instance_id=instance_id)
    bdir = jm.get_builds_dir_for_instance(instance_id=instance_id)
    detail = jenkins_svc.get_build_detail(build_number, base_url=iurl, builds_dir=bdir) or {}
    if not detail and not record:
        return None
    log_text = detail.get("log") or ""
    result = summary.get("result") or detail.get("status") or ""
    out = {
        **summary,
        "parameters": detail.get("parameters") or {},
        "log": log_text,
        "log_size": len(log_text),
        "result": result or summary.get("result") or "",
        "console_url": _instance_console_url(instance_id, build_number),
    }
    if out.get("result") == "FAILURE" and not out.get("failure_summary"):
        out["failure_summary"] = _extract_failure_summary(log_text)
    if out.get("result") == "ABORTED" and record and record.get("stopped_by"):
        out["failure_summary"] = f"由用户 {record.get('stopped_by')} 停止"
    return out


def delete_build(
    instance_id: str,
    build_number: int,
    version_id: str = "",
    project_id: str = "",
) -> Tuple[bool, Optional[str]]:
    iid = (instance_id or "").strip()
    bn = int(build_number)
    if not iid:
        return False, "缺少 Jenkins 实例"
    record = find_record(iid, bn, version_id=version_id, project_id=project_id)
    status_row = _resolve_build_status(record or {"instance_id": iid, "build_number": bn})
    if status_row.get("building"):
        return False, "构建进行中，无法删除"
    iurl = jm.get_jenkins_url_for_instance(instance_id=iid)
    bdir = jm.get_builds_dir_for_instance(instance_id=iid)
    ok_folder, folder_err = jenkins_svc.delete_build_folder(bn, base_url=iurl, builds_dir=bdir)
    if not ok_folder and folder_err and folder_err != "构建不存在":
        return False, folder_err or "删除 Jenkins 构建目录失败"
    removed, err = remove_record(iid, bn, version_id=version_id, project_id=project_id)
    if not removed:
        if ok_folder:
            return True, None
        return False, err or "未找到构建记录"
    return True, None


def delete_build_record(project_id: str, instance_id: str, build_number: int) -> Optional[str]:
    ok, err = delete_build(instance_id, build_number, project_id=project_id)
    return err if not ok else None


def batch_delete_builds(project_id: str, items: List[Dict[str, Any]]) -> Tuple[int, Optional[str]]:
    deleted = 0
    for item in items or []:
        if not isinstance(item, dict):
            continue
        iid = (item.get("instance_id") or "").strip()
        try:
            bn = int(item.get("build_number") or 0)
        except (TypeError, ValueError):
            continue
        vid = (item.get("version_id") or "").strip()
        ok, err = delete_build(iid, bn, version_id=vid, project_id=project_id)
        if ok:
            deleted += 1
        elif err:
            return deleted, err
    return deleted, None

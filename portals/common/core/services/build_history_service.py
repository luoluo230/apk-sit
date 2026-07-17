# -*- coding: utf-8 -*-
"""构建历史：记录、查询、详情、删除（含 Jenkins 构建目录）。"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from models.data import BUILD_VERSION_RECORDS_FILE, get_channel_by_id, load_json, project_versions_db, save_json
from services import jenkins as jenkins_svc
from services import jenkins_manager as jm
from services.release.env_registry import stage_to_env_key

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
    try:
        from services.webhook import fire_feishu

        fire_feishu(
            "build_complete",
            f"项目={project_id} 构建=#{build_number} 版本={entry.get('version_name') or version_id}",
        )
    except Exception:
        pass


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


def list_records_for_project(project_id: str, limit: int = MAX_RECORDS) -> list:
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


def _recent_status_map_for_instance(instance_id: str, cache: dict) -> Dict[int, Dict[str, Any]]:
    if not instance_id:
        return {}
    cache_key = f"status::{instance_id}"
    if cache_key in cache:
        return cache[cache_key]
    items: Dict[int, Dict[str, Any]] = {}
    try:
        iurl = jm.get_jenkins_url_for_instance(instance_id=instance_id)
        bdir = jm.get_builds_dir_for_instance(instance_id=instance_id)
        st = jenkins_svc.fetch_jenkins_status(base_url=iurl, builds_dir=bdir, instance_id=instance_id)
        for row in (st.get("recent") or []):
            try:
                num = int(row.get("number") or 0)
            except Exception:
                num = 0
            if num <= 0:
                continue
            items[num] = {
                "building": bool(row.get("building")),
                "result": str(row.get("result") or "").strip().upper(),
            }
    except Exception:
        items = {}
    cache[cache_key] = items
    return items


def _load_local_build_meta(builds_dir: str, build_number: int) -> Dict[str, Any]:
    if not builds_dir:
        return {}
    build_xml = os.path.join(builds_dir, str(build_number), "build.xml")
    if not os.path.exists(build_xml):
        return {}
    info: Dict[str, Any] = {}
    try:
        import xml.etree.ElementTree as ET

        tree = ET.parse(build_xml)
        root = tree.getroot()
        result_el = root.find("result")
        if result_el is not None and result_el.text:
            info["result"] = result_el.text.strip().upper()
        ts_el = root.find("timestamp")
        if ts_el is not None and ts_el.text:
            try:
                info["ended_at"] = datetime.fromtimestamp(int(ts_el.text) / 1000).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass
        duration_el = root.find("duration")
        if duration_el is not None and duration_el.text:
            try:
                duration_seconds = int(duration_el.text) / 1000
                info["duration"] = f"{duration_seconds:.1f}s"
                info["duration_seconds"] = duration_seconds
            except Exception:
                pass
    except Exception:
        return {}
    return info


def _extract_failure_summary(log_text: str, max_lines: int = 8) -> str:
    if not log_text:
        return "构建失败，请查看完整日志"
    lines = [ln.strip() for ln in log_text.splitlines() if ln.strip()]
    keys = ("error", "exception", "failed", "failure", "fatal", "错误", "失败")
    hits = [ln for ln in reversed(lines) if any(k in ln.lower() for k in keys)]
    if not hits:
        hits = lines[-max_lines:]
    return "\n".join(hits[:max_lines])


def _resolve_build_status(record: dict, recent_cache: Optional[dict] = None, detail_mode: bool = False) -> dict:
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
    local_meta = _load_local_build_meta(bdir, bn)
    recent_status = _recent_status_map_for_instance(iid, recent_cache).get(bn) or {}
    status = str(local_meta.get("result") or recent_status.get("result") or "").strip().upper()
    is_building = bool(recent_status.get("building"))
    if detail_mode and not (status or is_building):
        st = jenkins_svc.get_build_status(bn, base_url=iurl, builds_dir=bdir, instance_id=iid)
        status = (st.get("status") or "").strip().upper()
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
    item["ended_at"] = str(local_meta.get("ended_at") or "")
    item["duration"] = str(local_meta.get("duration") or "")
    item["duration_seconds"] = local_meta.get("duration_seconds")
    detail = {}
    if detail_mode:
        detail = jenkins_svc.get_build_detail(bn, base_url=iurl, builds_dir=bdir) or {}
        if detail.get("timestamp"):
            item["ended_at"] = detail.get("timestamp") or item["ended_at"]
        if detail.get("duration"):
            item["duration"] = detail.get("duration") or item["duration"]
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
        if detail_mode:
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


def _try_finalize_missing_apk(project_id: str, version_id: str, records: list, cache: dict) -> None:
    """Archive Jenkins output for the newest SUCCESS build when the version has no local APK yet."""
    pid = (project_id or "").strip()
    vid = (version_id or "").strip()
    if not pid or not vid or not records:
        return
    from repositories.admin import versions_repo

    meta = _version_meta(pid, vid)
    if meta and versions_repo.has_apk(pid, meta):
        return
    for rec in records:
        item = _resolve_build_status(rec, cache, detail_mode=False)
        if item.get("building"):
            continue
        if str(item.get("result") or "").upper() != "SUCCESS":
            continue
        iid = (rec.get("instance_id") or "").strip()
        bn = int(rec.get("build_number") or 0)
        if not iid or not bn:
            continue
        try:
            from services.apk_artifact_service import finalize_apk_from_jenkins_build

            fin = finalize_apk_from_jenkins_build(iid, bn)
            if fin.get("ok"):
                return
        except Exception:
            return


def builds_for_version_enriched(version_id: str, instance_id: str = "") -> list:
    records = list_records_for_version(version_id, instance_id=instance_id)
    cache: dict = {}
    pid = ""
    meta: dict = {}
    for rec in records:
        pid = (rec.get("project_id") or "").strip()
        if pid:
            break
    if not pid and version_id:
        for project_id, versions in project_versions_db.items():
            if not isinstance(versions, list):
                continue
            hit = next((x for x in versions if isinstance(x, dict) and (x.get("id") or "") == version_id), None)
            if hit:
                pid = str(project_id)
                meta = hit
                break
    if pid and version_id and not meta:
        meta = _version_meta(pid, version_id)
    _try_finalize_missing_apk(pid, version_id, records, cache)
    meta = _version_meta(pid, version_id) if pid and version_id else meta
    from repositories.admin import versions_repo

    apk_download = meta.get("apk_download") if isinstance(meta.get("apk_download"), dict) else {}
    apk_status = "found" if pid and meta and versions_repo.has_apk(pid, meta) else "not_found"
    if apk_status == "found" and pid and meta:
        try:
            from services.apk_artifact_service import build_download_info

            dl_info = build_download_info(pid, meta)
            if dl_info:
                apk_download = {
                    "local_download_url": dl_info.get("local_download_url") or "",
                    "local_qr_dataurl": dl_info.get("local_qr_dataurl") or "",
                    "oss_download_url": dl_info.get("oss_download_url") or "",
                    "oss_qr_dataurl": dl_info.get("oss_qr_dataurl") or "",
                    "oss_remote_key": dl_info.get("oss_remote_key") or "",
                    "public_download_url": dl_info.get("public_download_url") or "",
                    "public_qr_dataurl": dl_info.get("public_qr_dataurl") or "",
                    "public_download_reachable": bool(dl_info.get("public_download_reachable")),
                    "public_download_hint": dl_info.get("public_download_hint") or "",
                    "build_time": dl_info.get("build_time") or "",
                    "build_number": dl_info.get("build_number"),
                    "size_bytes": dl_info.get("size_bytes") or 0,
                }
        except Exception:
            pass
    env_key = stage_to_env_key(meta.get("env_key") or meta.get("stage") or "development")
    platform = str(meta.get("platform") or "").strip()
    channel_id = str(meta.get("channel") or "").strip()
    channel = get_channel_by_id(channel_id) or {}
    channel_name = str(channel.get("name") or channel_id or "未配置渠道")
    out = []
    for rec in records:
        item = _resolve_build_status(rec, cache, detail_mode=False)
        item["env_key"] = env_key
        item["platform"] = platform
        item["channel_id"] = channel_id
        item["channel_name"] = channel_name
        item["apk_download"] = apk_download
        item["apk_status"] = apk_status
        out.append(item)
    return out


def latest_build_for_version(version_id: str, project_id: str = "", instance_id: str = "") -> dict:
    """Return the newest build snapshot for a VersionCode, with release-order fallback."""
    vid = (version_id or "").strip()
    if not vid:
        return {}
    builds = builds_for_version_enriched(vid, instance_id=instance_id)
    if builds:
        return dict(builds[0])
    pid = (project_id or "").strip()
    if not pid:
        for rec in list_records_for_version(vid, instance_id=instance_id):
            pid = (rec.get("project_id") or "").strip()
            if pid:
                break
    if not pid:
        for cand, versions in project_versions_db.items():
            if not isinstance(versions, list):
                continue
            if any(isinstance(x, dict) and (x.get("id") or "") == vid for x in versions):
                pid = str(cand)
                break
    if not pid:
        return {}
    try:
        from services.release.release_order_service import find_release_order_for_version

        order = find_release_order_for_version(pid, vid)
    except Exception:
        order = None
    if not order:
        return {}
    payload = dict(order.get("payload") or {})
    bn_raw = str(payload.get("build_job_id") or "").strip()
    iid = str(payload.get("jenkins_instance_id") or "").strip()
    if not (bn_raw.isdigit() and iid):
        return {}
    rec = {
        "instance_id": iid,
        "build_number": int(bn_raw),
        "version_id": vid,
        "project_id": pid,
        "version_name": str(order.get("version_name") or ""),
        "version_code": str(order.get("version_code") or ""),
        "triggered_by": str(order.get("created_by") or ""),
        "created_at": str(order.get("updated_at") or order.get("created_at") or ""),
    }
    item = _resolve_build_status(rec, {}, detail_mode=False)
    item["env_key"] = stage_to_env_key(order.get("env_key") or "development")
    item["platform"] = str(order.get("platform") or "")
    item["channel_id"] = str(order.get("channel_id") or "")
    return item


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
        by_vid.setdefault(vid, []).append(_resolve_build_status(rec, cache, detail_mode=False))
    groups: Dict[str, dict] = {}
    for vid, builds in by_vid.items():
        meta = version_map.get(vid) or {}
        vn = (meta.get("version_name") or (builds[0].get("version_name") if builds else "") or "").strip()
        if not vn:
            vn = ("版本 " + vid[:8]) if vid else "未命名"
        vc = str(meta.get("version_code") or (builds[0].get("version_code") if builds else "") or "").strip()
        if not vc and vid:
            vc = vid[:8]
        channel_id = (meta.get("channel") or "").strip()
        channel = get_channel_by_id(channel_id) or {}
        channel_name = str(channel.get("name") or channel_id or "未配置渠道")
        env_key = stage_to_env_key(meta.get("env_key") or meta.get("stage") or "development")
        from repositories.admin import versions_repo

        apk_status = "found" if versions_repo.has_apk(project_id, meta) else "not_found"
        apk_download = meta.get("apk_download") if isinstance(meta.get("apk_download"), dict) else {}
        if apk_status == "found" and meta:
            try:
                from services.apk_artifact_service import build_download_info

                dl_info = build_download_info(project_id, meta)
                if dl_info:
                    apk_download = {
                        "local_download_url": dl_info.get("local_download_url") or "",
                        "local_qr_dataurl": dl_info.get("local_qr_dataurl") or "",
                        "oss_download_url": dl_info.get("oss_download_url") or "",
                        "oss_qr_dataurl": dl_info.get("oss_qr_dataurl") or "",
                        "oss_remote_key": dl_info.get("oss_remote_key") or "",
                        "public_download_url": dl_info.get("public_download_url") or "",
                        "public_qr_dataurl": dl_info.get("public_qr_dataurl") or "",
                        "public_download_reachable": bool(dl_info.get("public_download_reachable")),
                        "public_download_hint": dl_info.get("public_download_hint") or "",
                        "build_time": dl_info.get("build_time") or "",
                        "build_number": dl_info.get("build_number"),
                        "size_bytes": dl_info.get("size_bytes") or 0,
                    }
            except Exception:
                pass
        g = groups.setdefault(vn, {"version_name": vn, "version_codes": []})
        g["version_codes"].append({
            "version_id": vid,
            "version_code": vc,
            "channel_id": channel_id,
            "channel_name": channel_name,
            "env_key": env_key,
            "platform": meta.get("platform") or "",
            "apk_status": apk_status,
            "apk_download": apk_download,
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
    summary = _resolve_build_status(record or {"instance_id": instance_id, "build_number": build_number}, {}, detail_mode=True)
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

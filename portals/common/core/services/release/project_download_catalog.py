# -*- coding: utf-8 -*-
"""One download entry per project version: package QR, or the store link when there is no package."""

from __future__ import annotations

from typing import Any, Dict, List

from models.data import get_channel_by_id, products_db, project_versions_db
from services.release.completed_task_catalog import classify_release_mark
from services.release.env_registry import stage_to_env_key


def list_download_entries(project_id: str) -> List[Dict[str, Any]]:
    pid = str(project_id or "").strip()
    versions = [row for row in (project_versions_db.get(pid) or []) if isinstance(row, dict)]
    builds = _latest_builds(pid)
    from services.release.completed_task_catalog import _load_orders

    orders = _load_orders(pid)
    store = _store_links(pid)
    entries = []
    for meta in versions:
        vid = str(meta.get("id") or "")
        build = builds.get(vid) or {}
        apk = _apk_entry(pid, meta)
        platform = str(meta.get("platform") or "").strip().lower()
        channel_id = str(meta.get("channel_id") or meta.get("channel") or "").strip()
        channel = get_channel_by_id(channel_id) or {}
        store_url, store_label = _store_for(store, platform, str(channel.get("name") or ""))
        mark = "unreleased"
        if build.get("build_number"):
            mark = classify_release_mark(
                vid,
                int(build.get("build_number") or 0),
                orders,
                is_newest_success=True,
            )
        entry_url = apk.get("url") or store_url
        entries.append({
            "version_id": vid,
            "version_name": str(meta.get("version_name") or ""),
            "version_code": str(meta.get("version_code") or ""),
            "env_key": stage_to_env_key(meta.get("env_key") or meta.get("stage") or ""),
            "channel_id": channel_id,
            "channel_name": str(channel.get("name") or channel_id or "未配置渠道"),
            "platform": platform,
            "kind": "apk" if apk.get("url") else ("store" if store_url else "empty"),
            "download_url": apk.get("url") or "",
            "store_url": store_url,
            "store_label": store_label,
            "entry_url": entry_url,
            "qr_dataurl": apk.get("qr") or (_qr(store_url) if store_url else ""),
            "size_bytes": apk.get("size_bytes") or 0,
            "build_number": build.get("build_number") or apk.get("build_number") or "",
            "triggered_by": str(build.get("triggered_by") or ""),
            "finished_at": str(apk.get("build_time") or build.get("created_at") or ""),
            "notes": str(meta.get("description") or meta.get("notes") or meta.get("remark") or ""),
            "release_mark": mark,
            "release_label": {"released": "已发版", "rolled_back": "已回滚"}.get(mark, "未发版"),
        })
    entries.sort(key=lambda row: (
        str(row.get("env_key") or ""),
        str(row.get("channel_id") or ""),
        str(row.get("platform") or ""),
        -_code_num(row.get("version_code")),
    ))
    return entries


def _latest_builds(project_id: str) -> Dict[str, dict]:
    from services.build_history_service import list_records_for_project

    found: Dict[str, dict] = {}
    for rec in list_records_for_project(project_id):
        vid = str(rec.get("version_id") or "")
        if vid and vid not in found:
            found[vid] = rec
    return found


def _apk_entry(project_id: str, meta: dict) -> Dict[str, Any]:
    try:
        from repositories.admin import versions_repo
        from services.apk_artifact_service import build_download_info

        if not versions_repo.has_apk(project_id, meta):
            return {}
        info = build_download_info(project_id, meta) or {}
    except Exception:
        return {}
    url = str(info.get("public_download_url") or info.get("local_download_url") or info.get("oss_download_url") or "")
    qr = str(info.get("public_qr_dataurl") or info.get("local_qr_dataurl") or info.get("oss_qr_dataurl") or "")
    if url and not qr:
        qr = _qr(url)
    return {
        "url": url,
        "qr": qr,
        "size_bytes": info.get("size_bytes") or 0,
        "build_number": info.get("build_number") or "",
        "build_time": info.get("build_time") or "",
    }


def _store_links(project_id: str) -> dict:
    from data.products import resolve_project_id_for_product

    for product in products_db if isinstance(products_db, list) else []:
        if not isinstance(product, dict):
            continue
        if resolve_project_id_for_product(product) != project_id:
            continue
        links = product.get("store_links") if isinstance(product.get("store_links"), dict) else {}
        return links
    return {}


def _store_for(links: dict, platform: str, channel_name: str) -> tuple:
    if platform == "ios":
        url = str(links.get("ios_store") or "").strip()
        return url, "App Store"
    channels = links.get("android_channels") if isinstance(links.get("android_channels"), list) else []
    for item in channels:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        name = str(item.get("name") or "").strip()
        if url and channel_name and channel_name.lower() in name.lower():
            return url, name or "商店"
    direct = str(links.get("android_direct") or "").strip()
    if direct:
        return direct, "官方下载"
    for item in channels:
        if isinstance(item, dict) and str(item.get("url") or "").strip():
            return str(item.get("url") or "").strip(), str(item.get("name") or "商店")
    return "", ""


def _qr(text: str) -> str:
    if not text:
        return ""
    try:
        from services.apk_artifact_service import _qr_png_dataurl

        return _qr_png_dataurl(text)
    except Exception:
        return ""


def _code_num(value: Any) -> int:
    text = str(value or "")
    return int(text) if text.isdigit() else -1

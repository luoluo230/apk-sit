# -*- coding: utf-8 -*-
"""Platform capability registry — build grid vs catalog-only platforms.

Plan: P1-03 — UI/API only promise platforms build_grid can build.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from data.platforms import get_platform_by_id, get_platforms_for_project, list_platform_catalog
from services.build.build_grid import PLATFORM_TO_JOB, artifact_type_for_platform, normalize_build_platform

CAPABILITY_BUILD = "build"
CAPABILITY_HOTUPDATE = "hotupdate"
CAPABILITY_STORE = "store"
CAPABILITY_SCOPE = "scope"

STORE_APK = "apk"
STORE_TESTFLIGHT = "testflight"
STORE_WX_BACKEND = "wx_backend"

_BADGE_BUILDABLE = "buildable"
_BADGE_CLIENT_ONLY = "client_only"
_BADGE_CATALOG_ONLY = "catalog_only"

_BADGE_LABELS = {
    _BADGE_BUILDABLE: "可构建",
    _BADGE_CLIENT_ONLY: "仅客户端",
    _BADGE_CATALOG_ONLY: "目录项",
}

_EXPLICIT: Dict[str, Dict[str, Any]] = {
    "android": {
        "can_build": True,
        "can_hotupdate": True,
        "store_backend": STORE_APK,
        "can_scope": True,
        "catalog_only": False,
        "badge": _BADGE_BUILDABLE,
    },
    "ios": {
        "can_build": True,
        "can_hotupdate": True,
        "store_backend": STORE_TESTFLIGHT,
        "can_scope": True,
        "catalog_only": False,
        "badge": _BADGE_BUILDABLE,
    },
    "wechat_minigame": {
        "can_build": True,
        "can_hotupdate": False,
        "store_backend": STORE_WX_BACKEND,
        "can_scope": True,
        "catalog_only": False,
        "badge": _BADGE_BUILDABLE,
    },
    "webgl": {
        "can_build": False,
        "can_hotupdate": False,
        "store_backend": "",
        "can_scope": True,
        "scope_mode": "optional",
        "catalog_only": False,
        "badge": _BADGE_CLIENT_ONLY,
    },
}


def _allow_catalog_only_scope() -> bool:
    return str(os.environ.get("ALLOW_CATALOG_ONLY_SCOPE") or "").lower() in ("1", "true", "yes")


def _normalize_platform_id(raw: Any) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    if get_platform_by_id(text):
        return text
    aliased = normalize_build_platform(text)
    return aliased if get_platform_by_id(aliased) else text


def _catalog_only_profile(platform_id: str) -> Dict[str, Any]:
    return {
        "can_build": False,
        "can_hotupdate": False,
        "store_backend": "",
        "can_scope": False,
        "catalog_only": True,
        "badge": _BADGE_CATALOG_ONLY,
    }


def resolve_platform_capability(platform_id: str) -> Dict[str, Any]:
    """Merge build_grid routing, catalog metadata, and capability flags."""
    pid = _normalize_platform_id(platform_id)
    if not pid:
        raise ValueError("平台 ID 无效")

    catalog = get_platform_by_id(pid) or {}
    if pid in _EXPLICIT:
        flags = dict(_EXPLICIT[pid])
    elif pid in PLATFORM_TO_JOB:
        flags = {
            "can_build": True,
            "can_hotupdate": pid in ("android", "ios"),
            "store_backend": STORE_APK if pid == "android" else (STORE_TESTFLIGHT if pid == "ios" else STORE_WX_BACKEND),
            "can_scope": True,
            "catalog_only": False,
            "badge": _BADGE_BUILDABLE,
        }
    else:
        flags = _catalog_only_profile(pid)

    badge = str(flags.get("badge") or _BADGE_CATALOG_ONLY)
    return {
        "platform_id": pid,
        "id": pid,
        "name": str(catalog.get("name") or pid),
        "description": str(catalog.get("description") or ""),
        "unity_build_target": str(catalog.get("unity_build_target") or ""),
        "order": int(catalog.get("order") or 0),
        "can_build": bool(flags.get("can_build")),
        "can_hotupdate": bool(flags.get("can_hotupdate")),
        "can_scope": bool(flags.get("can_scope")),
        "catalog_only": bool(flags.get("catalog_only")),
        "scope_mode": str(flags.get("scope_mode") or ("enabled" if flags.get("can_scope") else "disabled")),
        "store_backend": str(flags.get("store_backend") or ""),
        "artifact_type": artifact_type_for_platform(pid) if flags.get("can_build") else "",
        "jenkins_job": PLATFORM_TO_JOB.get(pid, ""),
        "badge": badge,
        "badge_label": _BADGE_LABELS.get(badge, badge),
        "capabilities": {
            CAPABILITY_BUILD: bool(flags.get("can_build")),
            CAPABILITY_HOTUPDATE: bool(flags.get("can_hotupdate")),
            CAPABILITY_STORE: bool(flags.get("store_backend")),
            CAPABILITY_SCOPE: bool(flags.get("can_scope") or flags.get("scope_mode") == "optional"),
        },
    }


def list_platform_capabilities() -> List[Dict[str, Any]]:
    rows = [resolve_platform_capability(str(item.get("id") or "")) for item in list_platform_catalog()]
    rows.sort(key=lambda row: (int(row.get("order") or 0), str(row.get("platform_id") or "")))
    return rows


def list_project_enabled_platforms(project_id: str, *, enabled_only: bool = True) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in get_platforms_for_project(project_id, enabled_only=enabled_only):
        pid = str(row.get("id") or "").strip().lower()
        if not pid:
            continue
        cap = resolve_platform_capability(pid)
        cap["enabled"] = True
        cap["assigned"] = True
        out.append(cap)
    return out


def can_build(platform_id: str) -> bool:
    return bool(resolve_platform_capability(platform_id).get("can_build"))


def can_create_scope(platform_id: str) -> bool:
    cap = resolve_platform_capability(platform_id)
    if cap.get("can_scope"):
        return True
    if str(cap.get("scope_mode") or "") == "optional":
        return True
    if cap.get("catalog_only") and _allow_catalog_only_scope():
        return True
    return False


def assert_platform_build_allowed(platform_id: str) -> None:
    cap = resolve_platform_capability(platform_id)
    if cap.get("can_build"):
        return
    label = str(cap.get("name") or cap.get("platform_id") or platform_id)
    raise ValueError(
        f"平台 {label} 未接入构建网格，暂不支持 quick-build；请选择 android / ios / 微信小游戏，或见 P1-05 构建节点安装。"
    )


def assert_scope_creation_allowed(platform_id: str) -> None:
    if can_create_scope(platform_id):
        return
    label = str(resolve_platform_capability(platform_id).get("name") or platform_id)
    raise ValueError(f"平台 {label} 为目录项，默认不可创建 ReleaseScope；开发环境可设置 ALLOW_CATALOG_ONLY_SCOPE=1。")

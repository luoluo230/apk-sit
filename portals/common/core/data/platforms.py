# -*- coding: utf-8 -*-
"""Release platform catalog and per-project platform whitelist."""

from __future__ import annotations

from typing import Any, Dict, List

# Unity BuildTarget 对齐的交付平台目录（用于项目白名单与交付线 env×channel×platform）
PLATFORM_CATALOG: List[Dict[str, Any]] = [
    {"id": "android", "name": "Android", "description": "Unity BuildTarget.Android", "order": 10, "unity_build_target": "Android"},
    {"id": "ios", "name": "iOS", "description": "Unity BuildTarget.iOS", "order": 20, "unity_build_target": "iOS"},
    {"id": "windows", "name": "Windows (64-bit)", "description": "Unity BuildTarget.StandaloneWindows64", "order": 30, "unity_build_target": "StandaloneWindows64"},
    {"id": "macos", "name": "macOS", "description": "Unity BuildTarget.StandaloneOSX", "order": 40, "unity_build_target": "StandaloneOSX"},
    {"id": "linux", "name": "Linux (64-bit)", "description": "Unity BuildTarget.StandaloneLinux64", "order": 50, "unity_build_target": "StandaloneLinux64"},
    {"id": "webgl", "name": "WebGL", "description": "Unity BuildTarget.WebGL", "order": 60, "unity_build_target": "WebGL"},
    {"id": "tvos", "name": "tvOS", "description": "Unity BuildTarget.tvOS", "order": 70, "unity_build_target": "tvOS"},
    {"id": "visionos", "name": "visionOS", "description": "Unity BuildTarget.VisionOS", "order": 80, "unity_build_target": "VisionOS"},
    {"id": "switch", "name": "Nintendo Switch", "description": "Unity BuildTarget.Switch", "order": 90, "unity_build_target": "Switch"},
    {"id": "ps4", "name": "PlayStation 4", "description": "Unity BuildTarget.PS4", "order": 100, "unity_build_target": "PS4"},
    {"id": "ps5", "name": "PlayStation 5", "description": "Unity BuildTarget.PS5", "order": 110, "unity_build_target": "PS5"},
    {"id": "xboxone", "name": "Xbox One", "description": "Unity BuildTarget.XboxOne", "order": 120, "unity_build_target": "XboxOne"},
    {"id": "xboxseries", "name": "Xbox Series X/S", "description": "Unity BuildTarget.GameCoreXboxSeries", "order": 130, "unity_build_target": "GameCoreXboxSeries"},
    {"id": "embeddedlinux", "name": "Embedded Linux", "description": "Unity BuildTarget.EmbeddedLinux", "order": 140, "unity_build_target": "EmbeddedLinux"},
    {"id": "qnx", "name": "QNX", "description": "Unity BuildTarget.QNX", "order": 150, "unity_build_target": "QNX"},
    {"id": "wsaplayer", "name": "Windows Store (UWP)", "description": "Unity BuildTarget.WSAPlayer", "order": 160, "unity_build_target": "WSAPlayer"},
    {"id": "linuxheadless", "name": "Linux Headless", "description": "Unity BuildTarget.LinuxHeadlessSimulation", "order": 170, "unity_build_target": "LinuxHeadlessSimulation"},
]

DEFAULT_PROJECT_PLATFORMS: List[str] = ["android", "ios"]

VALID_PLATFORMS = frozenset(str(row.get("id") or "").strip().lower() for row in PLATFORM_CATALOG if str(row.get("id") or "").strip())


def is_valid_platform_id(platform_id: str) -> bool:
    return _normalize_platform_id(platform_id) != ""


def _normalize_platform_id(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    return value if value in VALID_PLATFORMS else ""


def get_platform_by_id(platform_id: str) -> Dict[str, Any] | None:
    pid = _normalize_platform_id(platform_id)
    if not pid:
        return None
    for row in PLATFORM_CATALOG:
        if str(row.get("id") or "").strip().lower() == pid:
            return dict(row)
    return None


def get_project_assigned_platform_ids(project_id: str) -> List[str]:
    """返回项目白名单平台；未配置时默认 Android + iOS。"""
    from data.projects import projects_db

    proj = projects_db.get(project_id) or {}
    raw = proj.get("platforms")
    if isinstance(raw, list) and raw:
        return [_normalize_platform_id(x) for x in raw if _normalize_platform_id(x)]
    return list(DEFAULT_PROJECT_PLATFORMS)


def get_disabled_platform_ids(project_id: str) -> List[str]:
    """返回项目内已禁用的平台（仍在白名单，不参与交付线/发布）。"""
    from data.projects import projects_db

    proj = projects_db.get(project_id) or {}
    raw = proj.get("disabled_platforms")
    if not isinstance(raw, list):
        return []
    assigned = set(get_project_assigned_platform_ids(project_id))
    return [_normalize_platform_id(x) for x in raw if _normalize_platform_id(x) and _normalize_platform_id(x) in assigned]


def is_platform_enabled_for_project(project_id: str, platform_id: str) -> bool:
    pid = _normalize_platform_id(platform_id)
    if not pid:
        return False
    return pid not in set(get_disabled_platform_ids(project_id))


def get_platforms_for_project(project_id: str, enabled_only: bool = True) -> List[Dict[str, Any]]:
    """返回项目可用平台列表。enabled_only=True 时排除项目内已禁用的平台。"""
    out: List[Dict[str, Any]] = []
    allowed_ids = set(get_project_assigned_platform_ids(project_id))
    disabled_ids = set(get_disabled_platform_ids(project_id)) if enabled_only else set()
    for row in PLATFORM_CATALOG:
        pid = str(row.get("id") or "").strip().lower()
        if not pid or pid not in allowed_ids:
            continue
        if enabled_only and pid in disabled_ids:
            continue
        out.append(dict(row))
    out.sort(key=lambda x: (int(x.get("order") or 0), x.get("id", "")))
    return out


def get_platform_defs_for_project(project_id: str, enabled_only: bool = True) -> List[Dict[str, str]]:
    return [
        {"value": str(row.get("id") or ""), "label": str(row.get("name") or row.get("id") or "")}
        for row in get_platforms_for_project(project_id, enabled_only=enabled_only)
    ]


def list_platform_catalog() -> List[Dict[str, Any]]:
    return [dict(row) for row in PLATFORM_CATALOG]

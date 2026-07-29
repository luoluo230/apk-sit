# -*- coding: utf-8 -*-
"""Build grid constants and platform → Jenkins job routing."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

BUILD_ROLE_CONTROL = "control"
BUILD_ROLE_ANDROID = "build-android"
BUILD_ROLE_IOS = "build-ios"
BUILD_ROLE_WXMINIGAME = "build-wxminigame"
BUILD_ROLE_RUNTIME = "runtime"

BUILD_ROLES: Dict[str, Dict[str, Any]] = {
    BUILD_ROLE_CONTROL: {
        "label": "",
        "job_name": "",
        "display_name": "控制面",
        "os_allowed": ["windows"],
        "install_script": "scripts/Install-ReleasePlatform.ps1 -Role control",
    },
    BUILD_ROLE_ANDROID: {
        "label": "build-android",
        "job_name": "Android",
        "pipeline_script": "commercial_android_pipeline.sh",
        "display_name": "Android 构建",
        "os_allowed": ["windows"],
        "install_script": "scripts/Install-ReleasePlatform.ps1 -Role build-android",
    },
    BUILD_ROLE_IOS: {
        "label": "build-ios",
        "job_name": "iOS",
        "pipeline_script": "commercial_ios_pipeline.sh",
        "display_name": "iOS 构建",
        "os_allowed": ["darwin", "macos"],
        "install_script": "scripts/install_release_platform.sh --role build-ios",
    },
    BUILD_ROLE_WXMINIGAME: {
        "label": "build-wxminigame",
        "job_name": "WxMinigame",
        "pipeline_script": "commercial_wxminigame_pipeline.sh",
        "display_name": "微信小游戏构建",
        "os_allowed": ["windows"],
        "install_script": "scripts/Install-ReleasePlatform.ps1 -Role build-wxminigame",
    },
}

PLATFORM_ALIASES = {
    "android": "android",
    "ios": "ios",
    "iphone": "ios",
    "iphoneos": "ios",
    "wechat_minigame": "wechat_minigame",
    "wxminigame": "wechat_minigame",
    "minigame": "wechat_minigame",
    "webgl_minigame": "wechat_minigame",
}

PLATFORM_TO_JOB: Dict[str, str] = {
    "android": "Android",
    "ios": "iOS",
    "wechat_minigame": "WxMinigame",
}

PLATFORM_TO_ROLE: Dict[str, str] = {
    "android": BUILD_ROLE_ANDROID,
    "ios": BUILD_ROLE_IOS,
    "wechat_minigame": BUILD_ROLE_WXMINIGAME,
}

ARTIFACT_TYPES: Dict[str, str] = {
    "android": "apk",
    "ios": "ipa",
    "wechat_minigame": "wxgame_bundle",
}


def normalize_build_platform(value: str) -> str:
    raw = str(value or "").strip().lower()
    return PLATFORM_ALIASES.get(raw, raw if raw in PLATFORM_TO_JOB else "android")


def resolve_jenkins_job_for_platform(platform: str, explicit_job: str = "") -> str:
    job = str(explicit_job or "").strip()
    if job:
        return job
    return PLATFORM_TO_JOB.get(normalize_build_platform(platform), "Android")


def resolve_build_role_for_platform(platform: str) -> str:
    return PLATFORM_TO_ROLE.get(normalize_build_platform(platform), BUILD_ROLE_ANDROID)


def resolve_pipeline_script(platform: str) -> str:
    role = resolve_build_role_for_platform(platform)
    meta = BUILD_ROLES.get(role) or BUILD_ROLES[BUILD_ROLE_ANDROID]
    return str(meta.get("pipeline_script") or "commercial_android_pipeline.sh")


def resolve_assigned_node(platform: str) -> str:
    role = resolve_build_role_for_platform(platform)
    return str((BUILD_ROLES.get(role) or {}).get("label") or "")


def list_build_roles() -> List[Dict[str, Any]]:
    rows = []
    for role_id, meta in BUILD_ROLES.items():
        row = dict(meta)
        row["role_id"] = role_id
        rows.append(row)
    return rows


def artifact_type_for_platform(platform: str) -> str:
    return ARTIFACT_TYPES.get(normalize_build_platform(platform), "apk")

# -*- coding: utf-8 -*-
"""Normalize commercial release_plan / Jenkins params per Web-Jenkins-Unity-ParameterSpec."""

from __future__ import annotations

import os
import re
from typing import Any
from models.data import get_channel_by_id

DEFAULT_PROJECT_ROOT = "MyGame1"
DEFAULT_RESOURCE_SERVER = os.environ.get(
    "COMMERCIAL_RESOURCE_SERVER_URL",
    "https://wlhotupdate1.oss-cn-beijing.aliyuncs.com/MyGame1",
).rstrip("/")

_STAGE_TO_RELEASE_ENV = {
    "dev": "Development",
    "development": "Development",
    "test": "Testing",
    "testing": "Testing",
    "stage": "Staging",
    "staging": "Staging",
    "prod": "Production",
    "production": "Production",
}


def normalize_release_environment(value: str, version_stage: str = "") -> str:
    env = (value or "").strip()
    if env in ("Development", "Testing", "Staging", "Production"):
        return env
    stage = (version_stage or "").strip().lower()
    return _STAGE_TO_RELEASE_ENV.get(stage, "Development")


def resolve_config_remote_prefix(raw: str) -> str:
    """OSS ProjectRoot: single segment MyGame1 only (no /)."""
    prefix = (raw or "").strip().strip("/")
    if not prefix or "/" in prefix:
        return DEFAULT_PROJECT_ROOT
    return prefix


def normalize_step3_targets(raw: str) -> str:
    """Step3 RELEASE_TARGETS: code/resource only; config belongs to Step1."""
    parts = [p.strip().lower() for p in re.split(r"[,;]+", raw or "") if p.strip()]
    if not parts:
        return "code,resource"
    if "all" in parts:
        return "code,resource"
    allowed = []
    for part in parts:
        if part in ("code", "resource") and part not in allowed:
            allowed.append(part)
    return ",".join(allowed) if allowed else "code,resource"


def normalize_release_channel(value: str) -> str:
    """Normalize releaseChannel to semantic channel key (e.g. wechat), not numeric channel id."""
    ch = (value or "").strip()
    if not ch:
        return "common"
    cfg = get_channel_by_id(ch)
    if isinstance(cfg, dict):
        bp = str(cfg.get("build_param") or "").strip()
        if bp:
            m = re.search(r"CHANNEL\s*=\s*([A-Za-z0-9_.-]+)", bp, flags=re.IGNORECASE)
            if m and m.group(1):
                return m.group(1)
            if not re.fullmatch(r"\d+", bp):
                return bp
        subdir = str(cfg.get("apk_subdir") or "").strip()
        if subdir and not re.fullmatch(r"\d+", subdir):
            return subdir
    if ch and not re.fullmatch(r"\d+", ch):
        return ch
    return ch or "common"


def normalize_release_platform(value: str) -> str:
    """Normalize platform segment for remote path compatibility."""
    p = (value or "").strip().lower()
    if p in ("ios", "iphone", "iphoneos"):
        return "ios"
    return "android"


def build_version_relative_path(
    release_environment: str,
    release_channel: str,
    release_platform: str,
    release_version: str,
    version_code: str,
) -> str:
    version_folder = f"Version_{release_version}"
    code_segment = f"/{version_code}" if str(version_code or "").strip() else ""
    return (
        f"{release_environment}/{release_channel}/{release_platform}/"
        f"{version_folder}{code_segment}"
    )


def build_runtime_resolve_paths(
    *,
    resource_server_url: str,
    release_environment: str,
    release_channel: str,
    release_platform: str,
    release_version: str,
    version_code: str,
) -> dict[str, str]:
    rel = build_version_relative_path(
        release_environment, release_channel, release_platform, release_version, version_code
    )
    base = (resource_server_url or DEFAULT_RESOURCE_SERVER).rstrip("/")
    return {
        "resource_relative_path": rel,
        "config_relative_path": f"{rel}/config",
        "code_relative_path": f"{rel}/code",
        "config_manifest_path": f"{base}/{rel}/config/config_patch_manifest.json",
        "config_manifest_signature_path": f"{base}/{rel}/config/config_patch_manifest.signature.json",
        "code_manifest_path": f"{base}/{rel}/code/code_patch_manifest.json",
        "code_manifest_signature_path": f"{base}/{rel}/code/code_patch_manifest.signature.json",
        "catalog_file_name": f"catalog_{release_version}.bin",
    }


def apply_release_mode(
    params: dict[str, str],
    plan: dict[str, Any],
    release_mode: str,
    release_targets: str,
) -> dict[str, str]:
    """Map Web release_mode to Jenkins step switches (build vs publish vs activate)."""
    mode = (release_mode or "build-upload").strip().lower()
    params["RELEASE_MODE"] = release_mode
    params["COMMERCIAL_RELEASE_MODE"] = release_mode
    params["RELEASE_TARGETS"] = release_targets

    if mode == "activate":
        params["CONFIG_EXPORT_ENABLED"] = "false"
        params["RESOURCE_BUILD_ENABLED"] = "false"
        params["HOT_RELEASE_ENABLED"] = "true"
        params["RELEASE_UPLOAD"] = "false"
        params["RELEASE_ACTIVATE"] = "true"
        params["APK_BUILD_ENABLED"] = "false"
        return params

    if mode == "rollback":
        params["CONFIG_EXPORT_ENABLED"] = "false"
        params["RESOURCE_BUILD_ENABLED"] = "false"
        params["HOT_RELEASE_ENABLED"] = "true"
        params["RELEASE_UPLOAD"] = "false"
        params["RELEASE_ACTIVATE"] = "false"
        params["APK_BUILD_ENABLED"] = "false"
        return params

    if mode == "build":
        params["RELEASE_UPLOAD"] = "false"
        params["RELEASE_ACTIVATE"] = "false"
    elif mode == "upload":
        params["CONFIG_EXPORT_ENABLED"] = "true" if plan.get("configEnabled", False) else "false"
        params["RESOURCE_BUILD_ENABLED"] = "false"
        params["RELEASE_UPLOAD"] = "true"
        params["RELEASE_ACTIVATE"] = "true" if plan.get("releaseActivate") else "false"
    else:
        # build-upload (default full pipeline): Step1/2 构建，Step3 shell 将 CLI 映射为 upload
        params["RELEASE_UPLOAD"] = "true" if plan.get("releaseUpload", True) else "false"
        if plan.get("releaseActivate"):
            params["RELEASE_ACTIVATE"] = "true"

    return params


def resolve_step3_cli_mode(release_mode: str) -> str:
    """CommercialReleaseCli Step3：build/build-upload → upload（构建已在 Step1/2）。"""
    mode = (release_mode or "build-upload").strip().lower()
    if mode in ("build", "build-upload"):
        return "upload"
    return mode


def plan_to_jenkins_params(
    plan: dict[str, Any],
    plan_filepath: str,
    version_obj: dict[str, Any] | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Build Jenkins buildWithParameters dict + normalized automation_plan patch."""
    version_obj = version_obj or {}
    release_mode = str(plan.get("releaseMode") or "build-upload")
    release_version = str(plan.get("releaseVersion") or "").strip()
    if not release_version:
        release_version = str(version_obj.get("version_name") or "").strip()
    if not release_version:
        release_version = "0.0.1"
    release_env = normalize_release_environment(
        str(plan.get("releaseEnvironment") or ""),
        str(version_obj.get("stage") or ""),
    )
    release_channel = normalize_release_channel(str(plan.get("releaseChannel") or "common"))
    release_platform = normalize_release_platform(str(plan.get("releasePlatform") or "Android"))
    version_code = str(
        plan.get("versionCode") or version_obj.get("version_code") or ""
    ).strip()

    raw_targets = str(plan.get("releaseTargets") or "")
    config_enabled = bool(plan.get("configEnabled", True))
    if "config" in [t.strip().lower() for t in raw_targets.split(",") if t.strip()]:
        config_enabled = True
    release_targets = normalize_step3_targets(raw_targets)

    config_prefix = resolve_config_remote_prefix(str(plan.get("configRemotePrefix") or ""))

    app_name = str(plan.get("appName") or plan.get("targetProject") or "GameKu")
    params: dict[str, str] = {
        "RELEASE_VERSION": release_version,
        "RELEASE_ENVIRONMENT": release_env,
        "RELEASE_CHANNEL": release_channel,
        "RELEASE_PLATFORM": release_platform,
        "RELEASE_TARGETS": release_targets,
        "RELEASE_HOT_LABELS": str(plan.get("releaseHotLabels") or ""),
        "RELEASE_UPLOAD_MODE": str(plan.get("releaseUploadMode") or "incremental"),
        "RELEASE_PLAN_FILE": plan_filepath,
        "VERSION_NAME": release_version,
        "APP_NAME": app_name,
        "CONFIG_EXPORT_ENABLED": "true" if config_enabled else "false",
        "CONFIG_ENVIRONMENT": release_env,
        "CONFIG_PLATFORM": release_platform,
        "CONFIG_CLIENT_VERSION": release_version,
        "CONFIG_REMOTE_PREFIX": config_prefix,
        "CONFIG_INCLUDE_CODE": "true" if plan.get("configIncludeCode") else "false",
        "RESOURCE_BUILD_ENABLED": "true" if plan.get("resourceEnabled", True) else "false",
        "RESOURCE_PROVIDER": str(plan.get("resourceProvider") or "addressables-v2"),
        "RESOURCE_SCENARIO": str(plan.get("resourceScenario") or "default"),
        "HOT_RELEASE_ENABLED": "true" if plan.get("hotReleaseEnabled", True) else "false",
        "APK_BUILD_ENABLED": "true" if plan.get("apkBuildEnabled") else "false",
        "RUN_BASE_APK_BUILD_FIRST": (
            "true"
            if plan.get("runBaseApkBuildFirst", plan.get("apkBuildEnabled", False))
            else "false"
        ),
        "RELEASE_UPLOAD": "true" if plan.get("releaseUpload", True) else "false",
    }
    if version_code:
        params["VERSION_CODE"] = version_code

    unity_project_path = str(plan.get("unityProjectPath") or "").strip()
    if unity_project_path:
        params["UNITY_PROJECT_PATH"] = unity_project_path
    if plan.get("unityVersion"):
        params["UNITY_VERSION"] = str(plan.get("unityVersion"))
    if plan.get("gitBranch"):
        params["GIT_BRANCH"] = str(plan.get("gitBranch"))
    if plan.get("outputBaseDir"):
        params["OUTPUT_BASE_DIR"] = str(plan.get("outputBaseDir"))

    version_channel = str(version_obj.get("channel") or "").strip()
    if version_channel and not params.get("CHANNEL"):
        params["CHANNEL"] = version_channel

    saved = version_obj.get("jenkins_params") if isinstance(version_obj.get("jenkins_params"), dict) else {}
    for key in ("VERSION_CODE", "UNITY_VERSION", "GIT_BRANCH", "UNITY_PROJECT_PATH", "CHANNEL"):
        if saved.get(key) and not params.get(key):
            params[key] = str(saved[key])

    if release_mode == "rollback" and plan.get("releaseRollbackTarget"):
        params["RELEASE_ROLLBACK_TARGET"] = str(plan.get("releaseRollbackTarget"))

    for opt_key, param_key in (
        ("releaseCompressionOverride", "RELEASE_COMPRESSION_OVERRIDE"),
        ("releaseEncryptionOverride", "RELEASE_ENCRYPTION_OVERRIDE"),
        ("releaseSignatureOverride", "RELEASE_SIGNATURE_OVERRIDE"),
        ("codeCompression", "RELEASE_CODE_COMPRESSION"),
        ("codeEncryption", "RELEASE_CODE_ENCRYPTION"),
        ("codeSignature", "RELEASE_CODE_SIGNATURE"),
        ("codeUnits", "RELEASE_CODE_UNITS"),
        ("resourceCompression", "RELEASE_RESOURCE_COMPRESSION"),
        ("resourceEncryption", "RELEASE_RESOURCE_ENCRYPTION"),
        ("resourceSignature", "RELEASE_RESOURCE_SIGNATURE"),
        ("resourceUnits", "RELEASE_RESOURCE_UNITS"),
    ):
        if plan.get(opt_key):
            params[param_key] = str(plan[opt_key])

    apply_release_mode(params, plan, release_mode, release_targets)

    plan_patch = {
        "versionCode": version_code,
        "configRemotePrefix": config_prefix,
        "releaseTargets": release_targets,
        "configEnabled": config_enabled,
        "releaseEnvironment": release_env,
    }
    return params, plan_patch

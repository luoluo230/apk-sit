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
    project_id: str = "",
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
            "true" if plan.get("runBaseApkBuildFirst") else "false"
        ),
        "RELEASE_UPLOAD": "true" if plan.get("releaseUpload", True) else "false",
    }
    if version_code:
        params["VERSION_CODE"] = version_code

    pid = str(project_id or plan.get("projectId") or "").strip()
    if pid:
        params["PROJECT_ID"] = pid
    vid = str((version_obj or {}).get("id") or plan.get("versionId") or "").strip()
    if vid:
        params["VERSION_ID"] = vid
    params["RELEASE_PROJECT_ROOT"] = config_prefix or DEFAULT_PROJECT_ROOT

    unity_project_path = str(plan.get("unityProjectPath") or "").strip()
    if unity_project_path:
        params["UNITY_PROJECT_PATH"] = unity_project_path
    if plan.get("unityVersion"):
        params["UNITY_VERSION"] = str(plan.get("unityVersion"))
    if plan.get("gitBranch"):
        params["GIT_BRANCH"] = str(plan.get("gitBranch"))
    if plan.get("outputBaseDir"):
        params["OUTPUT_BASE_DIR"] = str(plan.get("outputBaseDir"))
    resource_server_url = str(
        plan.get("resourceServerUrl")
        or version_obj.get("resource_server_url")
        or ""
    ).strip()
    if resource_server_url:
        params["RESOURCE_SERVER_URL"] = resource_server_url.rstrip("/")

    version_channel = str(version_obj.get("channel") or "").strip()
    if version_channel and not params.get("CHANNEL"):
        params["CHANNEL"] = version_channel
    if version_channel:
        params["VERSION_CHANNEL_ID"] = version_channel

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


def plan_defaults_from_pipeline(version_obj: dict[str, Any] | None, project_id: str = "") -> dict[str, Any]:
    """Build commercial release plan defaults from version.pipeline (no release-order payload)."""
    version_obj = version_obj or {}
    pipeline = version_obj.get("pipeline") if isinstance(version_obj.get("pipeline"), dict) else {}
    config_export = pipeline.get("config_export") or {}
    resource_build = pipeline.get("resource_build") or {}
    hot_release = pipeline.get("hot_release") or {}
    apk_build = pipeline.get("apk_build") or {}
    if not isinstance(config_export, dict):
        config_export = {}
    if not isinstance(resource_build, dict):
        resource_build = {}
    if not isinstance(hot_release, dict):
        hot_release = {}
    if not isinstance(apk_build, dict):
        apk_build = {}
    plan: dict[str, Any] = {
        "configEnabled": config_export.get("enabled"),
        "configRemotePrefix": config_export.get("remote_prefix"),
        "configIncludeCode": config_export.get("include_code"),
        "resourceEnabled": resource_build.get("enabled"),
        "resourceProvider": resource_build.get("provider"),
        "resourceScenario": resource_build.get("scenario"),
        "hotReleaseEnabled": hot_release.get("enabled"),
        "apkBuildEnabled": apk_build.get("enabled"),
        "releaseMode": hot_release.get("release_mode"),
        "releaseEnvironment": hot_release.get("release_environment"),
        "releaseChannel": hot_release.get("release_channel"),
        "releaseTargets": hot_release.get("release_targets"),
        "releaseHotLabels": hot_release.get("release_hot_labels"),
        "releaseUploadMode": hot_release.get("release_upload_mode"),
        "releaseRollbackTarget": hot_release.get("release_rollback_target"),
        "releaseCompressionOverride": hot_release.get("release_compression_override"),
        "releaseEncryptionOverride": hot_release.get("release_encryption_override"),
        "releaseSignatureOverride": hot_release.get("release_signature_override"),
        "codeEnabled": hot_release.get("code_enabled"),
        "codeCompression": hot_release.get("code_compression"),
        "codeEncryption": hot_release.get("code_encryption"),
        "codeSignature": hot_release.get("code_signature"),
        "codeUnits": hot_release.get("code_units"),
        "resourceCompression": hot_release.get("resource_compression"),
        "resourceEncryption": hot_release.get("resource_encryption"),
        "resourceSignature": hot_release.get("resource_signature"),
        "resourceUnits": hot_release.get("resource_units"),
        "appName": apk_build.get("app_name"),
        "unityVersion": apk_build.get("unity_version"),
        "gitBranch": apk_build.get("git_branch") or pipeline.get("git_branch"),
        "outputBaseDir": apk_build.get("output_base_dir"),
        "unityProjectPath": apk_build.get("unity_project_path"),
        "versionCode": version_obj.get("version_code"),
        "releaseVersion": version_obj.get("version_name"),
        "releasePlatform": config_export.get("platform") or version_obj.get("platform"),
    }
    pid = str(project_id or "").strip()
    if pid:
        try:
            from services.admin.project_build_config_service import get_project_build_config

            pbc = get_project_build_config(pid)
            if not str(plan.get("appName") or "").strip():
                plan["appName"] = (pbc.get("app_name") or pid).strip()
            if not str(plan.get("unityProjectPath") or "").strip():
                plan["unityProjectPath"] = (pbc.get("unity_project_path") or "").strip()
            if not str(plan.get("outputBaseDir") or "").strip():
                plan["outputBaseDir"] = (pbc.get("output_base_dir") or "").strip()
            if not str(plan.get("gitBranch") or "").strip() and (pbc.get("default_git_branch") or "").strip():
                plan["gitBranch"] = (pbc.get("default_git_branch") or "").strip()
        except Exception:
            pass
    return {k: v for k, v in plan.items() if v is not None and str(v).strip() != ""}

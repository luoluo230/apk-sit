#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GomeKu 生产环境 1.0.0 Android 全链路：配置管线 → Jenkins 构建 → Unity 客户端热更验收。"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import load_dotenv

load_dotenv()

PROJECT_ID = "GomeKu"
USERNAME = "admin"
ENV_KEY = "production"
PLATFORM = "android"
VERSION_NAME = "1.0.0"
VERSION_CODE = "1"
CHANNEL_ID = "1001"
JENKINS_INSTANCE_ID = "10477171"
JENKINS_JOB_ID = "Android"
UNITY_PROJECT = "E:\\maclient"
OUTPUT_BASE = "E:\\maclient\\BuildOutput"
GIT_BRANCH = "codex/replace-logging-with-custom-logger-fvtg9m"
UNITY_VERSION = "6000.3.15f1"
GIT_URL = "https://github.com/luoluo230/MAClient.git"
RESOURCE_SERVER = "https://wlhotupdate1.oss-cn-beijing.aliyuncs.com/MyGame1"
CATALOG_NAME = "catalog_1.0.0.bin"
API_BASE = "http://127.0.0.1:5003"
BUILD_POLL_SEC = 30
BUILD_TIMEOUT_SEC = 7200


def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _pipeline_template() -> dict:
    return {
        "config_export": {
            "enabled": True,
            "remote_prefix": "MyGame1",
            "client_version": VERSION_NAME,
            "environment": "Production",
            "platform": "Android",
            "include_code": False,
        },
        "resource_build": {
            "enabled": True,
            "provider": "addressables-v2",
            "scenario": "default",
        },
        "hot_release": {
            "enabled": True,
            "release_mode": "build-upload",
            "release_environment": "Production",
            "release_channel": CHANNEL_ID,
            "release_targets": "code,resource",
            "release_upload_mode": "incremental",
            "release_hot_labels": "hotupdate,aotmeta",
            "code_enabled": True,
            "code_compression": "Zip",
            "code_encryption": "Aes",
            "code_signature": "builtin-signature",
            "code_units": "aotmeta, hotupdate, scriptpatch, symbols",
            "resource_enabled": True,
            "resource_compression": "None",
            "resource_encryption": "None",
            "resource_signature": "builtin-signature",
            "resource_units": "addressable, hotupdate, optional, platform, hd, streaming",
        },
        "apk_build": {
            "enabled": True,
            "git_branch": GIT_BRANCH,
            "unity_version": UNITY_VERSION,
            "app_name": "GomeKu",
            "unity_project_path": UNITY_PROJECT,
            "output_base_dir": OUTPUT_BASE,
            "package_format": "apk",
        },
        "git_branch": GIT_BRANCH,
    }


def setup_project() -> None:
    from repositories.admin import projects_repo
    from services.admin.project_build_config_service import apply_build_config_to_project_payload
    from services.release.env_registry import get_project_env_defs

    proj = projects_repo.get_project(PROJECT_ID)
    if not proj:
        raise RuntimeError("项目 GomeKu 不存在")

    apply_build_config_to_project_payload(
        proj,
        {
            "build_config": {
                "app_name": "GomeKu",
                "git_url": GIT_URL,
                "git_workspace": UNITY_PROJECT,
                "unity_project_path": UNITY_PROJECT,
                "output_base_dir": OUTPUT_BASE,
                "default_git_branch": GIT_BRANCH,
                "git_branches": [GIT_BRANCH, "main"],
            }
        },
    )
    proj["jenkins_instance_id"] = JENKINS_INSTANCE_ID
    proj["jenkins_job_id"] = JENKINS_JOB_ID

    defs = get_project_env_defs(PROJECT_ID)
    for row in defs:
        if str(row.get("env_key") or "").lower() == ENV_KEY:
            row["channels"] = [CHANNEL_ID]
            row["platforms"] = [PLATFORM]
            break
    proj["release_environments"] = defs
    projects_repo.save_projects_repo()
    _log("已更新项目 build_config、Jenkins 绑定与生产环境交付范围")


def setup_version_group() -> None:
    from services.admin import version_service as vs

    data = {
        "version_name": VERSION_NAME,
        "env_key": ENV_KEY,
        "platform": PLATFORM,
        "version_mode": "commercial",
        "status": "active",
        "pipeline_template": _pipeline_template(),
        "jenkins_instance_id": JENKINS_INSTANCE_ID,
        "jenkins_job_id": JENKINS_JOB_ID,
        "resource_server_url": RESOURCE_SERVER,
        "catalog_file_name": CATALOG_NAME,
        "min_client_version": VERSION_NAME,
        "rollout_percentage": 100,
        "force_update": False,
        "is_revoked": False,
    }
    groups = vs._load_version_groups_meta(PROJECT_ID)
    idx = vs._find_group_meta_index(groups, VERSION_NAME, ENV_KEY, PROJECT_ID, platform=PLATFORM)
    if idx >= 0:
        result, code = vs.update_version_group(PROJECT_ID, USERNAME, data)
    else:
        result, code = vs.create_version_group(PROJECT_ID, USERNAME, data)
    if code not in (200, 201):
        raise RuntimeError(f"配置版本组管线失败 ({code}): {result}")
    _log("已配置生产版本组 1.0.0 android 管线")


def ensure_production_vc() -> str:
    from models.data import project_versions_db
    from repositories.admin import versions_repo
    from services.admin import version_service as vs
    from services.release.env_registry import normalize_release_env_key

    versions = versions_repo.list_versions(PROJECT_ID)
    for row in versions:
        if (
            str(row.get("version_name")) == VERSION_NAME
            and normalize_release_env_key(row.get("env_key") or "", project_id=PROJECT_ID) == ENV_KEY
            and str(row.get("platform") or "").lower() == PLATFORM
            and str(row.get("channel")) == CHANNEL_ID
            and str(row.get("version_code")) == VERSION_CODE
        ):
            vid = str(row.get("id") or "")
            _log(f"复用已有 VersionCode id={vid}")
            return vid

    payload = {
        "version_name": VERSION_NAME,
        "version_code": VERSION_CODE,
        "channel": CHANNEL_ID,
        "channel_id": CHANNEL_ID,
        "platform": PLATFORM,
        "env_key": ENV_KEY,
        "stage": "production",
        "version_mode": "commercial",
        "version_status": "draft",
    }
    result, code = vs.create_version(PROJECT_ID, USERNAME, payload)
    if code != 200:
        raise RuntimeError(f"创建 VersionCode 失败 ({code}): {result}")
    vid = str(result.get("version", {}).get("id") or "")
    if not vid:
        versions = project_versions_db.get(PROJECT_ID, [])
        for row in versions:
            if (
                str(row.get("version_name")) == VERSION_NAME
                and normalize_release_env_key(row.get("env_key") or "", project_id=PROJECT_ID) == ENV_KEY
                and str(row.get("channel")) == CHANNEL_ID
            ):
                vid = str(row.get("id") or "")
                break
    if not vid:
        raise RuntimeError("创建 VersionCode 后未找到 id")
    _log(f"已创建生产 VersionCode id={vid}")
    return vid


def trigger_build(version_id: str) -> tuple[str, int]:
    from services import jenkins_manager as jm
    from services.admin.version_service import resolve_effective_pipeline
    from services.commercial_release_plan import plan_defaults_from_pipeline
    from services.release.release_order_service import ensure_draft_release_order, request_build
    from repositories.admin import versions_repo

    versions = versions_repo.list_versions(PROJECT_ID)
    version = next((v for v in versions if str(v.get("id")) == version_id), None)
    if not version:
        raise RuntimeError("VersionCode 不存在")

    pipeline = resolve_effective_pipeline(PROJECT_ID, version)
    if not pipeline:
        raise RuntimeError("有效管线为空")
    version_for_plan = dict(version)
    version_for_plan["pipeline"] = pipeline
    plan = plan_defaults_from_pipeline(version_for_plan, project_id=PROJECT_ID)
    git_branch = str(plan.get("gitBranch") or GIT_BRANCH)
    ok, err = jm.prepare_instance_for_project_build(
        JENKINS_INSTANCE_ID,
        PROJECT_ID,
        git_branch=git_branch,
        plan=plan,
    )
    if not ok:
        raise RuntimeError(f"Jenkins 环境准备失败: {err}")
    _log("Jenkins 实例环境已同步 (Windows 路径 + Unity 6000.3.15f1)")

    order = ensure_draft_release_order(PROJECT_ID, version_id, USERNAME, reason="生产 1.0.0 全链路 E2E")
    order_id = str(order.get("release_order_id") or "")
    if not order_id:
        raise RuntimeError("无法创建发布单")
    _log(f"发布单 {order_id} 已就绪，触发 Jenkins 构建…")
    updated = request_build(PROJECT_ID, order_id, USERNAME)
    payload = updated.get("payload") or {}
    build_no = int(payload.get("build_job_id") or 0)
    if not build_no:
        raise RuntimeError("Jenkins 构建号为空")
    return order_id, build_no


def poll_jenkins_build(build_number: int) -> bool:
    from services import jenkins as jenkins_svc
    from services import jenkins_manager as jm

    base_url = jm.get_jenkins_url_for_instance(instance_id=JENKINS_INSTANCE_ID)
    builds_dir = jm.get_builds_dir_for_instance(instance_id=JENKINS_INSTANCE_ID)
    deadline = time.time() + BUILD_TIMEOUT_SEC
    while time.time() < deadline:
        status = jenkins_svc.get_build_status(
            build_number,
            base_url=base_url,
            builds_dir=builds_dir,
            instance_id=JENKINS_INSTANCE_ID,
        )
        _log(f"Jenkins #{build_number} 状态: {status}")
        if status == "SUCCESS":
            return True
        if status in ("FAILURE", "ABORTED", "UNSTABLE"):
            log_tail = jenkins_svc.get_build_log_content(
                build_number,
                max_chars=8000,
                base_url=base_url,
                builds_dir=builds_dir,
                instance_id=JENKINS_INSTANCE_ID,
            )
            print(log_tail[-8000:], flush=True)
            return False
        time.sleep(BUILD_POLL_SEC)
    raise TimeoutError(f"Jenkins 构建 #{build_number} 超时 ({BUILD_TIMEOUT_SEC}s)")


def verify_version_artifacts(version_id: str) -> dict:
    from repositories.admin import versions_repo

    versions = versions_repo.list_versions(PROJECT_ID)
    row = next((v for v in versions if str(v.get("id")) == version_id), None)
    if not row:
        raise RuntimeError("版本行丢失")
    keys = ("apk_path", "resource_path", "config_path", "resource_server_url", "catalog_file_name")
    snapshot = {k: row.get(k) for k in keys}
    _log(f"版本产物: {json.dumps(snapshot, ensure_ascii=False)}")
    missing = [k for k in ("apk_path", "resource_path") if not str(row.get(k) or "").strip()]
    if missing:
        raise RuntimeError(f"构建后缺少产物字段: {missing}")
    return row


def run_unity_acceptance() -> dict:
    from services.unity_client_hotupdate_runner import run_unity_client_startup_acceptance

    _log("启动 Unity 客户端热更验收 (Production / wechat / 1.0.0)…")
    return run_unity_client_startup_acceptance(
        unity_project=UNITY_PROJECT,
        api_base=API_BASE,
        project_id=PROJECT_ID,
        channel="wechat",
        environment="Production",
        version_name=VERSION_NAME,
        version_code=VERSION_CODE,
        platform="Android",
        resource_server=RESOURCE_SERVER,
        scenario="basic",
        timeout_sec=120,
        use_unified_bootstrap=True,
    )


def main() -> int:
    _log("=== GomeKu 生产 1.0.0 Android 全链路 E2E ===")
    from app_new import app
    from models.db import init_db

    init_db()

    with app.test_request_context():
        from flask import session

        session["user"] = USERNAME
        setup_project()
        setup_version_group()
        version_id = ensure_production_vc()
        order_id, build_no = trigger_build(version_id)
        _log(f"Jenkins 构建已触发 order={order_id} build=#{build_no}")

        if not poll_jenkins_build(build_no):
            _log("FAIL: Jenkins 构建失败")
            return 1

        _log("Jenkins 构建 SUCCESS")
        verify_version_artifacts(version_id)

    result = run_unity_acceptance()
    passed = bool(result.get("passed"))
    _log(f"Unity 验收: {'PASS' if passed else 'FAIL'} — {result.get('summary')}")
    _log(f"报告: {result.get('report_path')}")
    print("RESULT:", "PASS" if passed else "FAIL", flush=True)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())

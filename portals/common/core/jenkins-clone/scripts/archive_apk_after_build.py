#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Jenkins Step4 后：将 APK 归档到 apk-site 本地目录并更新版本落盘信息。"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def _repo_core() -> Path:
    script = Path(__file__).resolve()
    candidates = [
        script.parents[4] / "portals" / "common" / "core",
        Path(os.environ.get("APK_SITE_CORE", "")),
    ]
    for p in candidates:
        if p.is_dir():
            return p
    raise SystemExit(f"找不到 apk-site core 目录: {candidates}")


def _parse_oss_remote_from_log(log_path: Path) -> str:
    if not log_path.is_file():
        return ""
    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    matches = re.findall(r"remote=([^\s]+/apk/[^\s]+\.apk)", text)
    return matches[-1].strip() if matches else ""


def main() -> int:
    apk_file = os.environ.get("APK_FILE", "").strip()
    if not apk_file or not Path(apk_file).is_file():
        print(f"ERROR: APK 文件不存在: {apk_file or '(未设置 APK_FILE)'}", file=sys.stderr)
        return 1

    core = _repo_core()
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))

    from services.apk_artifact_service import (  # noqa: WPS433
        archive_apk,
        resolve_version_id,
    )

    project_id = os.environ.get("PROJECT_ID", "GomeKu").strip()
    version_id = os.environ.get("VERSION_ID", "").strip()
    version_code = os.environ.get("VERSION_CODE", "").strip()
    version_name = os.environ.get("VERSION_NAME", os.environ.get("RELEASE_VERSION", "1.0.0")).strip()
    app_name = os.environ.get("APP_NAME", "GomeKu").strip()
    release_channel = os.environ.get("RELEASE_CHANNEL", os.environ.get("CHANNEL", "wechat")).strip()
    release_env = os.environ.get("RELEASE_ENVIRONMENT", "Development").strip()
    stage = os.environ.get("VERSION_STAGE", "dev").strip() or "dev"
    unity_project = os.environ.get("UNITY_PROJECT_PATH", "").strip()
    build_number = os.environ.get("BUILD_NUMBER", "").strip()
    log_file = os.environ.get("UNITY_LOG", os.environ.get("APK_UPLOAD_LOG", "")).strip()
    channel_id = os.environ.get("VERSION_CHANNEL_ID", os.environ.get("CHANNEL_ID", "")).strip()

    if not version_id:
        version_id = resolve_version_id(
            project_id,
            version_code=version_code,
            version_name=version_name,
            channel=channel_id,
            stage=stage,
        )
        if version_id:
            print(f"OK: 解析 VERSION_ID={version_id} (project={project_id} vc={version_code})")

    oss_remote = os.environ.get("OSS_APK_REMOTE_KEY", "").strip()
    if not oss_remote and log_file:
        oss_remote = _parse_oss_remote_from_log(Path(log_file))
    if not oss_remote and version_code:
        oss_remote = (
            f"MyGame1/{release_env}/{release_channel}/android/apk/"
            f"{app_name}_{version_name}_vc{version_code}.apk"
        )

    result = archive_apk(
        apk_file=apk_file,
        app_name=app_name,
        release_version=version_name,
        version_code=version_code or "0",
        release_channel=release_channel,
        release_environment=release_env,
        stage=stage,
        oss_remote_key=oss_remote,
        unity_project_path=unity_project,
        project_id=project_id,
        version_id=version_id,
        build_number=int(build_number) if build_number.isdigit() else None,
    )

    print(f"OK: 本地归档 -> {result.get('pub_download_path')}")
    if version_id:
        print(f"OK: 版本落盘已写入 version_id={version_id}")
    else:
        print("WARN: 未解析到 VERSION_ID，仅完成本地文件归档", file=sys.stderr)
    if oss_remote:
        print(f"OK: OSS remote -> {oss_remote}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

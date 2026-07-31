# -*- coding: utf-8 -*-
"""Local artifact landing + OSS key helpers (local → oss → external)."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from services.build.build_grid import artifact_type_for_platform, normalize_build_platform

_CORE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_REPO_ROOT = os.path.abspath(os.path.join(_CORE_ROOT, "..", "..", ".."))


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_landing_root() -> str:
    custom = (os.getenv("ARTIFACT_LANDING_ROOT") or "").strip()
    if custom:
        return custom
    return os.path.join(_REPO_ROOT, "data", "artifacts")


def build_landing_dir(
    project_id: str,
    scope_id: str,
    build_number: str,
    *,
    platform: str = "android",
) -> str:
    plat = normalize_build_platform(platform)
    safe_scope = str(scope_id or "unknown").replace(":", "_").replace("/", "_")
    path = os.path.join(
        artifact_landing_root(),
        str(project_id or "unknown"),
        safe_scope,
        str(build_number or "0"),
        plat,
    )
    os.makedirs(path, exist_ok=True)
    return path


def landing_manifest_path(landing_dir: str) -> str:
    return os.path.join(landing_dir, "artifact_manifest.json")


def write_landing_manifest(landing_dir: str, payload: Dict[str, Any]) -> str:
    os.makedirs(landing_dir, exist_ok=True)
    body = dict(payload or {})
    body["landed_at"] = _now_iso()
    path = landing_manifest_path(landing_dir)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(body, fh, ensure_ascii=False, indent=2)
    return path


def land_file(
    source_path: str,
    landing_dir: str,
    *,
    dest_name: str = "",
) -> str:
    if not source_path or not os.path.isfile(source_path):
        raise FileNotFoundError(f"源产物不存在: {source_path}")
    os.makedirs(landing_dir, exist_ok=True)
    name = dest_name or os.path.basename(source_path)
    dest = os.path.join(landing_dir, name)
    shutil.copy2(source_path, dest)
    return dest


def oss_object_key(
    *,
    project_root: str,
    release_environment: str,
    release_channel: str,
    platform: str,
    artifact_file_name: str,
    subdir: str = "artifacts",
) -> str:
    plat = normalize_build_platform(platform)
    oss_plat = "iOS" if plat == "ios" else ("WebGL" if plat == "wechat_minigame" else "android")
    root = str(project_root or "MyGame1").strip().strip("/")
    env = str(release_environment or "Development")
    ch = str(release_channel or "common")
    fname = str(artifact_file_name or "artifact.bin").strip()
    return f"{root}/{env}/{ch}/{oss_plat}/{subdir}/{fname}"


def default_artifact_type(platform: str) -> str:
    return artifact_type_for_platform(platform)


def read_landing_manifest(landing_dir: str) -> Dict[str, Any]:
    path = landing_manifest_path(landing_dir)
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}

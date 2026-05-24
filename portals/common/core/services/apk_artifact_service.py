# -*- coding: utf-8 -*-
"""APK 本地备份 + 本地/OSS 双份下载二维码 + 版本/下载中心元数据。"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import qrcode

from config import Config
from models.data import get_channel_by_id, parse_apk_metadata, save_project_versions, project_versions_db
from services.startup import get_canonical_base_url


def _safe_segment(value: str, default: str = "common") -> str:
    seg = re.sub(r"[^A-Za-z0-9_.-]+", "_", (value or "").strip()) or default
    return seg


def _qr_png_dataurl(text: str) -> str:
    import base64

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=8, border=3)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _save_qr_png(text: str, out_path: Path) -> str:
    import base64

    dataurl = _qr_png_dataurl(text)
    raw = base64.b64decode(dataurl.split(",", 1)[1])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(raw)
    return str(out_path)


def _meta_path_for_apk(apk_full_path: str | Path) -> Path:
    return Path(str(apk_full_path) + ".meta.json")


def write_apk_meta(apk_full_path: str | Path, meta: dict[str, Any]) -> str:
    path = _meta_path_for_apk(apk_full_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def read_apk_meta(apk_full_path: str | Path) -> dict[str, Any]:
    path = _meta_path_for_apk(apk_full_path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _channel_apk_subdir(channel_id: str) -> str:
    ch = get_channel_by_id(channel_id)
    return ((ch or {}).get("apk_subdir") or "").strip()


def _expected_archive_filename(version: dict[str, Any], project_id: str = "") -> str:
    vn = (version.get("version_name") or "1.0.0").strip()
    vc = str(version.get("version_code") or "").strip()
    pipeline = version.get("pipeline") if isinstance(version.get("pipeline"), dict) else {}
    apk_build = pipeline.get("apk_build") if isinstance(pipeline.get("apk_build"), dict) else {}
    app = (apk_build.get("app_name") or version.get("app_name") or project_id or "GameKu").strip()
    if not app:
        app = "GameKu"
    return f"{_safe_segment(app, 'GameKu')}_{vn}_vc{vc}.apk"


def resolve_version_apk_rel_path(project_id: str, version: dict[str, Any]) -> str:
    """解析版本对应的本地 APK 相对路径（优先 apk_path / apk_download / 约定文件名）。"""
    if not isinstance(version, dict):
        return ""
    stored = (version.get("apk_path") or "").strip().replace("\\", "/")
    if stored:
        full = stored if stored.startswith("/") else os.path.join(Config.APK_DIR, stored.replace("/", os.sep))
        if os.path.isfile(full):
            return stored if not stored.startswith("/") else os.path.relpath(full, Config.APK_DIR).replace("\\", "/")

    apk_dl = version.get("apk_download") if isinstance(version.get("apk_download"), dict) else {}
    pub = (apk_dl.get("pub_download_path") or apk_dl.get("local_rel_path") or "").strip().replace("\\", "/")
    if pub:
        full = os.path.join(Config.APK_DIR, pub.replace("/", os.sep))
        if os.path.isfile(full):
            return pub

    channel_id = (version.get("channel") or "").strip()
    stage = (version.get("stage") or "dev").strip() or "dev"
    subdir = _channel_apk_subdir(channel_id)
    fname = _expected_archive_filename(version, project_id)
    candidates = []
    if subdir:
        candidates.append(f"{subdir}/{stage}/{fname}")
    candidates.append(f"{stage}/{fname}")
    if stored and "/" not in stored:
        if subdir:
            candidates.append(f"{subdir}/{stage}/{stored}")
        candidates.append(f"{stage}/{stored}")
    for rel in candidates:
        full = os.path.join(Config.APK_DIR, rel.replace("/", os.sep))
        if os.path.isfile(full):
            return rel
    return ""


def version_apk_build_enabled(version: dict[str, Any]) -> bool:
    if not isinstance(version, dict):
        return False
    pipeline = version.get("pipeline") if isinstance(version.get("pipeline"), dict) else {}
    apk_build = pipeline.get("apk_build") if isinstance(pipeline.get("apk_build"), dict) else {}
    if apk_build.get("enabled"):
        return True
    apk_dl = version.get("apk_download") if isinstance(version.get("apk_download"), dict) else {}
    return bool(apk_dl.get("local_download_url") or apk_dl.get("pub_download_path"))


def _format_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "0 B"
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def build_download_info(project_id: str, version: dict[str, Any]) -> dict[str, Any] | None:
    """构建版本 APK 下载详情（供弹窗/下载中心复用）。"""
    if not isinstance(version, dict):
        return None
    rel_path = resolve_version_apk_rel_path(project_id, version)
    if not rel_path:
        return None
    full_path = os.path.join(Config.APK_DIR, rel_path.replace("/", os.sep))
    if not os.path.isfile(full_path):
        return None

    sidecar = read_apk_meta(full_path)
    apk_dl = version.get("apk_download") if isinstance(version.get("apk_download"), dict) else {}
    merged = {**sidecar, **apk_dl}

    try:
        stat = os.stat(full_path)
        size_bytes = int(stat.st_size)
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        size_bytes = int(merged.get("size_bytes") or 0)
        mtime = str(merged.get("build_time") or merged.get("archived_at") or "")

    parsed = parse_apk_metadata(full_path) or {}
    package_name = (
        merged.get("package_name")
        or parsed.get("package")
        or version.get("package_name")
        or ""
    )
    app_name = merged.get("app_name") or parsed.get("app_name") or ""
    base_url = Config.get_public_base_url() or get_canonical_base_url()
    local_url = merged.get("local_download_url") or f"{base_url.rstrip('/')}/pub/download/{rel_path}?source=qr"
    oss_url = merged.get("oss_download_url") or ""
    oss_remote_key = (merged.get("oss_remote_key") or "").strip()
    if not oss_url and oss_remote_key:
        oss_url = f"{base_url.rstrip('/')}/pub/oss-download/{oss_remote_key.lstrip('/')}?source=qr"

    local_qr = merged.get("local_qr_dataurl") or ""
    oss_qr = merged.get("oss_qr_dataurl") or ""
    if not local_qr and local_url:
        local_qr = _qr_png_dataurl(local_url)
    if not oss_qr and oss_url:
        oss_qr = _qr_png_dataurl(oss_url)

    channel_id = (version.get("channel") or "").strip()
    stage = (version.get("stage") or "dev").strip() or "dev"
    ch = get_channel_by_id(channel_id) or {}
    channel_label = (ch.get("name") or channel_id or "-").strip()
    channel_subdir = (ch.get("apk_subdir") or "").strip()
    stage_labels = {"dev": "开发", "test": "测试", "production": "线上"}
    return {
        "available": True,
        "project_id": project_id,
        "version_id": (version.get("id") or "").strip(),
        "version_name": (version.get("version_name") or "").strip(),
        "version_code": str(version.get("version_code") or "").strip(),
        "channel": channel_id,
        "channel_label": channel_label,
        "channel_subdir": channel_subdir,
        "stage": stage,
        "stage_label": stage_labels.get(stage, stage),
        "platform": (version.get("platform") or "android").strip(),
        "build_time": str(merged.get("build_time") or merged.get("archived_at") or mtime),
        "build_number": merged.get("build_number"),
        "package_name": package_name,
        "app_name": app_name,
        "file_name": os.path.basename(rel_path),
        "pub_download_path": rel_path,
        "size_bytes": size_bytes,
        "size_label": _format_size(size_bytes),
        "local_download_url": local_url,
        "local_qr_dataurl": local_qr,
        "oss_download_url": oss_url,
        "oss_qr_dataurl": oss_qr,
        "oss_remote_key": oss_remote_key,
    }


def persist_archive_to_version(
    project_id: str,
    version_id: str,
    archive_result: dict[str, Any],
    *,
    build_time: str = "",
    build_number: int | None = None,
    package_name: str = "",
    app_name: str = "",
) -> bool:
    """将归档结果写入版本记录与 sidecar 元数据。"""
    pid = (project_id or "").strip()
    vid = (version_id or "").strip()
    if not pid or not vid or not isinstance(archive_result, dict):
        return False
    versions = project_versions_db.get(pid) or []
    if not isinstance(versions, list):
        return False
    idx = next((i for i, row in enumerate(versions) if (row.get("id") or "") == vid), None)
    if idx is None:
        return False
    row = versions[idx]
    rel_path = (archive_result.get("pub_download_path") or "").strip().replace("\\", "/")
    full_path = archive_result.get("local_apk_path") or os.path.join(Config.APK_DIR, rel_path.replace("/", os.sep))
    try:
        size_bytes = os.path.getsize(full_path)
    except OSError:
        size_bytes = 0
    archived_at = build_time.strip() or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = {
        "project_id": pid,
        "version_id": vid,
        "version_name": row.get("version_name"),
        "version_code": row.get("version_code"),
        "channel": row.get("channel"),
        "stage": row.get("stage"),
        "build_time": archived_at,
        "build_number": build_number,
        "archived_at": archived_at,
        "package_name": package_name or row.get("package_name") or "",
        "app_name": app_name,
        "size_bytes": size_bytes,
        "pub_download_path": rel_path,
        "local_download_url": archive_result.get("local_download_url") or "",
        "local_qr_dataurl": archive_result.get("local_qr_dataurl") or "",
        "oss_download_url": archive_result.get("oss_download_url") or "",
        "oss_qr_dataurl": archive_result.get("oss_qr_dataurl") or "",
        "oss_remote_key": archive_result.get("oss_remote_key") or "",
    }
    if full_path:
        write_apk_meta(full_path, meta)

    row["apk_path"] = rel_path
    row["apk_download"] = {
        "pub_download_path": rel_path,
        "local_download_url": archive_result.get("local_download_url") or "",
        "local_qr_dataurl": archive_result.get("local_qr_dataurl") or "",
        "oss_download_url": archive_result.get("oss_download_url") or "",
        "oss_qr_dataurl": archive_result.get("oss_qr_dataurl") or "",
        "oss_remote_key": archive_result.get("oss_remote_key") or "",
        "build_time": archived_at,
        "build_number": build_number,
        "package_name": meta["package_name"],
        "size_bytes": size_bytes,
        "updated_at": datetime.now().isoformat(),
    }
    row["updated_at"] = datetime.now().isoformat()
    versions[idx] = row
    project_versions_db[pid] = versions
    save_project_versions()
    return True


def archive_apk(
    *,
    apk_file: str,
    app_name: str,
    release_version: str,
    version_code: str,
    release_channel: str,
    release_environment: str,
    stage: str = "dev",
    oss_remote_key: str = "",
    unity_project_path: str = "",
    project_id: str = "",
    version_id: str = "",
    build_time: str = "",
    build_number: int | None = None,
    package_name: str = "",
) -> dict[str, Any]:
    src = Path(apk_file).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"APK 不存在: {src}")

    channel_dir = _safe_segment(release_channel)
    stage_dir = _safe_segment(stage or release_environment.lower(), "dev")
    fname = f"{_safe_segment(app_name, 'GameKu')}_{release_version}_vc{version_code}.apk"
    rel_path = f"{channel_dir}/{stage_dir}/{fname}"
    dest = Path(Config.APK_DIR) / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)

    base_url = Config.get_public_base_url() or get_canonical_base_url()
    local_download_url = f"{base_url.rstrip('/')}/pub/download/{rel_path}?source=qr"

    if not oss_remote_key:
        oss_remote_key = (
            f"MyGame1/{release_environment}/{release_channel}/android/"
            f"Version_{release_version}/{version_code}/apk/"
            f"{app_name}_{release_version}_{src.name}"
        )
    oss_remote_key = oss_remote_key.lstrip("/")

    oss_download_url = ""
    if unity_project_path:
        try:
            from services.oss_client_helper import load_oss_config, public_url

            cfg = load_oss_config(unity_project_path)
            oss_download_url = public_url(cfg, oss_remote_key)
        except Exception:
            oss_download_url = f"{base_url.rstrip('/')}/pub/oss-download/{oss_remote_key}?source=qr"
    elif oss_remote_key:
        oss_download_url = f"{base_url.rstrip('/')}/pub/oss-download/{oss_remote_key}?source=qr"

    qr_dir = dest.parent / "qr"
    local_qr_file = qr_dir / f"{fname}.local.png"
    oss_qr_file = qr_dir / f"{fname}.oss.png"
    _save_qr_png(local_download_url, local_qr_file)
    if oss_download_url:
        _save_qr_png(oss_download_url, oss_qr_file)

    result = {
        "ok": True,
        "local_apk_path": str(dest),
        "local_download_url": local_download_url,
        "local_qr_file": str(local_qr_file),
        "local_qr_dataurl": _qr_png_dataurl(local_download_url),
        "oss_remote_key": oss_remote_key,
        "oss_download_url": oss_download_url,
        "oss_qr_file": str(oss_qr_file) if oss_download_url else "",
        "oss_qr_dataurl": _qr_png_dataurl(oss_download_url) if oss_download_url else "",
        "pub_download_path": rel_path,
    }

    sidecar = {
        "project_id": project_id,
        "version_id": version_id,
        "version_name": release_version,
        "version_code": version_code,
        "channel_subdir": channel_dir,
        "stage": stage_dir,
        "build_time": build_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "build_number": build_number,
        "app_name": app_name,
        "package_name": package_name,
        "pub_download_path": rel_path,
        "local_download_url": local_download_url,
        "local_qr_dataurl": result["local_qr_dataurl"],
        "oss_download_url": oss_download_url,
        "oss_qr_dataurl": result["oss_qr_dataurl"],
        "oss_remote_key": oss_remote_key,
    }
    try:
        sidecar["size_bytes"] = dest.stat().st_size
    except OSError:
        pass
    write_apk_meta(dest, sidecar)

    if project_id and version_id:
        persist_archive_to_version(
            project_id,
            version_id,
            result,
            build_time=build_time,
            build_number=build_number,
            package_name=package_name,
            app_name=app_name,
        )

    return result

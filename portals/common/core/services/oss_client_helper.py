# -*- coding: utf-8 -*-
"""OSS 读写辅助（复用 Unity OSSConfig.json）。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def load_oss_config(unity_project_path: str | None = None) -> dict[str, Any]:
    root = Path(unity_project_path or os.environ.get("UNITY_PROJECT_PATH") or "").expanduser()
    path = root / "Assets/Editor/Configs/OSSConfig.json"
    if not path.is_file():
        raise FileNotFoundError(f"OSSConfig 不存在: {path}")
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("OSSConfig.json 格式错误")
    return data


def ensure_oss2():
    try:
        import oss2  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "oss2"], timeout=120)


def get_bucket(unity_project_path: str | None = None):
    ensure_oss2()
    import oss2

    cfg = load_oss_config(unity_project_path)
    bucket = cfg.get("BucketName") or cfg.get("bucket")
    endpoint = cfg.get("Endpoint") or cfg.get("endpoint")
    ak = cfg.get("AccessKeyId") or cfg.get("accessKeyId")
    sk = cfg.get("AccessKeySecret") or cfg.get("accessKeySecret")
    if not all([bucket, endpoint, ak, sk]):
        raise ValueError("OSSConfig 缺少 Bucket/Endpoint/AccessKey")
    auth = oss2.Auth(ak, sk)
    return oss2.Bucket(auth, f"https://{endpoint}", bucket), cfg


def _custom_domain(cfg: dict[str, Any]) -> str:
    """OSS 自定义域名（CNAME），APK 公网下载必须走此域名。"""
    for key in ("CustomDomain", "customDomain", "CdnDomain", "cdnDomain", "PublicBaseUrl", "publicBaseUrl"):
        val = (cfg.get(key) or "").strip().rstrip("/")
        if val:
            if val.startswith("http://") or val.startswith("https://"):
                return val.rstrip("/")
            return f"https://{val}"
    return ""


def public_url(cfg: dict[str, Any], object_key: str) -> str:
    key = object_key.lstrip("/")
    custom = _custom_domain(cfg)
    if custom:
        return f"{custom}/{key}"
    endpoint = (cfg.get("Endpoint") or cfg.get("endpoint") or "").strip()
    bucket = (cfg.get("BucketName") or cfg.get("bucket") or "").strip()
    return f"https://{bucket}.{endpoint}/{key}"


def is_oss_apk_forbidden_url(url: str) -> bool:
    """阿里云默认 OSS 域名公网直链 .apk 会返回 ApkDownloadForbidden。"""
    u = (url or "").lower()
    return u.endswith(".apk") and ".aliyuncs.com/" in u


def apk_download_url(
    cfg: dict[str, Any],
    object_key: str,
    *,
    site_base_url: str | None = None,
) -> str:
    """APK 远端下载地址：优先 OSS CNAME；否则走 apk-site OSS 代理（绕过 ApkDownloadForbidden）。"""
    key = object_key.lstrip("/")
    custom = _custom_domain(cfg)
    if custom:
        return f"{custom}/{key}"
    base = (site_base_url or "").strip().rstrip("/")
    if not base:
        from config import Config
        from services.startup import get_canonical_base_url

        base = Config.get_public_base_url() or get_canonical_base_url()
    return f"{base.rstrip('/')}/pub/oss-download/{key}?source=qr"


def stream_object(object_key: str, unity_project_path: str | None = None):
    """从 OSS 读取对象，返回 (iterator, content_type, content_length)。"""
    ensure_oss2()
    bucket, _ = get_bucket(unity_project_path)
    key = object_key.lstrip("/")
    result = bucket.get_object(key)
    headers = result.headers or {}
    content_type = headers.get("Content-Type") or "application/vnd.android.package-archive"
    content_length = headers.get("Content-Length")
    return result, content_type, content_length


def file_md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def upload_file(local_path: Path, remote_key: str, unity_project_path: str | None = None) -> str:
    bucket, cfg = get_bucket(unity_project_path)
    bucket.put_object_from_file(remote_key.lstrip("/"), str(local_path))
    return public_url(cfg, remote_key)


def list_prefix(prefix: str, unity_project_path: str | None = None, max_keys: int = 500) -> list[str]:
    ensure_oss2()
    import oss2

    bucket, _ = get_bucket(unity_project_path)
    keys: list[str] = []
    for obj in oss2.ObjectIterator(bucket, prefix=prefix.lstrip("/"), max_keys=max_keys):
        keys.append(obj.key)
    return keys

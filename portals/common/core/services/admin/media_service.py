"""Media API service."""

from __future__ import annotations

import os
from typing import Any, Dict, Tuple

from repositories.admin import media_repo


def sanitize_relative_path(relative_path: str) -> str | None:
    clean_relative = os.path.normpath(str(relative_path or "").replace("\\", "/")).replace("\\", "/")
    if clean_relative.startswith(".."):
        return None
    return clean_relative


def upload_media(form: Dict[str, Any], files: list) -> Tuple[Dict[str, Any], int]:
    scope = (form.get("scope") or "shared").strip() or "shared"
    bucket = (form.get("project_id") or form.get("bucket") or "shared").strip() or "shared"
    uploaded = media_repo.save_files(files, scope=scope, bucket=bucket)
    if not uploaded:
        return {"error": "请选择本地图片或视频文件"}, 400
    return {"ok": True, "files": uploaded, "file": uploaded[0]}, 200

"""Project-side helper services (list/query/upload/file serve)."""

from __future__ import annotations

import os
import re
import secrets
from typing import Any, Dict, Tuple

from config import DATA_DIR
from models.data import (
    can_view_project,
    get_project_apk_count,
    get_project_download_count,
    normalize_public_url,
    project_tasks_db,
    projects_db,
    users_db,
)


PROJECT_PHASES = [
    ("kickoff", "立项/预研"),
    ("prototype", "原型/白盒"),
    ("preprod", "预生产/绿光"),
    ("production", "正式开发"),
    ("alpha", "Alpha"),
    ("beta", "Beta"),
    ("polish", "调优/收尾"),
    ("launch", "上线/运营"),
    ("maintenance", "维护"),
]

PROJECT_ICONS_DIR = os.path.join(DATA_DIR, "project_icons")
TASK_UPLOADS_DIR = os.path.join(DATA_DIR, "task_uploads")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def upload_project_icon(file_storage: Any) -> Tuple[Dict[str, Any], int]:
    if not file_storage or not getattr(file_storage, "filename", ""):
        return {"error": "未选择文件"}, 400
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in IMAGE_EXTS:
        return {"error": "仅支持图片格式：png, jpg, gif, webp"}, 400
    safe_name = re.sub(r"[^\w\-.]", "", file_storage.filename)
    safe_name = safe_name[:50] or "img"
    name = f"{secrets.token_hex(4)}_{safe_name}{ext}"
    os.makedirs(PROJECT_ICONS_DIR, exist_ok=True)
    path = os.path.join(PROJECT_ICONS_DIR, name)
    try:
        file_storage.save(path)
    except Exception as exc:
        return {"error": f"保存失败: {str(exc)}"}, 500
    return {"url": f"/admin/projects/icon/{name}"}, 200


def validate_icon_filename(filename: str) -> str | None:
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return None
    path = os.path.join(PROJECT_ICONS_DIR, filename)
    if not os.path.isdir(PROJECT_ICONS_DIR):
        return None
    if not os.path.isfile(path) or not os.path.abspath(path).startswith(os.path.abspath(PROJECT_ICONS_DIR)):
        return None
    return filename


def upload_task_file(project_id: str, username: str, file_storage: Any) -> Tuple[Dict[str, Any], int]:
    if project_id not in projects_db or not can_view_project(project_id, username):
        return {"error": "无权限"}, 403
    if not file_storage or not getattr(file_storage, "filename", ""):
        return {"error": "未选择文件"}, 400
    safe_name = re.sub(r"[^\w\-.]", "", os.path.basename(file_storage.filename))[:80] or "file"
    name = f"{project_id}_{secrets.token_hex(4)}_{safe_name}"
    subdir = os.path.join(TASK_UPLOADS_DIR, project_id)
    os.makedirs(subdir, exist_ok=True)
    path = os.path.join(subdir, name)
    try:
        file_storage.save(path)
    except Exception as exc:
        return {"error": f"保存失败: {str(exc)}"}, 500
    return {"url": f"/admin/projects/{project_id}/tasks/file/{name}", "name": safe_name}, 200


def validate_task_file(project_id: str, filename: str, username: str) -> Tuple[Dict[str, Any], int]:
    if project_id not in projects_db or not can_view_project(project_id, username):
        return {"error": "无权限"}, 403
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return {"error": "not_found"}, 404
    subdir = os.path.join(TASK_UPLOADS_DIR, project_id)
    path = os.path.join(subdir, filename)
    if not os.path.isfile(path) or not os.path.abspath(path).startswith(os.path.abspath(subdir)):
        return {"error": "not_found"}, 404
    is_image = filename.lower().endswith(IMAGE_EXTS)
    download_name = filename.split("_", 2)[-1] if "_" in filename else filename
    return {"subdir": subdir, "filename": filename, "is_image": is_image, "download_name": download_name}, 200


def project_user_options() -> Dict[str, Any]:
    users = []
    for uid, user in users_db.items():
        if user.get("role") in ("super_admin", "admin"):
            continue
        if user.get("disabled"):
            continue
        users.append({"id": uid})
    return {"users": users}


def validate_username(username: str) -> Dict[str, Any]:
    user = (username or "").strip()
    if not user:
        return {"exists": False}
    if user not in users_db:
        return {"exists": False}
    if users_db[user].get("disabled"):
        return {"exists": False, "disabled": True}
    return {"exists": True, "username": user}


def list_projects_for_user(username: str, status_filter: str = "active") -> Dict[str, Any]:
    projects = []
    phase_map = dict(PROJECT_PHASES)
    for project_id, item in projects_db.items():
        if not can_view_project(project_id, username):
            continue
        status = item.get("status", "active")
        if status_filter == "active" and status == "archived":
            continue
        if status_filter == "archived" and status != "archived":
            continue
        phase = item.get("phase", "kickoff")
        tasks = project_tasks_db.get(project_id) or []
        projects.append(
            {
                "id": project_id,
                "name": item.get("name", project_id),
                "name_en": item.get("name_en", ""),
                "icon": item.get("icon", ""),
                "phase": phase,
                "phase_label": phase_map.get(phase, phase),
                "intro": item.get("intro", "") or item.get("description", ""),
                "created_by": item.get("created_by", ""),
                "created_at": item.get("created_at", ""),
                "task_count": len(tasks),
                "apk_count": get_project_apk_count(project_id),
                "download_count": get_project_download_count(project_id),
                "status": status,
                "is_template": bool(item.get("is_template")),
                "player_public_url": normalize_public_url(item.get("player_public_url")),
                "forum_public_url": normalize_public_url(item.get("forum_public_url")),
                "admin_public_url": normalize_public_url(item.get("admin_public_url")),
            }
        )
    projects.sort(key=lambda row: (projects_db.get(row["id"]) or {}).get("order", 9999))
    return {"projects": projects}

# -*- coding: utf-8 -*-
"""Project registry and access control."""

import os
import re
from datetime import datetime
from difflib import SequenceMatcher

from config import Config
from data._store import PROJECTS_FILE
from repositories.admin import users_repo as _users_repo


def _user_role(username: str) -> str:
    row = _users_repo.get_user(username) or {}
    return str(row.get("role") or "user")

from repositories.registry._proxies import ProjectsDbProxy
from repositories.registry.project_repo import get_project_repository

projects_db = ProjectsDbProxy()


def save_projects():
    get_project_repository()._mirror_all()


def _normalize_project_token(value):
    text = str(value or '').strip().lower()
    if not text:
        return ''
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', text)


def resolve_project_id(project_ref):
    """Resolve a project reference to the canonical project id."""
    project_ref = str(project_ref or '').strip()
    if not project_ref or not isinstance(projects_db, dict):
        return ''
    if project_ref in projects_db:
        return project_ref
    lowered = project_ref.lower()
    normalized_ref = _normalize_project_token(project_ref)
    best_match = ('', 0.0)
    for project_id, project in projects_db.items():
        payload = project if isinstance(project, dict) else {}
        aliases_raw = payload.get('aliases') or payload.get('alias') or []
        if isinstance(aliases_raw, str):
            aliases_raw = [part.strip() for part in aliases_raw.split(',') if part.strip()]
        elif not isinstance(aliases_raw, (list, tuple, set)):
            aliases_raw = []
        aliases = [
            str(project_id or '').strip(),
            str(payload.get('name') or '').strip(),
            str(payload.get('name_en') or '').strip(),
        ] + [str(alias or '').strip() for alias in aliases_raw]
        for alias in aliases:
            if alias and (alias == project_ref or alias.lower() == lowered):
                return str(project_id)
            normalized_alias = _normalize_project_token(alias)
            if normalized_ref and normalized_alias and normalized_ref == normalized_alias:
                return str(project_id)
            if normalized_ref and normalized_alias:
                ratio = SequenceMatcher(None, normalized_ref, normalized_alias).ratio()
                if ratio > best_match[1]:
                    best_match = (str(project_id), ratio)
    # Fuzzy fallback for legacy typo / transliteration drift (e.g. GameKu vs GomeKu).
    if best_match[0] and best_match[1] >= 0.82:
        return best_match[0]
    return ''


def get_project_record(project_ref):
    project_id = resolve_project_id(project_ref)
    if not project_id:
        return None, None
    payload = projects_db.get(project_id)
    if not isinstance(payload, dict):
        payload = {}
    return project_id, payload


def normalize_public_url(value):
    """Normalize external portal URL input for cross-server routing."""
    text = str(value or '').strip()
    if not text:
        return ''
    text = text.replace('\\', '/')
    if text.startswith('//'):
        text = 'https:' + text
    if not re.match(r'^https?://', text, re.IGNORECASE):
        text = 'https://' + text
    return text.rstrip('/')


def get_project_portal_urls(project_ref=''):
    """Resolve project-level portal domains with global config fallback."""
    project_id, project = get_project_record(project_ref)
    project = project or {}
    player_public_url = normalize_public_url(project.get('player_public_url'))
    forum_public_url = normalize_public_url(project.get('forum_public_url'))
    admin_public_url = normalize_public_url(project.get('admin_public_url'))
    if not player_public_url:
        player_public_url = normalize_public_url(getattr(Config, 'PLAYER_PUBLIC_URL', ''))
    if not forum_public_url:
        forum_public_url = normalize_public_url(getattr(Config, 'FORUM_PUBLIC_URL', ''))
    if not admin_public_url:
        admin_public_url = normalize_public_url(getattr(Config, 'ADMIN_PUBLIC_URL', ''))
    return {
        'project_id': project_id or '',
        'player_public_url': player_public_url,
        'forum_public_url': forum_public_url,
        'admin_public_url': admin_public_url,
    }


def can_view_project(project_id, username):
    """用户是否可查看该项目（管理员、创建者、编辑者、查看者均可）。旧项目无 created_by/viewers/editors 时视为全员可查看。"""
    if not username:
        return False
    role = _user_role(username)
    if role in ('super_admin', 'admin'):
        return True
    if project_id not in projects_db:
        return False
    p = projects_db[project_id]
    created_by = p.get('created_by')
    editors = p.get('editors') or []
    viewers = p.get('viewers') or []
    # 旧项目：无创建者且未配置查看/编辑名单，视为所有有模块权限的用户可查看
    if not created_by and not editors and not viewers:
        return True
    if created_by == username:
        return True
    if username in editors or username in viewers:
        return True
    return False


def can_edit_project(project_id, username):
    """用户是否可编辑该项目（管理员、创建者、编辑者）。旧项目仅管理员可编辑。"""
    if not username:
        return False
    role = _user_role(username)
    if role in ('super_admin', 'admin'):
        return True
    if project_id not in projects_db:
        return False
    p = projects_db[project_id]
    created_by = p.get('created_by')
    editors = p.get('editors') or []
    if not created_by and not editors:
        return False  # 旧项目仅管理员可编辑
    if created_by == username:
        return True
    if username in editors:
        return True
    return False


def get_project_apk_count(project_id):
    from data.packages import extract_project_name, iter_package_files

    count = 0
    for filename, _ in iter_package_files():
        if extract_project_name(filename) == project_id:
            count += 1
    return count


def get_project_download_count(project_id):
    """本项目下所有包件的下载次数总和"""
    from data.downloads import download_stats
    from data.packages import extract_project_name, iter_package_files

    total = 0
    for filename, _ in iter_package_files():
        if extract_project_name(filename) == project_id:
            total += download_stats.get(filename, download_stats.get(os.path.basename(filename), 0))
    return total


def get_active_projects_count():
    from data.packages import extract_project_name, iter_package_files

    active = set()
    for filename, _ in iter_package_files():
        active.add(extract_project_name(filename))
    return len(active)

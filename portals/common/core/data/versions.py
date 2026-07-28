# -*- coding: utf-8 -*-
"""Version records, changelog, and project version management."""

import os
from datetime import datetime

from config import Config
from data._store import CHANGELOG_FILE, VERSIONS_FILE, load_document, save_document
from repositories.registry._proxies import ProjectVersionsDbProxy
from repositories.registry.accessors import (
    list_all_project_versions,
    list_project_versions,
    mirror_project_versions_json,
    save_project_versions,
)

versions_db = load_document(VERSIONS_FILE, {})
changelog_db = load_document(CHANGELOG_FILE, {})
project_versions_db = ProjectVersionsDbProxy()


def _normalize_version_platforms():
    changed = False
    grouped = list_all_project_versions()
    if not isinstance(grouped, dict):
        return changed
    for project_id, versions in list(grouped.items()):
        if not isinstance(versions, list):
            continue
        project_changed = False
        for version in versions:
            if not isinstance(version, dict):
                continue
            platform = (version.get('platform') or '').strip().lower()
            if platform not in ('android', 'ios'):
                apk_path = version.get('apk_path') or ''
                ext = os.path.splitext(apk_path or '')[1].lower()
                version['platform'] = 'ios' if ext == '.ipa' else 'android'
                project_changed = True
                changed = True
        if project_changed:
            save_project_versions(project_id, versions)
    return changed


if _normalize_version_platforms():
    mirror_project_versions_json()


def save_versions():
    save_document(VERSIONS_FILE, versions_db)


def save_changelog():
    save_document(CHANGELOG_FILE, changelog_db)


def save_project_versions_snapshot():
    mirror_project_versions_json()


def get_version_download_count(project_id, version):
    """某版本对应 APK 的下载次数。仅基于 apk_path 对应的文件，无则返回 0。"""
    from data.downloads import download_stats

    if not project_id:
        return 0
    apk_path = (version.get('apk_path') or '').strip()
    if not apk_path:
        return 0
    if apk_path.startswith('/'):
        if not os.path.isfile(apk_path):
            return 0
        key = os.path.basename(apk_path)
    else:
        full = os.path.join(Config.APK_DIR, apk_path.replace('/', os.path.sep))
        if not os.path.isfile(full):
            return 0
        key = apk_path
    return download_stats.get(key, download_stats.get(os.path.basename(apk_path), 0))


def get_channel_for_apk(project_id, filename, project_versions=None):
    """根据 project_versions 匹配 filename，返回渠道标签；无匹配返回空"""
    from data.packages import detect_platform, extract_version_from_filename

    versions = project_versions if project_versions is not None else list_project_versions(project_id)
    if not isinstance(versions, list):
        return ''
    ver_from_file = extract_version_from_filename(filename)
    fn_lower = filename.lower()
    for v in versions:
        platform = (v.get('platform') or '').strip().lower()
        if platform in ('android', 'ios') and platform != detect_platform(filename):
            continue
        vn = (v.get('version_name') or '').lower()
        vc = (v.get('version_code') or '').lower()
        apk_path = (v.get('apk_path') or '').strip().lower()
        if apk_path and apk_path in fn_lower:
            return v.get('channel', '') or ''
        if vn and vn in fn_lower:
            return v.get('channel', '') or ''
        if vc and vc in fn_lower:
            return v.get('channel', '') or ''
        if ver_from_file and (vn == ver_from_file.lower() or vc == ver_from_file.lower()):
            return v.get('channel', '') or ''
    return ''


def version_is_recommended(project_id, version):
    """版本是否被标记为推荐：版本级 changelog 或任一匹配 APK 的 changelog"""
    from data.packages import extract_project_name, iter_package_files

    if not project_id:
        return False
    vid = version.get('id') or ''
    vkey = 'version:' + project_id + ':' + vid
    vch = changelog_db.get(vkey)
    if isinstance(vch, dict) and vch.get('recommended'):
        return True
    apk_path = (version.get('apk_path') or '').strip()
    if apk_path and os.path.sep not in apk_path and not apk_path.startswith('/'):
        ch = changelog_db.get(apk_path)
        if isinstance(ch, dict) and ch.get('recommended'):
            return True
    if not os.path.isdir(Config.APK_DIR):
        return False
    ver_name = (version.get('version_name') or '').lower()
    ver_code = (version.get('version_code') or '').lower()
    for fname, _ in iter_package_files():
        if extract_project_name(fname) != project_id:
            continue
        fn_lower = fname.lower()
        match = (ver_name and ver_name in fn_lower) or (ver_code and ver_code in fn_lower) or (not ver_name and not ver_code)
        if match:
            ch = changelog_db.get(fname)
            if isinstance(ch, dict) and ch.get('recommended'):
                return True
    return False


def get_changelog_for_file(filename):
    """获取文件对应的 Changelog：优先按文件名，其次按匹配的版本配置（version:project:vid）"""
    from data.packages import extract_project_name

    raw = changelog_db.get(filename)
    if raw is not None:
        if isinstance(raw, dict):
            return raw.get('text', ''), bool(raw.get('recommended'))
        return (str(raw)[:500], False)
    project_id = extract_project_name(filename)
    versions = list_project_versions(project_id)
    if not isinstance(versions, list):
        return '', False
    for v in versions:
        vkey = 'version:' + project_id + ':' + (v.get('id') or '')
        vch = changelog_db.get(vkey)
        if not vch or not isinstance(vch, dict):
            continue
        vn = (v.get('version_name') or '').lower()
        vc = (v.get('version_code') or '').lower()
        apk_path = (v.get('apk_path') or '').strip().lower()
        fn_lower = filename.lower()
        if apk_path and apk_path in fn_lower:
            return vch.get('text', ''), bool(vch.get('recommended'))
        if vn and vn in fn_lower:
            return vch.get('text', ''), bool(vch.get('recommended'))
        if vc and vc in fn_lower:
            return vch.get('text', ''), bool(vch.get('recommended'))
    return '', False


def version_has_apk(project_id, version):
    """判断版本是否有对应 APK 已落盘。优先 apk_path，再按约定文件名（含 _vcN）探测。"""
    if not project_id:
        return False
    apk_path = (version.get('apk_path') or '').strip()
    if apk_path:
        if apk_path.startswith('/'):
            if os.path.isfile(apk_path):
                return True
        else:
            full = os.path.join(Config.APK_DIR, apk_path.replace('/', os.path.sep))
            if os.path.isfile(full):
                return True
    try:
        from services.apk_artifact_service import resolve_version_apk_rel_path

        return bool(resolve_version_apk_rel_path(project_id, version))
    except Exception:
        return False


def get_version_platform(version):
    from data.packages import detect_platform

    platform = (version.get('platform') or '').strip().lower()
    if platform in ('android', 'ios'):
        return platform
    return detect_platform(version.get('apk_path') or '')

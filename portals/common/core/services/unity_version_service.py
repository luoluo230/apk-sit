# -*- coding: utf-8 -*-
"""Local Unity Editor detection and catalog helpers (shared by Jenkins manage + version editor)."""

from __future__ import annotations

import glob
import os


def detect_local_unity_installations():
    """Detect locally installed Unity editors on the current host."""
    candidates = []
    if os.name == 'nt':
        pf = os.environ.get('ProgramFiles', r'C:\Program Files')
        pfx86 = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
        local_app = os.environ.get('LocalAppData', '')
        base_dirs = [
            os.path.join(pf, 'Unity', 'Hub', 'Editor'),
            os.path.join(pfx86, 'Unity', 'Hub', 'Editor'),
            os.path.join(local_app, 'Programs', 'Unity', 'Hub', 'Editor') if local_app else '',
        ]
        exe_candidates = (
            'Unity.exe',
            os.path.join('Editor', 'Unity.exe'),
        )
    else:
        home = os.path.expanduser('~')
        base_dirs = [
            '/Applications/Unity/Hub/Editor',
            os.path.join(home, 'Applications', 'Unity', 'Hub', 'Editor'),
        ]
        exe_candidates = ('Unity.app', 'Unity')

    for base in base_dirs:
        if not base or not os.path.isdir(base):
            continue
        for d in sorted(os.listdir(base), reverse=True):
            full = os.path.join(base, d)
            if not os.path.isdir(full):
                continue
            found_path = ''
            for rel in exe_candidates:
                p = os.path.join(full, rel)
                if os.path.isfile(p) or os.path.isdir(p):
                    found_path = p
                    break
            if not found_path and os.name == 'nt':
                hits = glob.glob(os.path.join(full, 'Editor', 'Unity*.exe'))
                if hits:
                    found_path = hits[0]
            if not found_path and os.name != 'nt':
                hits = glob.glob(os.path.join(full, 'Unity*.app'))
                if hits:
                    found_path = hits[0]
            if found_path:
                candidates.append({'version': d, 'path': found_path})

    uniq = []
    seen = set()
    for item in candidates:
        key = (item.get('version', ''), item.get('path', ''))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)
    return uniq


def _path_looks_like_other_platform(path: str) -> bool:
    text = str(path or '').strip()
    if not text:
        return False
    winish = ('\\' in text) or (len(text) > 1 and text[1] == ':')
    if os.name == 'nt':
        return text.startswith('/Applications/') or text.startswith('/Users/')
    return winish


def resolve_unity_app_path(version: str, path_hint: str = '') -> str:
    """解析 Unity 编辑器 .app / 安装目录路径（供 unity_paths.json 使用）。"""
    ver = str(version or '').strip()
    hint = str(path_hint or '').strip()
    if hint and not _path_looks_like_other_platform(hint):
        if hint.lower().endswith('.app') and os.path.isdir(hint):
            return hint
        if os.path.isdir(hint) and os.path.isdir(os.path.join(hint, 'Unity.app')):
            return os.path.join(hint, 'Unity.app')
        if os.name == 'nt' and os.path.isfile(hint) and hint.lower().endswith('.exe'):
            return hint

    for item in detect_local_unity_installations():
        if str(item.get('version') or '').strip() != ver:
            continue
        p = str(item.get('path') or '').strip()
        if p and not _path_looks_like_other_platform(p):
            if p.lower().endswith('.app') or (os.name == 'nt' and p.lower().endswith('.exe')):
                return p
            app = os.path.join(p, 'Unity.app')
            if os.path.isdir(app):
                return app
    return ''


def resolve_unity_executable_path(version: str, path_hint: str = '') -> str:
    """解析 Unity 可执行文件路径（Unity.exe / Unity.app/Contents/MacOS/Unity）。"""
    app_path = resolve_unity_app_path(version, path_hint)
    if not app_path:
        return ''
    if os.name == 'nt':
        if app_path.lower().endswith('.exe') and os.path.isfile(app_path):
            return app_path
        for rel in (os.path.join('Editor', 'Unity.exe'), 'Unity.exe'):
            p = os.path.join(app_path, rel) if not app_path.lower().endswith('.exe') else app_path
            if os.path.isfile(p):
                return p
        return ''
    if app_path.endswith('.app') and os.path.isdir(app_path):
        exe = os.path.join(app_path, 'Contents', 'MacOS', 'Unity')
        return exe if os.path.isfile(exe) else ''
    return app_path if os.path.isfile(app_path) else ''


def unity_version_strings(installations=None):
    """Return sorted version id list from installation dicts."""
    items = installations if installations is not None else detect_local_unity_installations()
    versions = []
    for it in items or []:
        v = str((it or {}).get('version') or '').strip()
        if v and v not in versions:
            versions.append(v)
    return versions

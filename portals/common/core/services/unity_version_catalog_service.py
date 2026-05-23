# -*- coding: utf-8 -*-
"""Global Unity version catalog: status, category, note; shared by Jenkins / version editor / build."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from config import DATA_DIR
from utils import load_json, save_json
from services.unity_version_service import detect_local_unity_installations

CATALOG_FILE = os.path.join(DATA_DIR, 'unity_version_catalog.json')
STATUS_ACTIVE = 'active'
STATUS_INACTIVE = 'inactive'
DEFAULT_CATEGORIES = ('Unity6', 'Unity2022', '其他')


def _utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _empty_catalog():
    return {'entries': [], 'categories': list(DEFAULT_CATEGORIES)}


def load_catalog():
    data = load_json(CATALOG_FILE, _empty_catalog())
    if not isinstance(data, dict):
        data = _empty_catalog()
    if not isinstance(data.get('entries'), list):
        data['entries'] = []
    cats = data.get('categories')
    if not isinstance(cats, list) or not cats:
        data['categories'] = list(DEFAULT_CATEGORIES)
    else:
        merged = list(DEFAULT_CATEGORIES)
        for c in cats:
            c = str(c or '').strip()
            if c and c not in merged:
                merged.append(c)
        data['categories'] = merged
    if not data['entries']:
        _migrate_legacy_into_catalog(data)
    return data


def save_catalog(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    save_json(CATALOG_FILE, data)


def _migrate_legacy_into_catalog(data):
    """Import unity_versions from Jenkins instances when catalog is empty."""
    try:
        from models.data import load_jenkins_instances
    except Exception:
        return
    instances = load_jenkins_instances() or []
    seen = set()
    for inst in instances:
        bd = (inst or {}).get('build_defaults') or {}
        for u in bd.get('unity_versions') or []:
            if isinstance(u, dict):
                ver = str(u.get('version') or '').strip()
                path = str(u.get('path') or '').strip()
            elif isinstance(u, str) and u.strip():
                parts = u.split(',', 1)
                ver = parts[0].strip()
                path = parts[1].strip() if len(parts) > 1 else ''
            else:
                continue
            if not ver or ver in seen:
                continue
            seen.add(ver)
            data['entries'].append(_new_entry(ver, path=path, category=_guess_category(ver), note='从 Jenkins 实例迁移'))


def _guess_category(version):
    v = str(version or '')
    if v.startswith('6000.') or v.startswith('6.'):
        return 'Unity6'
    if v.startswith('2022.') or v.startswith('2021.') or v.startswith('2020.'):
        return 'Unity2022'
    return '其他'


def _new_entry(version, path='', category='', status=STATUS_ACTIVE, note=''):
    now = _utc_now()
    return {
        'id': str(uuid.uuid4()),
        'version': str(version or '').strip(),
        'path': str(path or '').strip(),
        'category': str(category or '').strip() or '其他',
        'status': status if status in (STATUS_ACTIVE, STATUS_INACTIVE) else STATUS_ACTIVE,
        'note': str(note or '').strip(),
        'created_at': now,
        'updated_at': now,
    }


def _find_entry(data, entry_id):
    for e in data.get('entries') or []:
        if isinstance(e, dict) and e.get('id') == entry_id:
            return e
    return None


def list_entries(active_only=False, category=None):
    data = load_catalog()
    rows = []
    for e in data.get('entries') or []:
        if not isinstance(e, dict) or not (e.get('version') or '').strip():
            continue
        if active_only and e.get('status') != STATUS_ACTIVE:
            continue
        if category and str(e.get('category') or '') != category:
            continue
        rows.append(dict(e))
    rows.sort(key=lambda x: (x.get('category') or '', x.get('version') or ''), reverse=True)
    return rows, data.get('categories') or list(DEFAULT_CATEGORIES)


def list_active_for_selectors():
    """Shape compatible with legacy detect API: version, path, category, note."""
    entries, _ = list_entries(active_only=True)
    out = []
    for e in entries:
        out.append({
            'id': e.get('id'),
            'version': e.get('version'),
            'path': e.get('path') or '',
            'category': e.get('category') or '',
            'note': e.get('note') or '',
        })
    return out


def list_active_as_build_versions():
    """Jenkins build_defaults / unity_paths format."""
    entries, _ = list_entries(active_only=True)
    return [{'version': e['version'], 'path': e.get('path') or ''} for e in entries]


def resolve_unity_versions_for_build(build_defaults=None):
    """Active catalog first; else instance unity_versions; else Hub detect."""
    from services.unity_version_service import resolve_unity_app_path

    active = list_active_as_build_versions()
    if active:
        out = []
        for item in active:
            ver = str(item.get('version') or '').strip()
            if not ver:
                continue
            path = resolve_unity_app_path(ver, str(item.get('path') or '').strip())
            out.append({'version': ver, 'path': path})
        return out
    bd = build_defaults or {}
    uv = bd.get('unity_versions') or []
    if isinstance(uv, list) and uv:
        out = []
        for u in uv:
            if isinstance(u, dict) and (u.get('version') or '').strip():
                out.append({
                    'version': str(u.get('version', '')).strip(),
                    'path': str(u.get('path') or '').strip(),
                })
            elif isinstance(u, str) and u.strip():
                parts = u.split(',', 1)
                out.append({
                    'version': parts[0].strip(),
                    'path': parts[1].strip() if len(parts) > 1 else '',
                })
        if out:
            resolved = []
            for item in out:
                ver = str(item.get('version') or '').strip()
                path = resolve_unity_app_path(ver, str(item.get('path') or '').strip())
                resolved.append({'version': ver, 'path': path})
            return resolved
    detected = detect_local_unity_installations()
    if detected:
        return [{'version': d.get('version', ''), 'path': d.get('path') or ''} for d in detected if d.get('version')]
    return [{'version': '6000.3.8f1', 'path': ''}]


def create_entry(version, path='', category='', status=STATUS_ACTIVE, note=''):
    version = str(version or '').strip()
    if not version:
        return None, '版本号不能为空'
    data = load_catalog()
    for e in data.get('entries') or []:
        if isinstance(e, dict) and e.get('version') == version:
            return None, '版本号已存在：%s' % version
    cat = str(category or '').strip() or _guess_category(version)
    if cat and cat not in data['categories']:
        data['categories'].append(cat)
    entry = _new_entry(version, path=path, category=cat, status=status, note=note)
    data['entries'].append(entry)
    save_catalog(data)
    return entry, None


def update_entry(entry_id, fields):
    data = load_catalog()
    entry = _find_entry(data, entry_id)
    if not entry:
        return None, '未找到该记录'
    if 'version' in fields:
        ver = str(fields.get('version') or '').strip()
        if not ver:
            return None, '版本号不能为空'
        for e in data.get('entries') or []:
            if e is not entry and isinstance(e, dict) and e.get('version') == ver:
                return None, '版本号已被占用：%s' % ver
        entry['version'] = ver
    if 'path' in fields:
        entry['path'] = str(fields.get('path') or '').strip()
    if 'category' in fields:
        cat = str(fields.get('category') or '').strip() or '其他'
        entry['category'] = cat
        if cat not in data['categories']:
            data['categories'].append(cat)
    if 'status' in fields:
        st = str(fields.get('status') or '').strip()
        if st in (STATUS_ACTIVE, STATUS_INACTIVE):
            entry['status'] = st
    if 'note' in fields:
        entry['note'] = str(fields.get('note') or '').strip()
    entry['updated_at'] = _utc_now()
    save_catalog(data)
    return entry, None


def import_detected_entries(as_active=True):
    """Merge Hub-detected installs into catalog; skip existing version ids."""
    detected = detect_local_unity_installations()
    data = load_catalog()
    existing = {e.get('version') for e in data.get('entries') or [] if isinstance(e, dict)}
    added = []
    status = STATUS_ACTIVE if as_active else STATUS_INACTIVE
    for d in detected:
        ver = str((d or {}).get('version') or '').strip()
        if not ver or ver in existing:
            continue
        entry = _new_entry(
            ver,
            path=str((d or {}).get('path') or '').strip(),
            category=_guess_category(ver),
            status=status,
            note='本机检测导入',
        )
        data['entries'].append(entry)
        existing.add(ver)
        added.append(entry)
    save_catalog(data)
    return added, detected

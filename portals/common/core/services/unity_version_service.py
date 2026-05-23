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


def unity_version_strings(installations=None):
    """Return sorted version id list from installation dicts."""
    items = installations if installations is not None else detect_local_unity_installations()
    versions = []
    for it in items or []:
        v = str((it or {}).get('version') or '').strip()
        if v and v not in versions:
            versions.append(v)
    return versions

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot codemod: replace projects_db/channels_db/project_versions_db with registry accessors."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {
    'repositories/registry/_proxies.py',
    'repositories/registry/accessors.py',
    'repositories/registry/project_repo.py',
    'repositories/registry/channel_repo.py',
    'repositories/registry/version_row_repo.py',
    'scripts/codemod_registry_accessors.py',
    'data/__init__.py',
}

ACCESSOR_IMPORT = (
    'from repositories.registry.accessors import get_project, has_project, list_projects, save_project, '
    'list_channels, list_project_versions, save_project_versions'
)

IMPORT_RE = re.compile(
    r'^from models\.data import (.+)$',
    re.MULTILINE,
)
DATA_IMPORT_RE = re.compile(
    r'^from data\.(?:projects|channels|versions) import (.+)$',
    re.MULTILINE,
)


def _should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return rel in SKIP or rel.startswith('tests/gate-fixture')


def _strip_db_symbols(import_line: str) -> tuple[str, set[str]]:
    symbols = [s.strip() for s in import_line.split(',')]
    removed = set()
    kept = []
    for sym in symbols:
        base = sym.split(' as ')[0].strip()
        if base in {'projects_db', 'channels_db', 'project_versions_db'}:
            removed.add(base)
        else:
            kept.append(sym)
    return ', '.join(kept), removed


def _transform(content: str, path: Path) -> str:
    removed: set[str] = set()
    needs_accessor = False

    def _repl_models(m):
        nonlocal needs_accessor
        kept, rm = _strip_db_symbols(m.group(1))
        removed.update(rm)
        if rm:
            needs_accessor = True
        if not kept.strip():
            return ''
        return f'from models.data import {kept}'

    content = IMPORT_RE.sub(_repl_models, content)

    def _repl_data(m):
        nonlocal needs_accessor
        kept, rm = _strip_db_symbols(m.group(1))
        removed.update(rm)
        if rm:
            needs_accessor = True
        if not kept.strip():
            return ''
        return f'from data.projects import {kept}'

    content = DATA_IMPORT_RE.sub(_repl_data, content)

    if 'projects_db' in removed or 'channels_db' in removed or 'project_versions_db' in removed:
        needs_accessor = True

    replacements = [
        (r'\bprojects_db\.get\(', 'get_project('),
        (r'\bhas_project\(\s*([^)]+?)\s*\)\s*is\s+not\s+None', r'has_project(\1)'),  # noop guard
        (r'(\w+)\s+in\s+projects_db\b', r'has_project(\1)'),
        (r'\bprojects_db\.items\(\)', 'list_projects().items()'),
        (r'\bprojects_db\.keys\(\)', 'list_projects().keys()'),
        (r'\bprojects_db\.values\(\)', 'list_projects().values()'),
        (r'\bprojects_db\[([^\]]+)\]\s*=', r'save_project(\1, '),
        (r'\bprojects_db\[([^\]]+)\]', r'(get_project(\1) or {})'),
        (r'\bprojects_db\s+or\s+\{\}', 'list_projects()'),
        (r'\(projects_db\s+or\s+\{\}\)', 'list_projects()'),
        (r'\bisinstance\(projects_db,\s*dict\)', 'True'),
        (r'\bproject_versions_db\.get\(', 'list_project_versions('),
        (r'\bproject_versions_db\[([^\]]+)\]\s*=', r'save_project_versions(\1, '),
        (r'\bproject_versions_db\.setdefault\(', 'list_project_versions('),  # manual fixups may be needed
        (r'\(project_versions_db\s+or\s+\{\}\)', 'list_all_project_versions()'),
        (r'\bproject_versions_db\s+or\s+\{\}', 'list_all_project_versions()'),
        (r'channels_db\s+if\s+isinstance\(channels_db,\s*list\)\s+else\s+\[\]', 'list_channels()'),
        (r'for\s+c\s+in\s+\(channels_db\s+if\s+isinstance\(channels_db,\s*list\)\s+else\s+\[\]\)', 'for c in list_channels()'),
        (r'for\s+row\s+in\s+channels_db\s+if\s+isinstance\(channels_db,\s*list\)\s+else\s+\[\]', 'for row in list_channels()'),
        (r'for\s+c\s+in\s+channels_db\b', 'for c in list_channels()'),
        (r'isinstance\(channels_db,\s*list\)\s+and\s+channels_db', 'list_channels()'),
    ]
    for pattern, repl in replacements:
        if re.search(pattern, content):
            needs_accessor = True
        content = re.sub(pattern, repl, content)

    if needs_accessor and 'from repositories.registry.accessors import' not in content:
        extra = ACCESSOR_IMPORT
        if 'list_all_project_versions' in content:
            extra = extra.replace(
                'save_project_versions',
                'save_project_versions, list_all_project_versions',
            )
        lines = content.splitlines()
        insert_at = 0
        for idx, line in enumerate(lines[:40]):
            if line.startswith('import ') or line.startswith('from '):
                insert_at = idx + 1
        lines.insert(insert_at, extra)
        content = '\n'.join(lines)

    return content


def main() -> int:
    changed = 0
    for path in ROOT.rglob('*.py'):
        if _should_skip(path):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith('archives/'):
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            text = path.read_text(encoding='gbk', errors='ignore')
        if not any(token in text for token in ('projects_db', 'channels_db', 'project_versions_db')):
            continue
        new_text = _transform(text, path)
        if new_text != text:
            path.write_text(new_text, encoding='utf-8')
            changed += 1
            print('updated', rel)
    print(f'done: {changed} files')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

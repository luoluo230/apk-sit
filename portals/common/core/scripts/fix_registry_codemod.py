#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix broken codemod replacements for registry accessors."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FIXES = [
    (r'\bproject_id has_project\(not\)', 'not has_project(project_id)'),
    (r'\bpid has_project\(not\)', 'not has_project(pid)'),
    (r'for pid, has_project\(p\)\.items\(\)', 'for pid, p in list_projects().items()'),
    (r'for pid, has_project\(row\)\.items\(\)', 'for pid, row in list_projects().items()'),
    (r'for pid, has_project\(proj\)\.items\(\)', 'for pid, proj in list_projects().items()'),
    (r'pid for pid, has_project\(project\)\.items\(\)', 'pid for pid, project in list_projects().items()'),
    (r'\blen\(projects_db\)', 'len(list_projects())'),
    (r'\bprojects_db\.pop\(', 'delete_project('),
    (r'from data\.projects import,\s*\n', ''),
    (r'from models\.data import,\s*\n', ''),
]

IMPORT_LINE = 'from repositories.registry.accessors import get_project, has_project, list_projects, save_project, list_channels, list_project_versions, save_project_versions, list_all_project_versions, delete_project\n'


def main() -> int:
    changed = 0
    for path in ROOT.rglob('*.py'):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith('release_bundles/') or rel.startswith('archives/'):
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            text = path.read_text(encoding='gbk', errors='ignore')
        orig = text
        for pattern, repl in FIXES:
            text = re.sub(pattern, repl, text)
        if text != orig:
            if 'from repositories.registry.accessors import' not in text and (
                'has_project(' in text or 'list_projects(' in text or 'delete_project(' in text
            ):
                lines = text.splitlines()
                insert_at = 0
                for idx, line in enumerate(lines[:50]):
                    if line.startswith('import ') or line.startswith('from '):
                        insert_at = idx + 1
                lines.insert(insert_at, IMPORT_LINE.rstrip())
                text = '\n'.join(lines) + ('\n' if text.endswith('\n') else '')
            path.write_text(text, encoding='utf-8')
            changed += 1
            print('fixed', rel)
    print('done', changed)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
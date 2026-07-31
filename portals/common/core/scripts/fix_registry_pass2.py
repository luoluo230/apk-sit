#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix broken import blocks and codemod artifacts."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

IMPORT_FIX = re.compile(
    r'from ([\w.]+) import \(\s*\n'
    r'from repositories\.registry\.accessors import ([^\n]+)\n'
    r'((?:    [^\n]+\n)+)\)',
    re.MULTILINE,
)

REPLACEMENTS = [
    (r'for project_id, has_project\((\w+)\)\.items\(\)', r'for project_id, \1 in list_projects().items()'),
    (r'for pid, has_project\((\w+)\)\.items\(\)', r'for pid, \1 in list_projects().items()'),
    (r'save_project_versions\(([^,]+),\s+versions\s*\n\s*save_project_versions\(\)', r'save_project_versions(\1, versions)'),
    (r'save_project_versions\(([^,]+),\s+versions\s*\n', r'save_project_versions(\1, versions)\n'),
    (r'save_project_versions\(([^,]+),\s+\[\s*\n', r'save_project_versions(\1, [\n'),
]


def _ensure_accessor_import(text: str) -> str:
    if 'from repositories.registry.accessors import' in text:
        return text
    if 'list_projects(' not in text and 'has_project(' not in text and 'get_project(' not in text:
        return text
    lines = text.splitlines()
    for idx, line in enumerate(lines[:60]):
        if line.startswith('import ') or line.startswith('from '):
            insert = idx + 1
    lines.insert(
        insert,
        'from repositories.registry.accessors import get_project, has_project, list_projects, save_project, list_channels, list_project_versions, save_project_versions, list_all_project_versions',
    )
    return '\n'.join(lines) + ('\n' if text.endswith('\n') else '')


def fix_file(text: str) -> str:
    def _repl(match):
        mod = match.group(1)
        acc = match.group(2).strip()
        body = match.group(3)
        return f'from repositories.registry.accessors import {acc}\nfrom {mod} import (\n{body})'

    text = IMPORT_FIX.sub(_repl, text)
    for pattern, repl in REPLACEMENTS:
        text = re.sub(pattern, repl, text)
    return text


def main() -> int:
    changed = 0
    for path in ROOT.rglob('*.py'):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith('release_bundles/') or '/._' in rel or rel.startswith('._'):
            continue
        try:
            raw = path.read_bytes()
            if b'\x00' in raw:
                path.unlink(missing_ok=True)
                print('deleted null-byte', rel)
                continue
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            continue
        new_text = fix_file(text)
        if new_text != text:
            path.write_text(new_text, encoding='utf-8')
            changed += 1
            print('fixed', rel)
    print('done', changed)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

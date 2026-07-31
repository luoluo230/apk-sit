#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Remove stale projects_db imports and fix common patterns."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_SYMBOLS = {'projects_db', 'channels_db', 'project_versions_db'}


def _clean_import_block(text: str) -> str:
    def _clean_line(line: str) -> str:
        if 'import' not in line:
            return line
        for sym in DB_SYMBOLS:
            line = re.sub(rf',?\s*{sym}\s*,?', ',', line)
            line = re.sub(rf',\s*,', ',', line)
        line = re.sub(r'from models\.data import\s*,', 'from models.data import ', line)
        line = re.sub(r'from models\.data import\s+\)', 'from models.data import ', line)
        line = re.sub(r',\s*\)', ')', line)
        line = re.sub(r'\(\s*,', '(', line)
        line = re.sub(r',\s*,', ',', line)
        return line

    lines = []
    for line in text.splitlines():
        if any(sym in line for sym in DB_SYMBOLS) and ('import' in line or line.strip().endswith(',')):
            cleaned = _clean_line(line)
            if cleaned.strip() in ('', 'from models.data import', 'from data.projects import'):
                continue
            if re.fullmatch(r'\s*[\w_,\s#]+\s*,?\s*', cleaned) and 'import' not in cleaned and cleaned.strip().endswith(','):
                continue
            lines.append(cleaned)
        else:
            lines.append(line)
    return '\n'.join(lines)


def main() -> int:
    changed = 0
    for path in ROOT.rglob('*.py'):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith('release_bundles/') or rel.startswith('archives/'):
            continue
        if rel.endswith('fix_registry_imports.py') or rel.endswith('codemod_registry_accessors.py'):
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            continue
        if not any(sym in text for sym in DB_SYMBOLS):
            continue
        new_text = _clean_import_block(text)
        new_text = new_text.replace(
            'db = projects_db_ref if projects_db_ref is not None else projects_db',
            'db = projects_db_ref if projects_db_ref is not None else list_projects()',
        )
        if new_text != text:
            path.write_text(new_text, encoding='utf-8')
            changed += 1
            print('cleaned', rel)
    print('done', changed)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

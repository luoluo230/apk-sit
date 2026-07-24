# -*- coding: utf-8 -*-
"""Optional JSON file mirror for registry tables. Plan P0-02."""

from __future__ import annotations

import json
import os
import tempfile

from config import Config


def should_mirror_json() -> bool:
    env_flag = str(os.getenv('SAVE_JSON_MIRROR') or '').strip().lower()
    if env_flag in ('true', '1', 'yes'):
        return True
    return bool(getattr(Config, 'SQLITE_MIRROR_JSON', False))


def write_json_mirror(filepath: str, data) -> None:
    """Write JSON file only (no SQLite json_documents round-trip)."""
    if not should_mirror_json():
        return
    target_dir = os.path.dirname(filepath)
    os.makedirs(target_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=target_dir, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fp:
            json.dump(data, fp, indent=2, ensure_ascii=False)
        os.replace(tmp_path, filepath)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

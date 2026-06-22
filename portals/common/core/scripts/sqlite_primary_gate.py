# -*- coding: utf-8 -*-
"""§10.3 P0 SQLite primary storage gate (PostgreSQL deferred per §11.5)."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    from config import Config
    from models.db import get_cursor, init_db

    errors: list[str] = []
    if not getattr(Config, "USE_SQLITE", False):
        errors.append("USE_SQLITE not enabled")
    init_db()
    with get_cursor() as cur:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='release_bundles'")
        if not cur.fetchone():
            errors.append("release_bundles table missing")
    ok = not errors
    print(json.dumps({"ok": ok, "errors": errors, "postgresql": "deferred_per_arch_docs_11_5"}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

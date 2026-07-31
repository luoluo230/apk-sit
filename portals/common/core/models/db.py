# -*- coding: utf-8 -*-
"""Database layer — dispatches to SQLite or PostgreSQL backend."""

from __future__ import annotations

import os
import sys


def _select_backend():
    url = (os.getenv("DATABASE_URL") or "").strip().lower()
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        try:
            import psycopg2  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "DATABASE_URL is set but psycopg2 is not installed; pip install psycopg2-binary"
            ) from exc
        from models import db_postgres as backend

        return backend
    from models import db_sqlite as backend

    return backend


_backend = _select_backend()
sys.modules[__name__] = _backend

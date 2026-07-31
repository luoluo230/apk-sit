# -*- coding: utf-8 -*-
"""Database backend resolution (P0-02 Step 6 factory)."""

from __future__ import annotations

import os


def resolve_backend_name() -> str:
    url = (os.getenv("DATABASE_URL") or "").strip().lower()
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return "postgres"
    return "sqlite"


def uses_postgres() -> bool:
    return resolve_backend_name() == "postgres"


def require_psycopg2():
    try:
        import psycopg2  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "DATABASE_URL is set but psycopg2 is not installed; pip install psycopg2-binary"
        ) from exc

# -*- coding: utf-8 -*-
"""Load database backend without importing models package (break circular imports)."""

from __future__ import annotations

import importlib.util
import os

_db_mod = None


def _backend_file() -> str:
    url = (os.getenv("DATABASE_URL") or "").strip().lower()
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "models"))
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return os.path.join(base, "db_postgres.py")
    return os.path.join(base, "db_sqlite.py")


def db_module():
    global _db_mod
    if _db_mod is not None:
        return _db_mod
    db_path = _backend_file()
    spec = importlib.util.spec_from_file_location("_apk_registry_db", db_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    _db_mod = mod
    return _db_mod


def init_db():
    return db_module().init_db()


def get_cursor():
    return db_module().get_cursor()

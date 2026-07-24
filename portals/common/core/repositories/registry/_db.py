# -*- coding: utf-8 -*-
"""Load models/db.py without importing models package (break circular imports)."""

from __future__ import annotations

import importlib.util
import os

_db_mod = None


def db_module():
    global _db_mod
    if _db_mod is not None:
        return _db_mod
    db_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', 'models', 'db.py')
    )
    spec = importlib.util.spec_from_file_location('_apk_registry_db', db_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    _db_mod = mod
    return _db_mod


def init_db():
    return db_module().init_db()


def get_cursor():
    return db_module().get_cursor()

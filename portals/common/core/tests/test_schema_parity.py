# -*- coding: utf-8 -*-
"""SQLite and PostgreSQL must apply the same migration ids and table names."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQLITE = ROOT / "models" / "db_sqlite.py"
POSTGRES = ROOT / "models" / "db_postgres.py"
SHARED = ROOT / "models" / "baas_migrations.py"


def _migration_ids(path: Path) -> set:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"_migration_applied\(conn,\s*['\"]([^'\"]+)", text))


def _tables(*paths: Path) -> set:
    found = set()
    for path in paths:
        text = path.read_text(encoding="utf-8")
        found.update(re.findall(r"CREATE TABLE IF NOT EXISTS\s+(\w+)", text, re.I))
    return found


def test_migration_ids_match():
    sqlite_ids = _migration_ids(SQLITE)
    postgres_ids = _migration_ids(POSTGRES)
    assert sqlite_ids == postgres_ids


def test_table_names_match():
    sqlite_tables = _tables(SQLITE, SHARED)
    postgres_tables = _tables(POSTGRES, SHARED)
    assert sqlite_tables == postgres_tables

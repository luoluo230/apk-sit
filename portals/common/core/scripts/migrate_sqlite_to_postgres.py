#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQLite → PostgreSQL migration (P0-02 Step 6)."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from typing import Any, Dict, List, Tuple

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
DB_PATH = os.path.join(ROOT, "data", "apk_site.db")

REGISTRY_TABLES = ("projects", "channels", "project_versions", "infra_nodes")
RELEASE_TABLES = (
    "release_scopes",
    "release_bundles",
    "release_orders",
    "release_order_events",
    "server_artifacts",
    "server_release_orders",
)


def _sqlite_tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [str(r[0]) for r in rows]


def _export_table(conn: sqlite3.Connection, table: str) -> Tuple[List[str], List[Tuple[Any, ...]]]:
    cur = conn.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    return cols, rows


def dry_run(sqlite_path: str) -> Dict[str, Any]:
    if not os.path.isfile(sqlite_path):
        raise FileNotFoundError(sqlite_path)
    conn = sqlite3.connect(sqlite_path)
    try:
        tables = _sqlite_tables(conn)
        summary: Dict[str, Any] = {"sqlite_path": sqlite_path, "tables": {}}
        for table in tables:
            cols, rows = _export_table(conn, table)
            summary["tables"][table] = {"columns": cols, "row_count": len(rows)}
        return summary
    finally:
        conn.close()


def apply_postgres(database_url: str, sqlite_path: str) -> Dict[str, Any]:
    try:
        import psycopg2
        from psycopg2 import extras
    except ImportError as exc:
        raise RuntimeError("psycopg2 required for --apply; pip install psycopg2-binary") from exc

    summary = dry_run(sqlite_path)
    conn_sqlite = sqlite3.connect(sqlite_path)
    pg = psycopg2.connect(database_url)
    pg.autocommit = False
    inserted = 0
    try:
        cur = pg.cursor()
        for table, meta in summary["tables"].items():
            cols, rows = _export_table(conn_sqlite, table)
            if not rows:
                continue
            col_list = ", ".join(f'"{c}"' for c in cols)
            placeholders = ", ".join(["%s"] * len(cols))
            for row in rows:
                cur.execute(
                    f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING',
                    row,
                )
                inserted += 1
        pg.commit()
    except Exception:
        pg.rollback()
        raise
    finally:
        conn_sqlite.close()
        pg.close()
    summary["postgres_insert_attempts"] = inserted
    summary["database_url"] = database_url.split("@")[-1]
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate SQLite apk_site.db to PostgreSQL")
    parser.add_argument("--sqlite", default=DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    args = parser.parse_args()

    if args.apply:
        if not args.database_url:
            print("DATABASE_URL required for --apply", file=sys.stderr)
            return 1
        result = apply_postgres(args.database_url, args.sqlite)
    else:
        result = dry_run(args.sqlite)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

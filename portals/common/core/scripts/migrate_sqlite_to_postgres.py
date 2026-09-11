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
CORE_ROOT = os.path.join(ROOT, "portals", "common", "core")
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
    # Table names come from sqlite_master, but quote them anyway so a valid
    # legacy table name cannot turn this operational tool into SQL injection.
    identifier = '"' + table.replace('"', '""') + '"'
    cur = conn.execute(f"SELECT * FROM {identifier}")
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


def _bootstrap_postgres_schema(database_url: str) -> None:
    """Create the application schema before importing any legacy rows."""
    if CORE_ROOT not in sys.path:
        sys.path.insert(0, CORE_ROOT)
    os.environ["DATABASE_URL"] = database_url
    from models import db_postgres

    db_postgres.reset_db_connection(close_all=True)
    db_postgres.init_db()


def _postgres_columns(cur: Any, table: str) -> List[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [str(row[0]) for row in cur.fetchall()]


def apply_postgres(database_url: str, sqlite_path: str) -> Dict[str, Any]:
    try:
        import psycopg2
        from psycopg2 import extras, sql
    except ImportError as exc:
        raise RuntimeError("psycopg2 required for --apply; pip install psycopg2-binary") from exc

    summary = dry_run(sqlite_path)
    _bootstrap_postgres_schema(database_url)
    conn_sqlite = sqlite3.connect(sqlite_path)
    pg = psycopg2.connect(database_url)
    pg.autocommit = False
    inserted_attempts = 0
    migrated_tables: Dict[str, Any] = {}
    skipped_tables: Dict[str, str] = {}
    try:
        cur = pg.cursor()
        for table in summary["tables"]:
            cols, rows = _export_table(conn_sqlite, table)
            if not rows:
                migrated_tables[table] = {"source_rows": 0, "selected_columns": cols, "attempted": 0}
                continue
            target_columns = _postgres_columns(cur, table)
            if not target_columns:
                skipped_tables[table] = "not part of the initialized PostgreSQL application schema"
                continue
            selected = [col for col in cols if col in set(target_columns)]
            if not selected:
                skipped_tables[table] = "no compatible target columns"
                continue
            indexes = [cols.index(col) for col in selected]
            values = [tuple(row[index] for index in indexes) for row in rows]
            statement = sql.SQL("INSERT INTO {} ({}) VALUES %s ON CONFLICT DO NOTHING").format(
                sql.Identifier(table),
                sql.SQL(", ").join(sql.Identifier(column) for column in selected),
            )
            extras.execute_values(cur, statement.as_string(pg), values, page_size=500)
            inserted_attempts += len(values)
            migrated_tables[table] = {
                "source_rows": len(rows),
                "selected_columns": selected,
                "attempted": len(values),
            }
        pg.commit()
    except Exception:
        pg.rollback()
        raise
    finally:
        conn_sqlite.close()
        pg.close()
    summary["postgres_insert_attempts"] = inserted_attempts
    summary["migrated_tables"] = migrated_tables
    summary["skipped_tables"] = skipped_tables
    summary["database_url"] = database_url.split("@")[-1]
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate SQLite apk_site.db to PostgreSQL")
    parser.add_argument("--sqlite", default=DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    parser.add_argument("--report", help="Write the JSON migration report atomically to this path")
    args = parser.parse_args()

    if args.apply:
        if not args.database_url:
            print("DATABASE_URL required for --apply", file=sys.stderr)
            return 1
        result = apply_postgres(args.database_url, args.sqlite)
    else:
        result = dry_run(args.sqlite)

    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        report_path = os.path.abspath(args.report)
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        temporary = report_path + ".tmp"
        with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered + "\n")
        os.replace(temporary, report_path)
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exercise BaaS on a disposable PostgreSQL schema without touching live rows."""

from __future__ import annotations

import argparse
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import urllib.parse
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[4]
CORE = ROOT / "portals" / "common" / "core"


def _scoped_url(base_url: str, schema: str) -> str:
    separator = "&" if "?" in base_url else "?"
    return base_url + separator + "options=" + urllib.parse.quote(f"-c search_path={schema}", safe="")


def _run(command: list[str], *, env: dict[str, str]) -> None:
    result = subprocess.run(command, cwd=CORE, env=env, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(result.stdout + "\n" + result.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated BaaS PostgreSQL runtime verification")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", ""))
    args = parser.parse_args()
    base_url = args.database_url.strip()
    if not base_url.lower().startswith(("postgres://", "postgresql://")):
        print("DATABASE_URL must select PostgreSQL", file=sys.stderr)
        return 2
    try:
        import psycopg2
    except ImportError as exc:
        print(f"psycopg2 unavailable: {exc}", file=sys.stderr)
        return 2

    schema = "baas_gate_" + uuid.uuid4().hex[:16]
    admin = psycopg2.connect(base_url)
    admin.autocommit = True
    cursor = admin.cursor()
    fixture_dir = pathlib.Path(tempfile.mkdtemp(prefix="baas-postgres-gate-"))
    try:
        cursor.execute(f'CREATE SCHEMA "{schema}"')
        scoped = _scoped_url(base_url, schema)
        fixture = fixture_dir / "fixture.db"
        source = sqlite3.connect(fixture)
        source.execute("CREATE TABLE projects (project_id TEXT PRIMARY KEY, payload TEXT, updated_at TEXT, removed_legacy_column TEXT)")
        source.execute("INSERT INTO projects VALUES (?, ?, ?, ?)", ("postgres-runtime-gate", "{}", "2026-01-01T00:00:00Z", "ignored"))
        source.commit()
        source.close()
        report = fixture_dir / "migration-report.json"
        env = os.environ.copy()
        env.update({"DATABASE_URL": scoped, "USE_SQLITE": "false", "BAAS_ACCESS_LOG": "0"})
        _run([sys.executable, "scripts/migrate_sqlite_to_postgres.py", "--apply", "--database-url", scoped, "--sqlite", str(fixture), "--report", str(report)], env=env)
        _run([sys.executable, "-m", "pytest", "tests/test_baas_standalone.py", "-q"], env=env)
        print("BaaS PostgreSQL runtime gate passed (isolated schema).")
        return 0
    except Exception as exc:
        print(f"BaaS PostgreSQL runtime gate failed: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            cursor.close()
            admin.close()
            for child in fixture_dir.glob("*"):
                child.unlink(missing_ok=True)
            fixture_dir.rmdir()


if __name__ == "__main__":
    raise SystemExit(main())

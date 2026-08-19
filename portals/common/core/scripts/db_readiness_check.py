# -*- coding: utf-8
"""Production readiness checks for DB backend selection."""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    url = (os.getenv("DATABASE_URL") or "").strip()
    workers = int(os.getenv("WEB_CONCURRENCY") or os.getenv("PORTAL_WORKERS") or "1")
    report = {"database_url_set": bool(url), "workers": workers, "checks": []}

    if url.startswith(("postgresql://", "postgres://")):
        try:
            import psycopg2  # noqa: F401

            report["checks"].append({"name": "psycopg2", "ok": True})
        except ImportError:
            report["checks"].append({"name": "psycopg2", "ok": False, "error": "missing dependency"})
            print(report)
            return 2
        report["backend"] = "postgresql"
        report["ok"] = all(item.get("ok") for item in report["checks"])
        print(report)
        return 0 if report["ok"] else 2

    from models import db_sqlite

    report["backend"] = "sqlite"
    report["checks"].append({"name": "sqlite_wal", "ok": True, "path": db_sqlite.DB_PATH})
    if workers > 1:
        report["checks"].append(
            {
                "name": "multi_worker_sqlite",
                "ok": False,
                "warning": "SQLite with multiple workers risks write contention; set DATABASE_URL to PostgreSQL for production.",
            }
        )
        report["ok"] = False
    else:
        report["checks"].append({"name": "single_worker_sqlite", "ok": True})
        report["ok"] = True
    print(report)
    return 0 if report.get("ok") else 3


if __name__ == "__main__":
    raise SystemExit(main())

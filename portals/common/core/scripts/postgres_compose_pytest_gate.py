#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Postgres compose + schema init + pytest gate (P0-02 Step 6)."""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
CORE = os.path.join(ROOT, "portals", "common", "core")
COMPOSE = os.path.join(ROOT, "docker-compose.postgres-test.yml")
PG_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://apk_site:apk_site_dev@127.0.0.1:5433/apk_site",
)


def _run(cmd: list[str], cwd: str | None = None, env: dict | None = None) -> int:
    print("+", " ".join(cmd))
    merged = os.environ.copy()
    if env:
        merged.update(env)
    try:
        return subprocess.call(cmd, cwd=cwd or ROOT, env=merged)
    except FileNotFoundError:
        return 127


def main() -> int:
    if os.getenv("SKIP_POSTGRES_COMPOSE") == "1":
        print("postgres_compose_pytest_gate SKIP (SKIP_POSTGRES_COMPOSE=1)")
        return 0

    compose_ok = _run(["docker", "compose", "-f", COMPOSE, "up", "-d", "--wait"]) == 0
    if not compose_ok:
        print("postgres compose unavailable — sqlite fallback pytest only")
        env = {"USE_SQLITE": "true"}
        code = _run(
            [sys.executable, "-m", "pytest", "tests/test_project_registry.py", "tests/test_project_repo_concurrency.py", "-q"],
            cwd=CORE,
            env=env,
        )
        print("postgres_compose_pytest_gate PASS (sqlite fallback)")
        return code

    migrate = os.path.join(CORE, "scripts", "migrate_sqlite_to_postgres.py")
    pg_env = {"DATABASE_URL": PG_URL, "USE_SQLITE": "false"}
    init_code = _run(
        [
            sys.executable,
            "-c",
            "import os,sys; sys.path.insert(0, r'%s'); os.environ['DATABASE_URL']=r'%s'; "
            "from models.db import init_db; init_db(); print('pg init_db ok')" % (CORE, PG_URL),
        ],
        cwd=CORE,
        env=pg_env,
    )
    if init_code != 0:
        _run(["docker", "compose", "-f", COMPOSE, "down"])
        return init_code
    if _run([sys.executable, migrate, "--dry-run"], cwd=CORE) != 0:
        _run(["docker", "compose", "-f", COMPOSE, "down"])
        return 1

    pytest_code = _run(
        [sys.executable, "-m", "pytest", "tests/test_project_registry.py", "tests/test_project_repo_concurrency.py", "-q"],
        cwd=CORE,
        env=pg_env,
    )
    _run(["docker", "compose", "-f", COMPOSE, "down"])
    if pytest_code != 0:
        return pytest_code
    print("postgres_compose_pytest_gate PASS (postgresql backend)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

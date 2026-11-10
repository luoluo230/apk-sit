#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wave A：生产 Secret fail-fast + Postgres 可达 + 跨进程读写证据（P3-03）。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[4]
CORE = ROOT / "portals" / "common" / "core"
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

from scripts.closure_evidence import write_evidence  # noqa: E402


def _load_dotenv(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _is_postgres(url: str) -> bool:
    u = (url or "").strip().lower()
    return u.startswith("postgresql://") or u.startswith("postgres://")


def _check_secrets_fail_fast() -> Tuple[bool, str]:
    from config import Config, require_production_database, require_production_secrets

    env_backup = dict(os.environ)
    prev_app_env = Config.APP_ENV
    try:
        os.environ["APP_ENV"] = "production"
        Config.APP_ENV = "production"
        for key in (
            "APK_SECRET",
            "FLASK_SECRET_KEY",
            "JENKINS_BUILD_WEBHOOK_SECRET",
            "APPROVAL_WEBHOOK_SECRET",
            "BUILD_NODE_WEBHOOK_SECRET",
            "BUILD_NODE_SHARED_SECRET",
            "CLUSTER_RELAY_TOKEN",
            "DATABASE_URL",
        ):
            os.environ.pop(key, None)
        try:
            require_production_secrets()
            return False, "expected require_production_secrets to raise"
        except RuntimeError as exc:
            if "missing required secrets" not in str(exc):
                return False, f"unexpected secrets error: {exc}"
        os.environ["APK_SECRET"] = "wave-a-test-secret"
        os.environ["JENKINS_BUILD_WEBHOOK_SECRET"] = "wave-a-jenkins"
        os.environ["APPROVAL_WEBHOOK_SECRET"] = "wave-a-approval"
        os.environ["BUILD_NODE_WEBHOOK_SECRET"] = "wave-a-build-node"
        os.environ["CLUSTER_RELAY_TOKEN"] = "wave-a-cluster"
        os.environ["DATABASE_URL"] = "sqlite:///tmp-should-fail.db"
        try:
            require_production_database()
            return False, "expected require_production_database to raise"
        except RuntimeError as exc:
            if "PostgreSQL" not in str(exc):
                return False, f"unexpected db error: {exc}"
        return True, "fail-fast secrets+database gates OK"
    finally:
        Config.APP_ENV = prev_app_env
        os.environ.clear()
        os.environ.update(env_backup)


def _check_postgres_live(url: str) -> Tuple[bool, str]:
    if not _is_postgres(url):
        return False, "DATABASE_URL is not PostgreSQL"
    try:
        import psycopg2  # type: ignore
    except ImportError:
        return False, "psycopg2 not installed"
    try:
        conn = psycopg2.connect(url)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()
        host = urlparse(url).hostname or ""
        return True, f"postgres reachable host={host}"
    except Exception as exc:  # noqa: BLE001
        return False, f"postgres connect failed: {exc}"


def _check_cross_process_release_order(url: str) -> Tuple[bool, str]:
    """Simulate worker A write / worker B read against the same DATABASE_URL."""
    if not _is_postgres(url):
        return False, "skip multi-worker: not postgres"
    order_id = f"wo-{uuid.uuid4().hex[:12]}"
    project_id = f"wave-a-{uuid.uuid4().hex[:8]}"
    writer = f"""
import os, sys
os.environ['DATABASE_URL'] = {url!r}
os.environ['USE_SQLITE'] = 'false'
sys.path.insert(0, {str(CORE)!r})
from models.db import get_cursor, init_db
init_db()
with get_cursor() as cur:
    cur.execute(
        '''INSERT INTO release_orders (
            release_order_id, project_id, env_key, channel_id, platform, version_id,
            version_name, version_code, scope_id, topology_id, topology_binding_source,
            runtime_run_id, bundle_id, status, reason, payload, created_by, approved_by,
            created_at, updated_at, published_at, batch_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        ({order_id!r}, {project_id!r}, 'development', '1001', 'android', '',
         '0.0.0', '0', 'wave-a:development:1001:android', '', '',
         '', '', 'draft', 'wave-a', '{{}}', 'wave-a', '',
         '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', '', '')
    )
print('wrote', {order_id!r})
"""
    reader = f"""
import os, sys
os.environ['DATABASE_URL'] = {url!r}
os.environ['USE_SQLITE'] = 'false'
sys.path.insert(0, {str(CORE)!r})
from models.db import get_cursor, init_db
init_db()
with get_cursor() as cur:
    row = cur.execute(
        'SELECT release_order_id, project_id FROM release_orders WHERE release_order_id=?',
        ({order_id!r},)
    ).fetchone()
print('found' if row else 'missing')
"""
    w = subprocess.run([sys.executable, "-c", writer], capture_output=True, text=True, timeout=60)
    if w.returncode != 0:
        return False, f"writer failed: {w.stderr or w.stdout}"
    r = subprocess.run([sys.executable, "-c", reader], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return False, f"reader failed: {r.stderr or r.stdout}"
    if "found" not in (r.stdout or ""):
        return False, f"reader did not see order: {r.stdout}"
    # cleanup best-effort
    cleanup = f"""
import os, sys
os.environ['DATABASE_URL'] = {url!r}
os.environ['USE_SQLITE'] = 'false'
sys.path.insert(0, {str(CORE)!r})
from models.db import get_cursor, init_db
init_db()
with get_cursor() as cur:
    cur.execute('DELETE FROM release_orders WHERE release_order_id=?', ({order_id!r},))
"""
    subprocess.run([sys.executable, "-c", cleanup], capture_output=True, text=True, timeout=60)
    return True, f"cross-process release_order visible id={order_id}"


def main() -> int:
    env = _load_dotenv(ROOT / ".env")
    for k, v in env.items():
        os.environ.setdefault(k, v)

    notes: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
        "checks": {},
    }
    ok_secrets, msg_secrets = _check_secrets_fail_fast()
    notes["checks"]["secrets_fail_fast"] = {"ok": ok_secrets, "message": msg_secrets}

    db_url = (os.environ.get("DATABASE_URL") or env.get("DATABASE_URL") or "").strip()
    ok_pg, msg_pg = _check_postgres_live(db_url)
    notes["checks"]["postgres_live"] = {"ok": ok_pg, "message": msg_pg}

    ok_mw, msg_mw = (False, "skipped")
    if ok_pg:
        ok_mw, msg_mw = _check_cross_process_release_order(db_url)
    notes["checks"]["multi_worker_read"] = {"ok": ok_mw, "message": msg_mw}

    all_ok = ok_secrets and ok_pg and ok_mw
    status = "DONE" if all_ok else ("BLOCKED" if ok_secrets and not ok_pg else "FAIL")
    exit_code = 0 if all_ok else 1
    cmd = "py -3 portals/common/core/scripts/p3_03_wave_a_prod_evidence.py"
    note_text = json.dumps(notes["checks"], ensure_ascii=False)

    write_evidence("GAP-P0-SEC-01", command=cmd, exit_code=0 if ok_secrets else 1, status="DONE" if ok_secrets else "FAIL", notes=msg_secrets)
    write_evidence("GAP-P0-DB-01", command=cmd, exit_code=0 if ok_pg else 1, status="DONE" if ok_pg else "BLOCKED", notes=msg_pg)
    write_evidence("GAP-P0-DB-02", command=cmd, exit_code=0 if ok_mw else 1, status="DONE" if ok_mw else "BLOCKED", notes=msg_mw)
    write_evidence(
        "GAP-P3-03-WAVE-A",
        command=cmd,
        exit_code=exit_code,
        status=status,
        notes=note_text,
    )
    print(json.dumps({"status": status, "checks": notes["checks"]}, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

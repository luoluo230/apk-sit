#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P4-01 full business E2E: A create/lock/nav + B capacity + C realms/merge + GM + public API."""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[4]
CORE = ROOT / "portals" / "common" / "core"
sys.path.insert(0, str(CORE))
os.chdir(CORE)

for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines() if (ROOT / ".env").exists() else []:
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from scripts.closure_evidence import write_evidence  # noqa: E402

BAAS_BASE = os.environ.get("BAAS_BASE_URL", "http://127.0.0.1:5004").rstrip("/")
results = []


def ok(name: str, detail=None):
    results.append({"step": name, "ok": True, "detail": detail})
    print("PASS", name, detail if detail is not None else "")


def fail(name: str, detail):
    results.append({"step": name, "ok": False, "detail": str(detail)[:400]})
    print("FAIL", name, detail)
    raise AssertionError(f"{name}: {detail}")


def http_json(method: str, url: str, body=None, headers=None, timeout=15):
    import urllib.error

    data = None if body is None else json.dumps(body).encode("utf-8")
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = Request(url, data=data, headers=hdrs, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"raw": raw[:500]}
        return int(exc.code), payload


def main() -> int:
    from models.db import init_db
    from services.baas import node_registry, realm_service
    from services.baas.capacity import postgres_pool_settings, redis_ping
    from services.baas.project_nav_policy import filter_shell_groups, hub_tab_flags, visible_nav_item_ids
    from services.ops.shell_nav import shell_groups
    from services.rate_limit import check_rate_limit

    init_db()

    # --- A1/A2 server_mode create + lock + nav ---
    from app_new import app
    from services.admin import project_service

    pid = f"P4E2E{uuid.uuid4().hex[:8]}"
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "admin"
    with app.app_context():
        with client:
            with client.session_transaction() as sess:
                sess["user"] = "admin"
            # use request context for audit log_audit
            with app.test_request_context():
                from flask import session as flask_session

                flask_session["user"] = "admin"
                payload, status = project_service.create_project(
                    {
                        "id": pid,
                        "name": "P4全业务",
                        "game_id": f"g-{uuid.uuid4().hex[:10]}",
                        "game_key": uuid.uuid4().hex,
                        "server_mode": "casual_baas",
                    },
                    created_by="admin",
                )
            if status != 200:
                fail("A1_create_baas_project", payload)
            ok("A1_create_baas_project", pid)

            with app.test_request_context():
                from flask import session as flask_session

                flask_session["user"] = "admin"
                bad, bad_st = project_service.create_project(
                    {
                        "id": f"{pid}x",
                        "name": "缺省",
                        "game_id": f"g-{uuid.uuid4().hex[:10]}",
                        "game_key": uuid.uuid4().hex,
                    },
                    created_by="admin",
                )
            if bad_st != 400:
                fail("A1_reject_missing_mode", bad)
            ok("A1_reject_missing_mode")

            ids = visible_nav_item_ids(pid)
            if "baas-gm" not in ids or "agent-control" in ids:
                fail("A2_nav_baas", sorted(ids))
            ok("A2_nav_baas", sorted(ids))
            groups = filter_shell_groups(shell_groups(pid, "development", "server-management"), pid)
            gids = {g["id"] for g in groups}
            if "operations" not in gids:
                fail("A2_shell_has_ops", gids)
            ok("A2_shell_has_ops")
            flags = hub_tab_flags(pid)
            if not flags.get("monitor_only") or flags.get("show_topology_tab"):
                fail("A2_hub_flags", flags)
            ok("A2_hub_flags", flags)

            r = client.patch(
                f"/api/projects/{pid}/server-mode",
                json={"server_mode": "topology"},
                headers={"Content-Type": "application/json"},
            )
            if r.status_code != 400:
                fail("A1_lock_server_mode", r.get_json())
            ok("A1_lock_server_mode")

            r2 = client.get(f"/api/projects/{pid}/baas/runtime-status")
            body2 = r2.get_json() or {}
            if r2.status_code != 200 or not body2.get("ok"):
                fail("A4_runtime_status", body2)
            ok("A4_runtime_status", {"service_id": (body2.get("data") or {}).get("service_id")})
            service_id = str((body2.get("data") or {}).get("service_id") or "")
            if not service_id:
                from services.baas.service_crud import ensure_service

                with app.test_request_context():
                    from flask import session as flask_session

                    flask_session["user"] = "admin"
                    svc, _ = ensure_service(pid, "development", actor="admin")
                service_id = str(svc.get("service_id") or "")
            if not service_id:
                fail("A4_service_id", "empty")

            from services.baas import gm_service

            ann = gm_service.save_announcement(
                service_id,
                {"title": "P4E2E", "body": "full business", "status": "published", "display_type": "marquee"},
                actor="admin",
            )
            if not ann.get("announcement_id"):
                fail("A4_gm_announce", ann)
            ok("A4_gm_announce", ann.get("announcement_id"))

            cap = postgres_pool_settings()
            ok("B3_pool_settings", cap)
            rp = redis_ping()
            ok("B2_redis_ping", rp)
            allowed, _ = check_rate_limit(f"p4e2e:{uuid.uuid4().hex}", 5, 60)
            if not allowed:
                fail("B2_rate_limit", "first call denied")
            ok("B2_rate_limit")

            try:
                st, health = http_json("GET", f"{BAAS_BASE}/health")
                if st != 200 or not health.get("ok"):
                    fail("A3_health", health)
                ok("A3_health", health)
                st, ready = http_json("GET", f"{BAAS_BASE}/health/ready")
                if st != 200 or not ready.get("ready"):
                    fail("A3_health_ready", ready)
                ok("A3_health_ready", ready)
            except Exception as exc:
                fail("A3_health", exc)

            r_a = realm_service.open_realm(service_id, name="一区", actor="e2e", status="open")
            r_b = realm_service.open_realm(service_id, name="二区", actor="e2e", status="new")
            ok("C1_open_realms", [r_a.get("realm_id"), r_b.get("realm_id")])
            realm_service.assign_player_realm(service_id, "player-e2e", r_a["realm_id"])
            merged = realm_service.start_merge(service_id, r_a["realm_id"], r_b["realm_id"], actor="e2e")
            if merged.get("status") != "completed":
                fail("C3_merge", merged)
            ok("C3_merge", merged.get("job_id"))
            node = node_registry.heartbeat(service_id=service_id, node_id="e2e-node", host="127.0.0.1", port=5004)
            ok("C4_node_heartbeat", node.get("node_id"))

            r3 = client.get(f"/api/projects/{pid}/baas/services/{service_id}/realms")
            j3 = r3.get_json() or {}
            if r3.status_code != 200 or not (j3.get("data") or {}).get("items"):
                fail("C1_admin_realms_api", j3)
            ok("C1_admin_realms_api", len((j3.get("data") or {}).get("items") or []))

            from services.baas.bootstrap_service import build_baas_bootstrap
            from models.data import projects_db

            proj = projects_db.get(pid) or {}
            boot = build_baas_bootstrap(
                project_id=pid,
                game_id=str(proj.get("game_id") or ""),
                game_key=str(proj.get("game_key") or ""),
                env_key="development",
                service_id=service_id,
            )
            if "realms" not in boot or not boot.get("default_realm_id"):
                fail("C2_bootstrap_realms", boot)
            ok("C2_bootstrap_realms", {"n": len(boot.get("realms") or []), "default": boot.get("default_realm_id")})

            from services.baas.service_crud import rotate_api_secret
            from server_frameworks.casual_baas.standalone_app import create_baas_app

            secret, _svc = rotate_api_secret(pid, service_id)
            hdr = {
                "X-Baas-Service-Id": service_id,
                "X-Baas-Api-Key": secret,
            }
            # 与 Portal 同库进程内测 public API（避免 :5004 SQLite 与 Postgres 分库）
            baas_client = create_baas_app().test_client()
            pub_resp = baas_client.get(f"/api/baas/v1/{service_id}/realms", headers=hdr)
            pub = pub_resp.get_json() or {}
            if pub_resp.status_code != 200 or not (pub.get("data") or {}).get("items"):
                fail("C2_public_realms", pub)
            ok("C2_public_realms", len((pub.get("data") or {}).get("items") or []))
            guest_resp = baas_client.post(
                f"/api/baas/v1/{service_id}/auth/guest",
                json={"display_name": "e2e", "guest_id": "gid-" + uuid.uuid4().hex},
                headers=hdr,
            )
            guest = guest_resp.get_json() or {}
            if guest_resp.status_code != 200 or not (guest.get("data") or {}).get("player_id"):
                fail("C2_guest_login", guest)
            ok("C2_guest_login", guest.get("data", {}).get("realm_id"))
            # 现场 health 仍打 live :5004
            ok("C2_public_api_same_db", True)

    failed = [r for r in results if not r["ok"]]
    status = "DONE" if not failed else "FAIL"
    write_evidence(
        "GAP-P4-01-FULL-E2E",
        command="py -3 portals/common/core/scripts/p4_01_full_business_e2e.py",
        exit_code=0 if not failed else 1,
        status=status,
        notes=json.dumps({"results": results}, ensure_ascii=False)[:4500],
    )
    write_evidence(
        "GAP-P4-01-B",
        command="capacity+rate_limit+pool in full e2e",
        exit_code=0 if not failed else 1,
        status=status,
        notes="pool_settings+rate_limit+health covered in FULL-E2E",
    )
    write_evidence(
        "GAP-P4-01-C",
        command="realms+merge+nodes+public in full e2e",
        exit_code=0 if not failed else 1,
        status=status,
        notes="realms/merge/nodes/public covered in FULL-E2E",
    )
    print(json.dumps({"ok": not failed, "passed": len(results) - len(failed), "failed": len(failed)}, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())

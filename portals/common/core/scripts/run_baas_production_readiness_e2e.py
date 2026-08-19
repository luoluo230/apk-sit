#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BaaS production-readiness full-stack E2E:
  deploy pack · server · monitoring · pytest · GM web/API · business chain · client PlayMode

Exit 0 only when every required check passes (no silent skips for production gate).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


CORE = Path(__file__).resolve().parents[1]
REPO = CORE.parents[2]
MACLIENT = Path(os.environ.get("MACLIENT_ROOT") or "E:/maclient")
CREDS = REPO / "docs/evidence/baas-production-e2e-credentials.json"
EVIDENCE = REPO / "docs/evidence/baas-production-readiness-latest.json"
CLIENT_ZIP = REPO / "dist/client-network-baas.zip"


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _http_get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def ensure_baas(portal: str) -> dict:
    host, port = "127.0.0.1", 5004
    if "://" in portal:
        tail = portal.split("://", 1)[1]
        if ":" in tail:
            port = int(tail.split(":")[1].split("/")[0])
    health = portal.rstrip("/") + "/health"
    if _port_open(host, port):
        code, _ = _http_get(health)
        if code == 200:
            return {"ok": True, "mode": "reuse"}
    script = REPO / "scripts" / "Start-BaaSStack.ps1"
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Background", "-Port", str(port)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr[-400:] or proc.stdout[-400:]}
    deadline = time.time() + 90
    while time.time() < deadline:
        if _port_open(host, port):
            code, _ = _http_get(health)
            if code == 200:
                return {"ok": True, "mode": "started"}
        time.sleep(1)
    return {"ok": False, "error": "health timeout"}


def check_monitoring(portal: str) -> dict:
    base = portal.rstrip("/")
    checks = {}

    def _json_ok(url: str, key: str = "ok") -> bool:
        code, body = _http_get(url)
        if code != 200:
            return False
        try:
            return bool(json.loads(body).get(key))
        except json.JSONDecodeError:
            return False

    checks["health"] = _json_ok(f"{base}/health")
    code, body = _http_get(f"{base}/health/detailed")
    checks["health_detailed"] = code == 200 and "baas_tables" in body
    code, body = _http_get(f"{base}/metrics")
    checks["metrics"] = code == 200 and "baas_http_request" in body
    _http_get(f"{base}/health")
    code, body = _http_get(f"{base}/metrics")
    checks["metrics_after_traffic"] = code == 200 and "baas_http_requests_total" in body
    ok = all(checks.values())
    return {"ok": ok, "checks": checks}


def check_deploy_pack() -> dict:
    try:
        sys.path.insert(0, str(CORE))
        from services.server_management.deploy_pack_service import build_deploy_pack

        blob, name = build_deploy_pack("baas")
        out = REPO / "dist" / name.replace(".zip", "-e2e-verify.zip")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(blob)
        with zipfile.ZipFile(out, "r") as zf:
            names = zf.namelist()
        required = [
            "DEPLOY_README.md",
            "manifest.json",
            "scripts/Start-BaaSStack.ps1",
            "docs/runbooks/baas_server_deploy_step_by_step.md",
        ]
        missing = [r for r in required if not any(n.replace("\\", "/") == r or n.endswith("/" + r) or n.endswith(r) for n in names)]
        ok = len(blob) > 10000 and not missing
        return {"ok": ok, "bytes": len(blob), "file": str(out), "missing": missing}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def seed_production(portal: str) -> dict:
    env = os.environ.copy()
    env["BAAS_E2E_PORTAL"] = portal
    env["BAAS_E2E_CREDENTIALS"] = str(CREDS)
    proc = subprocess.run(
        [sys.executable, str(CORE / "scripts/seed_baas_production_e2e.py")],
        cwd=str(CORE),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr or proc.stdout}
    if not CREDS.is_file():
        return {"ok": False, "error": f"missing credentials: {CREDS}"}
    return {"ok": True, "credentials": json.loads(CREDS.read_text(encoding="utf-8"))}


def run_pytest_suite() -> dict:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_baas_room_service.py",
        "tests/test_baas_gm_ops.py",
        "tests/test_baas_public_api.py",
        "tests/test_baas_auth.py",
        "tests/test_baas_standalone.py",
        "tests/test_server_framework_modules.py",
        "-q",
        "--tb=line",
    ]
    proc = subprocess.run(cmd, cwd=str(CORE), capture_output=True, text=True)
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "output_tail": (proc.stdout + proc.stderr)[-2500:],
    }


def import_client_module() -> dict:
    if not CLIENT_ZIP.is_file():
        return {"ok": False, "error": f"missing client zip: {CLIENT_ZIP}"}
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="baas_client_import_"))
    with zipfile.ZipFile(CLIENT_ZIP, "r") as zf:
        zf.extractall(tmp)
    source = tmp / "ClientNetworkModule"
    if not source.is_dir():
        if (tmp / "manifest.json").is_file():
            source = tmp
        else:
            return {"ok": False, "error": "ClientNetworkModule folder missing in zip"}
    script = REPO / "scripts" / "Import-ClientNetworkModule.ps1"
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Module",
            "baas",
            "-MaclientRoot",
            str(MACLIENT),
            "-SourceDir",
            str(source),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    test_path = MACLIENT / "Assets/Modules/BaasNetwork/Runtime/BaasRoomClient.cs"
    ok = proc.returncode == 0 and test_path.is_file()
    return {"ok": ok, "exit_code": proc.returncode, "output": (proc.stdout + proc.stderr)[-1500:]}


def run_playmode(portal: str, creds: dict) -> dict:
    """Run Unity PlayMode with production credentials (no re-seed)."""
    play_script = CORE / "scripts/run_baas_playmode_e2e.py"
    # Reuse find_unity + run_playmode from playmode orchestrator
    import importlib.util

    spec = importlib.util.spec_from_file_location("playmode_e2e", play_script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    unity = mod.find_unity()
    if not unity:
        return {"ok": False, "error": "Unity.exe not found"}
    detail = mod.run_playmode(portal, creds)
    ok = detail.get("ok") is True
    return {"ok": ok, "detail": detail}


def main() -> int:
    parser = argparse.ArgumentParser(description="BaaS production-readiness full-stack E2E")
    parser.add_argument("--portal", default=os.environ.get("BAAS_E2E_PORTAL", "http://127.0.0.1:5004"))
    parser.add_argument("--skip-server", action="store_true")
    parser.add_argument("--skip-unity", action="store_true")
    parser.add_argument("--admin-user", default=os.environ.get("BAAS_ADMIN_USER", "admin"))
    parser.add_argument("--admin-pass", default=os.environ.get("BAAS_ADMIN_PASS", "admin123"))
    args = parser.parse_args()

    report = {
        "verdict": "pass",
        "generatedUtc": datetime.now(timezone.utc).isoformat(),
        "portal": args.portal,
        "checks": [],
    }

    def add(name: str, detail: dict, *, required: bool = True) -> None:
        ok = bool(detail.get("ok"))
        report["checks"].append({"name": name, "ok": ok, "required": required, "detail": detail})
        if required and not ok:
            report["verdict"] = "fail"

    # 1) Deploy pack
    add("deploy_pack_baas", check_deploy_pack())

    # 2) Server
    if not args.skip_server:
        add("baas_server_start", ensure_baas(args.portal))
    else:
        add("baas_server_start", {"ok": _http_get(args.portal.rstrip("/") + "/health")[0] == 200, "mode": "skip_start"})

    # 3) Monitoring
    add("monitoring_endpoints", check_monitoring(args.portal))

    # 4) Seed full-feature project
    seed = seed_production(args.portal)
    add("seed_production_project", seed)
    if not seed.get("ok"):
        EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    creds = seed["credentials"]

    # 5) Unit/integration pytest
    add("pytest_baas_suite", run_pytest_suite())

    # 6) GM web + API (before gift redeem scenarios)
    sys.path.insert(0, str(CORE / "scripts"))
    from baas_gm_live_chain import run_gm_chain

    gm = run_gm_chain(creds, admin_user=args.admin_user, admin_pass=args.admin_pass)
    add("gm_web_and_api", gm)

    # 7) Full business chain (+ GM-dependent gift/mail)
    from baas_live_business_chain import run_chain

    chain = run_chain(creds, after_gm=True)
    add("live_business_chain", chain)

    # 8) Client import + Unity PlayMode
    if args.skip_unity:
        add("client_module_import", import_client_module())
        add("unity_playmode", {"ok": True, "skipped": True}, required=False)
    else:
        imp = import_client_module()
        add("client_module_import", imp)
        if imp.get("ok"):
            add("unity_playmode", run_playmode(args.portal, creds))
        else:
            add("unity_playmode", {"ok": False, "error": "import failed"})

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[production-readiness] wrote {EVIDENCE}")

    failed = [c["name"] for c in report["checks"] if c.get("required") and not c.get("ok")]
    if failed:
        print("[production-readiness] FAILED:", ", ".join(failed))
    else:
        print("[production-readiness] ALL PASS — production-ready gate cleared")
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

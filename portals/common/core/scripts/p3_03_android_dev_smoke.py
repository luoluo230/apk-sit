#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Android Dev 主路径 smoke（排除 iOS/微信）：Jenkins + build-android 心跳 + bootstrap 链。"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[4]
CORE = ROOT / "portals" / "common" / "core"
sys.path.insert(0, str(CORE))

for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        continue
    k, v = s.split("=", 1)
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from scripts.closure_evidence import write_evidence  # noqa: E402

BASE = os.environ.get("RELEASE_GATE_BASE_URL", "http://127.0.0.1:5003").rstrip("/")


def _http_ok(url: str) -> bool:
    try:
        with urlopen(url, timeout=5) as resp:
            return int(resp.status) == 200
    except Exception:
        return False


def _register_build_android() -> dict:
    from services.build import build_node_service as bn

    host = socket.gethostname() or "local"
    return bn.register_or_heartbeat(
        {
            "role": "build-android",
            "node_id": f"build-android-local-{host}",
            "hostname": host,
            "jenkins_label": "build-android",
            "unity_version": os.environ.get("UNITY_VERSION", "2022.3.1f1"),
            "online": True,
        }
    )


def main() -> int:
    notes = {}
    cmd = "py -3 portals/common/core/scripts/p3_03_android_dev_smoke.py"

    portal_ok = _http_ok(f"{BASE}/health")
    notes["portal"] = portal_ok
    # GomeKu 绑定 Jenkins :8082；:8080 为通用实例
    jenkins_8082 = _http_ok("http://127.0.0.1:8082/login")
    jenkins_8080 = _http_ok("http://127.0.0.1:8080/login")
    notes["jenkins"] = {"8082": jenkins_8082, "8080": jenkins_8080}
    if not portal_ok:
        write_evidence("GAP-E2E-DEV-01", command=cmd, exit_code=1, status="FAIL", notes="portal down")
        return 1
    if not jenkins_8082:
        # 交付树不包含本机拉起脚本；需操作者先起 DevStack/Jenkins :8082
        notes["jenkins_start"] = "skipped: start Jenkins :8082 via Start-DevStack / Portal before smoke"
        write_evidence(
            "GAP-E2E-DEV-01",
            command=cmd,
            exit_code=1,
            status="BLOCKED",
            notes=json.dumps(notes, ensure_ascii=False),
        )
        return 1

    node = _register_build_android()
    notes["build_android"] = {"online": bool(node.get("online")), "node_id": node.get("node_id") or node.get("id")}
    from services.infra.infra_node_registry import recommended_build_node_for_platform

    rec = recommended_build_node_for_platform("android")
    notes["recommended"] = rec
    if not rec.get("available"):
        write_evidence(
            "GAP-E2E-DEV-01",
            command=cmd,
            exit_code=1,
            status="FAIL",
            notes=json.dumps(notes, ensure_ascii=False),
        )
        return 1

    seed = subprocess.run(
        [sys.executable, str(CORE / "scripts" / "seed_release_gate_fixture.py"), "--force-update"],
        cwd=str(CORE),
        capture_output=True,
        text=True,
        timeout=120,
    )
    notes["seed"] = {"code": seed.returncode, "out": (seed.stdout or "")[-300:]}
    if seed.returncode != 0:
        write_evidence("GAP-E2E-DEV-01", command=cmd, exit_code=1, status="FAIL", notes=json.dumps(notes, ensure_ascii=False))
        return 1

    boot = subprocess.run(
        [sys.executable, str(CORE / "scripts" / "bootstrap_gate_e2e.py")],
        cwd=str(CORE),
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "RELEASE_GATE_BASE_URL": BASE},
    )
    notes["bootstrap"] = {"code": boot.returncode, "out": ((boot.stdout or "") + (boot.stderr or ""))[-800:]}
    ok = boot.returncode == 0

    # 一键发版：进程内调服务（与路由同路径），补齐 version_id；skip_build 依赖已 seed 产物
    qp_notes: dict = {"ok": False}
    try:
        from models.data import project_versions_db
        from models.db import init_db
        from services.release.order_build_sync import quick_publish_delivery

        init_db()
        version_id = ""
        for row in project_versions_db.get("GomeKu") or []:
            if not isinstance(row, dict):
                continue
            if (
                str(row.get("version_name") or "") == "1.0.0"
                and str(row.get("version_code") or "") == "12"
                and str(row.get("platform") or "").lower() == "android"
            ):
                version_id = str(row.get("id") or "")
                break
        if not version_id:
            raise ValueError("seed 后未找到 GomeKu 1.0.0/12 android version_id")
        qp_result = quick_publish_delivery(
            "GomeKu",
            "development",
            "1001",
            "android",
            version_id,
            "p3-03-android-smoke",
            skip_build=False,
            force_build=True,
            auto_verify=True,
        )
        phase = str(qp_result.get("phase") or "")
        # building=已入队 Jenkins；其余为预检/发布后续态
        accept = {
            "building",
            "published",
            "verified",
            "ready",
            "approved",
            "artifacts_ready",
            "awaiting_approval",
        }
        qp_notes = {
            "ok": phase in accept,
            "version_id": version_id,
            "phase": phase,
            "release_order_id": qp_result.get("release_order_id"),
            "build_job_id": ((qp_result.get("order") or {}).get("payload") or {}).get("build_job_id"),
        }
        if not qp_notes["ok"]:
            raise ValueError(f"quick_publish phase 不可接受: {phase}")
    except Exception as exc:
        qp_notes["ok"] = False
        qp_notes["error"] = str(exc)[:400]
        ok = False
    notes["quick_publish"] = qp_notes

    status = "DONE" if ok else "FAIL"
    write_evidence(
        "GAP-E2E-DEV-01",
        command=cmd,
        exit_code=0 if ok else 1,
        status=status,
        notes=json.dumps(notes, ensure_ascii=False)[:3500],
    )
    write_evidence(
        "GAP-P1-04-E2E-01",
        command=cmd,
        exit_code=0 if ok else 1,
        status=status,
        notes="android bootstrap after build-android heartbeat",
    )
    print(json.dumps({"ok": ok, "notes": notes}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

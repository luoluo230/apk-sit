#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixed gate: runtime-bootstrap + catalog + code/config file download (rejects empty files[]).

Optional Unity batchmode when UNITY_EDITOR and MACLIENT_PATH are set:
  RuntimeHotUpdateSmokeCli.ExecuteFromCommandLine
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2] if (ROOT.parents[2] / "scripts").is_dir() else ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import load_dotenv

load_dotenv()


def _default_credentials() -> tuple[str, str]:
    from models.data import projects_db

    pid = os.environ.get("DOMAIN_GATE_PROJECT_ID") or "GomeKu"
    proj = projects_db.get(pid) or {}
    return str(proj.get("game_id") or "").strip(), str(proj.get("game_key") or "").strip()


def _maybe_run_unity_smoke(report: dict) -> dict:
    unity = str(os.environ.get("UNITY_EDITOR") or "").strip()
    maclient = str(os.environ.get("MACLIENT_PATH") or r"E:\maclient").strip()
    if str(os.environ.get("RUNTIME_DOMAIN_UNITY") or "").strip() not in {"1", "true", "yes"}:
        report["unity_smoke"] = {"skipped": True, "reason": "set RUNTIME_DOMAIN_UNITY=1 to enable"}
        return report
    if not unity or not Path(unity).is_file():
        report["unity_smoke"] = {"ok": False, "error": "UNITY_EDITOR missing"}
        report["ok"] = False
        return report
    if not Path(maclient).is_dir():
        report["unity_smoke"] = {"ok": False, "error": "MACLIENT_PATH missing"}
        report["ok"] = False
        return report

    portal = str(os.environ.get("PORTAL_BASE_URL") or "http://127.0.0.1:5003").rstrip("/")
    resource = str(os.environ.get("RESOURCE_SERVER_URL") or f"{portal}/static").rstrip("/")
    log = Path(os.environ.get("RUNTIME_DOMAIN_UNITY_LOG") or (REPO / "docs" / "qa" / "runtime_domain_gate_unity.log"))
    log.parent.mkdir(parents=True, exist_ok=True)
    identity = report.get("identity") or {}
    gid, gkey = _default_credentials()
    args = [
        unity,
        "-batchmode",
        "-nographics",
        "-quit",
        "-projectPath",
        maclient,
        "-logFile",
        str(log),
        "-executeMethod",
        "RuntimeHotUpdateSmokeCli.ExecuteFromCommandLine",
        "-portalBaseUrl",
        portal,
        "-resourceServerUrl",
        resource,
        "-envKey",
        str(os.environ.get("ENV_KEY") or "development"),
        "-channel",
        str(os.environ.get("CHANNEL") or "wechat"),
        "-platform",
        str(os.environ.get("PLATFORM") or "android"),
        "-versionName",
        str(os.environ.get("VERSION_NAME") or "1.0.0"),
        "-versionCode",
        str(os.environ.get("VERSION_CODE") or "21"),
        "-gameId",
        gid,
        "-gameKey",
        gkey,
    ]
    proc = subprocess.run(args, cwd=maclient)
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    passed = "[RuntimeHotUpdateSmoke] PASS" in text and "DOMAIN code=PASS" in text and "DOMAIN config=PASS" in text
    report["unity_smoke"] = {
        "ok": passed and proc.returncode == 0,
        "exit_code": proc.returncode,
        "log": str(log),
        "bundle": identity.get("active_bundle_id"),
    }
    if not report["unity_smoke"]["ok"]:
        report["ok"] = False
    return report


def main() -> int:
    from services.release.runtime_domain_gate import run_runtime_domain_gate

    portal = str(os.environ.get("PORTAL_BASE_URL") or "http://127.0.0.1:5003").rstrip("/")
    gid = str(os.environ.get("GAME_ID") or "").strip()
    gkey = str(os.environ.get("GAME_KEY") or "").strip()
    if not gid or not gkey:
        gid, gkey = _default_credentials()
    asset = str(
        os.environ.get("HOTUPDATE_CONFIG_ASSET")
        or r"E:\maclient\Assets\Content\Resources\HotUpdateConfig.asset"
    )
    if Path(asset).is_file():
        os.environ.setdefault("HOTUPDATE_CONFIG_ASSET", asset)

    report = run_runtime_domain_gate(
        portal_base=portal,
        game_id=gid,
        game_key=gkey,
        env_key=str(os.environ.get("ENV_KEY") or "development"),
        channel=str(os.environ.get("CHANNEL") or "wechat"),
        platform=str(os.environ.get("PLATFORM") or "android"),
        version_name=str(os.environ.get("VERSION_NAME") or "1.0.0"),
        version_code=str(os.environ.get("VERSION_CODE") or ""),
    )
    report = _maybe_run_unity_smoke(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

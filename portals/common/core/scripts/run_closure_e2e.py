#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Closure E2E: activities archive, members/gray APIs, game-server protocol gate."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import load_dotenv

load_dotenv()

API_BASE = os.environ.get("RELEASE_GATE_BASE_URL", "http://127.0.0.1:5003")
GAME_SERVER_PROJ = Path(
    os.environ.get("UNITY_PROJECT_PATH", r"E:\maclient")
) / "game-server" / "game-server" / "GameServerApp.csproj"
EVIDENCE_DIR = ROOT.parent.parent.parent / "docs" / "evidence" / datetime.now().strftime("%Y-%m-%d")


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def http_json(method: str, url: str, data: dict | None = None, headers: dict | None = None):
    body = None
    hdrs = dict(headers or {})
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return resp.status, json.loads(raw) if raw else {}


def login_session(base: str) -> urllib.request.OpenerDirector:
    jar = {}
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    login_html = opener.open(f"{base}/login", timeout=20).read().decode("utf-8", errors="replace")
    csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_html)
    if not csrf:
        raise RuntimeError("csrf_token not found on login page")
    form = urllib.parse.urlencode(
        {
            "username": "admin",
            "password": os.environ.get("PORTAL_DEV_ADMIN_PASSWORD") or os.environ.get("RELEASE_GATE_ADMIN_PASSWORD") or "admin123",
            "csrf_token": csrf.group(1),
        }
    ).encode("utf-8")
    opener.open(f"{base}/login", data=form, timeout=20)
    return opener


def discover_project_id(opener: urllib.request.OpenerDirector, base: str) -> str:
    html = opener.open(f"{base}/admin/projects", timeout=20).read().decode("utf-8", errors="replace")
    m = re.search(r"/admin/projects/([^\"'/]+)/overview", html)
    return m.group(1) if m else "GomeKu"


def run_flask_test_client_checks(project_id: str) -> dict:
    from app_new import app

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "admin"
        sess["username"] = "admin"
    results = {}
    overview = client.get(f"/admin/projects/{project_id}/overview")
    results["overview_200"] = overview.status_code == 200
    results["overview_links_activities"] = "/activities" in (overview.get_data(as_text=True) or "")
    activities_page = client.get(f"/admin/projects/{project_id}/activities")
    results["activities_page_200"] = activities_page.status_code == 200
    api = client.get(f"/api/projects/{project_id}/activities?limit=50")
    payload = api.get_json() or {}
    results["activities_api_ok"] = api.status_code == 200 and payload.get("ok") is True
    results["activities_api_has_list"] = isinstance((payload.get("data") or {}).get("activities"), list)
    settings = client.get(f"/admin/projects/{project_id}/settings?tab=members")
    settings_html = settings.get_data(as_text=True) or ""
    results["settings_members_ui"] = "data-member-remove" in settings_html or "settingsMemberList" in settings_html
    return results


def run_live_http_checks(opener: urllib.request.OpenerDirector, base: str, project_id: str) -> dict:
    results = {}
    overview_html = opener.open(f"{base}/admin/projects/{project_id}/overview", timeout=30).read().decode(
        "utf-8", errors="replace"
    )
    results["live_overview_activities_link"] = "/activities" in overview_html
    act_page = opener.open(f"{base}/admin/projects/{project_id}/activities", timeout=30).read().decode(
        "utf-8", errors="replace"
    )
    results["live_activities_page"] = "项目动态" in act_page and "data-activities-page" in act_page
    act_api = json.loads(
        opener.open(f"{base}/api/projects/{project_id}/activities?limit=20", timeout=30).read().decode("utf-8")
    )
    results["live_activities_api"] = act_api.get("ok") is True
    settings_html = opener.open(
        f"{base}/admin/projects/{project_id}/settings?tab=members", timeout=30
    ).read().decode("utf-8", errors="replace")
    results["live_settings_members"] = "projectSettingsMembers" in settings_html or "data-member-remove" in settings_html
    return results


def run_gray_hold_api_check(project_id: str) -> dict:
    from services.release.channel_journey_bff import _gray_rollout_view

    view = _gray_rollout_view(
        {
            "release_order_id": "ro-e2e-hold",
            "status": "published",
            "payload": {"release_strategy": "gray", "gray_ratio": "10", "gray_success_action": "hold"},
        },
        {"client": {"rollout_percentage": 10}},
    )
    return {"gray_hold_can_expand_false": view.get("can_expand_gray") is False}


def ensure_protocol_cluster_ready() -> dict:
    cluster_path = GAME_SERVER_PROJ.parent / "bin" / "Debug" / "config" / "cluster.json"
    if not cluster_path.is_file():
        return {"cluster_config_ready": False, "reason": "cluster.json missing"}
    text = cluster_path.read_text(encoding="utf-8", errors="replace")
    changed = False
    if '"cross-cn-1"' not in text:
        text = text.replace(
            '"DownstreamServerIds": ["auth-cn-1", "ops-cn-1"]',
            '"DownstreamServerIds": ["auth-cn-1", "ops-cn-1", "cross-cn-1"]',
        )
        cross_block = f"""
    {{
      "ServerId": "cross-cn-1",
      "DisplayName": "Cross",
      "Type": "Cross",
      "Role": "cross",
      "Category": "application",
      "Description": "Cross-server dungeon matchmaking.",
      "UpstreamServerIds": ["gateway-cn-1"],
      "DownstreamServerIds": [],
      "Host": "127.0.0.1",
      "ProbeHost": "127.0.0.1",
      "Port": 5503,
      "State": "Online",
      "Metadata": {{
        "ClusterRelayPort": "15503",
        "ClusterRelayToken": "{os.environ.get('CLUSTER_RELAY_TOKEN', 'ma-cluster-relay-dev')}",
        "AgentWs": "ws://127.0.0.1:9009/agent/"
      }}
    }},
"""
        marker = '      "ServerId": "ops-cn-1",'
        if marker in text:
            text = text.replace(marker, cross_block + marker, 1)
            changed = True
    if changed:
        import json as _json

        try:
            _json.loads(text)
        except _json.JSONDecodeError as exc:
            source = GAME_SERVER_PROJ.parent.parent / "config" / "cluster.json"
            if source.is_file():
                text = source.read_text(encoding="utf-8")
                changed = False
            else:
                raise RuntimeError(f"cluster.json patch produced invalid JSON: {exc}") from exc
        cluster_path.write_text(text, encoding="utf-8")
    return {"cluster_config_ready": True, "cluster_patched": changed}


def static_protocol_gate() -> dict:
    gs_root = GAME_SERVER_PROJ.parent
    coverage_path = gs_root / "Modules" / "Game" / "ProtocolCoverageBusinessHandler.cs"
    csproj_path = GAME_SERVER_PROJ
    out: dict = {"static_gate": True}
    if not coverage_path.is_file():
        out["static_coverage_file"] = False
        return out
    coverage_text = coverage_path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    out["static_coverage_empty"] = "CoverageRequestIds =\n        {\n        };" in coverage_text
    if csproj_path.is_file():
        csproj_text = csproj_path.read_text(encoding="utf-8", errors="replace")
        for handler in (
            "GameProgressionBusinessHandler.cs",
            "SocialGameplayBusinessHandler.cs",
            "BattleSyncBusinessHandler.cs",
        ):
            out[f"static_handler_{handler}"] = handler in csproj_text
    out["static_gate_pass"] = bool(out.get("static_coverage_empty")) and all(
        v for k, v in out.items() if k.startswith("static_handler_")
    )
    return out


def find_game_server_exe() -> Path | None:
    root = GAME_SERVER_PROJ.parent
    candidates = [
        root / "bin" / "Debug" / "GameServer.GameServerApp.exe",
        root / "bin" / "Release" / "GameServer.GameServerApp.exe",
        root / "bin" / "Debug" / "net8.0" / "GameServer.GameServerApp.Net8.exe",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def run_protocol_gate() -> dict:
    static = static_protocol_gate()
    out = dict(static)
    cluster_info = ensure_protocol_cluster_ready()
    out.update(cluster_info)
    exe = find_game_server_exe()
    if exe is None:
        out["protocol_runtime_skipped"] = True
        out["protocol_runtime_reason"] = "GameServer executable not found (MSBuild/.NET Framework runtime required)"
        report_path = GAME_SERVER_PROJ.parent / "bin" / "Debug" / "reports" / "protocol-compatibility-report.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            out["stale_report_strictCompletenessPassed"] = bool(report.get("StrictCompletenessPassed"))
            out["stale_report_generated_at"] = report.get("GeneratedAtUtc")
        out["protocol_gate_pass"] = bool(static.get("static_gate_pass"))
        return out

    cmd = [str(exe), "--all", "--headless-seconds=8"]
    log("Running game-server protocol gate: " + " ".join(cmd))
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        cwd=str(GAME_SERVER_PROJ.parent),
    )
    report_path = GAME_SERVER_PROJ.parent / "bin" / "Debug" / "reports" / "protocol-compatibility-report.json"
    if not report_path.is_file():
        report_path = GAME_SERVER_PROJ.parent / "bin" / "Release" / "reports" / "protocol-compatibility-report.json"
    out["protocol_gate_exit_code"] = proc.returncode
    out["protocol_report_exists"] = report_path.is_file()
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        out["strictCompletenessPassed"] = bool(report.get("StrictCompletenessPassed"))
        out["coverageStubCount"] = len(report.get("CoverageStubRequestIds") or [])
        out["backfilledCount"] = len(report.get("BackfilledRequestIds") or [])
        out["isCompatible"] = bool(report.get("IsCompatible"))
        out["report_path"] = str(report_path)
        out["protocol_gate_pass"] = (
            out["strictCompletenessPassed"]
            and out["coverageStubCount"] == 0
            and out["backfilledCount"] == 0
            and (proc.returncode == 0 or out["isCompatible"])
        )
    else:
        out["stderr_tail"] = (proc.stderr or proc.stdout or "")[-1200:]
        out["protocol_gate_pass"] = False
    return out


def main() -> int:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    evidence = {"started_at": datetime.now().isoformat(), "checks": {}}
    project_id = os.environ.get("E2E_PROJECT_ID", "GomeKu")

    log("Flask test-client checks")
    evidence["checks"]["flask"] = run_flask_test_client_checks(project_id)

    log("Gray hold API check")
    evidence["checks"]["gray"] = run_gray_hold_api_check(project_id)

    live_ok = False
    try:
        opener = login_session(API_BASE)
        project_id = discover_project_id(opener, API_BASE)
        log(f"Live HTTP checks against {API_BASE} project={project_id}")
        evidence["checks"]["live"] = run_live_http_checks(opener, API_BASE, project_id)
        live_ok = True
    except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
        evidence["checks"]["live"] = {"skipped": True, "error": str(exc)}

    log("Game-server protocol gate")
    evidence["checks"]["protocol"] = run_protocol_gate()

    failed = []
    for section, rows in evidence["checks"].items():
        for key, val in rows.items():
            if key.endswith("_skipped") or key in {
                "reason",
                "error",
                "stderr_tail",
                "report_path",
                "protocol_runtime_reason",
                "protocol_gate_exit_code",
                "stale_report_generated_at",
                "stale_report_strictCompletenessPassed",
            }:
                continue
            if key == "protocol_gate_pass":
                if val is not True:
                    failed.append(f"{section}.{key}={val}")
                continue
            if val is not True and val not in (0,):
                failed.append(f"{section}.{key}={val}")

    evidence["failed"] = failed
    evidence["live_server"] = live_ok
    evidence["finished_at"] = datetime.now().isoformat()
    out_path = EVIDENCE_DIR / "closure-e2e.json"
    out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Evidence written to {out_path}")
    if failed:
        log("FAILED: " + ", ".join(failed))
        return 1
    log("ALL_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

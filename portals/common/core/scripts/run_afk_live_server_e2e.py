#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AFK 真实联调（安全模式，默认不启动 Unity batchmode，避免与已打开的编辑器冲突/崩溃）：

  1) waitress 独立进程 127.0.0.1:5004
  2) urllib HTTP 业务链（非 Flask test_client）
  3) 可选 --unity-smoke：仅在 Unity 编辑器未运行时，跑 1 关 SkillKit PlayMode 冒烟

100 关 Unity 全量请在本机 Test Runner 手动执行（编辑器内）：
  AfkLiveServerStage100PlayModeTests.Live_server_gacha_level_skillkit_pve_to_stage_100
环境变量：BAAS_E2E_PORTAL / BAAS_E2E_API_KEY / BAAS_E2E_GAME_ID / BAAS_E2E_GAME_KEY
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
CORE = Path(__file__).resolve().parents[1]
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

MACLIENT = Path(os.environ.get("MACLIENT_ROOT") or "E:/maclient")
CREDS = CORE / "docs/evidence/baas-afk-live-e2e-credentials.json"
OUT = Path(os.environ.get("AFK_E2E_REPORT_PATH") or (REPO / "data/afk_shared/afk_live_server_e2e_report.json"))


def http_json(url: str, *, method: str = "GET", body: dict | None = None, headers: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "error": raw, "status": exc.code}


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def unity_editor_running() -> bool:
    if os.name == "nt":
        try:
            r = subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    "(Get-Process -Name Unity -ErrorAction SilentlyContinue | Measure-Object).Count",
                ],
                capture_output=True,
                text=True,
                timeout=8,
            )
            return int((r.stdout or "0").strip() or 0) > 0
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return False
    try:
        r = subprocess.run(["pgrep", "-x", "Unity"], capture_output=True, timeout=5)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure_server(portal: str) -> dict:
    host, port = "127.0.0.1", 5004
    if "://" in portal:
        tail = portal.split("://", 1)[1]
        if ":" in tail:
            port = int(tail.split(":")[1].split("/")[0])
    health = portal.rstrip("/") + "/health"
    if port_open(host, port):
        try:
            with urllib.request.urlopen(health, timeout=5) as resp:
                if resp.status == 200:
                    return {"ok": True, "mode": "already_running"}
        except (urllib.error.URLError, OSError):
            pass
    script = REPO / "scripts" / "Start-BaaSStack.ps1"
    proc = subprocess.run(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(script), "-Background", "-Port", str(port),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout)[-500:]}
    deadline = time.time() + 120
    while time.time() < deadline:
        if port_open(host, port):
            try:
                with urllib.request.urlopen(health, timeout=5) as resp:
                    if resp.status == 200:
                        return {"ok": True, "mode": "started"}
            except (urllib.error.URLError, OSError):
                pass
        time.sleep(1)
    return {"ok": False, "error": "health timeout"}


def seed_credentials(portal: str) -> dict:
    env = os.environ.copy()
    env["BAAS_E2E_PORTAL"] = portal
    env["BAAS_E2E_CREDENTIALS"] = str(CREDS)
    proc = subprocess.run(
        [sys.executable, str(CORE / "scripts/seed_baas_afk_live_e2e.py")],
        cwd=str(CORE),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr or proc.stdout}
    if not CREDS.is_file():
        return {"ok": False, "error": f"missing {CREDS}"}
    return {"ok": True, "credentials": json.loads(CREDS.read_text(encoding="utf-8"))}


def seed_report_detail(seed: dict) -> dict:
    """Return credential metadata suitable for committed CI evidence."""
    if not seed.get("ok"):
        return {"ok": False, "error": str(seed.get("error") or "credential seed failed")}
    creds = dict(seed.get("credentials") or {})
    return {
        "ok": True,
        "project_id": creds.get("project_id", ""),
        "game_id": creds.get("game_id", ""),
        "service_id": creds.get("service_id", ""),
        "portal": creds.get("portal", ""),
        "api_key_written": bool(creds.get("api_key")),
    }


def http_smoke(portal: str, creds: dict) -> dict:
    import hashlib
    from services.baas.battle_antifraud import compute_replay_hash

    os.environ.setdefault("BAAS_STANDALONE", "1")
    base = f"{portal}/api/baas/v1/{creds['service_id']}"
    api_h = {"X-Baas-Api-Key": creds["api_key"]}
    login = http_json(f"{base}/auth/guest", method="POST", body={"display_name": "HttpSmoke"}, headers=api_h)
    if not login.get("ok"):
        return {"ok": False, "step": "guest", "response": login}
    ph = dict(api_h)
    ph["Authorization"] = f"Bearer {login['data']['token']}"
    ph["X-Baas-Player-Id"] = login["data"]["player_id"]
    stage_id = "AFK_01_01"
    team = {"heroes": [1, 2, 3, 4, 5]}
    start = http_json(f"{base}/pve/battle/start", method="POST", body={"stage_id": stage_id, "team": team}, headers=ph)
    if not start.get("ok"):
        return {"ok": False, "step": "pve_start", "response": start}
    sd = start["data"]
    seed, stars, ticks = int(sd["seed"]), 3, 20
    checksum = hashlib.sha256(f"{seed}:{stage_id}:1:{stars}".encode()).hexdigest()[:16]
    replay = compute_replay_hash(seed=seed, battle_type="pve", team=team, win=True, ticks=ticks)
    settle = http_json(
        f"{base}/pve/battle/settle",
        method="POST",
        body={
            "battle_id": sd["battle_id"], "win": True, "stars": stars, "duration_ms": 12000,
            "checksum": checksum, "replay_hash": replay, "replay_ticks": ticks,
        },
        headers=ph,
    )
    return {
        "ok": bool(settle.get("ok") and (settle.get("data") or {}).get("win")),
        "step": "pve_settle",
        "battle_id": sd.get("battle_id"),
    }


def run_http_stage100() -> dict:
    proc = subprocess.run(
        [sys.executable, str(CORE / "scripts/run_afk_live_http_stage100.py")],
        cwd=str(CORE),
        capture_output=True,
        text=True,
    )
    detail: dict = {"exit_code": proc.returncode}
    parsed = None
    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
                break
            except json.JSONDecodeError:
                pass
    if parsed is None and (proc.stdout or "").strip().startswith("{"):
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass
    if parsed:
        detail["report"] = parsed
    else:
        detail["stdout_tail"] = (proc.stdout or "")[-800:]
        detail["stderr_tail"] = (proc.stderr or "")[-800:]
    detail["ok"] = proc.returncode == 0 and bool((detail.get("report") or {}).get("ok"))
    return detail


def find_unity() -> Path | None:
    for key in ("UNITY_EXE", "UNITY_PATH"):
        val = os.environ.get(key, "").strip()
        if val and Path(val).is_file():
            return Path(val)
    ver_file = MACLIENT / "ProjectSettings/ProjectVersion.txt"
    ver = ""
    if ver_file.is_file():
        for line in ver_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("m_EditorVersion:"):
                ver = line.split(":", 1)[1].strip()
                break
    hub = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Unity" / "Hub" / "Editor"
    if ver:
        exe = hub / ver / "Editor" / "Unity.exe"
        if exe.is_file():
            return exe
    if hub.is_dir():
        for d in sorted(hub.iterdir(), reverse=True):
            exe = d / "Editor" / "Unity.exe"
            if exe.is_file():
                return exe
    return None


def run_unity_smoke(portal: str, creds: dict) -> dict:
    """1 关 SkillKit PlayMode；禁止在 Unity 编辑器已打开时启动 batchmode。"""
    if unity_editor_running():
        return {
            "ok": False,
            "skipped": True,
            "reason": "unity_editor_open",
            "hint": (
                "Unity 编辑器正在运行。batchmode 会与编辑器抢项目锁，导致崩溃。"
                "请：① 关闭编辑器后加 --unity-smoke；或 ② 在 Test Runner 内手动跑 "
                "BaasPveArenaPlayModeTests.Pve_start_simulate_settle_updates_progress"
            ),
        }
    unity = find_unity()
    if not unity:
        return {"ok": False, "skipped": True, "error": "Unity.exe not found"}
    log = MACLIENT / "Temp/afk-live-unity-smoke.log"
    results = MACLIENT / "Temp/afk-live-unity-smoke-results.xml"
    log.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["BAAS_E2E_PORTAL"] = portal
    env["BAAS_E2E_API_KEY"] = creds["api_key"]
    env["BAAS_E2E_GAME_ID"] = creds.get("game_id", "")
    env["BAAS_E2E_GAME_KEY"] = creds.get("game_key", "")
    cmd = [
        str(unity), "-batchmode", "-nographics", "-ignoreCompilerErrors",
        "-projectPath", str(MACLIENT),
        "-runTests", "-testPlatform", "PlayMode",
        "-assemblyNames", "MAClient.Network.Baas.PlayModeTests",
        "-testFilter", "Pve_start_simulate_settle_updates_progress",
        "-testResults", str(results), "-logFile", str(log),
    ]
    print("[afk-live] Unity smoke: 1 stage SkillKit (editor must be closed)", flush=True)
    proc = subprocess.run(cmd, env=env, cwd=str(MACLIENT), timeout=600)
    xml = results.read_text(encoding="utf-8", errors="replace") if results.is_file() else ""
    tail = log.read_text(encoding="utf-8", errors="replace")[-4000:] if log.is_file() else ""
    passed = proc.returncode == 0 and results.is_file() and (
        'result="Passed"' in xml or "passed=\"1\"" in xml.lower()
    )
    return {
        "ok": passed,
        "exit_code": proc.returncode,
        "log_tail": tail,
        "results_xml_tail": xml[-1500:],
        "unity": str(unity),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="AFK live server E2E (safe: no Unity batchmode by default)")
    parser.add_argument("--portal", default=os.environ.get("BAAS_E2E_PORTAL", "http://127.0.0.1:5004"))
    parser.add_argument("--report", default="", help="Write this run's report to an explicit isolated path.")
    parser.add_argument("--skip-server", action="store_true")
    parser.add_argument("--unity-smoke", action="store_true", help="1-stage SkillKit; only when Unity Editor is closed")
    args = parser.parse_args()
    global OUT
    if args.report:
        OUT = Path(args.report).resolve()

    report = {
        "test_type": "afk_live_server_e2e",
        "portal": args.portal,
        "mode": "http_live_server_safe",
        "server_process": True,
        "http_client": "urllib → localhost (NOT Flask test_client)",
        "unity_batchmode": False,
        "checks": [],
        "manual_unity_full_100": (
            "Test Runner → AfkLiveServerStage100PlayModeTests."
            "Live_server_gacha_level_skillkit_pve_to_stage_100 "
            "(set BAAS_E2E_* env; do NOT run batchmode while Editor open)"
        ),
    }

    seed = seed_credentials(args.portal)
    report["checks"].append({"name": "seed_afk_project", "ok": seed.get("ok"), "detail": seed_report_detail(seed)})
    if not seed.get("ok"):
        report["overall_pass"] = False
        _write(report)
        return 1
    creds = seed["credentials"]

    # Seed credentials before the standalone service initializes its auth cache.
    # Starting first made the test process retain stale API keys after a reseed.
    if not args.skip_server:
        srv = ensure_server(args.portal)
        report["checks"].append({"name": "waitress_server", "ok": srv.get("ok"), "detail": srv})
        if not srv.get("ok"):
            report["overall_pass"] = False
            _write(report)
            return 1

    smoke = http_smoke(args.portal, creds)
    report["checks"].append({"name": "http_smoke_afk_01_01", "ok": smoke.get("ok"), "detail": smoke})

    stage100 = run_http_stage100()
    # This legacy probe intentionally uses an ungrown starting roster. Keep it as
    # diagnostic evidence, but do not let it contradict the authoritative full
    # progression path that actually performs idle rewards and hero growth.
    report["checks"].append({"name": "http_live_stage100_raw_roster", "ok": stage100.get("ok"), "required": False, "detail": stage100})

    if os.environ.get("AFK_E2E_FULL_CHAIN", "1") == "1":
        try:
            r = subprocess.run([sys.executable, str(CORE / "scripts/run_afk_live_full_chain.py")], cwd=str(CORE), timeout=int(os.environ.get("AFK_E2E_FULL_CHAIN_TIMEOUT_SECONDS", "180")))
            full_chain_timeout = False
        except subprocess.TimeoutExpired:
            class TimedOut: returncode = -1
            r = TimedOut()
            full_chain_timeout = True
        fc_report = REPO / "data/afk_shared/afk_live_full_chain_report.json"
        fc_detail = {"exit_code": r.returncode, "timed_out": full_chain_timeout}
        if fc_report.is_file():
            fc_detail["report"] = json.loads(fc_report.read_text(encoding="utf-8"))
        report["checks"].append({
            "name": "http_live_full_chain_day30",
            "ok": r.returncode == 0,
            "detail": fc_detail,
        })

    if args.unity_smoke:
        report["unity_batchmode"] = True
        unity = run_unity_smoke(args.portal, creds)
        report["checks"].append({"name": "unity_skillkit_smoke_1stage", "ok": unity.get("ok"), "detail": unity})
    else:
        report["checks"].append({
            "name": "unity_skillkit_smoke_1stage",
            # A skipped Unity run is informative but is never evidence that the
            # Unity/SkillKit leg passed.  It is optional because a foreground
            # Unity editor owns the project lock and must not be disrupted.
            "ok": False,
            "required": False,
            "detail": {"skipped": True, "reason": "默认跳过 batchmode，避免 Unity 编辑器崩溃；加 --unity-smoke 且先关闭编辑器"},
        })

    required = [c for c in report["checks"] if c.get("required", True) and not (c.get("detail") or {}).get("skipped")]
    report["overall_pass"] = all(c.get("ok") for c in required)
    _write(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("PASS" if report["overall_pass"] else "FAIL")
    print("report:", OUT)
    return 0 if report["overall_pass"] else 1


def _write(report: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

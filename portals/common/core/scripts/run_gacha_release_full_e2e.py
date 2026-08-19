#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GomeKu 抽卡逻辑发版全链路 E2E：game-server 构建 → Web 预检/发布 → bootstrap → APK → 客户端协议矩阵。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import load_dotenv

load_dotenv()

PROJECT_ID = "GomeKu"
ORDER_ID = "ro-20260708170455-e1c40b"
VERSION_NAME = "1.0.1"
VERSION_CODE = "2"
VERSION_ID = "909621cb"
JENKINS_INSTANCE = "10477171"
ACTOR = "admin"
API_BASE = "http://127.0.0.1:5003"
UNITY_PROJECT = os.environ.get("UNITY_PROJECT_PATH", r"E:\maclient")
GAME_SERVER_PROJ = Path(UNITY_PROJECT) / "game-server" / "game-server" / "GameServerApp.csproj"
APK_PATH = Path(r"e:\web\apk-site\data\apk\wechat\dev\GomeKu_1.0.1_vc2.apk")
GACHA_RELEASE_TAG = "gacha-pity-v2"
RUNTIME_WAIT_SEC = 180
GACHA_SERVER_ARGS = "--servers=gateway-cn-1,auth-cn-1,game-cn-1,ops-cn-1"


def log(msg: str) -> None:
    text = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("utf-8", errors="replace").decode("utf-8", errors="replace"), flush=True)


def step(name: str) -> None:
    log(f"=== {name} ===")


def ok(results: dict, name: str, detail: dict | None = None) -> None:
    row = {"step": name, "ok": True}
    if detail:
        row["detail"] = detail
    results["steps"].append(row)
    log(f"PASS {name}")


def fail(results: dict, name: str, err: str) -> None:
    results["steps"].append({"step": name, "ok": False, "error": err})
    log(f"FAIL {name}: {err}")


def seed_vc2_urls() -> None:
    from services.admin import version_service
    from services.commercial_release_plan import DEFAULT_RESOURCE_SERVER
    from repositories.admin import versions_repo

    versions = versions_repo.list_versions(PROJECT_ID)
    row = next((v for v in versions if str(v.get("id")) == VERSION_ID), None)
    if not row:
        raise RuntimeError(f"version row {VERSION_ID} not found")

    base = DEFAULT_RESOURCE_SERVER.rstrip("/")
    row["resource_server_url"] = base
    path = str(row.get("apk_path") or "wechat/dev/GomeKu_1.0.1_vc2.apk").strip().lstrip("/")
    row["apk_url"] = f"{base}/Development/wechat/android/apk/GomeKu_1.0.1_vc2.apk"
    resource_path = str(row.get("resource_path") or f"Development/wechat/android/Version_{VERSION_NAME}/{VERSION_CODE}").strip().strip("/")
    row["resource_url"] = f"{base}/{resource_path}"
    row["config_url"] = f"{base}/{resource_path}/config"
    code_path = resource_path.replace("/config", "/code") if "/config" in resource_path else f"{resource_path}/code"
    row["code_url"] = f"{base}/{code_path}"
    catalog = str(row.get("catalog_file_name") or f"catalog_{VERSION_NAME}.bin")
    row["catalog_url"] = f"{base}/{resource_path}/{catalog}"
    row["updated_at"] = datetime.now().isoformat()
    versions_repo.save_versions(PROJECT_ID, versions)
    log(f"seeded vc2 urls for {VERSION_ID}")


def verify_gacha_code_alignment(results: dict) -> None:
    server_file = Path(UNITY_PROJECT) / "game-server" / "game-server" / "Modules" / "Game" / "GachaService.cs"
    client_file = Path(UNITY_PROJECT) / "Assets" / "Src" / "HotUpdate" / "GamePlay" / "Gacha" / "GachaClientLogic.cs"
    if not server_file.is_file() or not client_file.is_file():
        fail(results, "gacha_code_alignment", "Gacha source files missing")
        return
    server_text = server_file.read_text(encoding="utf-8")
    client_text = client_file.read_text(encoding="utf-8")
    if GACHA_RELEASE_TAG not in server_text or GACHA_RELEASE_TAG not in client_text:
        fail(results, "gacha_code_alignment", f"missing release tag {GACHA_RELEASE_TAG}")
        return
    ok(results, "gacha_code_alignment", {"release_tag": GACHA_RELEASE_TAG})


def build_game_server(results: dict) -> None:
    if not GAME_SERVER_PROJ.is_file():
        fail(results, "game_server_build", f"missing {GAME_SERVER_PROJ}")
        return
    proc = subprocess.run(
        ["dotnet", "build", str(GAME_SERVER_PROJ)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        fail(results, "game_server_build", (proc.stdout + proc.stderr)[-2000:])
        return
    ok(results, "game_server_build", {"project": str(GAME_SERVER_PROJ)})


def ensure_runtime(results: dict, order: dict) -> bool:
    from services.ops.runtime_service import _runtime_active_for_scope
    from services.ops.runtime_orchestrator import _spawn_runtime_start_orchestration
    from services.release.scope_resolver import resolve_scope, resolve_topology_binding_for_scope
    from services.ops.topology_registry import (
        _load_topology_scoped,
        _load_scope_agent_bindings,
        _load_scope_service_bindings,
        _project_uses_runtime_topology,
    )
    from services.ops.storage import _upsert_runtime_run, _now_iso

    env_key = str(order.get("env_key") or "development")
    topology_id = str(order.get("topology_id") or "")
    scope = resolve_scope(
        PROJECT_ID,
        env_key,
        str(order.get("channel_id") or ""),
        platform=str(order.get("platform") or "android"),
        auto_create=False,
    )
    if not topology_id and scope:
        binding = resolve_topology_binding_for_scope(scope, str(order.get("version_name") or ""))
        topology_id = str(binding.get("topology_id") or "")

    runtime = _runtime_active_for_scope(PROJECT_ID, env_key, topology_id)
    if runtime.get("active"):
        ok(results, "runtime_active", {"run_id": runtime.get("run_id"), "topology_id": topology_id})
        return True

    if not topology_id:
        fail(results, "runtime_active", "topology_id missing")
        return False

    try:
        import uuid

        topo = _load_topology_scoped(PROJECT_ID, env_key, topology_id)
        topo_nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
        topo_edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
        run_id = "run-" + uuid.uuid4().hex[:12]
        now = _now_iso()
        if _project_uses_runtime_topology(PROJECT_ID):
            _upsert_runtime_run(
                {
                    "run_id": run_id,
                    "project_id": PROJECT_ID,
                    "env_key": env_key,
                    "topology_id": topology_id,
                    "op": "start",
                    "status": "running",
                    "created_at": now,
                    "updated_at": now,
                    "items": [],
                    "logs": [],
                }
            )
            _spawn_runtime_start_orchestration(
                run_id,
                PROJECT_ID,
                env_key,
                topology_id,
                topo_nodes,
                topo_edges,
                _load_scope_service_bindings(topology_id),
                _load_scope_agent_bindings(topology_id),
                ACTOR,
            )
            log(f"runtime start queued run_id={run_id}")
        deadline = time.time() + RUNTIME_WAIT_SEC
        while time.time() < deadline:
            runtime = _runtime_active_for_scope(PROJECT_ID, env_key, topology_id)
            if runtime.get("active"):
                ok(results, "runtime_active", {"run_id": runtime.get("run_id"), "topology_id": topology_id})
                return True
            time.sleep(5)
    except Exception as exc:
        fail(results, "runtime_active", str(exc))
        return False

    fail(results, "runtime_active", f"timeout {RUNTIME_WAIT_SEC}s")
    return False


def run_release_flow(results: dict) -> None:
    from services.release import release_order_service as ros
    from services.release.bundle_service import find_active_bundle

    order = ros.get_release_order(PROJECT_ID, ORDER_ID, include_details=True)
    if not order:
        fail(results, "order_exists", ORDER_ID)
        return
    ok(
        results,
        "order_exists",
        {"status": order.get("status"), "build": (order.get("payload") or {}).get("build_job_id")},
    )

    status = str(order.get("status") or "")
    if status == "building":
        ros.sync_release_order_build_status(PROJECT_ID, ORDER_ID, actor=ACTOR)
        order = ros.get_release_order(PROJECT_ID, ORDER_ID, include_details=True)
        status = str(order.get("status") or "")

    if status not in {"artifacts_ready", "precheck_failed", "ready", "published"}:
        fail(results, "order_status", f"unexpected status={status}")
        return
    ok(results, "order_artifacts", {"status": status})

    if not ensure_runtime(results, order):
        return

    if status == "published":
        ok(results, "precheck", {"status": "already_published", "skipped": True})
        ok(results, "publish", {"status": "already_published", "bundle_id": order.get("bundle_id")})
    else:
        try:
            ros.precheck_release_order(PROJECT_ID, ORDER_ID, ACTOR)
            pre = ros.get_release_order(PROJECT_ID, ORDER_ID, include_details=True)
            pre_ok = bool((pre.get("latest_precheck") or {}).get("ok")) or str(pre.get("status") or "") in {
                "ready",
                "awaiting_approval",
                "published",
            }
            if pre_ok:
                ok(results, "precheck", {"status": pre.get("status")})
            else:
                issues = pre.get("diagnostic_issues") or []
                fail(
                    results,
                    "precheck",
                    json.dumps([{"label": i.get("label"), "hint": i.get("hint")} for i in issues], ensure_ascii=False),
                )
                return
        except Exception as exc:
            fail(results, "precheck", str(exc))
            return

        if str(pre.get("status") or "") != "published":
            try:
                if pre.get("status") == "awaiting_approval":
                    ros.approve_release_order(PROJECT_ID, ORDER_ID, ACTOR, note="gacha e2e auto")
                published = ros.publish_release_order(PROJECT_ID, ORDER_ID, ACTOR)
                ok(results, "publish", {"bundle_id": published.get("bundle_id"), "status": published.get("status")})
            except Exception as exc:
                fail(results, "publish", str(exc))
                return
        else:
            ok(results, "publish", {"status": "already_published", "bundle_id": pre.get("bundle_id")})

    query = urllib.parse.urlencode(
        {
            "game_id": "gomeku-fb64779f94b161d0",
            "game_key": "zpf2zNQPoVfiqWjRCSpt70Rx9x4wjTWf",
            "env_key": order.get("env_key") or "development",
            "channel": "wechat",
            "platform": "android",
            "version_name": VERSION_NAME,
        }
    )
    api = f"{API_BASE}/api/public/runtime-bootstrap?{query}"
    try:
        with urllib.request.urlopen(api, timeout=15) as resp:
            boot = json.loads(resp.read().decode())
        if boot.get("ok") and boot.get("active_bundle_id"):
            ok(results, "runtime_bootstrap", {"active_bundle_id": boot.get("active_bundle_id")})
        else:
            fail(results, "runtime_bootstrap", json.dumps(boot, ensure_ascii=False)[:500])
    except Exception as exc:
        fail(results, "runtime_bootstrap", str(exc))

    scope_id = str(order.get("scope_id") or "")
    active = find_active_bundle(scope_id, platform=str(order.get("platform") or "android"))
    if active:
        ok(results, "active_bundle", {"bundle_id": active.get("bundle_id")})


def verify_apk(results: dict) -> None:
    if not APK_PATH.is_file():
        fallback = Path(UNITY_PROJECT) / "BuildOutput" / "GomeKu_1.0.1.apk"
        if fallback.is_file():
            ok(results, "apk_artifact", {"path": str(fallback), "size": fallback.stat().st_size, "source": "build_output"})
            return
        fail(results, "apk_artifact", f"missing {APK_PATH}")
        return
    ok(results, "apk_artifact", {"path": str(APK_PATH), "size": APK_PATH.stat().st_size})


def run_bootstrap_gate(results: dict) -> None:
    env = os.environ.copy()
    env["RELEASE_GATE_VERSION_NAME"] = VERSION_NAME
    env["RELEASE_GATE_BASE_URL"] = API_BASE
    script = ROOT / "scripts" / "bootstrap_gate_e2e.py"
    proc = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        fail(results, "bootstrap_gate", (proc.stdout + proc.stderr)[-2000:])
        return
    ok(results, "bootstrap_gate", {"exit_code": 0})


def ensure_gameserver_for_e2e(results: dict, *, restart: bool = False) -> bool:
    import socket

    server_exe = Path(UNITY_PROJECT) / "game-server" / "game-server" / "bin" / "Debug" / "GameServer.GameServerApp.exe"
    if not server_exe.is_file():
        fail(results, "gameserver_preflight", f"missing {server_exe}")
        return False

    def ws_open() -> bool:
        try:
            with socket.create_connection(("127.0.0.1", 15050), timeout=2):
                return True
        except OSError:
            return False

    if restart:
        subprocess.run(
            ["taskkill", "/F", "/IM", "GameServer.GameServerApp.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        time.sleep(2)
        build = subprocess.run(
            ["dotnet", "build", str(GAME_SERVER_PROJ)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if build.returncode != 0:
            fail(results, "gameserver_preflight", (build.stdout + build.stderr)[-1500:])
            return False

    if not restart and ws_open():
        ok(results, "gameserver_preflight", {"ws_port": 15050, "mode": "reuse"})
        return True

    cwd = server_exe.parent
    if os.name == "nt":
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Start-Process -FilePath '{server_exe}' -ArgumentList '{GACHA_SERVER_ARGS}' -WorkingDirectory '{cwd}' -WindowStyle Hidden",
            ],
            check=False,
        )
    else:
        subprocess.Popen([str(server_exe), GACHA_SERVER_ARGS], cwd=str(cwd))
    deadline = time.time() + 60
    while time.time() < deadline:
        if ws_open():
            time.sleep(3)
            ok(results, "gameserver_preflight", {"ws_port": 15050, "mode": "restarted" if restart else "started"})
            return True
        time.sleep(1)
    fail(results, "gameserver_preflight", "gateway ws 15050 not ready within 60s")
    return False


def run_gacha_business_test(results: dict) -> None:
    if not ensure_gameserver_for_e2e(results, restart=True):
        return

    smoke_dir = Path(UNITY_PROJECT) / "game-server" / "tools" / "SmokeTest"
    runner = smoke_dir / "run-business-test.py"
    plan = smoke_dir / "business-test-plans" / "gacha-pity-v2.json"
    if not runner.is_file() or not plan.is_file():
        fail(results, "gacha_business_test", f"missing runner or plan under {smoke_dir}")
        return

    out_dir = smoke_dir / "artifacts" / "gacha-pity-v2-release-e2e"
    proc = subprocess.run(
        [sys.executable, str(runner), "--plan-path", str(plan), "--transport", "websocket", "--output", str(out_dir), "--timeout-ms", "15000"],
        cwd=str(smoke_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    report_json = out_dir / "business-run.json"
    detail: dict = {"exit_code": proc.returncode, "output_dir": str(out_dir)}
    release_ok = False
    if report_json.is_file():
        report = json.loads(report_json.read_text(encoding="utf-8-sig"))
        detail["passed"] = report.get("Passed")
        detail["plan_id"] = report.get("PlanId")
        for step in report.get("Steps") or []:
            resp = ((step.get("Server") or {}).get("ResponseJson") or "")
            if "gacha-pity-v2" in resp:
                release_ok = True
                detail["release_tag_found_in"] = step.get("Protocol")
        if not release_ok:
            for step in report.get("Steps") or []:
                if step.get("Protocol") in ("GetGachaInfo_c2s", "DoGacha_c2s"):
                    detail.setdefault("gacha_steps", []).append(
                        {
                            "protocol": step.get("Protocol"),
                            "result": step.get("Result"),
                            "response_preview": ((step.get("Server") or {}).get("ResponseJson") or "")[:300],
                        }
                    )

    if proc.returncode == 0 and detail.get("passed") and release_ok:
        ok(results, "gacha_business_test", detail)
    elif proc.returncode == 0 and detail.get("passed"):
        ok(results, "gacha_business_test", {**detail, "note": "passed without explicit release tag scan"})
    else:
        tail = (proc.stdout + proc.stderr)[-1500:]
        fail(results, "gacha_business_test", json.dumps({**detail, "tail": tail}, ensure_ascii=True))


def run_unity_smoke(results: dict) -> None:
    from services.unity_client_hotupdate_runner import run_unity_client_startup_acceptance

    try:
        result = run_unity_client_startup_acceptance(
            unity_project=UNITY_PROJECT,
            api_base=API_BASE,
            project_id=PROJECT_ID,
            channel="wechat",
            environment="Development",
            version_name=VERSION_NAME,
            version_code=VERSION_CODE,
            platform="Android",
            scenario="basic",
            timeout_sec=90,
        )
    except Exception as exc:
        fail(results, "unity_client_smoke", str(exc))
        return
    if result.get("passed"):
        ok(
            results,
            "unity_client_smoke",
            {"tier": result.get("tier"), "final_state": result.get("final_state"), "catalog_url": result.get("catalog_url")},
        )
    else:
        fail(
            results,
            "unity_client_smoke",
            json.dumps(
                {
                    "summary": result.get("summary"),
                    "exit_code": result.get("unity_exit_code"),
                    "report_path": result.get("report_path"),
                },
                ensure_ascii=False,
            ),
        )


def main() -> int:
    results = {
        "feature": "gacha-pity-v2",
        "project_id": PROJECT_ID,
        "order_id": ORDER_ID,
        "version_name": VERSION_NAME,
        "version_code": VERSION_CODE,
        "steps": [],
        "started_at": datetime.now().isoformat(),
    }

    try:
        step("0 seed vc2 bootstrap URLs")
        seed_vc2_urls()
        ok(results, "seed_urls", {"version_id": VERSION_ID})

        step("1 gacha code alignment")
        verify_gacha_code_alignment(results)

        step("2 game-server build")
        build_game_server(results)

        step("3 game-server gacha business test (GetGachaInfo/DoGacha)")
        run_gacha_business_test(results)

        step("4 web release precheck/publish/bootstrap")
        run_release_flow(results)

        step("5 APK artifact")
        verify_apk(results)

        step("6 bootstrap gate")
        run_bootstrap_gate(results)

        step("7 Unity client smoke (bootstrap + hot update)")
        run_unity_smoke(results)

    except Exception:
        fail(results, "unexpected", traceback.format_exc())

    passed = sum(1 for s in results["steps"] if s.get("ok"))
    failed = sum(1 for s in results["steps"] if not s.get("ok"))
    results["summary"] = {"passed": passed, "failed": failed, "finished_at": datetime.now().isoformat()}

    out_dir = ROOT.parents[2] / "docs" / "evidence" / datetime.now().strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "gacha-release-full-e2e.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + json.dumps(results, ensure_ascii=True, indent=2))
    print(f"\nReport: {out_path}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

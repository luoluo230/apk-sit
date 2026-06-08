#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全链路生态联调：game-server cluster.json ↔ Agent 管控中心 ↔ 拓扑编排。

对齐参数：
  - project_id: GomeKu（与 game-server ServerAgent runtime-configs 一致）
  - node_id: cluster.json ServerId（如 gateway-cn-1）
  - agent token: ops-write-key-2026（nodes 配置 ops_write_key）
  - ops_base_url: http://127.0.0.1:5504（cluster.json ops-cn-1）

Usage:
  python3 tools/ops_ecosystem_chain.py
  python3 tools/ops_ecosystem_chain.py --game-server-repo /path/to/game-server
  OPS_USERNAME=admin OPS_PASSWORD=123456 python3 tools/ops_ecosystem_chain.py
  python3 tools/ecosystem_supervisor.py --daemon   # 另开终端先启动 Agent 拉取循环
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GAME_SERVER = "/Users/wangling/Desktop/MyGame/GameClient/game-server"
AGENT_TOKEN = "ops-write-key-2026"


def _resolve_game_server_repo(explicit: str) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.getenv("GAME_SERVER_REPO", "").strip()
    if env and Path(env).is_dir():
        return Path(env).resolve()
    for cand in (DEFAULT_GAME_SERVER, r"E:\maclient\game-server"):
        p = Path(cand)
        if p.is_dir():
            return p.resolve()
    return Path(DEFAULT_GAME_SERVER)


def _load_cluster(repo: Path) -> List[Dict[str, Any]]:
    path = repo / "config" / "cluster.json"
    if not path.is_file():
        raise FileNotFoundError(f"cluster.json not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    servers = data.get("Servers") if isinstance(data, dict) else []
    return [s for s in servers if isinstance(s, dict)]


def _cluster_agents(servers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for srv in servers:
        sid = str(srv.get("ServerId") or "").strip()
        if not sid:
            continue
        host = str(srv.get("ProbeHost") or srv.get("Host") or "127.0.0.1").strip()
        if host in ("0.0.0.0", "*"):
            host = "127.0.0.1"
        port = int(srv.get("Port") or 0)
        role = str(srv.get("Role") or srv.get("Type") or "business").strip().lower()
        rows.append({
            "node_id": sid,
            "agent_id": f"agent-{sid}",
            "role": role,
            "host_name": host,
            "port": port,
            "remote_game_server_port": port,
            "desc": str(srv.get("Description") or srv.get("DisplayName") or sid),
        })
    return rows


def _is_embedded_cluster_node(node_id: str, servers: List[Dict[str, Any]]) -> bool:
    nid = str(node_id or "").strip().lower()
    for srv in servers:
        if str(srv.get("ServerId") or "").strip().lower() == nid:
            if str(srv.get("Type") or "").strip().lower() in ("auth", "game"):
                return True
    return nid.startswith("auth-") or nid.startswith("game-")


def _essential_ports_ready(agents: List[Dict[str, Any]], servers: List[Dict[str, Any]]) -> bool:
    """Gateway/Ops/TCP 需端口可达；Auth/Game 为进程内模块，不要求独立端口。"""
    for ag in agents:
        if _is_embedded_cluster_node(ag.get("node_id") or "", servers):
            continue
        if not _tcp_ok(ag["host_name"], ag["port"]):
            return False
    return True


def _tcp_ok(host: str, port: int, timeout: float = 2.0) -> bool:
    if port <= 0:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _ts() -> str:
    return datetime.utcnow().strftime("%H:%M:%S")


def _post(base: str, path: str, payload: Dict[str, Any], cookie: str = "", token: str = "") -> Dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    if token:
        headers["X-Agent-Token"] = token
    r = requests.post(
        base.rstrip("/") + path,
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        timeout=20,
    )
    body = r.json() if r.content else {}
    body["_status"] = r.status_code
    return body


def _get(base: str, path: str, cookie: str = "") -> Dict[str, Any]:
    headers = {"Cookie": cookie} if cookie else {}
    r = requests.get(base.rstrip("/") + path, headers=headers, timeout=15)
    body = r.json() if r.content else {}
    body["_status"] = r.status_code
    return body


def login(base: str, username: str = "", password: str = "") -> Tuple[bool, str]:
    username = (username or os.getenv("OPS_USERNAME") or "admin").strip()
    password = (password or os.getenv("OPS_PASSWORD") or "admin123").strip()
    s = requests.Session()
    r = s.get(f"{base}/login", timeout=10)
    if "登录次数过多" in (r.text or ""):
        return False, ""
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text or "")
    csrf = m.group(1) if m else ""
    r2 = s.post(
        f"{base}/login",
        data={"username": username, "password": password, "csrf_token": csrf},
        timeout=10,
        allow_redirects=False,
    )
    if r2.status_code in (301, 302, 303, 307, 308) and s.cookies:
        return True, "; ".join(f"{k}={v}" for k, v in s.cookies.items())
    if s.cookies:
        return True, "; ".join(f"{k}={v}" for k, v in s.cookies.items())
    return False, ""


def step_cluster_sync(base: str, cookie: str, project_id: str, repo: Path) -> Tuple[bool, List[str]]:
    logs: List[str] = []
    resp = _post(base, "/api/ops-platform/cluster/sync", {"project_id": project_id}, cookie)
    ok = bool(resp.get("ok"))
    logs.append(f"[{_ts()}] cluster/sync repo={resp.get('game_server_repo') or repo} ok={ok}")
    sync = resp.get("sync") if isinstance(resp.get("sync"), dict) else {}
    if sync:
        logs.append(f"[{_ts()}]   synced={sync.get('synced')} added={sync.get('added')} updated={sync.get('updated')} stale={sync.get('stale')}")
    if not ok:
        logs.append(f"[{_ts()}]   error={resp.get('message') or resp.get('error')}")
    return ok, logs


def step_agent_protocol_register(base: str, agents: List[Dict[str, Any]], project_id: str) -> Tuple[bool, List[str]]:
    """注册单个本地 Agent，并通过 services 挂载多个服务节点。"""
    logs: List[str] = []
    canonical_id = "agent-local-cn-1"
    device_id = "local-game-server"
    services = []
    for ag in agents or []:
        node_id = str(ag.get("node_id") or "").strip()
        if not node_id:
            continue
        port = int(ag.get("port") or ag.get("remote_game_server_port") or 0)
        services.append({
            "service_id": node_id,
            "node_id": node_id,
            "agent_id": canonical_id,
            "device_id": device_id,
            "project_id": project_id,
            "display_name": str(ag.get("desc") or ag.get("agent_id") or node_id),
            "service_type": str(ag.get("role") or ""),
            "service_port": port,
            "remote_game_server_port": port,
            "status": "ONLINE",
            "run_state": "RUNNING",
            "probe_status": "",
            "metrics": {},
            "updated_at": "",
        })
    if not services:
        return False, ["[register] no services"]
    ops_port = 5504
    for svc in services:
        if svc["node_id"] == "ops-cn-1":
            ops_port = int(svc.get("service_port") or 5504)
            break
    host = str((agents[0] or {}).get("host_name") or "127.0.0.1")
    auth_node = "ops-cn-1"
    register_payload = {
        "node_id": auth_node,
        "agent_id": canonical_id,
        "project_id": project_id,
        "device_id": device_id,
        "host_name": host,
        "host_ip": host,
        "display_name": "本地 GameServer Agent",
        "port": ops_port,
        "remote_game_server_port": ops_port,
        "desc": "单 Agent 管理本机全部拓扑服务节点",
        "version": "ecosystem-v1",
        "run_state": "RUNNING",
        "status": "ONLINE",
        "capabilities": ["health_check", "start", "stop", "restart", "smoke_test", "stress_test"],
        "network": {"endpoints": [f"{host}:{ops_port}"]},
        "token": AGENT_TOKEN,
    }
    resp = _post(base, "/api/ops-platform/agent/register", register_payload, token=AGENT_TOKEN)
    ok = bool(resp.get("ok"))
    logs.append(f"[{_ts()}] agent/register {canonical_id}: {'OK' if ok else resp.get('error')}")
    if not ok:
        return False, logs
    try:
        import psutil
        metrics = {
            "control": {
                "cpu_percent": round(psutil.cpu_percent(interval=0.1), 1),
                "mem_percent": round(psutil.virtual_memory().percent, 1),
                "qps": 0,
                "rtt_ms": 0.0,
                "source": "runtime.sample",
            }
        }
    except Exception:
        metrics = {"control": {"cpu_percent": 8, "mem_percent": 22, "qps": 0, "rtt_ms": 1.0, "source": "runtime.sample"}}
    hb = _post(base, "/api/ops-platform/agent/heartbeat", {
        "node_id": auth_node,
        "agent_id": canonical_id,
        "project_id": project_id,
        "device_id": device_id,
        "status": "ONLINE",
        "run_state": "RUNNING",
        "port": ops_port,
        "remote_game_server_port": ops_port,
        "metrics": metrics,
        "token": AGENT_TOKEN,
    }, token=AGENT_TOKEN)
    logs.append(f"[{_ts()}] agent/heartbeat {canonical_id}: {'OK' if hb.get('ok') else hb.get('error')}")
    return bool(hb.get("ok")), logs


def step_probe_all(base: str, cookie: str, project_id: str) -> Tuple[bool, List[str]]:
    logs: List[str] = []
    resp = _post(base, "/api/ops-platform/agents/probe-all", {"project_id": project_id}, cookie)
    ok = bool(resp.get("ok"))
    pass_count = int(resp.get("pass_count") or 0)
    fail_count = int(resp.get("fail_count") or 0)
    logs.append(f"[{_ts()}] probe-all pass={pass_count} fail={fail_count}")
    for row in resp.get("results") or []:
        if not isinstance(row, dict):
            continue
        logs.append(f"[{_ts()}]   {row.get('agent_id')}: {'PASS' if row.get('ok') else 'FAIL'} {row.get('message') or ''}")
    return ok and fail_count == 0, logs


def step_auto_bind(base: str, cookie: str, scope: Dict[str, str]) -> Tuple[bool, List[str]]:
    logs: List[str] = []
    resp = _post(base, "/api/ops-platform/topology/auto-bind-agents", scope, cookie)
    ok = bool(resp.get("ok"))
    logs.append(f"[{_ts()}] auto-bind bound={resp.get('bound_count')} skipped={resp.get('skipped_count')} failed={resp.get('failed_count')}")
    for row in resp.get("detail") or []:
        if isinstance(row, dict):
            logs.append(f"[{_ts()}]   {row.get('node_id')}: {row.get('status')} {row.get('reason') or ''}")
    return ok and int(resp.get("failed_count") or 0) == 0 and int(resp.get("bound_count") or 0) > 0, logs


def step_flow_control(base: str, cookie: str, scope: Dict[str, str], op: str) -> Tuple[bool, str, List[str]]:
    logs: List[str] = []
    resp = _post(base, "/api/ops-platform/runtime/flow-control", dict(scope, op=op), cookie)
    if not resp.get("ok") and str(resp.get("error") or "") == "topology_run_active" and op == "start":
        old_run = str(resp.get("run_id") or "")
        logs.append(f"[{_ts()}] flow-control start blocked by active run {old_run}, issuing stop first")
        _post(base, "/api/ops-platform/runtime/flow-control", dict(scope, op="stop"), cookie)
        resp = _post(base, "/api/ops-platform/runtime/flow-control", dict(scope, op=op), cookie)
    ok = bool(resp.get("ok"))
    run_id = str(resp.get("run_id") or "")
    logs.append(f"[{_ts()}] flow-control {op}: {'OK' if ok else resp.get('message') or resp.get('error')} run_id={run_id}")
    return ok, run_id, logs


def step_flow_status(base: str, cookie: str, run_id: str, timeout_sec: int = 60) -> Tuple[bool, List[str]]:
    logs: List[str] = []
    if not run_id:
        return False, ["[missing run_id]"]
    deadline = time.time() + timeout_sec
    last = {}
    while time.time() < deadline:
        resp = _get(base, f"/api/ops-platform/runtime/flow-status?run_id={run_id}", cookie)
        last = resp
        status = str(resp.get("status") or "").lower()
        done = int(resp.get("done") or 0)
        total = int(resp.get("total") or 0)
        failed = int(resp.get("failed") or 0)
        logs.append(f"[{_ts()}] flow-status status={status} done={done}/{total} failed={failed}")
        if status in ("success", "failed", "canceled", "timeout"):
            return status == "success" and failed == 0, logs
        time.sleep(2)
    logs.append(f"[{_ts()}] flow-status timeout last={json.dumps(last, ensure_ascii=False)[:200]}")
    return False, logs


def step_contract_registry() -> Tuple[bool, List[str]]:
    logs: List[str] = []
    path = ROOT / "docs" / "ops_alignment" / "node_contract_registry.json"
    if not path.is_file():
        logs.append(f"[{_ts()}] contract registry missing: {path}")
        return False, logs
    data = json.loads(path.read_text(encoding="utf-8"))
    contracts = data.get("contracts") if isinstance(data.get("contracts"), list) else []
    preset_ids = {str(c.get("preset_id") or "") for c in contracts if isinstance(c, dict)}
    ok = len(contracts) == 10 and "mysql_db" not in preset_ids
    logs.append(f"[{_ts()}] node contract registry: count={len(contracts)} mysql_removed={'mysql_db' not in preset_ids}")
    daemon_types = sum(1 for c in contracts if isinstance(c, dict) and str(c.get("cluster_type") or "") == "Daemon")
    logs.append(f"[{_ts()}]   daemon contracts={daemon_types}")
    return ok, logs


def step_blueprints_no_mysql(base: str, cookie: str) -> Tuple[bool, List[str]]:
    logs: List[str] = []
    resp = _get(base, "/api/ops-platform/topology-blueprints", cookie)
    rows = resp.get("blueprints") if isinstance(resp.get("blueprints"), list) else []
    bad_mysql = []
    bad_framework = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        bid = str(row.get("blueprint_id") or "")
        nodes = row.get("nodes") if isinstance(row.get("nodes"), list) else []
        presets = {str(n.get("preset_id") or "") for n in nodes if isinstance(n, dict)}
        for n in nodes:
            if isinstance(n, dict) and str(n.get("preset_id") or "") == "mysql_db":
                bad_mysql.append(bid)
        if bid in ("minimal_framework", "medium_framework", "full_framework"):
            if "auth_service" not in presets or "ops_service" not in presets:
                bad_framework.append(bid)
            if "pressure_worker" in presets:
                bad_framework.append(f"{bid}:pressure")
        if bid == "pressure_test_framework":
            if "pressure_worker" not in presets:
                bad_framework.append(bid)
            if "auth_service" in presets or "ops_service" in presets or "mongo_db" in presets:
                bad_framework.append(f"{bid}:production_mix")
    ok = bool(resp.get("ok")) and not bad_mysql and not bad_framework
    logs.append(f"[{_ts()}] topology blueprints: count={len(rows)} mysql_refs={bad_mysql or 'none'} framework={bad_framework or 'ok'}")
    return ok, logs


def step_full_framework_export(base: str, cookie: str, scope: Dict[str, str], repo: Path) -> Tuple[bool, List[str]]:
    """Apply full_framework blueprint, save topology, verify cluster.json Daemon entries."""
    logs: List[str] = []
    apply_resp = _post(base, "/api/ops-platform/topology/apply-blueprint", dict(scope, blueprint_id="full_framework", replace_existing=True), cookie)
    if not apply_resp.get("ok"):
        logs.append(f"[{_ts()}] apply full_framework FAIL: {apply_resp.get('error') or apply_resp.get('message')}")
        return False, logs
    created = int(apply_resp.get("created_count") or 0)
    logs.append(f"[{_ts()}] apply full_framework created={created}")

    topo = apply_resp.get("topology") if isinstance(apply_resp.get("topology"), dict) else {}
    save_resp = _post(base, "/api/ops-platform/topology/save", dict(scope, topology=topo), cookie)
    if not save_resp.get("ok"):
        logs.append(f"[{_ts()}] topology save after blueprint FAIL: {save_resp.get('message') or save_resp.get('error')}")
        if isinstance(save_resp.get("errors"), list):
            for err in save_resp.get("errors") or []:
                logs.append(f"[{_ts()}]   {err}")
        return False, logs
    sync = save_resp.get("sync") if isinstance(save_resp.get("sync"), dict) else {}
    logs.append(f"[{_ts()}] topology save sync ok={sync.get('ok')} status={sync.get('status')}")

    try:
        servers = _load_cluster(repo)
    except Exception as ex:
        logs.append(f"[{_ts()}] cluster.json read FAIL: {ex}")
        return False, logs
    daemon_rows = [s for s in servers if str(s.get("Type") or "").strip().lower() == "daemon"]
    app_types = {str(s.get("Type") or "").strip() for s in servers}
    infra_roles = {"cache", "database", "mq", "scheduler", "pressure"}
    infra_count = sum(1 for s in daemon_rows if str(s.get("Role") or "").strip().lower() in infra_roles)
    logs.append(f"[{_ts()}] cluster.json servers={len(servers)} daemon={len(daemon_rows)} infra_roles={infra_count} app_types={sorted(app_types)}")
    for srv in daemon_rows[:8]:
        sid = str(srv.get("ServerId") or "")
        port = int(srv.get("Port") or 0)
        meta = srv.get("Metadata") if isinstance(srv.get("Metadata"), dict) else {}
        start_cmd = str(meta.get("StartCommand") or "")
        logs.append(f"[{_ts()}]   {sid} port={port} start={'yes' if start_cmd else 'no'}")
    ok = (
        len(daemon_rows) >= 4
        and infra_count >= 4
        and "Auth" in app_types
        and "Ops" in app_types
        and "Gateway" in app_types
        and "Game" in app_types
    )
    return ok, logs


def resolve_topology_scope(base: str, cookie: str, project_id: str) -> Dict[str, str]:
    resp = _get(base, f"/api/ops-platform/topologies?project_id={project_id}", cookie)
    topologies = resp.get("topologies") if isinstance(resp.get("topologies"), list) else []
    hit = next((t for t in topologies if isinstance(t, dict) and t.get("is_default")), None)
    if not hit and topologies:
        hit = topologies[0]
    if not hit:
        return {"project_id": project_id, "env_key": "production", "topology_id": ""}
    return {
        "project_id": project_id,
        "env_key": str(hit.get("env_key") or "production"),
        "topology_id": str(hit.get("topology_id") or ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent + 拓扑 + game-server 全链路联调")
    parser.add_argument("--base", default="http://127.0.0.1:5003")
    parser.add_argument("--project", default="GomeKu")
    parser.add_argument("--game-server-repo", default="")
    parser.add_argument("--skip-flow", action="store_true")
    parser.add_argument("--full-framework", action="store_true", help="Apply full_framework blueprint and verify cluster export")
    parser.add_argument("--username", default="", help="apk-site login (default: OPS_USERNAME or admin)")
    parser.add_argument("--password", default="", help="apk-site login (default: OPS_PASSWORD or 123456)")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    project_id = args.project
    repo = _resolve_game_server_repo(args.game_server_repo)
    logs: List[str] = []

    def log(msg: str) -> None:
        print(msg)
        logs.append(msg)

    try:
        servers = _load_cluster(repo)
        agents = _cluster_agents(servers)
    except Exception as ex:
        log(f"❌ 无法读取 cluster.json: {ex}")
        return 1

    log(f"[{_ts()}] ═══ 生态全链路联调 ═══")
    log(f"[{_ts()}] apk-site={base} project={project_id} game-server={repo}")
    log(f"[{_ts()}] cluster nodes: {', '.join(a['node_id'] for a in agents)}")

    # Preflight ports
    log(f"\n[{_ts()}] ── Preflight: game-server 端口 ──")
    for ag in agents:
        alive = _tcp_ok(ag["host_name"], ag["port"])
        embedded = _is_embedded_cluster_node(ag.get("node_id") or "", servers)
        if embedded and not alive:
            log(f"[{_ts()}]   {ag['node_id']}:{ag['port']} EMBEDDED (cluster-managed)")
        else:
            log(f"[{_ts()}]   {ag['node_id']}:{ag['port']} {'LISTENING' if alive else 'CLOSED'}")
    port_ok = _essential_ports_ready(agents, servers)
    if not port_ok:
        log(f"[{_ts()}] ⚠ 关键 game-server 端口未就绪。请先执行:")
        log(f"    cd {repo} && bash scripts/Start-GameServer.sh")
        log(f"    python3 tools/ecosystem_supervisor.py --daemon")

    ok_login, cookie = login(base, args.username, args.password)
    log(f"\n[{_ts()}] login: {'OK' if ok_login else 'FAIL'}")
    if not ok_login:
        log(f"[{_ts()}] 登录失败或账号被锁定。可设置 OPS_USERNAME/OPS_PASSWORD 或 --username/--password")
        return 1

    steps: Dict[str, bool] = {}

    log(f"\n[{_ts()}] ── Node Contract Registry ──")
    contract_ok, l = step_contract_registry()
    for x in l:
        log(x)
    steps["contract_registry"] = contract_ok

    log(f"\n[{_ts()}] ── Blueprints (no MySQL) ──")
    bp_ok, l = step_blueprints_no_mysql(base, cookie)
    for x in l:
        log(x)
    steps["blueprints_no_mysql"] = bp_ok

    log(f"\n[{_ts()}] ── cluster.json → apk-site 同步 ──")
    sync_ok, l = step_cluster_sync(base, cookie, project_id, repo)
    for x in l:
        log(x)
    steps["cluster_sync"] = sync_ok
    reg_ok, l = step_agent_protocol_register(base, agents, project_id)
    for x in l:
        log(x)
    steps["agent_register"] = reg_ok

    log(f"\n[{_ts()}] ── 探测 ──")
    probe_ok, l = step_probe_all(base, cookie, project_id)
    for x in l:
        log(x)
    steps["probe"] = probe_ok

    scope = resolve_topology_scope(base, cookie, project_id)
    if not scope.get("topology_id"):
        log(f"[{_ts()}] ❌ 未找到项目 {project_id} 的拓扑注册")
        return 1
    log(f"[{_ts()}] topology scope: {scope}")

    log(f"\n[{_ts()}] ── 拓扑自动绑定 ──")
    bind_ok, l = step_auto_bind(base, cookie, scope)
    for x in l:
        log(x)
    steps["auto_bind"] = bind_ok

    if args.full_framework:
        log(f"\n[{_ts()}] ── full_framework 蓝图导出验证 ──")
        ff_ok, l = step_full_framework_export(base, cookie, scope, repo)
        for x in l:
            log(x)
        steps["full_framework_export"] = ff_ok

    if not args.skip_flow and bind_ok and probe_ok:
        log(f"\n[{_ts()}] ── 运行模式 flow-control start ──")
        fc_ok, run_id, l = step_flow_control(base, cookie, scope, "start")
        for x in l:
            log(x)
        fs_ok, l2 = step_flow_status(base, cookie, run_id)
        for x in l2:
            log(x)
        steps["flow_start"] = fc_ok and fs_ok
    else:
        steps["flow_start"] = False
        if args.skip_flow:
            log(f"[{_ts()}] skip flow-control (--skip-flow)")
        else:
            log(f"[{_ts()}] skip flow-control (probe/bind preflight failed)")

    log(f"\n[{_ts()}] ═══ 结果 ═══")
    for name, ok in steps.items():
        log(f"  {'✅' if ok else '❌'} {name}")

    fails = [k for k, v in steps.items() if not v]
    report_dir = ROOT / "data" / "logs"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"ecosystem-chain-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.log"
    report_path.write_text("\n".join(logs), encoding="utf-8")
    log(f"\n报告: {report_path}")

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

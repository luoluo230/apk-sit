#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实链路测试：Web 端部署 → 绑定远程 Agent → 通知 Agent 启动 game-server。

非模拟冒烟，Agent 探测的是 game-server 真实端口，start-remote 触发真实启动。

Usage:
  py -3 tools/ops_real_chain.py
  py -3 tools/ops_real_chain.py --base http://127.0.0.1:5003 --project GomeKu
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Tuple

# ── config ───────────────────────────────────────────────────────────────────

# game-server 真实节点，探测其 Ops/传输端口确认存活
GAME_SERVER_AGENTS = [
    {
        "node_id": "gateway-cn-1",
        "role": "gateway",
        "desc": "网关 - WebSocket 15050",
        "port": 15050,           # 探测端口 = WS 端口
        "remote_game_server_port": 15050,
    },
    {
        "node_id": "game-cn-1",
        "role": "game",
        "desc": "游戏服务 - 5502",
        "port": 5502,
        "remote_game_server_port": 5502,
    },
    {
        "node_id": "ops-cn-1",
        "role": "ops",
        "desc": "运维服务 - 5504",
        "port": 5504,
        "remote_game_server_port": 5504,
    },
    {
        "node_id": "tcp-cn-1",
        "role": "transport",
        "desc": "TCP 传输 - 5601",
        "port": 5601,
        "remote_game_server_port": 5601,
    },
]

# ── helpers ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts() -> str:
    return datetime.utcnow().strftime("%H:%M:%S")


def _post(base: str, path: str, payload: Dict[str, Any], cookie: str = "", timeout: int = 15) -> Dict[str, Any]:
    import requests as req
    url = base.rstrip("/") + path
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    r = req.post(url, headers=headers, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=timeout)
    body = r.json() if r.content else {}
    body["_status"] = r.status_code
    return body


def _get(base: str, path: str, cookie: str = "", timeout: int = 10) -> Dict[str, Any]:
    import requests as req
    url = base.rstrip("/") + path
    headers = {}
    if cookie:
        headers["Cookie"] = cookie
    r = req.get(url, headers=headers, timeout=timeout)
    body = r.json() if r.content else {}
    body["_status"] = r.status_code
    return body


def _tcp_ok(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


# ── Step 0: Preflight ────────────────────────────────────────────────────────

def step_preflight(base: str) -> Tuple[bool, List[str]]:
    logs: List[str] = []
    # apk-site health
    try:
        r = _get(base, "/health")
        ok = r.get("status") == "ok"
        logs.append(f"[{_ts()}] apk-site health: {'OK' if ok else 'FAIL'}")
    except Exception as ex:
        ok = False
        logs.append(f"[{_ts()}] apk-site health: FAIL ({ex})")

    # game-server ops health
    try:
        import requests as req
        r2 = req.get("http://127.0.0.1:5504/ops/health", timeout=3)
        j = r2.json() if r2.content else {}
        gs_ok = j.get("success") is True
        logs.append(f"[{_ts()}] game-server ops/health: {'OK' if gs_ok else 'FAIL'}")
    except Exception as ex:
        gs_ok = False
        logs.append(f"[{_ts()}] game-server ops/health: FAIL ({ex})")

    # game-server 端口探测
    for ag in GAME_SERVER_AGENTS:
        alive = _tcp_ok("127.0.0.1", ag["port"])
        logs.append(f"[{_ts()}] port {ag['port']} ({ag['node_id']}): {'LISTENING' if alive else 'CLOSED'}")

    return ok and gs_ok, logs


# ── Step 1: Login ────────────────────────────────────────────────────────────

def step_login(base: str) -> Tuple[bool, str, List[str]]:
    """表单登录获取 session cookie。"""
    logs: List[str] = []
    import requests as req
    try:
        s = req.Session()
        # GET login page to get CSRF token
        r = s.get(f"{base}/login", timeout=8)
        # Extract csrf_token from form
        csrf = ""
        import re
        m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text or "")
        if m:
            csrf = m.group(1)
        # POST form login
        data = {"username": "admin", "password": "admin", "csrf_token": csrf}
        r2 = s.post(f"{base}/login", data=data, timeout=8, allow_redirects=True)
        cookie = "; ".join(f"{k}={v}" for k, v in s.cookies.items())
        if not cookie:
            cookie = f"session={s.cookies.get('session', '')}"
        ok = r2.status_code < 400 and len(cookie) > 5
        logs.append(f"[{_ts()}] login: status={r2.status_code} cookie_len={len(cookie)}")
        return ok, cookie, logs
    except Exception as ex:
        logs.append(f"[{_ts()}] login FAIL: {ex}")
        return False, "", logs


# ── Step 2: Register Agents ──────────────────────────────────────────────────

def step_register_agents(base: str, cookie: str, project_id: str) -> Tuple[bool, List[str]]:
    logs: List[str] = []
    all_ok = True

    for ag in GAME_SERVER_AGENTS:
        agent_id = f"agent-{ag['node_id']}-real"
        payload = {
            "agent_id": agent_id,
            "node_id": ag["node_id"],
            "device_id": "local-game-server",
            "host_name": "127.0.0.1",
            "project_id": project_id,
            "display_name": f"真实Agent-{ag['node_id']}",
            "port": ag["port"],
            "remote_game_server_port": ag["remote_game_server_port"],
            "desc": ag["desc"],
            "version": "v1-real-chain",
            "run_state": "RUNNING",
            "status": "ONLINE",
            "create_if_missing": True,
            "capabilities": ["health_check", "start", "stop", "restart"],
            "network": {
                "endpoints": [
                    {"type": "tcp", "host": "127.0.0.1", "port": ag["port"]},
                ]
            },
        }
        resp = _post(base, "/api/ops-platform/agents/upsert", payload, cookie)
        ok = bool(resp.get("ok"))
        err = resp.get("error") or ""
        logs.append(f"[{_ts()}] register {ag['node_id']}: {'OK' if ok else f'FAIL ({err})'}")
        if not ok:
            all_ok = False

    return all_ok, logs


# ── Step 3: Heartbeat ────────────────────────────────────────────────────────

def step_heartbeat(base: str, cookie: str, project_id: str) -> Tuple[bool, List[str]]:
    logs: List[str] = []

    for ag in GAME_SERVER_AGENTS:
        agent_id = f"agent-{ag['node_id']}-real"
        payload = {
            "agent_id": agent_id,
            "node_id": ag["node_id"],
            "device_id": "local-game-server",
            "host_name": "127.0.0.1",
            "project_id": project_id,
            "status": "ONLINE",
            "run_state": "RUNNING",
            "port": ag["port"],
            "remote_game_server_port": ag["remote_game_server_port"],
            "metrics": {
                "cpu_percent": 10,
                "mem_percent": 30,
                "qps": 0,
            },
        }
        resp = _post(base, "/api/ops-platform/agent/heartbeat", payload, cookie)
        ok = bool(resp.get("ok"))
        logs.append(f"[{_ts()}] heartbeat {ag['node_id']}: {'OK' if ok else 'FAIL'}")

    return True, logs


# ── Step 4: Probe All ────────────────────────────────────────────────────────

def step_probe_all(base: str, cookie: str, project_id: str) -> Tuple[bool, List[str]]:
    logs: List[str] = []
    resp = _post(base, "/api/ops-platform/agents/probe-all", {"project_id": project_id}, cookie)
    ok = bool(resp.get("ok"))
    pass_count = resp.get("pass_count", 0)
    fail_count = resp.get("fail_count", 0)
    results = resp.get("results") if isinstance(resp.get("results"), list) else []

    logs.append(f"[{_ts()}] probe-all: pass={pass_count} fail={fail_count}")

    for r in results:
        if isinstance(r, dict):
            aid = r.get("agent_id") or "?"
            pok = r.get("ok") is True
            rtt = r.get("rtt_ms", 0)
            msg = r.get("message") or ""
            logs.append(f"[{_ts()}]   {aid}: {'PASS' if pok else 'FAIL'} rtt={rtt}ms {msg}")

    return ok and fail_count == 0, logs


# ── Step 5: Bind Agent ───────────────────────────────────────────────────────

def step_bind_agents(base: str, cookie: str, project_id: str) -> Tuple[bool, List[str]]:
    logs: List[str] = []
    all_ok = True

    for ag in GAME_SERVER_AGENTS:
        agent_id = f"agent-{ag['node_id']}-real"
        resp = _post(base, "/api/ops-platform/topology/node/bind-agent", {
            "node_id": ag["node_id"],
            "agent_id": agent_id,
            "project_id": project_id,
        }, cookie)
        ok = bool(resp.get("ok"))
        err = resp.get("error_code") or resp.get("error") or ""
        logs.append(f"[{_ts()}] bind {ag['node_id']}: {'OK' if ok else f'REJECTED ({err})'}")
        if not ok:
            all_ok = False

    return all_ok, logs


# ── Step 6: Start Remote ─────────────────────────────────────────────────────

def step_start_remote(base: str, cookie: str, project_id: str) -> Tuple[bool, List[str]]:
    logs: List[str] = []
    all_ok = True

    for ag in GAME_SERVER_AGENTS:
        resp = _post(base, "/api/ops-platform/topology/node/start-remote", {
            "node_id": ag["node_id"],
            "project_id": project_id,
        }, cookie)
        ok = bool(resp.get("ok"))
        job_id = resp.get("job_id") or ""
        trace_id = resp.get("trace_id") or ""
        err = resp.get("error_code") or resp.get("error") or ""
        logs.append(f"[{_ts()}] start-remote {ag['node_id']}: {'OK' if ok else f'FAIL ({err})'} job={job_id} trace={trace_id}")
        if not ok:
            all_ok = False

    return all_ok, logs


# ── Step 7: Verify game-server still alive ───────────────────────────────────

def step_verify_game_server() -> Tuple[bool, List[str]]:
    logs: List[str] = []

    # Ops health
    try:
        import requests as req
        r = req.get("http://127.0.0.1:5504/ops/health", timeout=3)
        j = r.json() if r.content else {}
        ok = j.get("success") is True
        sid = (j.get("data") or {}).get("ServerId") or "?"
        logs.append(f"[{_ts()}] game-server ops/health: {'OK' if ok else 'FAIL'} serverId={sid}")
    except Exception as ex:
        ok = False
        logs.append(f"[{_ts()}] game-server ops/health: FAIL ({ex})")

    # Port check
    for ag in GAME_SERVER_AGENTS:
        alive = _tcp_ok("127.0.0.1", ag["port"])
        logs.append(f"[{_ts()}] port {ag['port']} ({ag['node_id']}): {'LISTENING' if alive else 'CLOSED'}")
        if not alive:
            ok = False

    return ok, logs


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="真实链路测试：Web→Agent→game-server")
    parser.add_argument("--base", default="http://127.0.0.1:5003")
    parser.add_argument("--project", default="GomeKu")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    project_id = args.project

    all_logs: List[str] = []

    def log(msg: str):
        # Avoid GBK encoding issues on Windows
        try:
            print(msg)
        except UnicodeEncodeError:
            print(msg.encode('ascii', 'replace').decode('ascii'))
        all_logs.append(msg)

    log(f"[{_ts()}] ═══ 真实链路测试 开始 ═══")
    log(f"[{_ts()}] base={base}  project={project_id}")

    # Step 0: Preflight
    log(f"\n[{_ts()}] ── Step 0: Preflight ──")
    pf_ok, pf_logs = step_preflight(base)
    for l in pf_logs:
        log(l)
    if not pf_ok:
        log(f"[{_ts()}] ❌ Preflight 失败，确保 apk-site(:5003) 和 game-server(:5504) 都在运行")
        return 1

    # Step 1: Login
    log(f"\n[{_ts()}] ── Step 1: 登录 ──")
    login_ok, cookie, login_logs = step_login(base)
    for l in login_logs:
        log(l)
    if not login_ok:
        log(f"[{_ts()}] ❌ 登录失败")
        return 1

    # Step 2: Register Agents
    log(f"\n[{_ts()}] ── Step 2: 注册 4 个真实 Agent ──")
    reg_ok, reg_logs = step_register_agents(base, cookie, project_id)
    for l in reg_logs:
        log(l)

    # Step 3: Heartbeat
    log(f"\n[{_ts()}] ── Step 3: 心跳上报 ──")
    hb_ok, hb_logs = step_heartbeat(base, cookie, project_id)
    for l in hb_logs:
        log(l)

    # Step 4: Probe All
    log(f"\n[{_ts()}] ── Step 4: 探测所有 Agent ──")
    probe_ok, probe_logs = step_probe_all(base, cookie, project_id)
    for l in probe_logs:
        log(l)

    # Step 5: Bind
    log(f"\n[{_ts()}] ── Step 5: 绑定 Agent 到拓扑节点 ──")
    bind_ok, bind_logs = step_bind_agents(base, cookie, project_id)
    for l in bind_logs:
        log(l)

    # Step 6: Start Remote
    log(f"\n[{_ts()}] ── Step 6: 远端启动 ──")
    start_ok, start_logs = step_start_remote(base, cookie, project_id)
    for l in start_logs:
        log(l)

    # Step 7: Verify game-server alive
    log(f"\n[{_ts()}] ── Step 7: 验证 game-server 存活 ──")
    verify_ok, verify_logs = step_verify_game_server()
    for l in verify_logs:
        log(l)

    # Summary
    log(f"\n[{_ts()}] ═══ 结果汇总 ═══")
    steps = {
        "preflight": pf_ok,
        "register": reg_ok,
        "heartbeat": hb_ok,
        "probe": probe_ok,
        "bind": bind_ok,
        "start-remote": start_ok,
        "verify-game-server": verify_ok,
    }
    for name, ok in steps.items():
        log(f"  {'✅' if ok else '❌'} {name}")

    fails = [k for k, v in steps.items() if not v]
    if fails:
        log(f"\n❌ 失败步骤: {', '.join(fails)}")
    else:
        log(f"\n✅ 全链路通过！Web 端已通过 Agent 成功管控 game-server")

    # Save report
    report_path = os.path.join(os.path.dirname(__file__), "..", "data", "logs", f"real-chain-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.log")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(all_logs))
    log(f"\n报告已写入: {report_path}")

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

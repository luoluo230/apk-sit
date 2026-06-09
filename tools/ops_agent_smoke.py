#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键冒烟测试：4 Agent 联调 + Web 全链路业务测试。

完整闭环：
  probe PASS → bind → start-remote → flow-control(start) → flow-status(success) → flow-control(stop)

Usage:
  py -3 tools/ops_agent_smoke.py
  py -3 tools/ops_agent_smoke.py --base http://127.0.0.1:5003 --project GomeKu
  py -3 tools/ops_agent_smoke.py --skip-agents   # 跳过 Agent 启动，仅跑 API 链路
  py -3 tools/ops_agent_smoke.py --strict         # 任何非 ok 都算失败

Requires: requests, psutil (可选，Agent 指标采集)
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# ── helpers ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(stage: str, ok: bool, detail: str, elapsed_ms: float = 0) -> Dict[str, Any]:
    return {
        "ts": _now_iso(),
        "stage": stage,
        "ok": ok,
        "detail": detail,
        "elapsed_ms": round(elapsed_ms, 1),
    }


def _post_json(url: str, payload: Dict[str, Any], session_cookie: str = "", timeout: int = 10) -> Dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if session_cookie:
        headers["Cookie"] = session_cookie
    import requests as req
    try:
        r = req.post(url, headers=headers, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=timeout)
        body = r.json() if r.content else {}
        body["_status"] = r.status_code
        return body
    except Exception as ex:
        return {"ok": False, "error": str(ex), "_status": 0}


def _get_json(url: str, session_cookie: str = "", timeout: int = 10) -> Dict[str, Any]:
    headers = {}
    if session_cookie:
        headers["Cookie"] = session_cookie
    import requests as req
    try:
        r = req.get(url, headers=headers, timeout=timeout)
        body = r.json() if r.content else {}
        body["_status"] = r.status_code
        return body
    except Exception as ex:
        return {"ok": False, "error": str(ex), "_status": 0}


# ── Step 0: 登录 ─────────────────────────────────────────────────────────────

def step_login(base: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """登录获取 session cookie。"""
    import re

    logs: List[Dict[str, Any]] = []
    t0 = time.time()
    import requests as req
    try:
        s = req.Session()
        r = s.get(f"{base}/login", timeout=15)
        m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text or "")
        r = s.post(
            f"{base}/login",
            data={
                "username": "admin",
                "password": "admin123",
                "csrf_token": m.group(1) if m else "",
            },
            timeout=15,
        )
        cookie = "; ".join(f"{k}={v}" for k, v in s.cookies.items())
        ok = r.status_code < 400 and bool(s.cookies)
        logs.append(_log("login", ok, f"status={r.status_code}; cookie_len={len(cookie)}", (time.time() - t0) * 1000))
        return ok, cookie, logs
    except Exception as ex:
        logs.append(_log("login", False, str(ex), (time.time() - t0) * 1000))
        return False, "", logs


# ── Step 1: 注册 4 Agent ────────────────────────────────────────────────────

AGENT_DEFS = [
    {"node_id": "gateway-cn-1",   "port": 19101, "role": "gateway",   "desc": "网关 Agent"},
    {"node_id": "business-cn-1",  "port": 19102, "role": "business",  "desc": "业务 Agent"},
    {"node_id": "mongo-cn-1",     "port": 19103, "role": "database",  "desc": "Mongo Agent"},
    {"node_id": "redis-cn-1",     "port": 19104, "role": "cache",     "desc": "Redis Agent"},
]


def step_register_agents(base: str, cookie: str, project_id: str) -> Tuple[bool, List[Dict[str, Any]]]:
    """注册 4 个 Agent 并跑心跳循环。"""
    logs: List[Dict[str, Any]] = []
    agent_tokens: Dict[str, str] = {}

    for defn in AGENT_DEFS:
        t0 = time.time()
        agent_id = f"agent-{defn['node_id']}-{uuid.uuid4().hex[:6]}"
        token = f"smoke-token-{defn['node_id']}-{uuid.uuid4().hex[:8]}"
        payload = {
            "node_id": defn["node_id"],
            "agent_id": agent_id,
            "project_id": project_id,
            "device_id": "smoke-device-local",
            "host_name": socket.gethostname(),
            "display_name": agent_id,
            "port": defn["port"],
            "desc": defn["desc"],
            "version": "v1-smoke",
            "run_state": "RUNNING",
            "transport_mode": "local_bus",
            "local_bus_enabled": True,
            "local_bus_endpoint": f"pipe://smoke-device-local/{agent_id}",
            "local_bus_auth_mode": "token",
            "capabilities": ["health_check", "start", "stop", "restart"],
            "token": token,
        }
        resp = _post_json(f"{base}/api/ops-platform/agent/register", payload, cookie)
        ok = bool(resp.get("ok"))
        logs.append(_log(f"register:{defn['node_id']}", ok, str(resp.get("error") or resp.get("agent_id") or "ok"), (time.time() - t0) * 1000))
        agent_tokens[defn["node_id"]] = token

    # 跑 3 轮心跳确保 last_seen 刷新
    for _ in range(3):
        for defn in AGENT_DEFS:
            token = agent_tokens.get(defn["node_id"], "")
            hb = _post_json(
                f"{base}/api/ops-platform/agent/heartbeat",
                {
                    "node_id": defn["node_id"],
                    "agent_id": "",  # 会被服务端按 node_id 查找
                    "project_id": project_id,
                    "status": "ONLINE",
                    "run_state": "RUNNING",
                    "port": defn["port"],
                    "metrics": {"cpu_percent": 10, "mem_percent": 30, "qps": 0},
                    "token": token,
                },
                cookie,
            )
        time.sleep(0.3)

    return True, logs


# ── Step 2: 探测 ─────────────────────────────────────────────────────────────

def step_probe(base: str, cookie: str, project_id: str) -> Tuple[bool, List[Dict[str, Any]]]:
    """探测全部 Agent，确认 PASS。"""
    logs: List[Dict[str, Any]] = []
    t0 = time.time()
    resp = _post_json(
        f"{base}/api/ops-platform/agents/probe-all",
        {"project_id": project_id},
        cookie,
    )
    ok = bool(resp.get("ok"))
    pass_count = resp.get("pass_count", 0)
    fail_count = resp.get("fail_count", 0)
    logs.append(_log("probe-all", ok and fail_count == 0, f"pass={pass_count}; fail={fail_count}", (time.time() - t0) * 1000))
    return ok and fail_count == 0, logs


# ── Step 3: 绑定 ─────────────────────────────────────────────────────────────

def step_bind(base: str, cookie: str, project_id: str) -> Tuple[bool, List[Dict[str, Any]]]:
    """绑定 4 个 Agent 到对应节点。"""
    logs: List[Dict[str, Any]] = []

    # 先获取 agents 列表，找到已注册的 agent_id
    agents_resp = _get_json(f"{base}/api/ops-platform/agents?project_id={project_id}", cookie)
    agents = agents_resp.get("agents") if isinstance(agents_resp.get("agents"), list) else []
    agent_map: Dict[str, str] = {}
    for ag in agents:
        if isinstance(ag, dict):
            nid = str(ag.get("node_id") or "")
            aid = str(ag.get("agent_id") or "")
            if nid and aid:
                agent_map[nid] = aid

    for defn in AGENT_DEFS:
        t0 = time.time()
        aid = agent_map.get(defn["node_id"], "")
        if not aid:
            logs.append(_log(f"bind:{defn['node_id']}", False, "agent_id not found in registry", (time.time() - t0) * 1000))
            continue
        resp = _post_json(
            f"{base}/api/ops-platform/topology/node/bind-agent",
            {"node_id": defn["node_id"], "agent_id": aid, "project_id": project_id},
            cookie,
        )
        ok = bool(resp.get("ok"))
        err_code = resp.get("error_code") or resp.get("error") or ""
        logs.append(_log(f"bind:{defn['node_id']}", ok, str(err_code or "ok"), (time.time() - t0) * 1000))

    all_ok = all(l["ok"] for l in logs)
    return all_ok, logs


# ── Step 4: 远端启动 ─────────────────────────────────────────────────────────

def step_start_remote(base: str, cookie: str, project_id: str) -> Tuple[bool, List[Dict[str, Any]]]:
    """对 4 个节点执行远端启动。"""
    logs: List[Dict[str, Any]] = []

    for defn in AGENT_DEFS:
        t0 = time.time()
        resp = _post_json(
            f"{base}/api/ops-platform/topology/node/start-remote",
            {"node_id": defn["node_id"], "project_id": project_id},
            cookie,
        )
        ok = bool(resp.get("ok"))
        job_id = resp.get("job_id") or ""
        trace_id = resp.get("trace_id") or ""
        logs.append(_log(f"start-remote:{defn['node_id']}", ok, f"job={job_id}; trace={trace_id}", (time.time() - t0) * 1000))

    all_ok = all(l["ok"] for l in logs)
    return all_ok, logs


# ── Step 5: flow-control(start) ──────────────────────────────────────────────

def step_flow_control_start(base: str, cookie: str, project_id: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """flow-control op=start。"""
    logs: List[Dict[str, Any]] = []
    t0 = time.time()
    resp = _post_json(
        f"{base}/api/ops-platform/runtime/flow-control",
        {"op": "start", "project_id": project_id},
        cookie,
    )
    ok = bool(resp.get("ok"))
    run_id = str(resp.get("run_id") or "")
    logs.append(_log("flow-control:start", ok, f"run_id={run_id}", (time.time() - t0) * 1000))
    return ok, run_id, logs


# ── Step 6: flow-status 等待 success ────────────────────────────────────────

def step_flow_status_wait(base: str, cookie: str, run_id: str, max_wait: float = 30) -> Tuple[bool, List[Dict[str, Any]]]:
    """轮询 flow-status 直到 success 或超时。"""
    logs: List[Dict[str, Any]] = []
    t0 = time.time()
    while True:
        resp = _get_json(f"{base}/api/ops-platform/runtime/flow-status?run_id={run_id}", cookie)
        status = str(resp.get("status") or "").upper()
        elapsed = time.time() - t0
        if status in ("SUCCESS", "COMPLETED"):
            logs.append(_log("flow-status", True, f"status={status}; elapsed={elapsed:.1f}s", elapsed * 1000))
            return True, logs
        if status == "FAILED" or elapsed > max_wait:
            logs.append(_log("flow-status", False, f"status={status}; elapsed={elapsed:.1f}s", elapsed * 1000))
            return False, logs
        time.sleep(1)


# ── Step 7: flow-control(stop) ──────────────────────────────────────────────

def step_flow_control_stop(base: str, cookie: str, project_id: str) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """flow-control op=stop。"""
    logs: List[Dict[str, Any]] = []
    t0 = time.time()
    resp = _post_json(
        f"{base}/api/ops-platform/runtime/flow-control",
        {"op": "stop", "project_id": project_id},
        cookie,
    )
    ok = bool(resp.get("ok"))
    run_id = str(resp.get("run_id") or "")
    logs.append(_log("flow-control:stop", ok, f"run_id={run_id}", (time.time() - t0) * 1000))
    return ok, run_id, logs


# ── Step 8: 清理过期 Agent（验证清理 API） ──────────────────────────────────

def step_cleanup_expired(base: str, cookie: str, project_id: str, ttl_hours: int = 1) -> Tuple[bool, List[Dict[str, Any]]]:
    """调用清理过期 Agent API。"""
    logs: List[Dict[str, Any]] = []
    t0 = time.time()
    resp = _post_json(
        f"{base}/api/ops-platform/agents/cleanup-expired",
        {"project_id": project_id, "ttl_hours": ttl_hours},
        cookie,
    )
    ok = bool(resp.get("ok"))
    deleted = resp.get("deleted_count", 0)
    kept = resp.get("kept_count", 0)
    logs.append(_log("cleanup-expired", ok, f"deleted={deleted}; kept={kept}; ttl={ttl_hours}h", (time.time() - t0) * 1000))
    return ok, logs


# ── Step 9: 前置拦截验证（可选） ────────────────────────────────────────────

def step_probe_guard(base: str, cookie: str, project_id: str) -> Tuple[bool, List[Dict[str, Any]]]:
    """验证：probe FAIL 时绑定被拒。"""
    logs: List[Dict[str, Any]] = []

    # 注册一个 probe FAIL 的 agent（端口不可达）
    t0 = time.time()
    bad_agent_id = f"agent-bad-{uuid.uuid4().hex[:6]}"
    reg = _post_json(
        f"{base}/api/ops-platform/agent/register",
        {
            "node_id": "bad-node-test",
            "agent_id": bad_agent_id,
            "project_id": project_id,
            "device_id": "smoke-device-local",
            "host_name": socket.gethostname(),
            "display_name": bad_agent_id,
            "port": 19999,  # 不可达端口
            "desc": "测试用 Agent（不可达）",
            "version": "v1-smoke",
            "run_state": "RUNNING",
            "transport_mode": "local_bus",
            "local_bus_enabled": True,
            "local_bus_endpoint": f"pipe://smoke-device-local/{bad_agent_id}",
            "local_bus_auth_mode": "token",
            "capabilities": ["health_check"],
            "token": "bad-token",
        },
        cookie,
    )
    if not reg.get("ok"):
        logs.append(_log("probe-guard:register", False, f"register failed: {reg.get('error')}", (time.time() - t0) * 1000))
        # 非致命，继续
        return True, logs

    # 探测该 agent → 应该 FAIL
    probe = _post_json(
        f"{base}/api/ops-platform/agents/probe",
        {"agent_id": bad_agent_id, "project_id": project_id},
        cookie,
    )
    probe_ok = bool(probe.get("ok"))
    probe_results = probe.get("results") if isinstance(probe.get("results"), list) else []
    probe_pass = any(str(r.get("status") or "").upper() == "PASS" for r in probe_results if isinstance(r, dict))
    probe_fail_expected = not probe_pass
    logs.append(_log("probe-guard:probe", probe_fail_expected, f"probe_fail_as_expected={probe_fail_expected}; raw_ok={probe_ok}", (time.time() - t0) * 1000))

    # 尝试绑定 → 应该被拒 (OPS_AGENT_PROBE_REQUIRED)
    bind = _post_json(
        f"{base}/api/ops-platform/topology/node/bind-agent",
        {"node_id": "bad-node-test", "agent_id": bad_agent_id, "project_id": project_id},
        cookie,
    )
    bind_rejected = not bind.get("ok") and "PROBE" in str(bind.get("error") or bind.get("error_code") or "").upper()
    bind_error = bind.get("error") or bind.get("error_code") or ""
    logs.append(_log("probe-guard:bind-rejected", bind_rejected, f"rejected={bind_rejected}; error={bind_error}", (time.time() - t0) * 1000))

    # 清理
    _post_json(
        f"{base}/api/ops-platform/agents/cleanup-expired",
        {"project_id": project_id, "ttl_hours": 0},  # ttl=0 会 clamp 到 1h
        cookie,
    )

    return bind_rejected, logs


# ── Main ─────────────────────────────────────────────────────────────────────

def run(base: str, project_id: str, skip_agents: bool, strict: bool) -> Tuple[int, List[Dict[str, Any]]]:
    all_logs: List[Dict[str, Any]] = []

    def add(stage: str, ok: bool, detail: str, elapsed_ms: float = 0):
        all_logs.append(_log(stage, ok, detail, elapsed_ms))

    # Step 0: Login
    print("[Step 0] 登录...")
    login_ok, cookie, login_logs = step_login(base)
    all_logs.extend(login_logs)
    if not login_ok:
        add("abort", False, "登录失败，终止")
        return 1, all_logs
    if not cookie:
        add("abort", False, "无法获取 session cookie，终止")
        return 1, all_logs
    print(f"  ✅ 登录成功")

    # Step 1: Register Agents
    if not skip_agents:
        print("[Step 1] 注册 4 Agent...")
        reg_ok, reg_logs = step_register_agents(base, cookie, project_id)
        all_logs.extend(reg_logs)
        print(f"  {'✅' if reg_ok else '❌'} Agent 注册完成")
    else:
        print("[Step 1] 跳过 Agent 注册 (--skip-agents)")

    # Step 2: Probe
    print("[Step 2] 探测所有 Agent...")
    probe_ok, probe_logs = step_probe(base, cookie, project_id)
    all_logs.extend(probe_logs)
    print(f"  {'✅' if probe_ok else '❌'} 探测结果: {'全部 PASS' if probe_ok else '存在 FAIL'}")

    # Step 3: Bind
    print("[Step 3] 绑定 Agent...")
    bind_ok, bind_logs = step_bind(base, cookie, project_id)
    all_logs.extend(bind_logs)
    print(f"  {'✅' if bind_ok else '❌'} 绑定结果: {'全部成功' if bind_ok else '存在失败'}")

    # Step 4: Start Remote
    print("[Step 4] 远端启动...")
    start_ok, start_logs = step_start_remote(base, cookie, project_id)
    all_logs.extend(start_logs)
    print(f"  {'✅' if start_ok else '❌'} 远端启动: {'全部 ok' if start_ok else '存在失败'}")

    # Step 5: Flow Control (start)
    print("[Step 5] flow-control(start)...")
    fc_ok, run_id, fc_logs = step_flow_control_start(base, cookie, project_id)
    all_logs.extend(fc_logs)
    print(f"  {'✅' if fc_ok else '❌'} flow-control start: run_id={run_id}")

    # Step 6: Flow Status Wait
    if fc_ok and run_id:
        print("[Step 6] 等待 flow-status(success)...")
        fs_ok, fs_logs = step_flow_status_wait(base, cookie, run_id)
        all_logs.extend(fs_logs)
        print(f"  {'✅' if fs_ok else '❌'} flow-status: {'SUCCESS' if fs_ok else 'TIMEOUT/FAILED'}")
    else:
        print("[Step 6] 跳过（flow-control start 失败或无 run_id）")

    # Step 7: Flow Control (stop)
    print("[Step 7] flow-control(stop)...")
    fc_stop_ok, stop_run_id, fc_stop_logs = step_flow_control_stop(base, cookie, project_id)
    all_logs.extend(fc_stop_logs)
    print(f"  {'✅' if fc_stop_ok else '❌'} flow-control stop: run_id={stop_run_id}")

    if fc_stop_ok and stop_run_id:
        print("  等待 stop flow-status...")
        fs_stop_ok, fs_stop_logs = step_flow_status_wait(base, cookie, stop_run_id, max_wait=15)
        all_logs.extend(fs_stop_logs)
        print(f"  {'✅' if fs_stop_ok else '❌'} stop flow-status: {'SUCCESS' if fs_stop_ok else 'TIMEOUT/FAILED'}")

    # Step 8: Cleanup Expired
    print("[Step 8] 清理过期 Agent...")
    clean_ok, clean_logs = step_cleanup_expired(base, cookie, project_id, ttl_hours=1)
    all_logs.extend(clean_logs)
    print(f"  ✅ 清理 API 调用{'成功' if clean_ok else '失败'}（当前 Agent 心跳新鲜，不会被清理）")

    # Step 9: Probe Guard (optional)
    print("[Step 9] 前置拦截验证...")
    guard_ok, guard_logs = step_probe_guard(base, cookie, project_id)
    all_logs.extend(guard_logs)
    print(f"  {'✅' if guard_ok else '⚠️'} 前置拦截: {'PASS 时绑定被拒确认' if guard_ok else '验证不完整'}")

    # Summary
    fails = [l for l in all_logs if not l["ok"]]
    warns = [l for l in all_logs if "guard" in l.get("stage", "") and not l["ok"]]
    total = len(all_logs)
    passed = total - len(fails)

    print(f"\n{'='*60}")
    print(f"冒烟测试结果: {passed}/{total} 通过, {len(fails)} 失败")
    print(f"{'='*60}")

    if fails:
        print("失败项:")
        for f in fails:
            print(f"  ❌ [{f['stage']}] {f['detail']}")

    # 输出 JSON 报告
    report_path = os.path.join(os.path.dirname(__file__), "..", "data", "logs", f"agent-smoke-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fp:
        json.dump({
            "generated_at": _now_iso(),
            "base_url": base,
            "project_id": project_id,
            "total_steps": total,
            "passed": passed,
            "failed": len(fails),
            "steps": all_logs,
        }, fp, ensure_ascii=False, indent=2)
    print(f"报告已写入: {report_path}")

    return (1 if fails and strict else 0), all_logs


def main() -> int:
    parser = argparse.ArgumentParser(description="一键冒烟测试：4 Agent 联调 + Web 全链路")
    parser.add_argument("--base", default="http://127.0.0.1:5003", help="apk-site admin 地址")
    parser.add_argument("--project", default="GomeKu", help="project_id")
    parser.add_argument("--skip-agents", action="store_true", help="跳过 Agent 启动，仅跑 API 链路")
    parser.add_argument("--strict", action="store_true", help="任何非 ok 都算失败")
    args = parser.parse_args()
    code, _ = run(args.base.rstrip("/"), args.project, args.skip_agents, args.strict)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

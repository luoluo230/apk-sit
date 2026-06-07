#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 GomeKu 生产拓扑切换为最小可运行版本，并同步/探活/绑定 Agent。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.ops_ecosystem_chain import (  # noqa: E402
    AGENT_TOKEN,
    _post,
    login,
    resolve_topology_scope,
    step_agent_protocol_register,
    step_auto_bind,
    step_probe_all,
    _load_cluster,
    _cluster_agents,
    _resolve_game_server_repo,
)

BASE = "http://127.0.0.1:5003"
PROJECT = "GomeKu"


def _node(
    node_id: str,
    preset_id: str,
    role: str,
    name: str,
    kind: str,
    x: float,
    y: float,
    port: int = 0,
    daemon_profile: str = "ops_native",
    daemon_start_cmd: str = "",
    daemon_stop_cmd: str = "",
) -> Dict[str, Any]:
    ui: Dict[str, Any] = {
        "x": x,
        "y": y,
        "w": 220,
        "h": 90,
        "locked": False,
        "ports": {"in": [{"id": "in-1", "label": "in-1", "kind": "in", "max_links": 8, "required": False}], "out": [{"id": "out-1", "label": "out-1", "kind": "out", "max_links": 8, "required": False}]},
    }
    if port > 0:
        ui["remote"] = {"port": port}
        ui["network"] = {"endpoints": [f"127.0.0.1:{port}"]}
    row: Dict[str, Any] = {
        "id": node_id,
        "server_id": node_id,
        "preset_id": preset_id,
        "name": name,
        "role": role,
        "kind": kind,
        "desc": name,
        "bizStatus": "normal",
        "owner": "ops-admin",
        "project_id": PROJECT,
        "env": "production",
        "daemon_profile": daemon_profile,
        "x": x,
        "y": y,
        "tags": [role],
        "ui": ui,
    }
    if daemon_profile == "external_daemon":
        row["daemon_port"] = port
        row["daemon_start_cmd"] = daemon_start_cmd
        row["daemon_stop_cmd"] = daemon_stop_cmd
    return row


def build_minimal_topology() -> Dict[str, Any]:
    """GomeKu 最小可运行：4 进程节点 + Redis + Mongo（不含 TCP/压测/MQ）。"""
    nodes = [
        _node("gateway-cn-1", "gateway_http", "gateway", "网关服务", "gateway", 72, 48, 15050),
        _node("auth-cn-1", "auth_service", "auth", "认证服务", "auth", 72, 248),
        _node("ops-cn-1", "ops_service", "ops", "运维服务", "admin", 320, 48, 5504),
        _node("game-cn-1", "business_main", "business", "游戏服务", "game", 560, 168),
        _node(
            "mongo-db-cn-1",
            "mongo_db",
            "database",
            "Mongo 主存储",
            "database",
            820,
            320,
            27017,
            "external_daemon",
            "mongod --dbpath /tmp/gomeku-mongo --port 27017 --bind_ip 127.0.0.1",
            "mongosh --port 27017 --eval 'db.adminCommand({shutdown:1})'",
        ),
        _node(
            "redis-cache-cn-1",
            "redis_cache",
            "cache",
            "Redis 缓存",
            "cache",
            560,
            360,
            6379,
            "external_daemon",
            "redis-server --port 6379",
            "redis-cli -p 6379 shutdown nosave",
        ),
    ]
    edges: List[Dict[str, Any]] = []
    pairs = [
        ("gateway-cn-1", "auth-cn-1", "http:80"),
        ("gateway-cn-1", "ops-cn-1", "http:443"),
        ("auth-cn-1", "game-cn-1", "tcp:5512"),
        ("ops-cn-1", "game-cn-1", "tcp:5512"),
        ("game-cn-1", "mongo-db-cn-1", "structured-auto"),
        ("game-cn-1", "redis-cache-cn-1", "structured-auto"),
    ]
    for idx, (frm, to, note) in enumerate(pairs):
        edges.append(
            {
                "id": f"edge-min-{idx}",
                "from": frm,
                "to": to,
                "from_port": "out-1",
                "to_port": "in-1",
                "type": "depends_on",
                "note": note,
            }
        )
    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "viewport": {"x": 0, "y": 0, "zoom": 1},
            "layout_mode": "structured",
            "layout_locked": False,
            "layout_spacing": {"rank_gap": 268, "row_gap": 128},
            "runtime_topology": True,
            "description": "GomeKu 最小可运行拓扑（Gateway/Auth/Ops/Game + Mongo/Redis）",
            "updated_at": "2026-06-06T00:00:00Z",
        },
    }


def main() -> int:
    ok, cookie = login(BASE)
    if not ok:
        print("登录失败")
        return 1
    scope = resolve_topology_scope(BASE, cookie, PROJECT)
    if not scope.get("topology_id"):
        print("未找到 GomeKu 默认拓扑")
        return 1
    print("scope:", scope)

    topo = build_minimal_topology()
    save_resp = _post(
        BASE,
        "/api/ops-platform/topology/save",
        {**scope, "topology": topo},
        cookie,
    )
    purge = save_resp.get("purge") if isinstance(save_resp.get("purge"), dict) else {}
    if purge.get("removed_agents") or purge.get("removed_bindings"):
        print(f"demo 清理: agents={purge.get('removed_agents')} bindings={purge.get('removed_bindings')}")
    if not save_resp.get("ok"):
        print("拓扑保存失败:", save_resp.get("message") or save_resp.get("error"))
        if save_resp.get("errors"):
            for err in save_resp.get("errors") or []:
                print(" ", err)
        return 1
    print(f"拓扑已保存: nodes={len(topo['nodes'])} edges={len(topo['edges'])}")
    sync = save_resp.get("sync") if isinstance(save_resp.get("sync"), dict) else {}
    print(f"cluster apply: ok={sync.get('ok')} message={sync.get('message') or ''}")
    agents_stat = save_resp.get("agents") if isinstance(save_resp.get("agents"), dict) else {}
    print(f"agent upsert: added={agents_stat.get('added')} updated={agents_stat.get('updated')}")

    repo = _resolve_game_server_repo("")
    cluster_rows = _load_cluster(repo)
    cluster_agents = [a for a in _cluster_agents(cluster_rows) if a["node_id"] in {"gateway-cn-1", "auth-cn-1", "game-cn-1", "ops-cn-1"}]
    infra_agents = [
        {"node_id": "mongo-db-cn-1", "agent_id": "agent-mongo-db-cn-1", "role": "database", "host_name": "127.0.0.1", "port": 27017, "remote_game_server_port": 27017, "desc": "Mongo 主存储"},
        {"node_id": "redis-cache-cn-1", "agent_id": "agent-redis-cache-cn-1", "role": "cache", "host_name": "127.0.0.1", "port": 6379, "remote_game_server_port": 6379, "desc": "Redis 缓存"},
    ]
    reg_ok, reg_logs = step_agent_protocol_register(BASE, cluster_agents + infra_agents, PROJECT)
    for line in reg_logs:
        print(line)

    try:
        sys.path.insert(0, str(ROOT / "portals" / "common" / "core"))
        from routes import gm_legacy as gm  # type: ignore
        stat = gm._consolidate_runtime_agents_to_canonical(PROJECT)
        print(f"canonical consolidate: {stat}")
    except Exception as exc:
        print(f"registry consolidate skipped: {exc}")

    probe_ok, probe_logs = step_probe_all(BASE, cookie, PROJECT)
    for line in probe_logs:
        print(line)

    bind_ok, bind_logs = step_auto_bind(BASE, cookie, scope)
    for line in bind_logs:
        print(line)

    bind_resp = _post(BASE, "/api/ops-platform/topology/auto-bind-agents", scope, cookie)
    bindings = bind_resp.get("bindings") if isinstance(bind_resp.get("bindings"), dict) else {}
    print("\n=== 绑定结果 ===")
    for nid in [n["id"] for n in topo["nodes"]]:
        aid = bindings.get(nid, "")
        status = "BOUND" if aid else "UNBOUND"
        print(f"  {nid} -> {aid or '-'} [{status}]")

    # 清理 per-node 旧 Agent，只保留 canonical 单 Agent
    try:
        sys.path.insert(0, str(ROOT / "portals" / "common" / "core"))
        from routes import gm_legacy as gm  # type: ignore
        reg = gm._load_agent_registry_v2()
        now = gm._now_iso()
        removed = 0
        stale_marked = 0
        canonical_id = gm.CANONICAL_LOCAL_AGENT_ID
        for aid in list(reg.keys()):
            item = reg.get(aid)
            if not isinstance(item, dict):
                continue
            if str(item.get("project_id") or "") not in ("", PROJECT):
                continue
            if aid in ("agent-tcp-cn-1",) or str(item.get("node_id") or "") == "tcp-cn-1":
                reg.pop(aid, None)
                removed += 1
                continue
            if aid == canonical_id:
                continue
            nid = str(item.get("node_id") or "")
            if nid.endswith("-cn-1") or str(aid).endswith("-cn-1"):
                item["stale"] = True
                item["stale_reason"] = "consolidated_to_canonical"
                item["superseded_by"] = canonical_id
                item["updated_at"] = now
                stale_marked += 1
        gm._save_agent_registry_v2(reg)
        stat = gm._consolidate_runtime_agents_to_canonical(PROJECT)
        print(f"registry cleanup: stale_marked={stale_marked} removed={removed} canonical={stat}")
    except Exception as exc:
        print(f"registry cleanup skipped: {exc}")

    try:
        from routes import gm_legacy as gm  # type: ignore
        logical = gm._logical_agents_for_project(PROJECT)
        print(f"logical agents: {len(logical)} (expect 1)")
    except Exception:
        pass

    if not save_resp.get("ok"):
        return 1
    if int(bind_resp.get("bound_count") or 0) < len(topo["nodes"]):
        return 1
    if not reg_ok:
        return 1
    if not probe_ok:
        print("probe-all 未全通过（GameServer 未启动时可忽略，启动后重跑 probe-all）")

    print("\n最小拓扑已就绪，可在拓扑编排与 Agent 管控中心做联通测试。")
    print(f"Agent 管控: {BASE}/admin/ops-platform/agent-control?project_id={PROJECT}")
    print(f"拓扑编排: {BASE}/admin/ops-platform/topology?project_id={PROJECT}&env_key=production&topology_id={scope['topology_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

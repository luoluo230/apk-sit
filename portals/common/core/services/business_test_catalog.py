"""Business test protocol catalog and plan storage."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from config import DATA_DIR


def _maclient_root_from_repo(game_server_repo: str) -> str:
    repo = os.path.abspath(game_server_repo or "")
    if os.path.basename(repo).lower() == "game-server":
        return os.path.dirname(repo)
    return repo


def resolve_paths(game_server_repo: str) -> Dict[str, str]:
    repo = os.path.abspath(game_server_repo or "")
    root = _maclient_root_from_repo(repo)
    smoke_dir = os.path.join(repo, "tools", "SmokeTest")
    return {
        "game_server_repo": repo,
        "maclient_root": root,
        "catalog_path": os.path.join(root, "protocols", "generated", "protocol-catalog.json"),
        "protocols_json": os.path.join(root, "Assets", "Src", "Protocols", "protocols.json"),
        "builtin_plans_dir": os.path.join(smoke_dir, "business-test-plans"),
        "runner_py": os.path.join(smoke_dir, "run-business-test.py"),
        "smoke_exe": os.path.join(smoke_dir, "bin", "Debug", "SmokeTest.exe"),
        "custom_plans_dir": os.path.join(DATA_DIR, "business_test_plans"),
    }


def _load_catalog_file(catalog_path: str) -> Tuple[Dict[str, Any], str]:
    if os.path.isfile(catalog_path):
        with open(catalog_path, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
        mtime = datetime.fromtimestamp(os.path.getmtime(catalog_path), tz=timezone.utc).isoformat()
        return raw, mtime

    return {
        "protocols": [],
        "error": "catalog_missing",
        "catalog_path": catalog_path,
    }, ""


def build_catalog_view(game_server_repo: str) -> Dict[str, Any]:
    paths = resolve_paths(game_server_repo)
    raw, mtime = _load_catalog_file(paths["catalog_path"])
    if raw.get("error") == "catalog_missing":
        return {
            "ok": False,
            "error": "catalog_missing",
            "catalog_path": paths["catalog_path"],
            "generated_from": paths["catalog_path"],
            "mtime": mtime,
            "fallback": False,
            "module_count": 0,
            "protocol_count": 0,
            "modules": [],
            "protocols": [],
            "paths": {k: v for k, v in paths.items() if k.endswith("_dir") or k.endswith("_path")},
        }
    modules: Dict[str, List[Dict[str, Any]]] = {}
    protocols: List[Dict[str, Any]] = []
    for item in raw.get("protocols") or []:
        if not isinstance(item, dict):
            continue
        module = str(item.get("module") or "General")
        req = None
        resp = None
        for msg in item.get("messages") or []:
            if not isinstance(msg, dict):
                continue
            direction = str(msg.get("direction") or "").lower()
            if direction == "request":
                req = msg
            elif direction == "response":
                resp = msg
        if req is None:
            continue
        entry = {
            "name": item.get("name"),
            "module": module,
            "status": item.get("status") or "beta",
            "request_type": req.get("type"),
            "request_id": req.get("id"),
            "response_type": (resp or {}).get("type"),
            "response_id": (resp or {}).get("id"),
        }
        protocols.append(entry)
        modules.setdefault(module, []).append(entry)
    module_list = [
        {"name": name, "count": len(items), "protocols": items}
        for name, items in sorted(modules.items(), key=lambda x: x[0])
    ]
    return {
        "ok": True,
        "generated_from": raw.get("generatedFrom") or paths["catalog_path"],
        "mtime": mtime,
        "fallback": bool(raw.get("fallback")),
        "module_count": len(module_list),
        "protocol_count": len(protocols),
        "modules": module_list,
        "protocols": protocols,
        "paths": {k: v for k, v in paths.items() if k.endswith("_dir") or k.endswith("_path")},
    }


def _read_plan_file(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    if isinstance(plan, dict):
        plan.setdefault("source", "builtin" if "business-test-plans" in path.replace("\\", "/") else "custom")
        return plan
    return None


def list_plans(game_server_repo: str, category: str = "") -> Dict[str, Any]:
    paths = resolve_paths(game_server_repo)
    os.makedirs(paths["custom_plans_dir"], exist_ok=True)
    plans: List[Dict[str, Any]] = []
    builtin_dir = paths["builtin_plans_dir"]
    if os.path.isdir(builtin_dir):
        for name in sorted(os.listdir(builtin_dir)):
            if not name.endswith(".json") or name == "index.json":
                continue
            plan = _read_plan_file(os.path.join(builtin_dir, name))
            if plan:
                plans.append(_plan_summary(plan))
    custom_dir = paths["custom_plans_dir"]
    for name in sorted(os.listdir(custom_dir)):
        if not name.endswith(".json"):
            continue
        plan = _read_plan_file(os.path.join(custom_dir, name))
        if plan:
            plan["source"] = "custom"
            plans.append(_plan_summary(plan))
    if category:
        cat = category.strip()
        plans = [p for p in plans if str(p.get("category") or "") == cat]
    categories = sorted({str(p.get("category") or "General") for p in plans})
    return {"ok": True, "count": len(plans), "categories": categories, "plans": plans}


def _plan_summary(plan: Dict[str, Any]) -> Dict[str, Any]:
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    return {
        "plan_id": plan.get("plan_id"),
        "name": plan.get("name"),
        "category": plan.get("category"),
        "source": plan.get("source") or "builtin",
        "transport": plan.get("transport") or "websocket",
        "step_count": len(steps),
        "tags": plan.get("tags") or [],
        "version": plan.get("version") or 1,
    }


def get_plan(game_server_repo: str, plan_id: str) -> Optional[Dict[str, Any]]:
    paths = resolve_paths(game_server_repo)
    for base in (paths["builtin_plans_dir"], paths["custom_plans_dir"]):
        path = os.path.join(base, plan_id + ".json")
        plan = _read_plan_file(path)
        if plan:
            return plan
    return None


def save_custom_plan(plan: Dict[str, Any], game_server_repo: str) -> Dict[str, Any]:
    paths = resolve_paths(game_server_repo)
    os.makedirs(paths["custom_plans_dir"], exist_ok=True)
    plan_id = str(plan.get("plan_id") or "").strip()
    if not plan_id:
        return {"ok": False, "error": "missing_plan_id"}
    catalog = build_catalog_view(game_server_repo)
    if not catalog.get("ok"):
        return {
            "ok": False,
            "error": catalog.get("error") or "catalog_unavailable",
            "catalog_path": catalog.get("catalog_path"),
        }
    known = {p.get("request_type") for p in catalog.get("protocols") or []}
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    invalid = [s.get("protocol") for s in steps if isinstance(s, dict) and s.get("protocol") not in known]
    if invalid:
        return {"ok": False, "error": "unknown_protocols", "invalid": invalid}
    plan["source"] = "custom"
    plan.setdefault("version", 1)
    path = os.path.join(paths["custom_plans_dir"], plan_id + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    return {"ok": True, "plan_id": plan_id, "path": path, "plan": plan}


def delete_custom_plan(plan_id: str) -> Dict[str, Any]:
    paths = resolve_paths("")
    path = os.path.join(paths["custom_plans_dir"], plan_id + ".json")
    if not os.path.isfile(path):
        return {"ok": False, "error": "not_found"}
    os.remove(path)
    return {"ok": True, "plan_id": plan_id}


def resolve_gateway_endpoint(
    topology: Optional[Dict[str, Any]] = None,
    agent_bindings: Optional[Dict[str, str]] = None,
    transport: str = "websocket",
) -> Dict[str, Any]:
    """Resolve Gateway WS/TCP endpoint from topology canvas + agent bindings."""
    transport = str(transport or "websocket").strip().lower()
    nodes = topology.get("nodes") if isinstance(topology, dict) and isinstance(topology.get("nodes"), list) else []
    bindings = agent_bindings if isinstance(agent_bindings, dict) else {}
    gateway_node = None
    for node in nodes:
        if not isinstance(node, dict):
            continue
        role = str(node.get("role") or "").strip().lower()
        nid = str(node.get("id") or node.get("server_id") or "").strip().lower()
        if role in ("gateway", "edge") or nid.startswith("gateway-"):
            gateway_node = node
            break
    if gateway_node is None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if str(node.get("id") or "").strip().lower() == "gateway-cn-1":
                gateway_node = node
                break
    host = "127.0.0.1"
    port = 15050
    if isinstance(gateway_node, dict):
        ui = gateway_node.get("ui") if isinstance(gateway_node.get("ui"), dict) else {}
        remote = ui.get("remote") if isinstance(ui.get("remote"), dict) else {}
        network = ui.get("network") if isinstance(ui.get("network"), dict) else {}
        for candidate in (
            str(remote.get("host") or remote.get("probe_host") or "").strip(),
            str(network.get("probe_host") or "").strip(),
        ):
            if candidate and candidate not in ("0.0.0.0", "*"):
                host = candidate
                break
        for candidate in (
            int(remote.get("port") or 0),
            int(network.get("port") or 0),
            int(gateway_node.get("port") or 0),
        ):
            if candidate > 0:
                port = int(candidate)
                break
    ws_url = f"ws://{host}:{port}/ws/"
    tcp_host = host
    tcp_port = 5601
    return {
        "host": host,
        "port": port,
        "ws_url": ws_url,
        "tcp_host": tcp_host,
        "tcp_port": tcp_port,
        "transport": transport,
        "gateway_node_id": str((gateway_node or {}).get("id") or "gateway-cn-1"),
    }


def validate_plan_dict(plan: Dict[str, Any], game_server_repo: str) -> List[str]:
    catalog = build_catalog_view(game_server_repo)
    if not catalog.get("ok"):
        return ["catalog_missing:" + str(catalog.get("catalog_path") or "")]
    known = {p.get("request_type") for p in catalog.get("protocols") or []}
    issues: List[str] = []
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    if not steps:
        issues.append("steps_empty")
    for step in steps:
        if not isinstance(step, dict):
            issues.append("invalid_step")
            continue
        proto = step.get("protocol")
        if proto not in known:
            issues.append("unknown_protocol:" + str(proto))
    return issues

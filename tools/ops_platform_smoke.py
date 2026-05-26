#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ops platform API smoke test (admin session + Flask test_client).

Usage:
  py -3 tools/ops_platform_smoke.py --project GomeKu
  py -3 tools/ops_platform_smoke.py --project GomeKu --strict
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple


def _bootstrap_app():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    core = os.path.join(root, "portals", "common", "core")
    if core not in sys.path:
        sys.path.insert(0, core)
    os.environ["APP_PORTAL_MODE"] = "admin"
    from app_new import app  # type: ignore

    return app


def _is_external_dep_failure(resp: Dict[str, Any]) -> bool:
    message = str(resp.get("message") or "")
    if "Ops service unavailable" in message or "Failed to establish a new connection" in message:
        return True
    steps = resp.get("steps") if isinstance(resp.get("steps"), list) else []
    for s in steps:
        if not isinstance(s, dict):
            continue
        inner = s.get("result") if isinstance(s.get("result"), dict) else {}
        inner_msg = str(s.get("message") or inner.get("message") or "")
        if "Ops service unavailable" in inner_msg or "Failed to establish a new connection" in inner_msg:
            return True
    return False


def run(project_id: str, strict: bool = False) -> Tuple[int, List[Dict[str, Any]]]:
    app = _bootstrap_app()
    report: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, status: Optional[int], detail: str, level: str = "ok") -> None:
        report.append({"name": name, "ok": bool(ok), "status": status, "detail": detail, "level": level})

    with app.test_client() as c:
        with c.session_transaction() as s:
            s["user"] = "admin"

        def get_json(path: str, name: str) -> Optional[Dict[str, Any]]:
            r = c.get(path)
            ct = r.headers.get("Content-Type", "")
            if "application/json" not in ct:
                add(name, False, r.status_code, f"non-json content-type={ct}", "fail")
                return None
            d = r.get_json(silent=True)
            if d is None:
                add(name, False, r.status_code, "json parse failed", "fail")
                return None
            add(name, r.status_code < 500, r.status_code, str(d.get("error") or d.get("message") or "ok"))
            return d

        def post_json(path: str, payload: Dict[str, Any], name: str, allow_external_dep: bool = False) -> Optional[Dict[str, Any]]:
            r = c.post(path, json=payload)
            ct = r.headers.get("Content-Type", "")
            if "application/json" not in ct:
                add(name, False, r.status_code, f"non-json content-type={ct}", "fail")
                return None
            d = r.get_json(silent=True)
            if d is None:
                add(name, False, r.status_code, "json parse failed", "fail")
                return None
            ok = r.status_code < 500
            level = "ok"
            detail = str(d.get("error") or d.get("message") or "ok")
            if not ok and allow_external_dep and _is_external_dep_failure(d):
                ok = not strict
                level = "warn"
                detail = "external_dependency_unavailable: " + detail
            elif not ok:
                level = "fail"
            add(name, ok, r.status_code, detail, level)
            return d

        # GET contracts
        get_json(f"/api/ops-platform/overview?project_id={project_id}", "overview")
        get_json("/api/ops-platform/events?limit=20", "events")
        get_json("/api/ops-platform/module-map", "module-map")
        get_json("/api/ops-platform/control-plane/summary", "control-plane-summary")
        get_json(f"/api/ops-platform/agents?project_id={project_id}", "agents")
        get_json(f"/api/ops-platform/agents/devices?project_id={project_id}", "agents-devices")
        get_json("/api/ops-platform/change-governance/summary", "change-governance-summary")
        get_json("/api/ops-platform/action-catalog", "action-catalog")
        topo = get_json(f"/api/ops-platform/topology?project_id={project_id}", "topology")
        get_json("/api/ops-platform/node-presets", "node-presets")
        get_json("/api/ops-platform/topology-blueprints", "topology-blueprints")
        get_json("/api/ops-platform/node-onboarding", "node-onboarding")
        get_json("/api/ops-platform/agent/policy", "agent-policy-get")
        get_json("/api/ops-platform/agent/jobs?limit=20", "agent-jobs")

        nodes = []
        if topo and isinstance(topo.get("topology"), dict):
            nodes = list(topo["topology"].get("nodes") or [])
        first_node = nodes[0]["id"] if nodes else "local-gm"
        second_node = nodes[1]["id"] if len(nodes) > 1 else first_node

        # POST contracts
        post_json("/api/ops-platform/client-log", {"event": "smoke_test", "payload": {"t": "now"}}, "client-log")
        post_json(
            "/api/ops-platform/agent/policy",
            {"queue_max": 200, "lease_ttl_sec": 60, "retry_max": 3, "heartbeat_timeout_sec": 120},
            "agent-policy-post",
        )
        post_json(
            "/api/ops-platform/actions/validate",
            {"node_id": first_node, "action_type": "health_check", "target": first_node, "reason": "smoke"},
            "actions-validate",
        )
        exec_res = post_json(
            "/api/ops-platform/actions/execute",
            {"node_id": first_node, "action_type": "health_check", "target": first_node, "reason": "smoke-exec"},
            "actions-execute",
            allow_external_dep=True,
        )
        if exec_res and exec_res.get("trace_id"):
            get_json("/api/ops-platform/actions/" + str(exec_res.get("trace_id")), "actions-trace")

        post_json(
            "/api/ops-platform/flow-smoke",
            {"path_nodes": [first_node, second_node] if second_node != first_node else [first_node]},
            "flow-smoke",
            allow_external_dep=True,
        )
        post_json(
            "/api/ops-platform/stress-test",
            {"node_id": first_node, "qps": 30, "duration_sec": 10, "reason": "smoke"},
            "stress-test",
            allow_external_dep=True,
        )

        if first_node and second_node and first_node != second_node:
            up = post_json(
                "/api/ops-platform/topology/edge/upsert",
                {"from": first_node, "to": second_node, "from_port": "out-1", "to_port": "in-1", "type": "depends_on", "note": "smoke"},
                "edge-upsert",
            )
            if up and isinstance(up.get("topology"), dict):
                new_edges = up["topology"].get("edges") or []
                created = None
                for e in new_edges:
                    if e.get("from") == first_node and e.get("to") == second_node:
                        created = e.get("id")
                if created:
                    post_json("/api/ops-platform/topology/edge/delete", {"edge_id": created}, "edge-delete")

        if nodes:
            n = deepcopy(nodes[0])
            patch = {
                "role": n.get("role", "business"),
                "kind": n.get("kind", "standard"),
                "desc": n.get("desc", ""),
                "bizStatus": n.get("bizStatus", "normal"),
                "owner": n.get("owner", ""),
                "x": ((n.get("ui") or {}).get("x", 100)),
                "y": ((n.get("ui") or {}).get("y", 100)),
                "ui": (n.get("ui") or {}),
                "tags": (n.get("tags") or []),
            }
            post_json("/api/ops-platform/topology/node/update", {"node_id": n.get("id"), "patch": patch}, "node-update")

        if topo and isinstance(topo.get("topology"), dict):
            post_json("/api/ops-platform/topology/save", {"topology": topo.get("topology")}, "topology-save")

        post_json(
            "/api/ops-platform/topology/node/bind-agent",
            {"node_id": first_node, "agent_id": "", "project_id": project_id},
            "node-bind-agent-clear",
        )
        get_json(f"/api/ops-platform/topology/node/bindings?project_id={project_id}", "node-bindings")

        bps = get_json("/api/ops-platform/topology-blueprints", "topology-blueprints-2")
        bp_rows = (bps or {}).get("blueprints") or []
        if bp_rows:
            bid = bp_rows[0].get("blueprint_id")
            post_json(
                "/api/ops-platform/topology/apply-blueprint",
                {"project_id": project_id, "blueprint_id": bid, "replace_existing": False},
                "apply-blueprint-no-replace",
            )

    fails = [x for x in report if not x["ok"]]
    warns = [x for x in report if x.get("level") == "warn"]
    print(
        json.dumps(
            {"project_id": project_id, "strict": strict, "total": len(report), "failed": len(fails), "warn": len(warns), "fails": fails},
            ensure_ascii=False,
            indent=2,
        )
    )
    return (1 if fails else 0), report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="GomeKu")
    parser.add_argument("--strict", action="store_true", help="Treat external dependency unavailable as failure")
    args = parser.parse_args()
    code, _ = run(args.project, strict=args.strict)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

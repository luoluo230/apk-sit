#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ops alignment audit (read-only checks + optional API checks)."""
from __future__ import annotations
import argparse, json, re, pathlib, urllib.request, urllib.error

ROOT = pathlib.Path(r"E:/web/apk-site")
GM = ROOT / "portals/common/core/routes/gm_legacy.py"
AGENT = pathlib.Path(r"E:/maclient/game-server/tools/ServerAgent/AgentServer.cs")
APIJS = ROOT / "portals/common/core/static/ops_platform_api.js"

OPS_ENDPOINTS = [
  "/api/ops-platform/agent/register",
  "/api/ops-platform/agent/heartbeat",
  "/api/ops-platform/agent/pull",
  "/api/ops-platform/agent/report",
  "/api/ops-platform/agents",
  "/api/ops-platform/agents/devices",
  "/api/ops-platform/agents/probe",
  "/api/ops-platform/agents/probe-all",
  "/api/ops-platform/topology/node/bind-agent",
  "/api/ops-platform/topology/node/start-remote",
  "/api/ops-platform/runtime/flow-control",
  "/api/ops-platform/runtime/flow-status",
  "/api/ops-platform/runtime/active",
  "/api/ops-platform/actions/validate",
  "/api/ops-platform/actions/approval",
  "/api/ops-platform/actions/execute",
]

ACTIONS = ["status","health_check","ready_check","runtime_snapshot","start","stop","restart","start_all","stop_all","smoke_test","stress_test"]

def read(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")

def http_get(url: str, timeout=4):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read().decode("utf-8", "ignore")
            return {"ok": True, "status": r.status, "body": body[:400]}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": str(e)}
    except Exception as e:
        return {"ok": False, "status": 0, "error": str(e)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5003")
    ap.add_argument("--out", default=str(ROOT / "docs/ops_alignment/05_audit_result.json"))
    args = ap.parse_args()

    gm = read(GM)
    agent = read(AGENT)
    apijs = read(APIJS)

    res = {"static": {}, "runtime": {}, "summary": {}}

    # static route coverage
    route_hits = {ep: (ep in gm) for ep in OPS_ENDPOINTS}
    res["static"]["routes"] = route_hits

    # action coverage
    act_hits = {a: (re.search(rf'\b{re.escape(a)}\b', agent) is not None) for a in ACTIONS}
    res["static"]["agent_actions"] = act_hits

    # frontend API bindings
    fe_hits = {ep: (ep in apijs) for ep in OPS_ENDPOINTS if "flow-status" not in ep or "runtimeFlowStatus" in apijs}
    res["static"]["frontend_bindings"] = fe_hits

    # runtime basic availability
    res["runtime"]["health"] = http_get(args.base.rstrip("/") + "/health")
    res["runtime"]["overview"] = http_get(args.base.rstrip("/") + "/api/ops-platform/overview?project_id=GomeKu")
    res["runtime"]["agents"] = http_get(args.base.rstrip("/") + "/api/ops-platform/agents?project_id=GomeKu")

    total_routes = len(route_hits)
    ok_routes = sum(1 for v in route_hits.values() if v)
    total_actions = len(act_hits)
    ok_actions = sum(1 for v in act_hits.values() if v)

    res["summary"] = {
        "route_coverage": f"{ok_routes}/{total_routes}",
        "action_coverage": f"{ok_actions}/{total_actions}",
        "runtime_health": res["runtime"]["health"].get("ok", False),
        "note": "overview/agents may return 401/403 when no admin session is provided; static alignment still valid"
    }

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out))

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local mock Ops server for end-to-end ops-platform flow."""

from __future__ import annotations

import argparse
import time
import uuid
from flask import Flask, jsonify, request

app = Flask(__name__)


@app.get("/ops/health")
def health():
    return jsonify({"success": True, "message": "ok", "data": {"status": "healthy", "ts": time.time()}})


@app.get("/ops/ready")
def ready():
    return jsonify({"success": True, "message": "ready", "data": {"ready": True, "ts": time.time()}})


@app.get("/ops/runtime-snapshot")
def runtime_snapshot():
    return jsonify(
        {
            "success": True,
            "message": "runtime",
            "data": {
                "uptime_sec": int(time.time()) % 100000,
                "cpu_pct": 21.4,
                "mem_pct": 43.1,
                "threads": 18,
            },
        }
    )


@app.get("/ops/storage-metrics")
def storage_metrics():
    return jsonify(
        {
            "success": True,
            "message": "storage",
            "data": {
                "disk_used_gb": 18.2,
                "disk_total_gb": 120.0,
                "iops_read": 1320,
                "iops_write": 1180,
            },
        }
    )


@app.get("/ops/cluster")
def cluster():
    return jsonify(
        {
            "success": True,
            "message": "cluster",
            "data": {"node_count": 6, "healthy": 6, "degraded": 0, "offline": 0},
        }
    )


@app.get("/ops/deployment-catalog")
def deployment_catalog():
    return jsonify(
        {
            "success": True,
            "message": "catalog",
            "data": {
                "nodes": [
                    {"serverId": "gateway_http", "status": "ONLINE"},
                    {"serverId": "business_main", "status": "ONLINE"},
                    {"serverId": "mysql_db", "status": "ONLINE"},
                    {"serverId": "redis_cache", "status": "ONLINE"},
                ]
            },
        }
    )


@app.post("/ops/action")
def action():
    payload = request.get_json(silent=True) or {}
    action_type = str(payload.get("ActionType") or payload.get("action_type") or "").strip().lower()
    trace_id = "mock-" + uuid.uuid4().hex[:12]
    msg = f"action {action_type or 'unknown'} accepted"
    data = {"ResultCode": "OPS_OK", "ResultMessage": msg, "TraceId": trace_id, "Echo": payload}
    return jsonify({"success": True, "message": msg, "data": data})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5054)
    args = parser.parse_args()
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()


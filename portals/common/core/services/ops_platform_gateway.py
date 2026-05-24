# -*- coding: utf-8 -*-
"""Ops platform gateway: native Ops API integration for intranet."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import requests


class OpsPlatformGateway:
    """Unified native Ops API gateway with header injection and error normalization."""

    def __init__(self) -> None:
        self._timeout = int(os.getenv("OPS_PLATFORM_TIMEOUT_SECONDS", "10") or "10")

    @staticmethod
    def _normalize_base(base_url: str) -> str:
        base = str(base_url or "").strip().rstrip("/")
        if not base:
            return ""
        if not base.startswith("http://") and not base.startswith("https://"):
            base = "http://" + base
        return base

    def _headers(
        self,
        node: Dict[str, Any],
        *,
        write: bool,
        actor: str,
        reason: str,
        ticket_id: str,
    ) -> Dict[str, str]:
        read_key = str(node.get("ops_read_key") or os.getenv("GAME_OPS_READ_KEY", "") or "").strip()
        write_key = str(node.get("ops_write_key") or os.getenv("GAME_OPS_WRITE_KEY", "") or "").strip()
        key = write_key if write else (read_key or write_key)

        headers = {
            "X-Ops-Key": key,
            "X-Ops-Actor": str(node.get("ops_actor") or actor or "intranet-ops").strip(),
            "X-Ops-Role": str(node.get("ops_role") or "SuperAdmin").strip(),
            "X-Ops-Reason": str(reason or "ops-platform").strip(),
            "X-Ops-TicketId": str(ticket_id or "OPS-N/A").strip(),
        }
        return headers

    def _request(
        self,
        node: Dict[str, Any],
        *,
        method: str,
        path: str,
        write: bool,
        actor: str,
        reason: str,
        ticket_id: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        base = self._normalize_base(str(node.get("ops_base_url") or ""))
        if not base:
            return {"success": False, "status": 400, "message": "missing ops_base_url", "data": {}}

        headers = self._headers(node, write=write, actor=actor, reason=reason, ticket_id=ticket_id)
        url = f"{base}{path}"

        started = time.time()
        try:
            if method.upper() == "GET":
                resp = requests.get(url, headers=headers, params=params or {}, timeout=self._timeout)
            else:
                payload = json.dumps(json_body or {}, ensure_ascii=False)
                h = dict(headers)
                h["Content-Type"] = "application/json; charset=utf-8"
                resp = requests.post(url, headers=h, params=params or {}, data=payload.encode("utf-8"), timeout=self._timeout)

            latency_ms = int((time.time() - started) * 1000)
            try:
                body = resp.json() if resp.content else {}
            except Exception:
                body = {"success": resp.ok, "raw": (resp.text or "")[:800]}

            ok = bool(body.get("success", resp.status_code < 400))
            message = str(body.get("message") or "OK")
            data = body.get("data", body)
            if resp.status_code >= 400:
                ok = False
                if not message:
                    message = "ops request failed"

            return {
                "success": ok,
                "status": resp.status_code,
                "message": message,
                "latency_ms": latency_ms,
                "data": data,
                "raw": body,
            }
        except Exception as ex:
            return {
                "success": False,
                "status": 500,
                "message": f"Ops service unavailable: {ex}",
                "latency_ms": int((time.time() - started) * 1000),
                "data": {},
                "raw": {},
            }

    def health(self, node: Dict[str, Any], *, actor: str, reason: str, ticket_id: str) -> Dict[str, Any]:
        return self._request(node, method="GET", path="/ops/health", write=False, actor=actor, reason=reason, ticket_id=ticket_id)

    def ready(self, node: Dict[str, Any], *, actor: str, reason: str, ticket_id: str) -> Dict[str, Any]:
        return self._request(node, method="GET", path="/ops/ready", write=False, actor=actor, reason=reason, ticket_id=ticket_id)

    def runtime_snapshot(self, node: Dict[str, Any], *, actor: str, reason: str, ticket_id: str) -> Dict[str, Any]:
        return self._request(node, method="GET", path="/ops/runtime-snapshot", write=False, actor=actor, reason=reason, ticket_id=ticket_id)

    def storage_metrics(self, node: Dict[str, Any], *, actor: str, reason: str, ticket_id: str) -> Dict[str, Any]:
        return self._request(node, method="GET", path="/ops/storage-metrics", write=False, actor=actor, reason=reason, ticket_id=ticket_id)

    def cluster(self, node: Dict[str, Any], *, actor: str, reason: str, ticket_id: str) -> Dict[str, Any]:
        return self._request(node, method="GET", path="/ops/cluster", write=False, actor=actor, reason=reason, ticket_id=ticket_id)

    def deployment_catalog(self, node: Dict[str, Any], *, actor: str, reason: str, ticket_id: str) -> Dict[str, Any]:
        return self._request(node, method="GET", path="/ops/deployment-catalog", write=False, actor=actor, reason=reason, ticket_id=ticket_id)

    def execute_action(
        self,
        node: Dict[str, Any],
        *,
        action_type: str,
        domain: str,
        target: str,
        payload: Dict[str, Any],
        actor: str,
        reason: str,
        ticket_id: str,
        dry_run: bool,
    ) -> Dict[str, Any]:
        body = {
            "actionType": action_type,
            "domain": domain,
            "target": target,
            "payload": payload or {},
            "dryRun": bool(dry_run),
            "operatorContext": {
                "actor": actor,
                "reason": reason,
                "ticketId": ticket_id,
            },
        }
        result = self._request(
            node,
            method="POST",
            path="/ops/action",
            write=True,
            actor=actor,
            reason=reason,
            ticket_id=ticket_id,
            json_body=body,
        )

        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        trace_id = str(data.get("TraceId") or data.get("traceId") or "").strip()
        result_code = str(data.get("ResultCode") or data.get("resultCode") or "").strip()
        result_message = str(data.get("ResultMessage") or data.get("resultMessage") or result.get("message") or "")
        if result_code:
            result["success"] = result_code in ("OPS_OK", "OPS_DRY_RUN_OK")
            result["message"] = result_message or result.get("message")

        result["trace_id"] = trace_id
        result["result_code"] = result_code
        result["result_message"] = result_message
        return result

    @staticmethod
    def _pick_server_state(cluster_payload: Dict[str, Any], server_id: str) -> str:
        data = cluster_payload.get("data") if isinstance(cluster_payload, dict) else {}
        cluster = data if isinstance(data, dict) else {}
        servers = cluster.get("Servers") or cluster.get("servers") or []
        sid = str(server_id or "").strip().lower()
        for item in servers:
            if not isinstance(item, dict):
                continue
            current = str(item.get("ServerId") or item.get("serverId") or "").strip().lower()
            if sid and current == sid:
                return str(item.get("State") or item.get("state") or "UNKNOWN").upper()
        return "UNKNOWN"

    @staticmethod
    def _safe_num(value: Any, default: float = -1.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    def build_node_overview(self, node: Dict[str, Any], *, actor: str) -> Dict[str, Any]:
        reason = "ops overview"
        ticket = "OPS-OVERVIEW"
        health = self.health(node, actor=actor, reason=reason, ticket_id=ticket)
        ready = self.ready(node, actor=actor, reason=reason, ticket_id=ticket)
        runtime = self.runtime_snapshot(node, actor=actor, reason=reason, ticket_id=ticket)
        storage = self.storage_metrics(node, actor=actor, reason=reason, ticket_id=ticket)
        cluster = self.cluster(node, actor=actor, reason=reason, ticket_id=ticket)

        runtime_data = runtime.get("data") if isinstance(runtime.get("data"), dict) else {}
        telemetry = runtime_data.get("Telemetry") if isinstance(runtime_data.get("Telemetry"), dict) else runtime_data.get("telemetry")
        telemetry = telemetry if isinstance(telemetry, dict) else {}

        cpu = self._safe_num(telemetry.get("CpuUsagePercent") or telemetry.get("cpu") or telemetry.get("CPU"), -1)
        mem = self._safe_num(telemetry.get("MemoryUsageMb") or telemetry.get("memoryMb") or telemetry.get("memory"), -1)
        disk = self._safe_num(telemetry.get("DiskUsagePercent") or telemetry.get("diskUsagePercent") or telemetry.get("disk"), -1)
        qps = self._safe_num(telemetry.get("Qps") or telemetry.get("qps"), -1)
        p99 = self._safe_num(telemetry.get("P99Ms") or telemetry.get("p99Ms"), -1)

        sid = str(node.get("server_id") or "").strip()
        node_state = self._pick_server_state(cluster, sid)
        ready_ok = bool(ready.get("success"))
        health_ok = bool(health.get("success"))

        status = "ONLINE"
        if not health_ok:
            status = "OFFLINE"
        elif not ready_ok:
            status = "DEGRADED"
        elif node_state in ("OFFLINE", "MAINTENANCE"):
            status = node_state

        return {
            "id": node.get("id"),
            "name": node.get("name"),
            "server_id": sid,
            "project_id": node.get("project_id"),
            "env": node.get("env"),
            "channel": node.get("channel"),
            "owner": node.get("owner") or "",
            "base_url": node.get("base_url"),
            "ops_base_url": node.get("ops_base_url"),
            "status": status,
            "health_ok": health_ok,
            "ready_ok": ready_ok,
            "qps": (None if qps < 0 else qps),
            "p99_ms": (None if p99 < 0 else p99),
            "cpu": (None if cpu < 0 else cpu),
            "memory_mb": (None if mem < 0 else mem),
            "disk_percent": (None if disk < 0 else disk),
            "last_heartbeat": datetime.utcnow().isoformat() + "Z",
            "recent_change": "-",
            "raw": {
                "health": health,
                "ready": ready,
                "runtime": runtime,
                "storage": storage,
                "cluster": cluster,
            },
        }

    def execute_platform_action(
        self,
        node: Dict[str, Any],
        *,
        action_type: str,
        target: str,
        payload: Dict[str, Any],
        actor: str,
        reason: str,
        ticket_id: str,
        dry_run: bool,
    ) -> Dict[str, Any]:
        act = str(action_type or "").strip().lower()
        target_value = str(target or "").strip()
        p = payload if isinstance(payload, dict) else {}

        if act == "health_check":
            return self.health(node, actor=actor, reason=reason, ticket_id=ticket_id)
        if act == "ready_check":
            return self.ready(node, actor=actor, reason=reason, ticket_id=ticket_id)
        if act == "status":
            return self.runtime_snapshot(node, actor=actor, reason=reason, ticket_id=ticket_id)
        if act == "metrics_snapshot":
            runtime = self.runtime_snapshot(node, actor=actor, reason=reason, ticket_id=ticket_id)
            storage = self.storage_metrics(node, actor=actor, reason=reason, ticket_id=ticket_id)
            return {
                "success": bool(runtime.get("success")) and bool(storage.get("success")),
                "status": 200,
                "message": "metrics snapshot ready",
                "trace_id": "",
                "data": {"runtime": runtime.get("data"), "storage": storage.get("data")},
            }
        if act == "smoke_test":
            return self.execute_action(
                node,
                action_type="smoke_test",
                domain="lifecycle",
                target=target_value,
                payload=p,
                actor=actor,
                reason=reason,
                ticket_id=ticket_id,
                dry_run=dry_run,
            )
        if act == "stress_test":
            return self.execute_action(
                node,
                action_type="stress_test",
                domain="performance",
                target=target_value,
                payload=p,
                actor=actor,
                reason=reason,
                ticket_id=ticket_id,
                dry_run=dry_run,
            )
        if act == "db_migration":
            return self.execute_action(
                node,
                action_type="db_migration",
                domain="dataops",
                target=target_value,
                payload=p,
                actor=actor,
                reason=reason,
                ticket_id=ticket_id,
                dry_run=dry_run,
            )
        if act == "log_tail":
            return {
                "success": True,
                "status": 200,
                "message": "log-tail placeholder: connect centralized log backend in next stage",
                "trace_id": "",
                "data": {
                    "target": target_value,
                    "hint": "请接入日志系统（ELK/Loki）后替换为真实 tail。",
                },
            }

        if act in ("start", "stop", "start_all", "stop_all", "restart"):
            if act == "start_all":
                target_value = "*"
                state_value = "Online"
            elif act == "stop_all":
                target_value = "*"
                state_value = "Offline"
            elif act == "start":
                state_value = "Online"
            elif act == "stop":
                state_value = "Offline"
            else:
                state_value = "Offline"

            if act == "restart":
                if dry_run:
                    return self.execute_action(
                        node,
                        action_type="server_state",
                        domain="lifecycle",
                        target=target_value,
                        payload={"state": "Offline"},
                        actor=actor,
                        reason=reason,
                        ticket_id=ticket_id,
                        dry_run=True,
                    )
                stop_res = self.execute_action(
                    node,
                    action_type="server_state",
                    domain="lifecycle",
                    target=target_value,
                    payload={"state": "Offline"},
                    actor=actor,
                    reason=reason + " [restart:stop]",
                    ticket_id=ticket_id,
                    dry_run=False,
                )
                if not stop_res.get("success"):
                    return stop_res
                start_res = self.execute_action(
                    node,
                    action_type="server_state",
                    domain="lifecycle",
                    target=target_value,
                    payload={"state": "Online"},
                    actor=actor,
                    reason=reason + " [restart:start]",
                    ticket_id=ticket_id,
                    dry_run=False,
                )
                start_res["restart_chain"] = {"stop": stop_res}
                return start_res

            return self.execute_action(
                node,
                action_type="server_state",
                domain="lifecycle",
                target=target_value,
                payload={"state": state_value},
                actor=actor,
                reason=reason,
                ticket_id=ticket_id,
                dry_run=dry_run,
            )

        if act == "maintenance":
            return self.execute_action(
                node,
                action_type="maintenance",
                domain="ops",
                target=target_value,
                payload={"message": str(p.get("message") or "")},
                actor=actor,
                reason=reason,
                ticket_id=ticket_id,
                dry_run=dry_run,
            )

        if act == "feature_toggle":
            enabled = bool(p.get("enabled", True))
            return self.execute_action(
                node,
                action_type="feature_toggle",
                domain="feature",
                target=target_value,
                payload={"enabled": enabled},
                actor=actor,
                reason=reason,
                ticket_id=ticket_id,
                dry_run=dry_run,
            )

        if act == "whitelist":
            enabled = bool(p.get("enabled", True))
            return self.execute_action(
                node,
                action_type="whitelist",
                domain="liveops",
                target=target_value,
                payload={"enabled": enabled},
                actor=actor,
                reason=reason,
                ticket_id=ticket_id,
                dry_run=dry_run,
            )

        if act == "mute_chat":
            enabled = bool(p.get("enabled", True))
            return self.execute_action(
                node,
                action_type="mute_chat",
                domain="liveops",
                target=target_value,
                payload={"enabled": enabled},
                actor=actor,
                reason=reason,
                ticket_id=ticket_id,
                dry_run=dry_run,
            )

        if act in ("drain_node", "isolate_node", "recover_node"):
            msg = "drain mode" if act == "drain_node" else ("isolate mode" if act == "isolate_node" else "recover mode")
            return self.execute_action(
                node,
                action_type="maintenance",
                domain="ops",
                target=target_value,
                payload={"message": f"{msg} | {reason}"},
                actor=actor,
                reason=reason,
                ticket_id=ticket_id,
                dry_run=dry_run,
            )

        if act == "kick_session":
            return self.execute_action(
                node,
                action_type="kick_session",
                domain="incident",
                target=target_value,
                payload={},
                actor=actor,
                reason=reason,
                ticket_id=ticket_id,
                dry_run=dry_run,
            )

        if act == "retry_task":
            return self.execute_action(
                node,
                action_type="retry_task",
                domain="incident",
                target=target_value,
                payload={},
                actor=actor,
                reason=reason,
                ticket_id=ticket_id,
                dry_run=dry_run,
            )

        return {
            "success": False,
            "status": 400,
            "message": f"unsupported action_type: {action_type}",
            "trace_id": "",
            "data": {},
        }

    def inspect_risk(self, action_type: str) -> Tuple[str, bool, str]:
        act = str(action_type or "").strip().lower()
        high = {"start", "stop", "restart", "start_all", "stop_all", "kick_session", "drain_node", "isolate_node", "recover_node", "stress_test", "db_migration"}
        low = {"maintenance", "feature_toggle", "retry_task", "whitelist", "mute_chat", "smoke_test"}
        readonly = {"health_check", "ready_check", "status", "log_tail", "metrics_snapshot"}
        if act in high:
            return "high", True, "lifecycle"
        if act in low:
            return "medium", False, "ops"
        if act in readonly:
            return "low", False, "observability"
        return "medium", False, "ops"

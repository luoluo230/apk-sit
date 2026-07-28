# -*- coding: utf-8 -*-
"""Action execution center service layer."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from services.ops import deps as ops_helpers


def list_catalog() -> List[Dict[str, Any]]:
    rows = [
        {"groupId": "observe", "group": "Observe", "value": "health_check", "label": "健康检查", "risk": "low"},
        {"groupId": "observe", "group": "Observe", "value": "ready_check", "label": "就绪检查", "risk": "low"},
        {"groupId": "observe", "group": "Observe", "value": "status", "label": "运行快照", "risk": "low"},
        {"groupId": "observe", "group": "Observe", "value": "runtime_snapshot", "label": "运行态详情", "risk": "low"},
        {"groupId": "lifecycle", "group": "Lifecycle", "value": "start", "label": "启动节点", "risk": "high"},
        {"groupId": "lifecycle", "group": "Lifecycle", "value": "stop", "label": "停止节点", "risk": "high"},
        {"groupId": "lifecycle", "group": "Lifecycle", "value": "restart", "label": "重启节点", "risk": "high"},
        {"groupId": "special", "group": "Special Job", "value": "smoke_test", "label": "冒烟测试", "risk": "medium"},
        {"groupId": "special", "group": "Special Job", "value": "stress_test", "label": "压力测试", "risk": "high"},
    ]
    return rows


def list_targets(project_id: str, env_key: str = "production") -> Dict[str, Any]:
    pid = ops_helpers._resolve_ops_project_id(project_id)
    env = ops_helpers._resolve_ops_env_key(env_key)
    targets = ops_helpers._list_action_targets(pid, env)
    return {"ok": True, "project_id": pid, "env_key": env, "count": len(targets), "targets": targets}


def validate_request(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    node, err = ops_helpers._action_target_or_400(payload)
    if err:
        return {"ok": False, "error": "invalid_target"}, 400
    validation = ops_helpers._validate_ops_request(payload, node)
    if not validation.get("ok"):
        status = 400
        body = {
            "ok": False,
            "error": "validation_failed",
            "missing": validation.get("missing") or [],
            "risk": validation.get("risk"),
            "require_approval": validation.get("require_approval"),
        }
        if validation.get("unsupported"):
            body["error"] = "unsupported_action"
            body["supported_actions"] = validation.get("agent_supported_actions") or []
        return body, status
    return {
        "ok": True,
        "message": "预检通过",
        "risk": validation.get("risk"),
        "require_approval": validation.get("require_approval"),
        "approved": validation.get("approved"),
    }, 200


def execute_request(payload: Dict[str, Any], project_id: str = "") -> Tuple[Dict[str, Any], int]:
    node, err = ops_helpers._action_target_or_400(payload)
    if err:
        return {"ok": False, "error": "invalid_target"}, 400
    pid = str(project_id or payload.get("project_id") or node.get("project_id") or "").strip()
    freeze = ops_helpers._change_freeze_for_project(pid)
    validation = ops_helpers._validate_ops_request(payload, node)
    if not validation.get("ok"):
        return {"ok": False, "error": "validation_failed", "validation": validation}, 400
    if freeze.get("active") and validation.get("require_approval") and not validation.get("dry_run"):
        return {
            "ok": False,
            "error": "change_freeze_active",
            "freeze_reason": str(freeze.get("reason") or ""),
        }, 423
    if validation.get("require_approval") and (not validation.get("dry_run")) and (not validation.get("approved")):
        return {"ok": False, "error": "approval_required"}, 412
    result = ops_helpers._execute_ops_action(payload, node, validation)
    return result, 200 if result.get("ok") else 502


def get_trace(trace_id: str) -> Dict[str, Any]:
    item = ops_helpers._find_trace(trace_id)
    if not item:
        return {"ok": False, "error": "trace_not_found"}
    return {"ok": True, "trace": item}

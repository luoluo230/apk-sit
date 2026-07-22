# -*- coding: utf-8 -*-
"""Agent policy helpers (extracted from ops.helpers)."""

from __future__ import annotations

from typing import Any, Dict

from services.ops.constants import OPS_AGENT_POLICY_KEY
from services.ops.storage import _load_json_config, _save_json_config


def _default_agent_policy() -> Dict[str, Any]:
    return {
        "mtls_required": False,
        "lease_timeout_sec": 60,
        "max_retries": 2,
        "default_node_concurrency": 1,
        "agent_online_fresh_sec": 120,
        "rollout": {
            "enabled": False,
            "desired_version": "",
            "channel": "stable",
            "percent": 0,
            "allow_ids": [],
        },
    }


def _load_agent_policy() -> Dict[str, Any]:
    raw = _load_json_config(OPS_AGENT_POLICY_KEY, {})
    out = _default_agent_policy()
    if isinstance(raw, dict):
        for k in ("mtls_required", "lease_timeout_sec", "max_retries", "default_node_concurrency", "agent_online_fresh_sec"):
            if k in raw:
                out[k] = raw[k]
        if isinstance(raw.get("rollout"), dict):
            merged_rollout = out["rollout"]
            merged_rollout.update(raw.get("rollout"))
            out["rollout"] = merged_rollout
    return out


def _save_agent_policy(policy: Dict[str, Any]) -> None:
    out = _default_agent_policy()
    if isinstance(policy, dict):
        for k in ("mtls_required", "lease_timeout_sec", "max_retries", "default_node_concurrency", "agent_online_fresh_sec"):
            if k in policy:
                out[k] = policy.get(k)
        if isinstance(policy.get("rollout"), dict):
            merged_rollout = out["rollout"]
            merged_rollout.update(policy.get("rollout"))
            out["rollout"] = merged_rollout
    _save_json_config(OPS_AGENT_POLICY_KEY, out, description="Ops Agent 策略配置")

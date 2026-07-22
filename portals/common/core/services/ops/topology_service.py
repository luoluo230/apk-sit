# -*- coding: utf-8 -*-
"""Topology registry helpers (extracted from ops.helpers)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from services.ops.constants import OPS_TOPOLOGY_CONTENTS_KEY, OPS_TOPOLOGY_REGISTRY_KEY
from services.ops.storage import _load_json_config, _save_json_config


def _normalize_env_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    alias = {
        "dev": "development",
        "develop": "development",
        "development": "development",
        "test": "testing",
        "testing": "testing",
        "qa": "testing",
        "staging": "staging",
        "pre": "staging",
        "preprod": "staging",
        "pre-release": "staging",
        "prod": "production",
        "production": "production",
        "online": "production",
    }
    return alias.get(text, text or "production")


def _default_env_options() -> List[Dict[str, str]]:
    return [
        {"env_key": "development", "label": "开发环境"},
        {"env_key": "testing", "label": "测试环境"},
        {"env_key": "staging", "label": "预发环境"},
        {"env_key": "production", "label": "生产环境"},
    ]


def _env_label(env_key: str) -> str:
    key = _normalize_env_key(env_key)
    for item in _default_env_options():
        if str(item.get("env_key") or "") == key:
            return str(item.get("label") or key)
    return key or "生产环境"


def _load_topology_registry() -> List[Dict[str, Any]]:
    raw = _load_json_config(OPS_TOPOLOGY_REGISTRY_KEY, [])
    return raw if isinstance(raw, list) else []


def _save_topology_registry(rows: List[Dict[str, Any]]) -> None:
    items = rows if isinstance(rows, list) else []
    _save_json_config(OPS_TOPOLOGY_REGISTRY_KEY, items, description="Ops 拓扑注册表")


def _load_topology_contents() -> Dict[str, Any]:
    raw = _load_json_config(OPS_TOPOLOGY_CONTENTS_KEY, {})
    return raw if isinstance(raw, dict) else {}


def _save_topology_contents(data: Dict[str, Any]) -> None:
    payload = data if isinstance(data, dict) else {}
    _save_json_config(OPS_TOPOLOGY_CONTENTS_KEY, payload, description="Ops 拓扑内容分片")


def _scope_binding_key(topology_id: str, node_id: str) -> str:
    return f"{str(topology_id or '').strip()}::{str(node_id or '').strip()}"


def _topology_content_counts(topology_id: str) -> Tuple[int, int]:
    tid = str(topology_id or "").strip()
    if not tid:
        return 0, 0
    contents = _load_topology_contents()
    topo = contents.get(tid) if isinstance(contents.get(tid), dict) else {}
    nodes = topo.get("nodes") if isinstance(topo.get("nodes"), list) else []
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    return len(nodes), len(edges)

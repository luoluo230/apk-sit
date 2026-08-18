# -*- coding: utf-8 -*-
"""Four-way split: topology server, BaaS server, topology client network, BaaS client network."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Set

from models.data import projects_db

# ---------------------------------------------------------------------------
# Module catalog (deploy / import boundaries)
# ---------------------------------------------------------------------------

FRAMEWORK_MODULES: Dict[str, Dict[str, Any]] = {
    "topology_server": {
        "label": "拓扑服务器框架",
        "kind": "server",
        "server_mode": "topology",
        "description": "Agent / Runtime / 拓扑绑定 / runtime-bootstrap / Server Release",
        "portal_blueprints": ["project_ops"],
        "bootstrap_path": "/api/public/runtime-bootstrap",
        "env_flag": "topology",
    },
    "casual_baas_server": {
        "label": "轻度 BaaS 服务器框架",
        "kind": "server",
        "server_mode": "casual_baas",
        "description": "Portal 托管 REST BaaS + baas-bootstrap",
        "portal_blueprints": ["baas_public"],
        "bootstrap_path": "/api/public/baas-bootstrap",
        "env_flag": "baas",
    },
    "topology_client": {
        "label": "拓扑客户端网络模块",
        "kind": "client",
        "pairs_with": "topology_server",
        "package": "packages/client_network/topology",
        "bootstrap_path": "/api/public/runtime-bootstrap",
        "network_contract": "docs/client_bootstrap_contract.md",
        "unity_assets": [
            "Assets/Src/HotUpdate/Framework/Bootstrap/RuntimeBootstrapService.cs",
            "Assets/Resources/Protocol/ProtocolNetworkSettings.asset",
        ],
        "portal_editors": [
            "ops_topology_workbench",
            "topology_binding_drawer",
            "project_version_build_config.client_policy",
            "project_version_release_editor.server",
            "project_delivery.topology",
        ],
        "env_flag": "topology",
    },
    "baas_client": {
        "label": "BaaS 客户端网络模块",
        "kind": "client",
        "pairs_with": "casual_baas_server",
        "package": "packages/client_network/baas",
        "bootstrap_path": "/api/public/baas-bootstrap",
        "network_contract": "docs/client_bootstrap_contract_baas.md",
        "unity_assets": [
            "Assets/Src/HotUpdate/Framework/Bootstrap/BaasBootstrapService.cs",
            "Assets/Resources/Protocol/BaasNetworkSettings.asset",
        ],
        "portal_editors": [
            "casual_services_console",
            "project_settings.architecture",
        ],
        "env_flag": "baas",
    },
}

_ALL_FLAGS = {"topology", "baas", "all", "topology_server", "casual_baas_server", "topology_client", "baas_client"}


def _parse_enabled_flags() -> Set[str]:
    raw = str(os.getenv("PORTAL_SERVER_FRAMEWORKS") or "all").strip().lower()
    if not raw or raw == "all":
        return {"topology", "baas"}
    parts = {p.strip() for p in raw.replace(";", ",").split(",") if p.strip()}
    out: Set[str] = set()
    for part in parts:
        if part == "all":
            return {"topology", "baas"}
        if part in ("topology", "topology_server", "topology_client"):
            out.add("topology")
        elif part in ("baas", "casual_baas", "casual_baas_server", "baas_client"):
            out.add("baas")
        elif part in _ALL_FLAGS:
            if "topology" in part:
                out.add("topology")
            if "baas" in part:
                out.add("baas")
    return out or {"topology", "baas"}


def enabled_modules() -> Set[str]:
    """Return enabled env flags: {'topology', 'baas'}."""
    return _parse_enabled_flags()


def is_module_enabled(module_key: str) -> bool:
    mod = FRAMEWORK_MODULES.get(module_key) or {}
    flag = str(mod.get("env_flag") or "").strip()
    if not flag:
        return True
    return flag in enabled_modules()


def server_mode_for_project(project_id: str) -> str:
    proj = projects_db.get(project_id) or {}
    mode = str(proj.get("server_mode") or "topology").strip().lower()
    return mode if mode in ("topology", "casual_baas") else "topology"


def is_casual_baas_project(project_id: str) -> bool:
    return server_mode_for_project(project_id) == "casual_baas"


def is_topology_project(project_id: str) -> bool:
    return server_mode_for_project(project_id) == "topology"


def client_module_for_project(project_id: str) -> str:
    return "baas_client" if is_casual_baas_project(project_id) else "topology_client"


def server_module_for_project(project_id: str) -> str:
    return "casual_baas_server" if is_casual_baas_project(project_id) else "topology_server"


def module_manifest(module_key: str) -> Dict[str, Any]:
    base = dict(FRAMEWORK_MODULES.get(module_key) or {})
    base["key"] = module_key
    base["enabled"] = is_module_enabled(module_key)
    return base


def list_modules(*, kind: str = "") -> List[Dict[str, Any]]:
    rows = []
    for key in FRAMEWORK_MODULES:
        mod = FRAMEWORK_MODULES[key]
        if kind and mod.get("kind") != kind:
            continue
        rows.append(module_manifest(key))
    return rows


def is_topology_enabled() -> bool:
    return "topology" in enabled_modules()


def is_baas_enabled() -> bool:
    return "baas" in enabled_modules()


def register_server_frameworks(app, *, csrf=None) -> None:
    """Register optional server blueprints based on PORTAL_SERVER_FRAMEWORKS."""
    flags = enabled_modules()
    if "topology" in flags:
        from routes.ops import bp as project_ops_bp

        app.register_blueprint(project_ops_bp)
        if csrf is not None:
            csrf.exempt(project_ops_bp)
    if "baas" in flags:
        from routes.baas.public_api import baas_public_bp

        app.register_blueprint(baas_public_bp)
        if csrf is not None:
            csrf.exempt(baas_public_bp)

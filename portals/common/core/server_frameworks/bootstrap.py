# -*- coding: utf-8 -*-
"""Unified client bootstrap router (topology vs BaaS)."""

from __future__ import annotations

from flask import jsonify, request

from data.platforms import is_valid_platform_id
from models.data import projects_db
from server_frameworks.credentials import resolve_project_id
from server_frameworks.registry import (
    client_module_for_project,
    is_module_enabled,
    module_manifest,
    server_module_for_project,
)


def _resolve_project_id(game_id: str, game_key: str) -> str:
    return resolve_project_id(game_id=game_id, game_key=game_key)


def client_bootstrap():
    """Single entry: dispatch to runtime-bootstrap or baas-bootstrap by project server_mode."""
    game_id = str(request.args.get("game_id") or "").strip()
    game_key = str(request.args.get("game_key") or "").strip()
    project_id = str(request.args.get("project_id") or "").strip()
    if not project_id:
        project_id = _resolve_project_id(game_id, game_key)
    if not project_id or project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目凭证无效"}), 401

    server_mod = server_module_for_project(project_id)
    client_mod = client_module_for_project(project_id)

    if server_mod == "casual_baas_server":
        if not is_module_enabled("casual_baas_server"):
            return jsonify({"ok": False, "error": "BaaS 服务器框架未部署"}), 503
        from services.baas.bootstrap_service import build_baas_bootstrap

        try:
            payload = build_baas_bootstrap(
                project_id=project_id,
                game_id=game_id,
                game_key=game_key,
                env_key=str(request.args.get("env_key") or request.args.get("env") or "development"),
                service_id=str(request.args.get("service_id") or ""),
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        payload["framework"] = "casual_baas"
        payload["client_module"] = client_mod
        payload["bootstrap_kind"] = "baas"
        return jsonify(payload)

    if not is_module_enabled("topology_server"):
        return jsonify({"ok": False, "error": "拓扑服务器框架未部署"}), 503

    env_key = str(request.args.get("env_key") or request.args.get("environment") or "").strip()
    channel = str(request.args.get("channel") or request.args.get("channel_id") or "").strip()
    platform = str(request.args.get("platform") or "android").strip().lower()
    if not game_id or not game_key or not env_key or not channel:
        return jsonify({"ok": False, "error": "game_id、game_key、env_key、channel 必填"}), 400
    if not is_valid_platform_id(platform):
        return jsonify({"ok": False, "error": "platform 无效"}), 400

    from routes.delivery.public_api import runtime_bootstrap

    response = runtime_bootstrap()
    if hasattr(response, "get_json"):
        body = response.get_json(silent=True) or {}
        if isinstance(body, dict):
            body["framework"] = "topology"
            body["client_module"] = client_mod
            body["bootstrap_kind"] = "runtime"
            return jsonify(body), response.status_code
    return response


def client_network_module():
    """Return which client network package to import for a project."""
    game_id = str(request.args.get("game_id") or "").strip()
    game_key = str(request.args.get("game_key") or "").strip()
    project_id = str(request.args.get("project_id") or "").strip()
    if not project_id:
        project_id = _resolve_project_id(game_id, game_key)
    if not project_id or project_id not in projects_db:
        return jsonify({"ok": False, "error": "项目凭证无效"}), 401

    client_key = client_module_for_project(project_id)
    server_key = server_module_for_project(project_id)
    client = module_manifest(client_key)
    server = module_manifest(server_key)
    return jsonify({
        "ok": True,
        "project_id": project_id,
        "server_mode": server.get("server_mode") or "topology",
        "server_module": server,
        "client_module": client,
        "bootstrap_path": client.get("bootstrap_path"),
        "package_path": client.get("package"),
        "unity_assets": client.get("unity_assets") or [],
    })


def register_client_bootstrap_routes(target_bp) -> None:
    target_bp.add_url_rule(
        "/api/public/client-bootstrap",
        endpoint="delivery_client_bootstrap",
        view_func=client_bootstrap,
        methods=["GET"],
    )
    target_bp.add_url_rule(
        "/api/public/baas-bootstrap",
        endpoint="baas_client_bootstrap_legacy",
        view_func=client_bootstrap,
        methods=["GET"],
    )
    target_bp.add_url_rule(
        "/api/public/client-network-module",
        endpoint="delivery_client_network_module",
        view_func=client_network_module,
        methods=["GET"],
    )

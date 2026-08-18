# -*- coding: utf-8 -*-
"""Public delivery APIs: runtime-bootstrap and release-config."""

from __future__ import annotations

from flask import jsonify, make_response, request

from data.platforms import is_valid_platform_id
from models.data import get_channel_by_id, projects_db
from services.release.release_context import resolve_release_context
from services.release.scope_ids import build_scope_id, project_slug, resolve_channel_id
from services.release.storage import find_scope
def baas_bootstrap():
    """Public bootstrap for casual BaaS clients."""
    from server_frameworks.registry import is_module_enabled

    if not is_module_enabled("casual_baas_server"):
        return jsonify({"ok": False, "error": "BaaS 服务器框架未部署"}), 503
    from services.baas.bootstrap_service import build_baas_bootstrap

    game_id = str(request.args.get("game_id") or "").strip()
    game_key = str(request.args.get("game_key") or "").strip()
    env_key = str(request.args.get("env_key") or request.args.get("env") or "development").strip()
    service_id = str(request.args.get("service_id") or "").strip()
    try:
        payload = build_baas_bootstrap(
            game_id=game_id,
            game_key=game_key,
            env_key=env_key,
            service_id=service_id,
        )
        return jsonify(payload)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def release_config():
    """Public release context: scope, network profile preview, bootstrap paths."""
    game_id = str(request.args.get("game_id") or "").strip()
    game_key = str(request.args.get("game_key") or "").strip()
    env_key = str(request.args.get("env_key") or request.args.get("environment") or "").strip()
    channel = str(request.args.get("channel") or request.args.get("channel_id") or "").strip()
    platform = str(request.args.get("platform") or "android").strip().lower()
    version_name = str(request.args.get("version_name") or "").strip()

    if not game_id or not game_key or not env_key or not channel:
        return jsonify({"ok": False, "error": "game_id、game_key、env_key、channel 必填"}), 400
    if not is_valid_platform_id(platform):
        return jsonify({"ok": False, "error": "platform 无效"}), 400

    project_id = next((
        pid for pid, project in projects_db.items()
        if str(project.get("game_id") or "") == game_id and str(project.get("game_key") or "") == game_key
    ), "")
    if not project_id:
        return jsonify({"ok": False, "error": "项目凭证无效"}), 401

    resolved_channel_id = resolve_channel_id(project_id, channel)
    ctx = resolve_release_context(
        project_id,
        env_key,
        resolved_channel_id,
        auto_create_scope=False,
    )
    scope_id = str(ctx.get("scope_id") or build_scope_id(project_slug(project_id), env_key, resolved_channel_id, platform))
    scope = find_scope(scope_id) or ctx.get("scope") or {}
    prefer_bootstrap = "/api/public/runtime-bootstrap"

    return jsonify({
        "ok": True,
        "project_id": project_id,
        "scope_id": scope_id,
        "env_key": ctx.get("env_key"),
        "channel_id": ctx.get("channel_id"),
        "platform": platform,
        "version_name": version_name,
        "network_profile": ctx.get("network_profile") or {},
        "profile_source": ctx.get("profile_source") or "",
        "topology_binding_source": ctx.get("topology_binding_source") or "",
        "active_bundle_id": ctx.get("active_bundle_id") or "",
        "bootstrap_paths": ctx.get("bootstrap_paths") or {},
        "server_snapshot": ctx.get("server_snapshot") or {},
        "scope": scope,
        "prefer_runtime_bootstrap": prefer_bootstrap,
    })


def _bootstrap_response(project_id: str, channel_name: str, bundle: dict, rollout_meta: dict):
    client = bundle.get("client") if isinstance(bundle.get("client"), dict) else {}
    server = bundle.get("server") if isinstance(bundle.get("server"), dict) else {}
    bootstrap = dict(client)
    if not str(bootstrap.get("max_client_version") or "").strip():
        bootstrap["max_client_version"] = str(
            bootstrap.get("min_client_version") or bootstrap.get("version_name") or ""
        ).strip()
    bootstrap["rollout_percentage"] = int(rollout_meta.get("rollout_percentage") or 100)
    bootstrap["rollout_bucket"] = int(rollout_meta.get("rollout_bucket") or 0)
    payload = {
        "ok": True,
        "project_id": project_id,
        "channel": channel_name,
        "scope_id": bundle.get("scope_id"),
        "active_bundle_id": bundle.get("bundle_id"),
        "release_order_id": bundle.get("release_order_id"),
        "topology_id": server.get("topology_id"),
        "runtime_run_id": server.get("runtime_run_id"),
        "network_profile": server.get("network_profile_snapshot") or {},
        "server_snapshot": server,
        "bootstrap": bootstrap,
        "rollout_percentage": bootstrap["rollout_percentage"],
        "rollout_bucket": bootstrap["rollout_bucket"],
    }
    if rollout_meta.get("gray_miss"):
        payload["gray_rollout_miss"] = True
        payload["superseded_bundle_id"] = str(rollout_meta.get("superseded_bundle_id") or "")
        if rollout_meta.get("target_bundle_id"):
            payload["gray_target_bundle_id"] = str(rollout_meta.get("target_bundle_id") or "")
    return payload


def runtime_bootstrap():
    from server_frameworks.registry import is_module_enabled

    if not is_module_enabled("topology_server"):
        return jsonify({"ok": False, "error": "拓扑服务器框架未部署"}), 503
    game_id = str(request.args.get("game_id") or "").strip()
    game_key = str(request.args.get("game_key") or "").strip()
    env_key = str(request.args.get("env_key") or "").strip()
    channel = str(request.args.get("channel") or "").strip()
    platform = str(request.args.get("platform") or "").strip().lower()
    device_id = str(request.args.get("device_id") or "").strip()
    user_id = str(request.args.get("user_id") or "").strip()
    region = str(request.args.get("region") or request.args.get("client_region") or "").strip()
    if not game_id or not game_key or not env_key or not channel or not is_valid_platform_id(platform):
        return jsonify({"ok": False, "error": "game_id、game_key、env_key、channel、platform 必填"}), 400
    project_id = next((
        pid for pid, project in projects_db.items()
        if str(project.get("game_id") or "") == game_id and str(project.get("game_key") or "") == game_key
    ), "")
    if not project_id:
        return jsonify({"ok": False, "error": "项目凭证无效"}), 401
    resolved_channel_id = resolve_channel_id(project_id, channel)
    channel_row = get_channel_by_id(resolved_channel_id) or {}
    channel_name = str(channel_row.get("apk_subdir") or channel_row.get("name") or channel).strip()
    scope_id = build_scope_id(project_slug(project_id), env_key, resolved_channel_id, platform)
    scope = find_scope(scope_id)
    if not scope:
        legacy_scope_id = build_scope_id(project_slug(project_id), env_key, resolved_channel_id)
        if legacy_scope_id != scope_id:
            scope = find_scope(legacy_scope_id)
    if not scope:
        return jsonify({"ok": False, "error": "发布作用域不存在"}), 404
    from services.release.bundle_service import find_active_bundle

    bundle = find_active_bundle(scope_id, platform=platform) or find_active_bundle(
        str(scope.get("scope_id") or ""), platform=platform
    )
    if not bundle:
        return jsonify({"ok": False, "error": "当前作用域没有已发布 Bundle"}), 404
    from services.release.bundle_service import resolve_gray_rollout_bundle

    rollout = resolve_gray_rollout_bundle(bundle, device_id=device_id, user_id=user_id, region=region)
    effective = rollout.get("bundle") if isinstance(rollout.get("bundle"), dict) else {}
    if rollout.get("gray_miss") and not effective:
        return make_response(
            jsonify(
                {
                    "ok": False,
                    "error": "gray_rollout_miss",
                    "rollout_percentage": rollout.get("rollout_percentage"),
                    "rollout_bucket": rollout.get("rollout_bucket"),
                    "superseded_bundle_id": str(bundle.get("supersedes_bundle_id") or ""),
                    "target_bundle_id": str(bundle.get("bundle_id") or ""),
                }
            ),
            204,
        )
    if not effective:
        return jsonify({"ok": False, "error": "当前作用域没有已发布 Bundle"}), 404
    client = effective.get("client") if isinstance(effective.get("client"), dict) else {}
    if str(client.get("platform") or "").lower() != platform:
        return jsonify({"ok": False, "error": "已发布 Bundle 平台不匹配"}), 404
    return jsonify(_bootstrap_response(project_id, channel_name, effective, rollout))


def register_public_routes(target_bp):
    """Attach public routes to project_delivery blueprint."""
    from server_frameworks.bootstrap import register_client_bootstrap_routes

    register_client_bootstrap_routes(target_bp)
    target_bp.add_url_rule(
        "/api/public/baas-bootstrap",
        endpoint="delivery_baas_bootstrap",
        view_func=baas_bootstrap,
        methods=["GET"],
    )
    target_bp.add_url_rule(
        "/api/public/release-config",
        endpoint="delivery_release_config",
        view_func=release_config,
        methods=["GET"],
    )
    target_bp.add_url_rule(
        "/api/public/runtime-bootstrap",
        endpoint="delivery_runtime_bootstrap",
        view_func=runtime_bootstrap,
        methods=["GET"],
    )

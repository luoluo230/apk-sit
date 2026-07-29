# -*- coding: utf-8 -*-
"""Admin API for version-group platform config (kept separate from infra nodes)."""

from __future__ import annotations

from flask import jsonify, request, session

from services.authz import admin_required


def register_routes(bp):
    @bp.route("/api/admin/projects/<project_id>/version-groups/platform-config", methods=["GET", "PUT"])
    @admin_required("projects")
    def api_version_group_platform_config(project_id):
        from services.admin import version_service as vs
        from services.build.platform_signing_service import (
            assess_ios_signing_setup,
            normalize_ios_signing,
            normalize_wx_minigame_config,
            sanitize_ios_signing_for_api,
        )

        if request.method == "GET":
            data = request.args
            meta = vs.get_version_group_meta(
                project_id,
                str(data.get("version_name") or ""),
                str(data.get("env_key") or ""),
                str(data.get("platform") or "android"),
            )
            ios_signing = sanitize_ios_signing_for_api(meta.get("ios_signing"))
            release_env = str(data.get("release_environment") or data.get("env_key") or "")
            assessment = assess_ios_signing_setup(
                ios_signing,
                project_id=project_id,
                release_environment=release_env,
            ) if str(data.get("platform") or "").strip().lower() in ("ios", "iphone", "iphoneos") else None
            return jsonify({
                "ok": True,
                "ios_signing": ios_signing,
                "wx_minigame": normalize_wx_minigame_config(meta.get("wx_minigame")),
                "unity_version": str(meta.get("unity_version") or ""),
                "ios_signing_assessment": assessment,
            })
        body = request.get_json(silent=True) or {}
        try:
            updated = vs.update_version_group_platform_config(
                project_id,
                str(body.get("version_name") or ""),
                str(body.get("env_key") or ""),
                str(body.get("platform") or "android"),
                {
                    "ios_signing": body.get("ios_signing"),
                    "wx_minigame": body.get("wx_minigame"),
                    "unity_version": body.get("unity_version"),
                },
                actor=session.get("user") or "admin",
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        ios_signing = sanitize_ios_signing_for_api(updated.get("ios_signing"))
        return jsonify({"ok": True, "meta": updated, "ios_signing": ios_signing})

    @bp.route("/api/admin/projects/<project_id>/version-groups/ios-signing/validate", methods=["POST"])
    @admin_required("projects")
    def api_ios_signing_validate(project_id):
        from services.admin import version_service as vs
        from services.build.platform_signing_service import assess_ios_signing_setup, normalize_ios_signing

        body = request.get_json(silent=True) or {}
        version_name = str(body.get("version_name") or "").strip()
        env_key = str(body.get("env_key") or "").strip()
        platform = str(body.get("platform") or "ios").strip()
        signing_raw = body.get("ios_signing")
        if not isinstance(signing_raw, dict) and version_name:
            meta = vs.get_version_group_meta(project_id, version_name, env_key, platform)
            signing_raw = meta.get("ios_signing")
        signing = normalize_ios_signing(signing_raw if isinstance(signing_raw, dict) else {})
        release_env = str(body.get("release_environment") or env_key or "")
        assessment = assess_ios_signing_setup(
            signing,
            project_id=project_id,
            release_environment=release_env,
        )
        return jsonify({"ok": True, **assessment})

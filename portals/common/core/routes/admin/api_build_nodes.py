# -*- coding: utf-8
"""Admin API for version-group platform config (kept separate from infra nodes)."""

from __future__ import annotations

from flask import jsonify, request, session

from services.authz import admin_required


def register_routes(bp):
    @bp.route("/api/admin/projects/<project_id>/version-groups/platform-config", methods=["GET", "PUT"])
    @admin_required("projects")
    def api_version_group_platform_config(project_id):
        from services.admin import version_service as vs
        from services.build.platform_signing_service import normalize_ios_signing, normalize_wx_minigame_config

        if request.method == "GET":
            data = request.args
            meta = vs.get_version_group_meta(
                project_id,
                str(data.get("version_name") or ""),
                str(data.get("env_key") or ""),
                str(data.get("platform") or "android"),
            )
            return jsonify({
                "ok": True,
                "ios_signing": normalize_ios_signing(meta.get("ios_signing")),
                "wx_minigame": normalize_wx_minigame_config(meta.get("wx_minigame")),
                "unity_version": str(meta.get("unity_version") or ""),
            })
        body = request.get_json(silent=True) or {}
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
        return jsonify({"ok": True, "meta": updated})

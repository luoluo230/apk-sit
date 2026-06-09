# -*- coding: utf-8 -*-
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import log_audit
from services.authz import admin_required
import services.ops.helpers as ops_helpers
from routes.ops import bp

@bp.route("/admin/gm-classic")
@admin_required("gm_ops")
def gm_classic_page():
    try:
        content = ops_helpers._render_local_template("gm_classic_page.html")
        return ops_helpers._render_page(content, "经典 GM 模块")
    except Exception:
        return ops_helpers._render_page(
            '<section class="panel p-6"><h2 class="text-xl font-bold">经典 GM 模块</h2><p class="text-slate-600 mt-2">页面模板加载失败，请联系管理员检查模板文件。</p></section>',
            "经典 GM 模块",
        )


@bp.route("/api/gm-legacy/nodes")
@admin_required("gm_ops")
def gm_legacy_nodes_list():
    return jsonify({"ok": True, "count": len(ops_helpers._load_nodes()), "nodes": ops_helpers._load_nodes()})



@bp.route("/api/gm-legacy/nodes", methods=["POST"])
@admin_required("gm_ops")
def gm_legacy_nodes_save():
    payload = request.get_json(silent=True) or {}
    rows = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
    ops_helpers._save_nodes(rows)
    return jsonify({"ok": True, "count": len(ops_helpers._load_nodes()), "nodes": ops_helpers._load_nodes()})



@bp.route("/api/gm-classic/action", methods=["POST"])
@admin_required("gm_ops")
def gm_classic_action():
    if not ops_helpers._allow_gm_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少 GM 执行权限 (gm.classic.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip()
    if action not in GM_ACTION_PATHS:
        return jsonify({"ok": False, "error": "unsupported action"}), 400

    node, err = ops_helpers._node_or_400(payload)
    if err:
        return err

    result = ops_helpers._client.submit_form(
        base_url=str(node.get("base_url") or ""),
        username=str(node.get("username") or ""),
        password=str(node.get("password") or ""),
        path=GM_ACTION_PATHS[action],
        form=payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
    )
    return jsonify({"ok": bool(result.get("success")), "node": node.get("id"), "action": action, "result": result}), (200 if result.get("success") else 502)


# ---------------------------

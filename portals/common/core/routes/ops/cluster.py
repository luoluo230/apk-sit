# -*- coding: utf-8 -*-
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import log_audit
from services.authz import admin_required
import services.ops.helpers as ops_helpers
from routes.ops import bp

@bp.route("/api/ops-platform/cluster/sync", methods=["POST"])
@admin_required("gm_ops")
def ops_platform_cluster_sync():
    if not ops_helpers._allow_ops_execute():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维执行权限 (ops.platform.execute)"}), 403
    payload = request.get_json(silent=True) or {}
    project_id = str(payload.get("project_id") or request.args.get("project_id") or "GomeKu").strip()
    repo = ops_helpers._resolve_game_server_repo()
    cluster_path = CLUSTER_JSON_PATH
    if not os.path.isfile(cluster_path):
        return jsonify({
            "ok": False,
            "error": "cluster_json_missing",
            "message": f"未找到 cluster.json: {cluster_path}",
            "game_server_repo": repo,
        }), 404
    stat = ops_helpers._sync_cluster_to_agents(project_id)
    return jsonify({
        "ok": True,
        "project_id": project_id,
        "game_server_repo": repo,
        "cluster_json": cluster_path,
        "sync": stat,
    })



@bp.route("/api/ops-platform/deployment-catalog")
@admin_required("gm_ops")
def ops_platform_deployment_catalog():
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden", "message": "缺少运维查看权限 (ops.platform.view)"}), 403

    operator = str(session.get("user") or "intranet-ops")
    rows = [x for x in ops_helpers._load_nodes() if x.get("enabled")]
    out_nodes: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for node in rows:
        result = ops_gateway.deployment_catalog(node, actor=operator, reason="ops deployment catalog", ticket_id="OPS-CATALOG")
        if not result.get("success"):
            warnings.append(f"{node.get('id')}: {result.get('message')}")
            continue
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        nodes = data.get("nodes") if isinstance(data.get("nodes"), list) else []
        for item in nodes:
            if not isinstance(item, dict):
                continue
            out_nodes.append({
                "source_node_id": node.get("id"),
                "source_ops_base_url": node.get("ops_base_url"),
                **item,
            })

    # de-dup by serverId while preserving latest payload.
    dedup: Dict[str, Dict[str, Any]] = {}
    for item in out_nodes:
        sid = str(item.get("serverId") or "").strip()
        if sid:
            dedup[sid] = item
    merged = list(dedup.values())
    merged.sort(key=lambda x: str(x.get("serverId") or ""))
    return jsonify({
        "ok": True,
        "count": len(merged),
        "nodes": merged,
        "warnings": warnings,
        "generated_at": ops_helpers._now_iso(),
    })



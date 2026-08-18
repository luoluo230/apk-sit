# -*- coding: utf-8 -*-
"""Agents route submodule."""
from __future__ import annotations

from routes.ops.common import *  # noqa: F403
from flask import jsonify, redirect, render_template_string, request, session

from models.data import log_audit
from services.authz import admin_required
from routes.ops import deps as ops_helpers
from routes.ops import bp


@bp.route("/api/ops-platform/agents/stream")
@admin_required("gm_ops")
def ops_platform_agents_stream():
    """SSE 推送端点：前端用 EventSource 订阅，状态变化时推送完整 payload。"""
    if not ops_helpers._allow_ops_view():
        return jsonify({"ok": False, "error": "forbidden"}), 403
    ops_helpers._ensure_probe_bg_started()

    q: _queue_mod.Queue = _queue_mod.Queue(maxsize=64)
    with ops_helpers._sse_sub_lock:
        ops_helpers._sse_subscribers.append(q)

    def _generate():
        # 先推一次全量快照
        snap = None
        try:
            with ops_helpers._probe_cache_lock:
                snap = ops_helpers._build_sse_payload(
                    ops_helpers._probe_cache_agents, ops_helpers._probe_cache
                ) if ops_helpers._probe_cache_agents else None
        except Exception as exc:
            import logging
            logging.getLogger("ops.agent_stream").warning("build initial SSE payload failed: %s", exc, exc_info=True)
        if snap:
            yield f"event: full\ndata: {json.dumps(snap, ensure_ascii=False)}\n\n"

        # 后续增量推送
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield f"event: change\ndata: {msg}\n\n"
                except _queue_mod.Empty:
                    # 心跳：30s 无变化也推一次，防止连接超时
                    yield f": heartbeat {int(ops_helpers._time_mod.time())}\n\n"
        finally:
            with ops_helpers._sse_sub_lock:
                try:
                    ops_helpers._sse_subscribers.remove(q)
                except ValueError:
                    pass

    from flask import Response
    return Response(
        _generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )









































































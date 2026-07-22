# -*- coding: utf-8 -*-
"""Build status poll + SSE endpoints for journey pages."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict

from flask import Response, jsonify, make_response, request

from models.data import projects_db
from services.authz import admin_required
from services.build_history_service import latest_build_for_version
from services.release.channel_journey_bff import _jenkins_progress_pct
from services.release.release_order_service import find_release_order_for_version, sync_building_release_orders


def _build_snapshot(project_id: str, version_id: str, *, sync: bool = True) -> Dict[str, Any]:
    vid = str(version_id or "").strip()
    if sync and project_id in projects_db:
        try:
            sync_building_release_orders(project_id, actor="build-events")
        except Exception:
            pass
    build: Dict[str, Any] = {}
    if vid:
        build = latest_build_for_version(vid, project_id) or {}
        if build:
            build = dict(build)
            build["progress_pct"] = _jenkins_progress_pct(build)
    order_status = ""
    if vid and project_id in projects_db:
        try:
            order = find_release_order_for_version(project_id, vid) or {}
            order_status = str(order.get("status") or "")
        except Exception:
            order_status = ""
    building = bool(build.get("building")) or order_status == "building"
    return {
        "project_id": project_id,
        "version_id": vid,
        "platform": str(request.args.get("platform") or "").strip().lower(),
        "build": build or None,
        "building": building,
        "order_status": order_status,
        "polled_at": time.time(),
    }


def _etag_for_payload(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return f'"{hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]}"'


def register_build_events_routes(bp) -> None:
    @bp.route("/api/projects/<project_id>/build-events")
    @admin_required("projects")
    def build_events_poll(project_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        version_id = str(request.args.get("version_id") or "").strip()
        if not version_id:
            return jsonify({"ok": False, "error": "version_id 必填"}), 400
        snapshot = _build_snapshot(project_id, version_id, sync=True)
        etag = _etag_for_payload(snapshot)
        if request.headers.get("If-None-Match") == etag:
            resp = make_response("", 304)
            resp.headers["ETag"] = etag
            resp.headers["Cache-Control"] = "no-cache"
            return resp
        resp = make_response(jsonify({"ok": True, "data": snapshot}))
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @bp.route("/api/projects/<project_id>/build-events/stream")
    @admin_required("projects")
    def build_events_stream(project_id: str):
        if project_id not in projects_db:
            return jsonify({"ok": False, "error": "项目不存在"}), 404
        version_id = str(request.args.get("version_id") or "").strip()
        if not version_id:
            return jsonify({"ok": False, "error": "version_id 必填"}), 400

        def _generate():
            last_etag = ""
            idle_ticks = 0
            while idle_ticks < 40:
                snapshot = _build_snapshot(project_id, version_id, sync=True)
                etag = _etag_for_payload(snapshot)
                if etag != last_etag:
                    last_etag = etag
                    yield f"event: build\ndata: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
                    idle_ticks = 0
                else:
                    idle_ticks += 1
                    yield f": heartbeat {int(time.time())}\n\n"
                if not snapshot.get("building"):
                    yield f"event: done\ndata: {json.dumps({'building': False, 'version_id': version_id}, ensure_ascii=False)}\n\n"
                    break
                time.sleep(3)

        return Response(
            _generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

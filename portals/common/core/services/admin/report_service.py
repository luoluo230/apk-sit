"""Report APIs service."""

from __future__ import annotations

import csv as csv_module
import io
import uuid
from datetime import datetime
from typing import Any, Dict, Tuple

from flask import send_file

from repositories.admin import reports_repo


def create_template(username: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    name = (data.get("name") or "").strip()
    if not name:
        return {"error": "模板名称不能为空"}, 400

    project_id = reports_repo.resolve_project((data.get("project_id") or ((data.get("config") or {}).get("project_id")) or "").strip()) or ""
    config = data.get("config") or {}
    if not isinstance(config, dict):
        config = {}
    if project_id:
        config["project_id"] = project_id

    tid = uuid.uuid4().hex[:16]
    reports_repo.append_template(
        {
            "id": tid,
            "name": name,
            "description": (data.get("description") or "").strip(),
            "project_id": project_id,
            "config": config,
            "created_by": username,
            "created_at": datetime.now().isoformat(),
        }
    )
    reports_repo.audit("report_template_create", name)
    return {"success": True, "id": tid}, 200


def _compute_gate_pass_rate() -> float:
    from services.build_history_service import _load_records, _resolve_build_status

    records = _load_records()[-80:]
    if not records:
        return 1.0
    cache: dict = {}
    passed = total = 0
    for rec in records:
        status = str(_resolve_build_status(rec, cache).get("result") or "").upper()
        if status not in {"SUCCESS", "FAILURE", "ABORTED", "UNSTABLE"}:
            continue
        total += 1
        if status == "SUCCESS":
            passed += 1
    return round(passed / total, 3) if total else 1.0


def _compute_cluster_health() -> tuple[int, int]:
    try:
        from services.ops.storage import _load_agent_registry_v2

        reg = _load_agent_registry_v2()
        total = online = 0
        for row in (reg or {}).values():
            if not isinstance(row, dict):
                continue
            total += 1
            st = str(row.get("effective_status") or row.get("status") or "").upper()
            if st in ("ONLINE", "RUNNING", "READY"):
                online += 1
        return online, total
    except Exception:
        return 0, 0


def dashboard_catalog(username: str) -> Tuple[Dict[str, Any], int]:
    """§11.3 dashboard: draggable cards, chart types, filters, scheduled email."""
    from repositories.admin import reports_repo

    download_total = sum(count for _, count in reports_repo.download_stats_items())
    gate_pass_rate = _compute_gate_pass_rate()
    cluster_online, cluster_total = _compute_cluster_health()
    cards = [
        {
            "id": "downloads",
            "title": "下载统计",
            "chart": "bar",
            "metric": "download_count",
            "layout": {"x": 0, "y": 0, "w": 4, "h": 2},
            "series": [{"label": "total", "value": download_total}],
        },
        {
            "id": "gates",
            "title": "门禁通过率",
            "chart": "line",
            "metric": "gate_pass_rate",
            "layout": {"x": 4, "y": 0, "w": 4, "h": 2},
            "series": [{"label": "pass_rate", "value": gate_pass_rate}],
        },
        {
            "id": "cluster",
            "title": "集群健康",
            "chart": "stat",
            "metric": "cluster_health_passing",
            "layout": {"x": 8, "y": 0, "w": 4, "h": 2},
            "series": [{"label": "passing", "value": cluster_online}, {"label": "total", "value": cluster_total}],
        },
        {
            "id": "heatmap",
            "title": "下载热力",
            "chart": "heatmap",
            "metric": "download_heatmap",
            "layout": {"x": 0, "y": 2, "w": 12, "h": 3},
            "series": [],
        },
    ]
    return {
        "ok": True,
        "cards": cards,
        "filters": {
            "time_range": ["7d", "30d", "90d"],
            "project_id": [],
            "channel": [],
        },
        "schedule": {
            "email_enabled": True,
            "cron": "0 8 * * 1",
            "recipients": [username],
        },
    }, 200


def run_template(username: str, template_id: str):
    tpl = reports_repo.find_template(template_id)
    if not tpl:
        return "模板不存在", 404

    template_project_id = reports_repo.resolve_project((((tpl.get("config") or {}).get("project_id")) or tpl.get("project_id") or "").strip()) or ""
    buf = io.StringIO()
    w = csv_module.writer(buf)
    w.writerow(["文件名", "项目", "版本", "下载次数", "统计时间"])

    for fname, count in sorted(reports_repo.download_stats_items(), key=lambda x: -x[1]):
        resolved_name_project = reports_repo.resolve_project(reports_repo.parse_project(fname)) or ""
        if template_project_id and resolved_name_project != template_project_id:
            continue
        w.writerow([fname, reports_repo.parse_project(fname), reports_repo.parse_version(fname), count, datetime.now().strftime("%Y-%m-%d %H:%M")])

    buf.write("\n下载事件明细（最近）\n")
    w.writerow(["日期", "文件名", "来源", "IP"])
    for e in reports_repo.load_events()[-5000:]:
        event_project_id = reports_repo.resolve_project(reports_repo.parse_project(e.get("filename", ""))) or ""
        if template_project_id and event_project_id != template_project_id:
            continue
        w.writerow([e.get("date", ""), e.get("filename", ""), e.get("source", ""), e.get("ip", "")])

    bin_buf = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    bin_buf.seek(0)

    reports_repo.append_export_record(
        {
            "user": username,
            "template_id": template_id,
            "template_name": tpl.get("name", ""),
            "project_id": template_project_id,
            "params": tpl.get("config", {}),
            "exported_at": datetime.now().isoformat(),
            "format": "csv",
        }
    )
    reports_repo.audit("report_export", tpl.get("name", ""))

    fn = "report_%s_%s.csv" % (template_id[:8], datetime.now().strftime("%Y%m%d_%H%M"))
    return send_file(bin_buf, as_attachment=True, download_name=fn, mimetype="text/csv")

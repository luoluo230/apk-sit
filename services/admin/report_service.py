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

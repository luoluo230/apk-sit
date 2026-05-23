# -*- coding: utf-8 -*-
"""数据分析：下载趋势、版本/来源/地域与导出。"""

import csv
import io
import json
import os
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import quote as url_quote

from flask import Blueprint, jsonify, render_template, render_template_string, request, send_file

from config import Config
from models.data import (
    download_stats,
    extract_project_name,
    extract_version_from_filename,
    iter_package_files,
    load_download_events,
    projects_db,
)
from services.authz import admin_required

bp = Blueprint("dashboard_routes", __name__, url_prefix="")

_region_cache = {}


def _ip_to_country(ip):
    if not ip or ip in ("127.0.0.1", "localhost"):
        return "本地"
    if ip not in _region_cache:
        try:
            req = urllib.request.Request(
                "http://ip-api.com/json/" + ip + "?fields=country",
                headers={"User-Agent": "APK-Site/1.0"},
            )
            with urllib.request.urlopen(req, timeout=2) as response:
                data = json.loads(response.read().decode())
                _region_cache[ip] = data.get("country", "未知")
        except Exception:
            _region_cache[ip] = "未知"
    return _region_cache[ip]


def _parse_date_range():
    now = datetime.now()
    from_date = (request.args.get("from") or "").strip()
    to_date = (request.args.get("to") or "").strip()
    if not to_date:
        to_date = now.strftime("%Y-%m-%d")
    if not from_date:
        from_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    try:
        from_d = datetime.strptime(from_date, "%Y-%m-%d").date()
        to_d = datetime.strptime(to_date, "%Y-%m-%d").date()
    except ValueError:
        return None, None, from_date, to_date
    if from_d > to_d:
        from_d, to_d = to_d, from_d
        from_date, to_date = from_d.strftime("%Y-%m-%d"), to_d.strftime("%Y-%m-%d")
    return from_d, to_d, from_date, to_date


@bp.route("/api/analytics/downloads-by-date")
@admin_required("dashboard")
def api_downloads_by_date():
    project = (request.args.get("project") or "").strip()
    from_d, to_d, from_date, to_date = _parse_date_range()
    group_by = (request.args.get("group_by") or "day").strip().lower()
    if group_by not in ("day", "week"):
        group_by = "day"
    if not project:
        return jsonify({"error": "missing project"}), 400
    if not from_d or not to_d:
        return jsonify({"labels": [], "data": []})

    buckets = {}
    if group_by == "week":
        current = from_d
        while current <= to_d:
            week_start = current - timedelta(days=current.weekday())
            buckets[week_start.strftime("%Y-%m-%d")] = 0
            current += timedelta(days=7)
    else:
        current = from_d
        while current <= to_d:
            buckets[current.strftime("%Y-%m-%d")] = 0
            current += timedelta(days=1)

    for event in load_download_events():
        filename = event.get("filename") or ""
        if extract_project_name(filename) != project:
            continue
        date_str = event.get("date") or ""
        try:
            event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (from_d <= event_date <= to_d):
            continue
        key = date_str
        if group_by == "week":
            key = (event_date - timedelta(days=event_date.weekday())).strftime("%Y-%m-%d")
        if key in buckets:
            buckets[key] += 1

    labels = sorted(buckets.keys())
    return jsonify({"labels": labels, "data": [buckets[label] for label in labels]})


@bp.route("/api/analytics/trends")
@admin_required("dashboard")
def api_trends():
    events = load_download_events()
    today = datetime.now().date()
    week_counts = {}
    for index in range(8):
        week_end = today - timedelta(days=index * 7)
        week_start = week_end - timedelta(days=6)
        week_counts[week_start.strftime("%Y-%m-%d")] = 0
    for event in events:
        date_str = event.get("date")
        if not date_str:
            continue
        try:
            event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        week_start = event_date - timedelta(days=event_date.weekday())
        key = week_start.strftime("%Y-%m-%d")
        if key in week_counts:
            week_counts[key] += 1
    labels = sorted(week_counts.keys(), reverse=True)[:8]
    labels.reverse()
    data = [week_counts[key] for key in labels]
    this_week = data[-1] if data else 0
    last_week = data[-2] if len(data) >= 2 else 0
    wow = round((this_week - last_week) / last_week * 100, 1) if last_week else 0
    return jsonify(
        {
            "labels": labels,
            "data": data,
            "this_week": this_week,
            "last_week": last_week,
            "week_over_week_pct": wow,
        }
    )


@bp.route("/api/analytics/version-stats")
@admin_required("dashboard")
def api_version_stats():
    by_project_version = defaultdict(lambda: {"downloads": 0})
    for filename, count in download_stats.items():
        project = extract_project_name(filename)
        version = extract_version_from_filename(filename) or "未知"
        by_project_version[(project, version)]["downloads"] += count
    items = [
        {"project": project, "version": version, "downloads": data["downloads"]}
        for (project, version), data in by_project_version.items()
    ]
    total = sum(item["downloads"] for item in items)
    for item in items:
        item["pct"] = round(item["downloads"] / total * 100, 1) if total else 0
    items.sort(key=lambda item: (-item["downloads"], item["project"], item["version"]))
    return jsonify({"items": items, "total_downloads": total})


@bp.route("/api/analytics/source-stats")
@admin_required("dashboard")
def api_source_stats():
    counts = {"site": 0, "qr": 0, "direct": 0}
    for event in load_download_events():
        source = (event.get("source") or "site").strip().lower()
        counts[source] = counts.get(source, 0) + 1
    total = sum(counts.values())
    items = [
        {
            "label": "站内",
            "count": counts.get("site", 0),
            "pct": round(counts.get("site", 0) / total * 100, 1) if total else 0,
        },
        {
            "label": "扫码",
            "count": counts.get("qr", 0),
            "pct": round(counts.get("qr", 0) / total * 100, 1) if total else 0,
        },
        {
            "label": "直链",
            "count": counts.get("direct", 0),
            "pct": round(counts.get("direct", 0) / total * 100, 1) if total else 0,
        },
    ]
    return jsonify({"items": items, "total": total})


@bp.route("/api/analytics/region-stats")
@admin_required("dashboard")
def api_region_stats():
    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    by_country = defaultdict(int)
    for event in load_download_events():
        if (event.get("date") or "") < cutoff:
            continue
        ip = (event.get("ip") or "").strip()
        if ip:
            by_country[_ip_to_country(ip)] += 1
    items = [{"country": country, "count": count} for country, count in sorted(by_country.items(), key=lambda item: -item[1])]
    return jsonify({"items": items})


@bp.route("/api/analytics/retention")
@admin_required("dashboard")
def api_retention():
    events = load_download_events()
    total = len(events)
    ips = {(event.get("ip") or "").strip() for event in events if (event.get("ip") or "").strip()}
    distinct = len(ips)
    avg = round(total / distinct, 1) if distinct else 0
    return jsonify(
        {
            "total_downloads": total,
            "distinct_ips": distinct,
            "avg_per_ip": avg,
            "total_all_time": sum(download_stats.values()),
        }
    )


@bp.route("/dashboard")
@admin_required("dashboard")
def dashboard_page():
    from_d, to_d, from_date, to_date = _parse_date_range()
    project_filter = (request.args.get("project") or "").strip()
    now = datetime.now()

    try:
        total_packages = 0
        total_size = 0
        project_stats = defaultdict(lambda: {"count": 0, "size": 0, "downloads": 0})
        for filename, filepath in iter_package_files():
            project_name = extract_project_name(filename)
            if project_filter and project_name != project_filter:
                continue
            stat = os.stat(filepath)
            downloads = download_stats.get(filename, download_stats.get(os.path.basename(filename), 0))
            total_packages += 1
            total_size += stat.st_size
            project_stats[project_name]["count"] += 1
            project_stats[project_name]["size"] += stat.st_size
            project_stats[project_name]["downloads"] += downloads

        total_downloads = 0
        events = load_download_events()
        if from_d and to_d:
            for event in events:
                date_str = (event.get("date") or "")[:10]
                if from_date <= date_str <= to_date:
                    if not project_filter or extract_project_name(event.get("filename") or "") == project_filter:
                        total_downloads += 1
        else:
            total_downloads = sum(download_stats.values())

        project_data = {
            project_id: {
                "name": projects_db.get(project_id, {}).get("name", project_id),
                "count": stats["downloads"],
            }
            for project_id, stats in project_stats.items()
        }
        all_top = download_stats.items()
        if project_filter:
            all_top = [(filename, count) for filename, count in all_top if extract_project_name(filename) == project_filter]
        top_rows = [
            {"rank": index, "filename": filename, "downloads": count}
            for index, (filename, count) in enumerate(sorted(all_top, key=lambda item: -item[1])[:10], 1)
        ]
        project_option_ids = set(projects_db.keys()) | set(project_stats.keys())
        project_options = [
            {
                "id": project_id,
                "name": projects_db.get(project_id, {}).get("name", project_id),
                "selected": project_id == project_filter,
            }
            for project_id in sorted(project_option_ids, key=lambda item: (projects_db.get(item, {}).get("name", item), item))
        ]
        export_params = f"?from={from_date}&to={to_date}&project={url_quote(project_filter) if project_filter else ''}"
    except Exception as exc:
        import traceback

        traceback.print_exc()
        return render_template_string(
            """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>数据分析</title></head>
            <body class="p-8"><h1>数据分析</h1><p class="text-red-600">数据加载出错，请查看控制台日志。错误: """
            + str(exc)
            + """</p><a href="/admin">返回管理中心</a></body></html>"""
        )

    return render_template(
        "admin_dashboard.html",
        export_params=export_params,
        from_date=from_date,
        project_count=len(project_stats),
        project_data=project_data,
        project_filter=project_filter,
        project_options=project_options,
        server_today=now.strftime("%Y-%m-%d"),
        to_date=to_date,
        top_rows=top_rows,
        total_downloads=total_downloads,
        total_packages=total_packages,
        total_size_mb=total_size / 1024 / 1024,
    )


@bp.route("/dashboard/export")
@admin_required("dashboard")
def dashboard_export():
    _, _, from_date, to_date = _parse_date_range()
    project_filter = (request.args.get("project") or "").strip()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["文件名", "项目", "版本", "下载次数", "统计时间"])

    items = list(download_stats.items())
    if project_filter:
        items = [(filename, count) for filename, count in items if extract_project_name(filename) == project_filter]
    for filename, count in sorted(items, key=lambda item: -item[1]):
        writer.writerow(
            [
                filename,
                extract_project_name(filename),
                extract_version_from_filename(filename),
                count,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            ]
        )

    writer.writerow([])
    writer.writerow([f"下载事件明细：{from_date} 至 {to_date}"])
    writer.writerow(["日期", "文件名", "来源", "IP"])
    events = load_download_events()
    if from_date and to_date:
        events = [event for event in events if from_date <= (event.get("date") or "")[:10] <= to_date]
    if project_filter:
        events = [event for event in events if extract_project_name(event.get("filename") or "") == project_filter]
    for event in events[-5000:]:
        writer.writerow([event.get("date", ""), event.get("filename", ""), event.get("source", ""), event.get("ip", "")])

    output = io.BytesIO(buffer.getvalue().encode("utf-8-sig"))
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="apk_analytics_" + datetime.now().strftime("%Y%m%d_%H%M") + ".csv",
        mimetype="text/csv",
    )

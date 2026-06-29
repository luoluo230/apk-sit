# -*- coding: utf-8 -*-
"""One-shot script to extract admin_routes inline views into routes/admin/views/."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "routes" / "admin_routes.py"
VIEWS = ROOT / "routes" / "admin" / "views"

lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)


def sl(start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


def write(name: str, content: str) -> None:
    path = VIEWS / name
    path.write_text(content, encoding="utf-8")
    print(f"Wrote {path.name}: {len(content.splitlines())} lines")


# --- common.py ---
write(
    "common.py",
    '''# -*- coding: utf-8 -*-
"""Shared helpers for admin view modules."""

from models.data import can_view_project, projects_db, products_db
from services.player_content import forum_posts_db, player_news_db, player_welfare_db


def clean_display_text(value, fallback=""):
    text = "" if value is None else str(value).strip()
    if not text:
        return fallback
    question_ratio = text.count("?") / max(len(text), 1)
    if question_ratio >= 0.35 or "锟" in text or "�" in text:
        return fallback or text.replace("?", "").strip() or fallback
    return text


def visible_project_choices(username):
    rows = []
    for project_id, item in (projects_db or {}).items():
        if can_view_project(project_id, username):
            rows.append(
                {
                    "id": project_id,
                    "name": clean_display_text((item or {}).get("name"), project_id),
                }
            )
    rows.sort(key=lambda item: (item["name"], item["id"]))
    return rows


def product_project_map():
    mapping = {}
    for item in products_db if isinstance(products_db, list) else []:
        if not isinstance(item, dict):
            continue
        product_id = str(item.get("id") or "").strip()
        project_id = str(item.get("project_id") or "").strip()
        if product_id:
            mapping[product_id] = project_id
    return mapping


def content_project_id(approval_type, target_id):
    mapping = product_project_map()
    if approval_type == "news_publish":
        item = next(
            (row for row in player_news_db if isinstance(row, dict) and row.get("id") == target_id),
            None,
        )
        return mapping.get((item or {}).get("product_id") or "", "")
    if approval_type == "welfare_publish":
        item = next(
            (row for row in player_welfare_db if isinstance(row, dict) and row.get("id") == target_id),
            None,
        )
        return mapping.get((item or {}).get("product_id") or "", "")
    if approval_type == "forum_post_publish":
        item = next(
            (row for row in forum_posts_db if isinstance(row, dict) and row.get("id") == target_id),
            None,
        )
        return mapping.get((item or {}).get("product_id") or "", "")
    return ""


def approval_project_id(approval, projects_db_ref=None):
    db = projects_db_ref if projects_db_ref is not None else projects_db
    target_id = str((approval or {}).get("target_id") or "").strip()
    if target_id in (db or {}):
        return target_id
    return content_project_id((approval or {}).get("type") or "", target_id)
''',
)

# --- site_config.py ---
site_main = sl(326, 895).replace(
    "@bp.route('/admin/site-config')\n@admin_required()\ndef admin_site_config_page():",
    "def render_site_config_page():",
)
site_visual = sl(898, 1044).replace(
    "@bp.route('/admin/site-config/editor/<portal_kind>')\n@admin_required()\ndef admin_site_config_visual_editor(portal_kind):",
    "def render_site_config_visual_editor(portal_kind, get_csrf_token):",
).replace("_get_csrf_token()", "get_csrf_token()")

write(
    "site_config.py",
    f'''# -*- coding: utf-8 -*-
"""Admin site config pages."""

import html
import json
import uuid

from flask import render_template

from models.data import products_db
from services.company_profile import get_company_profile
from services.media_library import normalize_local_media_url, normalize_local_media_urls
from services.player_content import (
    get_active_welfare,
    get_forum_posts,
    get_latest_news,
)
from services.portal_content import get_dev_portal_content, get_player_portal_content
from routes.admin.views.common import clean_display_text

_clean_display_text = clean_display_text

{site_main}

{site_visual}

# API registration alias
visual_editor_normalize_modules = _visual_editor_normalize_modules
''',
)

# --- my_tasks.py ---
my_tasks_helpers = sl(1292, 1367) + sl(1483, 1517) + sl(1520, 1734)
my_tasks_route_body = sl(1372, 1480).replace("def my_tasks_page():", "def build_my_tasks_page_content(request, username, role_to_first_assignee):").replace(
    "    return _admin_layout(content, '我的任务', back_href='/admin')\n",
    "    return content\n",
)

write(
    "my_tasks.py",
    f'''# -*- coding: utf-8 -*-
"""Admin my-tasks page."""

import html
import json
from datetime import date, timedelta
from urllib.parse import urlencode

from models.data import can_view_project, get_task_plan, project_tasks_db, projects_db

TASK_STATUSES = [
    ("abandoned", "已作废"),
    ("not_started", "尚未开始"),
    ("in_progress", "进行中"),
    ("pending_review", "待验收"),
    ("review_passed", "验收通过"),
    ("review_failed", "验收未通过"),
    ("done", "已完成"),
]

PLAN_LABELS = {{
    "today_todo": "今日待办",
    "today_done": "今日完成",
    "tomorrow_plan": "明日计划",
    "backlog": "之前待办",
}}

{my_tasks_helpers}

{my_tasks_route_body}

def render_my_tasks_page(request, username, role_to_first_assignee):
    return build_my_tasks_page_content(request, username, role_to_first_assignee)
''',
)

# --- project_tasks.py ---
project_tasks_body = sl(1737, 1762).replace("def project_tasks_page(project_id):", "def render_project_tasks_page(project_id, username):").replace(
    "def project_tasks_stats_page(project_id):", "def render_project_tasks_stats_page(project_id, username):"
).replace("_current_username()", "username").replace(
    "    return _admin_layout(content,", "    return content  # layout applied in route; was _admin_layout(content,"
)

# Fix the broken return - need proper render functions
project_tasks_body = sl(1737, 1762)
project_tasks_html_funcs = sl(1765, 2143)
role_helper = sl(2146, 2153)

write(
    "project_tasks.py",
    f'''# -*- coding: utf-8 -*-
"""Admin project tasks pages."""

import json

from models.data import can_edit_project, can_view_project, projects_db
from routes.admin.views.my_tasks import TASK_STATUSES

{project_tasks_html_funcs}

{role_helper}

def render_project_tasks_page(project_id, username):
    if project_id not in projects_db or not can_view_project(project_id, username):
        return None, "无权限或项目不存在", 403
    proj = projects_db[project_id]
    editors = proj.get("editors") or []
    member_roles = proj.get("member_roles") or {{}}
    participants = [{{"user": u, "role": member_roles.get(u, "其他")}} for u in editors]
    if can_edit_project(project_id, username) and username and not any(p["user"] == username for p in participants):
        participants.insert(0, {{"user": username, "role": member_roles.get(username, "其他")}})
    status_opts = "".join('<option value="%s">%s</option>' % (k, v) for k, v in TASK_STATUSES)
    participants_opts = "".join(
        '<option value="%s">%s (%s)</option>' % (p["user"], p["user"], p["role"]) for p in participants
    )
    content = _project_tasks_html(project_id, proj.get("name", project_id), status_opts, participants_opts)
    title = "项目任务 - %s" % proj.get("name", project_id)
    return content, title, None


def render_project_tasks_stats_page(project_id, username):
    if project_id not in projects_db or not can_view_project(project_id, username):
        return None, "无权限或项目不存在", 403
    proj = projects_db[project_id]
    content = _project_tasks_stats_html(project_id, proj.get("name", project_id))
    title = "任务统计 - %s" % proj.get("name", project_id)
    return content, title, None
''',
)

# --- audit_log.py ---
audit_body = sl(2157, 2242).replace(
    "@bp.route('/admin/audit-log')\n@admin_required('audit_log')\ndef admin_audit_log_page():",
    "def render_audit_log_page(request, audit_log_db):",
).replace("    return _admin_layout(content, '操作日志')\n", "    return content\n")

write(
    "audit_log.py",
    f'''# -*- coding: utf-8 -*-
"""Admin audit log page."""

import html
from urllib.parse import quote

from services.admin import audit_service

AUDIT_SENSITIVE_ACTIONS = {{"delete_user", "delete_project", "task_delete", "task_batch_delete"}}


def filter_audit_entries(entries, user_filter, action_filter, date_from, date_to, keyword=None):
    return audit_service.filter_entries(entries, user_filter, action_filter, date_from, date_to, keyword or "")

{audit_body}
''',
)

# --- notifications.py ---
notif_body = sl(2248, 2285).replace(
    "@bp.route('/admin/notifications')\n@admin_required('notifications')\ndef admin_notifications_page():",
    "def render_notifications_page(username, type_filter):",
).replace("    username = _current_username()\n    type_filter = request.args.get('type', '').strip()\n", "").replace(
    "    return _admin_layout(content, '通知中心')\n", "    return content\n"
)

write(
    "notifications.py",
    f'''# -*- coding: utf-8 -*-
"""Admin notifications page."""

from services.admin import notification_page_service

{notif_body}
''',
)

# --- approval.py ---
approval_body = sl(2289, 2489).replace(
    "@bp.route('/admin/approval')\n@admin_required('approval')\ndef admin_approval_page():",
    "def render_approval_page(username, selected_project_id, get_csrf_token):",
).replace("    username = _current_username()\n    selected_project_id = resolve_project_id((request.args.get('project_id') or '').strip()) or ''\n", "").replace(
    "_visible_project_choices(username)", "visible_project_choices(username)"
).replace("_clean_display_text", "clean_display_text").replace("_approval_project_id", "approval_project_id").replace(
    "_get_csrf_token()", "get_csrf_token()"
).replace("    return _admin_layout(content, '\\u5ba1\\u6279\\u7ba1\\u7406')\n", "    return content\n")

write(
    "approval.py",
    f'''# -*- coding: utf-8 -*-
"""Admin approval page."""

import html

from models.data import (
    APPROVAL_TYPES,
    approvals_db,
    get_pending_approvals_for_user,
    projects_db,
    resolve_project_id,
)
from routes.admin.views.common import approval_project_id, clean_display_text, visible_project_choices

{approval_body}
''',
)

# --- reports.py ---
reports_body = sl(2493, 2607).replace(
    "@bp.route('/admin/reports')\n@admin_required('reports')\ndef admin_reports_page():",
    "def render_reports_page(username, selected_project_id):",
).replace("    username = _current_username()\n    selected_project_id = resolve_project_id((request.args.get('project_id') or '').strip()) or ''\n", "").replace(
    "_visible_project_choices(username)", "visible_project_choices(username)"
).replace("_clean_display_text", "clean_display_text").replace(
    "    return _admin_layout(content, '报表中心')\n", "    return content\n"
)

write(
    "reports.py",
    f'''# -*- coding: utf-8 -*-
"""Admin reports page."""

import html

from models.data import export_records_db, projects_db, report_templates_db, resolve_project_id
from routes.admin.views.common import clean_display_text, visible_project_choices

{reports_body}
''',
)

# --- settings.py ---
settings_body = sl(2661, 2728).replace(
    "@bp.route('/admin/settings')\n@admin_required('system_settings')\ndef admin_settings_page():",
    "def render_settings_page():",
).replace("    return _admin_layout(content, '系统设置')\n", "    return content\n")

write(
    "settings.py",
    f'''# -*- coding: utf-8 -*-
"""Admin system settings page."""

import html
import sys

from config import Config, DATA_DIR
from models.data import get_system_config

DEFAULT_SYSTEM_KEYS = [
    ("LOGIN_ATTEMPTS_LIMIT", "登录失败次数上限", "number", "5", "超过此次数将锁定账号"),
    ("LOGIN_LOCKOUT_MINUTES", "锁定时长（分钟）", "number", "15", "锁定后等待分钟数"),
    ("AUDIT_LOG_RETENTION_DAYS", "操作日志保留天数", "number", "365", "超期可归档或清理"),
    ("NOTIFICATION_SITE_ENABLED", "站内通知开关", "boolean", "true", "是否启用站内通知"),
    ("PASSWORD_MIN_LENGTH", "密码最小长度", "number", "6", "新建/重置密码时的最小长度"),
    ("REQUIRE_APPROVAL_FOR_DELETE", "高危操作需审批", "boolean", "false", "开启后：删除项目、删除版本、删除 Jenkins 实例需先提交审批并通过"),
    ("webhook_url", "Webhook URL", "string", "", "构建/版本等事件推送地址，留空不启用"),
    ("USE_SQLITE", "启用 SQLite", "boolean", "true", "核心 JSON 数据与审计日志同步到 SQLite，便于长期留存与恢复"),
]


def password_min_length():
    v = get_system_config("PASSWORD_MIN_LENGTH")
    try:
        return max(4, int(v)) if v is not None and str(v).strip() else 6
    except (ValueError, TypeError):
        return 6

{settings_body}
''',
)

print("All view modules written.")

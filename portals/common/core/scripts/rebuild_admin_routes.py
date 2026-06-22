# -*- coding: utf-8 -*-
"""Rebuild slim admin_routes.py after view extraction."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "routes" / "admin_routes.py"
lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)


def sl(start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


# Keep: imports header (trim at line 76), MODULE_LINKS block without TASK_STATUSES
header = sl(1, 76)
# Remove TASK_STATUSES block - it's in my_tasks now
header = header.replace(
    """# 任务状态
TASK_STATUSES = [
    ('abandoned', '已作废'),
    ('not_started', '尚未开始'),
    ('in_progress', '进行中'),
    ('pending_review', '待验收'),
    ('review_passed', '验收通过'),
    ('review_failed', '验收未通过'),
    ('done', '已完成'),
]

""",
    "",
)

helpers = sl(89, 269)  # MODULE_LINKS through _admin_layout
search_panel = sl(272, 321)
users_projects = sl(1151, 1283)
version_helpers = sl(1285, 1350)

view_imports = """
from routes.admin.views.site_config import (
    render_site_config_page,
    render_site_config_visual_editor,
    visual_editor_normalize_modules,
)
from routes.admin.views.audit_log import render_audit_log_page
from routes.admin.views.notifications import render_notifications_page
from routes.admin.views.approval import render_approval_page
from routes.admin.views.reports import render_reports_page
from routes.admin.views.settings import DEFAULT_SYSTEM_KEYS, password_min_length, render_settings_page
from routes.admin.views.my_tasks import render_my_tasks_page
from routes.admin.views.project_tasks import (
    render_project_tasks_page,
    render_project_tasks_stats_page,
    role_to_first_assignee,
)
from routes.admin.views.common import clean_display_text as _clean_display_text, visible_project_choices as _visible_project_choices
"""

thin_routes = '''
@bp.route('/admin/site-config')
@admin_required()
def admin_site_config_page():
    return _admin_layout(render_site_config_page(), '官网与外部模块配置')


@bp.route('/admin/site-config/editor/<portal_kind>')
@admin_required()
def admin_site_config_visual_editor(portal_kind):
    if portal_kind not in ('player', 'dev'):
        return _admin_layout(
            '<div class="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-rose-700">未知官网类型</div>',
            '可视化官网编辑器',
        )
    return render_site_config_visual_editor(portal_kind, _get_csrf_token)


@bp.route('/admin/my-tasks')
@admin_required('projects')
def my_tasks_page():
    content = render_my_tasks_page(request, _current_username(), role_to_first_assignee)
    return _admin_layout(content, '我的任务', back_href='/admin')


@bp.route('/admin/projects/<project_id>/tasks')
@admin_required('projects')
def project_tasks_page(project_id):
    content, title, err = render_project_tasks_page(project_id, _current_username())
    if err:
        return title, err
    return _admin_layout(content, title, back_href='/admin/projects')


@bp.route('/admin/projects/<project_id>/tasks/stats')
@admin_required('projects')
def project_tasks_stats_page(project_id):
    content, title, err = render_project_tasks_stats_page(project_id, _current_username())
    if err:
        return title, err
    proj = projects_db.get(project_id) or {}
    return _admin_layout(content, title, back_href='/admin/projects/%s/tasks' % project_id)


@bp.route('/admin/audit-log')
@admin_required('audit_log')
def admin_audit_log_page():
    return _admin_layout(render_audit_log_page(request, audit_log_db), '操作日志')


@bp.route('/admin/notifications')
@admin_required('notifications')
def admin_notifications_page():
    type_filter = request.args.get('type', '').strip()
    return _admin_layout(render_notifications_page(_current_username(), type_filter), '通知中心')


@bp.route('/admin/approval')
@admin_required('approval')
def admin_approval_page():
    selected_project_id = resolve_project_id((request.args.get('project_id') or '').strip()) or ''
    return _admin_layout(render_approval_page(_current_username(), selected_project_id, _get_csrf_token), '审批管理')


@bp.route('/admin/reports')
@admin_required('reports')
def admin_reports_page():
    selected_project_id = resolve_project_id((request.args.get('project_id') or '').strip()) or ''
    return _admin_layout(render_reports_page(_current_username(), selected_project_id), '报表中心')


@bp.route('/admin/settings')
@admin_required('system_settings')
def admin_settings_page():
    return _admin_layout(render_settings_page(), '系统设置')

'''

api_block = '''
def _password_min_length():
    return password_min_length()


def _register_split_api_routes():
    register_media_api_routes(bp)
    register_site_config_api_routes(bp, visual_editor_normalize_modules)
    register_user_api_routes(bp, _password_min_length)
    register_user_transfer_routes(bp, _password_min_length)
    register_project_misc_api_routes(
        bp,
        current_username_getter=_current_username,
        can_edit_lookup=lambda project_id: can_edit_project(project_id, _current_username()),
    )
    register_project_api_routes(
        bp,
        current_username_getter=_current_username,
        tenant_id_getter=lambda: session.get('tenant_id') or 'default',
    )
    register_channel_api_routes(bp)
    register_notification_api_routes(bp, _current_username)
    register_audit_api_routes(bp)
    register_settings_api_routes(bp, DEFAULT_SYSTEM_KEYS, _current_username)
    register_version_api_routes(bp, _current_username)
    register_task_api_routes(bp, _current_username)
    register_approval_api_routes(bp, _current_username)
    register_report_api_routes(bp, _current_username)


_register_split_api_routes()
'''

# Remove duplicate helpers now in common from helpers section
for fn in (
    "_clean_display_text",
    "_visible_project_choices",
    "_product_project_map",
    "_content_project_id",
    "_approval_project_id",
):
    # keep _get_csrf_token and _admin_layout only in helpers block - strip moved helpers manually
    pass

# Strip old helper functions from helpers block (lines 117-172 in original within helpers slice)
import re

helpers = re.sub(
    r"def _clean_display_text\(value, fallback=''\):.*?(?=\ndef _visible_project_choices)",
    "",
    helpers,
    flags=re.DOTALL,
)
helpers = re.sub(
    r"def _visible_project_choices\(username\):.*?(?=\ndef _product_project_map)",
    "",
    helpers,
    flags=re.DOTALL,
)
helpers = re.sub(
    r"def _product_project_map\(\):.*?(?=\ndef _content_project_id)",
    "",
    helpers,
    flags=re.DOTALL,
)
helpers = re.sub(
    r"def _content_project_id\(approval_type, target_id\):.*?(?=\ndef _approval_project_id)",
    "",
    helpers,
    flags=re.DOTALL,
)
helpers = re.sub(
    r"def _approval_project_id\(approval\):.*?(?=\ndef _admin_layout)",
    "",
    helpers,
    flags=re.DOTALL,
)

# Trim unused imports from header - remove player_content imports if only used by site_config
header = re.sub(
    r"from services\.player_content import \([\s\S]*?\)\n",
    "",
    header,
    count=1,
)
header = re.sub(
    r"from services\.portal_content import \([\s\S]*?\)\n",
    "",
    header,
    count=1,
)
header = re.sub(
    r"from services\.company_profile import get_company_profile\n",
    "",
    header,
)
header = re.sub(
    r"from services\.media_library import \([\s\S]*?\)\n",
    "",
    header,
    count=1,
)
header = re.sub(
    r"from services\.admin import notification_page_service\n",
    "",
    header,
)
header = re.sub(
    r"from services\.admin import audit_service\n",
    "",
    header,
)

out = header + view_imports + helpers + search_panel + thin_routes + users_projects + version_helpers + api_block
SRC.write_text(out, encoding="utf-8")
print(f"Rebuilt admin_routes.py: {len(out.splitlines())} lines")

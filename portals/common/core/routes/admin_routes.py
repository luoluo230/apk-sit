# -*- coding: utf-8 -*-
"""管理中心：面板、用户管理、项目管理、操作日志、通知/审批/报表/系统设置"""

import html
import html as html_module
import json
import os
import re
import uuid
from datetime import date, datetime, timedelta
from urllib.parse import quote
from flask import Blueprint, request, jsonify, render_template, render_template_string, session, abort, redirect
from services.authz import login_required, admin_required, admin_required_any, get_visible_modules, ADMIN_MODULES, ALL_MODULES_EXCEPT_USER_MANAGEMENT, is_super_admin_or_admin
from models.data import (
    projects_db, products_db, audit_log_db, project_tasks_db, project_versions_db,
    channels_db,  # 渠道配置：版本与下载中心使用
    get_channels_for_project, get_channel_by_id,
    save_users, save_projects, log_audit, save_project_tasks, save_project_versions,
    save_channels,
    get_project_apk_count, get_project_download_count, get_version_download_count, version_has_apk, version_is_recommended, can_view_project, can_edit_project,
    download_stats, changelog_db, save_changelog, extract_package_info, extract_project_name, iter_package_files,
    get_version_platform, get_platform_label,
    load_download_events, get_changelog_for_file,
    get_approved_approval, get_system_config,
    user_task_plans_db, get_task_plan, set_task_plan, save_user_task_plans,
    notifications_db, add_notification, get_notifications_for_user, save_notifications,
    approvals_db, approval_records_db, APPROVAL_TYPES, create_approval,
    get_pending_approvals_for_user, approve_or_reject, save_approvals, save_approval_records,
    system_config_db, get_system_config, set_system_config, save_system_config,
    report_templates_db, export_records_db, save_report_templates, save_export_records,
    load_jenkins_instances, resolve_project_id, normalize_public_url,
)
from config import Config, DATA_DIR
from routes.admin.api_users import register_routes as register_user_api_routes
from routes.admin.api_user_favorites import register_routes as register_user_favorites_api_routes
from routes.admin.api_users_transfer import register_routes as register_user_transfer_routes
from routes.admin.api_projects import register_routes as register_project_api_routes
from routes.admin.api_project_onboarding import register_routes as register_project_onboarding_api_routes
from routes.admin.api_platform_capabilities import register_routes as register_platform_capabilities_api_routes
from routes.admin.api_infra_nodes import register_routes as register_infra_nodes_api_routes
from routes.admin.api_server_release import register_routes as register_server_release_api_routes
from routes.admin.api_build_nodes import register_routes as register_build_nodes_api_routes
from routes.admin.pages_infra_nodes import register_routes as register_infra_nodes_page_routes
from routes.admin.pages_search import register_routes as register_search_page_routes
from routes.admin.pages_project_workspace import register_routes as register_project_workspace_page_routes
from routes.admin.api_projects_misc import register_routes as register_project_misc_api_routes
from routes.admin.api_approval import register_routes as register_approval_api_routes
from routes.admin.api_channels import register_routes as register_channel_api_routes
from routes.admin.api_notifications import register_routes as register_notification_api_routes
from routes.admin.api_settings import register_routes as register_settings_api_routes
from routes.admin.api_versions import register_routes as register_version_api_routes
from routes.admin.api_tasks import register_routes as register_task_api_routes
from routes.admin.api_reports import register_routes as register_report_api_routes
from routes.admin.api_media import register_routes as register_media_api_routes
from routes.admin.api_site_config import register_routes as register_site_config_api_routes
from routes.admin.api_audit import register_routes as register_audit_api_routes
from routes.admin.views.dashboard import admin_panel_descriptions, render_admin_panel_dashboard
from services.release.topology_binding_service import list_topology_bindings, resolve_topology_binding

from routes.admin.project_constants import PROJECT_PHASES, PROJECT_ROLES

bp = Blueprint('admin_routes', __name__, url_prefix='')

from routes.admin.views.site_config import (
    render_site_config_page,
    render_site_config_visual_editor,
    visual_editor_normalize_modules,
)
from routes.admin.views.audit_log import render_audit_log_page
from routes.admin.views.notifications import render_notifications_page
from routes.admin.views.approval import render_approval_page
from routes.admin.views.reports import render_reports_page
from routes.admin.views.rbac import render_rbac_page
from routes.admin.views.settings import DEFAULT_SYSTEM_KEYS, password_min_length, render_settings_page
from routes.admin.views.my_tasks import render_my_tasks_page
from routes.admin.views.project_tasks import (
    render_project_tasks_page,
    render_project_tasks_stats_page,
    role_to_first_assignee,
)
from routes.admin.views.common import clean_display_text as _clean_display_text, visible_project_choices as _visible_project_choices
# 模块 id -> (链接, 图标 class, 图标颜色 class)
MODULE_LINKS = {
    'user_management': ('/admin/users', 'fa-users', 'text-blue-500'),
    'projects': ('/admin/projects', 'fa-folder', 'text-green-500'),
    'community': ('/admin/community', 'fa-comments', 'text-pink-500'),
    'build': ('/admin/build', 'fa-cogs', 'text-orange-500'),
    'commercial_release': ('/admin/projects', 'fa-rocket', 'text-violet-500'),
    'dashboard': ('/admin/dashboard', 'fa-chart-pie', 'text-purple-500'),
    'versions': ('/admin/versions', 'fa-code-branch', 'text-teal-500'),
    'docs': ('/docs', 'fa-file-alt', 'text-cyan-500'),
    'jenkins': ('/admin/jenkins', 'fa-server', 'text-indigo-500'),
    'audit_log': ('/admin/audit-log', 'fa-history', 'text-gray-500'),
    'notifications': ('/admin/notifications', 'fa-bell', 'text-amber-500'),
    'approval': ('/admin/approval', 'fa-check-double', 'text-emerald-500'),
    'reports': ('/admin/reports', 'fa-file-alt', 'text-cyan-500'),
    'system_settings': ('/admin/settings', 'fa-cog', 'text-slate-500'),
}


def _get_csrf_token():
    try:
        from flask_wtf.csrf import generate_csrf

        return generate_csrf()
    except ImportError:
        return ''







def _admin_layout(content, title, back_href='/admin'):
    username = session.get("user") or ""
    is_ops_app = 'class="ops-app"' in (content or "")
    content_wrap_class = (
        "w-full px-0 py-0"
        if is_ops_app
        else "max-w-6xl mx-auto px-4 py-6 md:py-8"
    )
    header_html = f'''
        <header class="admin-nav shadow-lg">
            <div class="max-w-6xl mx-auto px-4">
                <div class="flex items-center justify-between h-14 md:h-16 gap-2">
                    <div class="flex items-center gap-2">
                        <span class="flex items-center justify-center w-9 h-9 rounded-xl bg-white/10 text-white">
                            <i class="fas fa-sliders-h text-lg"></i>
                        </span>
                        <div>
                            <h1 class="text-lg md:text-xl font-semibold text-white tracking-tight">{title}</h1>
                            <p class="hidden md:block text-[11px] text-slate-200/80">管理 APK 项目、版本、构建与权限</p>
                        </div>
                    </div>
                    <div class="flex items-center gap-2">
                        <a href="/download-center" class="hidden sm:inline-flex items-center gap-1.5 text-xs font-medium text-slate-100 hover:text-white transition">
                            <i class="fas fa-box-open"></i><span>下载中心</span>
                        </a>
                        <div class="hidden md:flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-xs text-slate-100">
                            <i class="fas fa-user-circle text-slate-200"></i>
                            <span class="font-semibold">{html.escape(username or '未登录')}</span>
                        </div>
                        <a href="/profile" class="hidden sm:inline-flex items-center gap-1.5 text-xs font-medium text-slate-100 hover:text-white transition">
                            <i class="fas fa-id-badge"></i><span>个人中心</span>
                        </a>
                        <a href="/logout" class="hidden sm:inline-flex items-center gap-1.5 text-xs font-medium text-slate-100 hover:text-white transition">
                            <i class="fas fa-right-from-bracket"></i><span>退出</span>
                        </a>
                        <form method="get" action="/admin/search" class="hidden sm:flex items-center bg-slate-900/20 rounded-lg px-2 py-1.5">
                            <i class="fas fa-search text-slate-300 text-xs mr-1.5"></i>
                            <input type="text" name="q" placeholder="搜索项目、文档、任务、版本、发布单…" class="bg-transparent outline-none border-0 text-xs text-slate-50 placeholder:text-slate-400 w-40 focus:ring-0">
                        </form>
                        <a href="{back_href}" class="inline-flex items-center gap-1.5 text-xs md:text-sm font-medium text-slate-100 hover:text-white hover:underline">
                            <i class="fas fa-arrow-left text-slate-200"></i><span>返回</span>
                        </a>
                    </div>
                </div>
            </div>
        </header>
        '''
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{html.escape(_get_csrf_token())}">
    <title>{title} - APK 下载中心</title>
    <link rel="stylesheet" href="/static/tailwind.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        .admin-nav {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 40%, #4f46e5 100%); }}
        .admin-card {{ transition: box-shadow 0.18s ease, transform 0.18s ease, background-color 0.18s ease; }}
        .admin-card:hover {{ box-shadow: 0 18px 45px -20px rgba(15,23,42,0.35); transform: translateY(-2px); }}
        .stat-card {{ background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%); }}
    </style>
</head>
<body class="bg-slate-50 min-h-screen text-slate-800 antialiased">
    <div class="min-h-screen flex flex-col">
        {header_html}
        <main class="flex-1">
            <div class="{content_wrap_class}">
                {content}
            </div>
        </main>
    </div>
    <script>
        (function() {{
            var tokenEl = document.querySelector('meta[name="csrf-token"]');
            var csrfToken = tokenEl && tokenEl.content ? tokenEl.content : '';
            if (!csrfToken || !window.fetch || window.__adminFetchCsrfPatched) return;
            var originalFetch = window.fetch.bind(window);
            window.fetch = function(resource, init) {{
                init = init || {{}};
                var method = String(init.method || 'GET').toUpperCase();
                var target = typeof resource === 'string' ? resource : ((resource && resource.url) || '');
                var isRelative = target && !/^https?:\\/\\//i.test(target);
                if (isRelative && ['POST', 'PUT', 'PATCH', 'DELETE'].indexOf(method) >= 0) {{
                    var headers = new Headers(init.headers || (resource && resource.headers) || undefined);
                    if (!headers.has('X-CSRFToken')) headers.set('X-CSRFToken', csrfToken);
                    init.headers = headers;
                }}
                return originalFetch(resource, init);
            }};
            window.__adminFetchCsrfPatched = true;
        }})();
    </script>
</body>
</html>
'''
# 页面主入口：admin 面板首页（项目优先导航）。数据来源：projects_db / 审批与通知聚合。
@bp.route('/admin')
@admin_required()
def admin_panel():
    visible = get_visible_modules()
    desc = admin_panel_descriptions()
    return render_admin_panel_dashboard(visible, desc, _current_username(), _admin_layout)

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

from routes.admin.views.users import render_users_page



@bp.route('/admin/users')
@admin_required('user_management')
def admin_users_page():
    page = render_users_page(_password_min_length())
    return _admin_layout(page, '用户管理')


@bp.route('/admin/rbac')
@admin_required('user_management')
def admin_rbac_page():
    return render_rbac_page(session.get('user') or 'admin')


@bp.route('/admin/api-docs')
@admin_required()
def admin_api_docs_page():
    return _admin_layout(render_api_docs_page(), 'API 文档')


# ---------- 项目管理 ----------
def _safe_json_for_script(s):
    """防止 JSON 中的 </script> 提前关闭 script 标签"""
    if not isinstance(s, str):
        return s
    return re.sub(r'(?i)</script>', r'<\\u002fscript>', s)

from routes.admin.views.api_docs import render_api_docs_page
from routes.admin.views.projects import projects_page_context, onboarding_wizard_page_context


def _current_username():
    return session.get('user') or ''


PROJECT_LIST_ASSET_VER = "20260723-favorites-sync"
ONBOARDING_WIZARD_ASSET_VER = "20260728-p102"


@bp.route('/admin/projects/new/wizard')
@admin_required('projects')
def admin_project_onboarding_wizard_page():
    from flask import render_template
    from services.ops.helpers import _render_ops_page

    content = render_template('project_onboarding_wizard.html', **onboarding_wizard_page_context())
    js = f'<script src="/static/project_onboarding.js?v={ONBOARDING_WIZARD_ASSET_VER}"></script>'
    return _render_ops_page(
        content,
        '新建项目向导',
        active_page='projects',
        breadcrumb_module='项目',
        extra_js=js,
    )


@bp.route('/admin/projects')
@admin_required('projects')
def admin_projects_page():
    from flask import render_template
    from services.ops.helpers import _render_ops_page

    content = render_template('project_list.html', **projects_page_context())
    css = (
        f'<link rel="stylesheet" href="/static/project_ui/pm-modal.css?v={PROJECT_LIST_ASSET_VER}">'
        f'<link rel="stylesheet" href="/static/project_ui/pm-project-card.css?v={PROJECT_LIST_ASSET_VER}">'
        f'<link rel="stylesheet" href="/static/project_ui/pm-right-rail.css?v={PROJECT_LIST_ASSET_VER}">'
        f'<link rel="stylesheet" href="/static/project_list.css?v={PROJECT_LIST_ASSET_VER}">'
    )
    js = (
        f'<script src="/static/user_favorites_sync.js?v={PROJECT_LIST_ASSET_VER}"></script>'
        f'<script src="/static/project_ui/pm-display-labels.js?v={PROJECT_LIST_ASSET_VER}"></script>'
        f'<script src="/static/project_list.js?v={PROJECT_LIST_ASSET_VER}"></script>'
    )
    return _render_ops_page(
        content,
        '项目列表',
        active_page='projects',
        breadcrumb_module='总览',
        extra_css=css,
        extra_js=js,
    )


def _user_project_role(project_id, username):
    """当前用户在该项目中的角色（仅编辑者有角色）。"""
    if not username or project_id not in projects_db:
        return None
    p = projects_db[project_id]
    return (p.get('member_roles') or {}).get(username)




def _parse_task_date(t, key):
    """Return date or None from task start_time/end_time."""
    s = (t.get(key) or '')[:10]
    if len(s) < 10:
        return None
    try:
        return date(int(s[:4]), int(s[5:7]), int(s[8:10]))
    except (ValueError, TypeError):
        return None



def _password_min_length():
    return password_min_length()


def _register_split_api_routes():
    register_media_api_routes(bp)
    register_site_config_api_routes(bp, visual_editor_normalize_modules)
    register_user_api_routes(bp, _password_min_length)
    register_user_favorites_api_routes(bp, _current_username)
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
    register_project_onboarding_api_routes(
        bp,
        current_username_getter=_current_username,
        tenant_id_getter=lambda: session.get('tenant_id') or 'default',
        projects_db=projects_db,
        can_edit_lookup=lambda project_id: can_edit_project(project_id, _current_username()),
    )
    register_platform_capabilities_api_routes(bp)
    register_infra_nodes_api_routes(bp)
    register_server_release_api_routes(bp)
    register_build_nodes_api_routes(bp)
    register_infra_nodes_page_routes(bp)
    register_search_page_routes(bp, admin_layout=_admin_layout, current_username=_current_username)
    register_project_workspace_page_routes(bp, current_username=_current_username)
    register_channel_api_routes(bp)
    register_notification_api_routes(bp, _current_username)
    register_audit_api_routes(bp)
    register_settings_api_routes(bp, DEFAULT_SYSTEM_KEYS, _current_username)
    register_version_api_routes(bp, _current_username)
    register_task_api_routes(bp, _current_username)
    register_approval_api_routes(bp, _current_username)
    register_report_api_routes(bp, _current_username)


_register_split_api_routes()

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
from flask import Blueprint, request, jsonify, render_template, render_template_string, session
from flask import redirect
from services.authz import login_required, admin_required, admin_required_any, get_visible_modules, ADMIN_MODULES, ALL_MODULES_EXCEPT_USER_MANAGEMENT, is_super_admin_or_admin
from models.data import (
    users_db, projects_db, products_db, audit_log_db, project_tasks_db, project_versions_db,
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
from services.portal_content import (
    get_dev_portal_content,
    get_player_portal_content,
)
from services.company_profile import get_company_profile
from services.media_library import (
    normalize_local_media_url,
    normalize_local_media_urls,
)
from services.player_content import (
    forum_posts_db,
    get_active_welfare,
    get_forum_posts,
    get_latest_news,
    player_news_db,
    player_welfare_db,
    set_forum_post_publish_state,
    set_news_publish_state,
    set_welfare_publish_state,
)
from routes.admin.api_users import register_routes as register_user_api_routes
from routes.admin.api_users_transfer import register_routes as register_user_transfer_routes
from routes.admin.api_projects import register_routes as register_project_api_routes
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
from services.admin import audit_service
from services.admin import notification_page_service

bp = Blueprint('admin_routes', __name__, url_prefix='')

# 项目阶段（成熟游戏流程）
PROJECT_PHASES = [
    ('kickoff', '立项/预研'),
    ('prototype', '原型/白盒'),
    ('preprod', '预生产/绿光'),
    ('production', '正式开发'),
    ('alpha', 'Alpha'),
    ('beta', 'Beta'),
    ('polish', '调优/收尾'),
    ('launch', '上线/运营'),
    ('maintenance', '维护'),
]
# 项目内角色
PROJECT_ROLES = ['策划', '数值', '美术', '特效', '前端', '后端', '测试', '其他']
# 任务状态
TASK_STATUSES = [
    ('abandoned', '已作废'),
    ('not_started', '尚未开始'),
    ('in_progress', '进行中'),
    ('pending_review', '待验收'),
    ('review_passed', '验收通过'),
    ('review_failed', '验收未通过'),
    ('done', '已完成'),
]

# 模块 id -> (链接, 图标 class, 图标颜色 class)
MODULE_LINKS = {
    'user_management': ('/admin/users', 'fa-users', 'text-blue-500'),
    'projects': ('/admin/projects', 'fa-folder', 'text-green-500'),
    'community': ('/admin/community', 'fa-comments', 'text-pink-500'),
    'build': ('/admin/build', 'fa-cogs', 'text-orange-500'),
    'commercial_release': ('/admin/build/commercial-release', 'fa-rocket', 'text-violet-500'),
    'dashboard': ('/admin/dashboard', 'fa-chart-pie', 'text-purple-500'),
    'versions': ('/admin/versions', 'fa-code-branch', 'text-teal-500'),
    'docs': ('/docs', 'fa-file-alt', 'text-cyan-500'),
    'jenkins': ('/admin/jenkins', 'fa-server', 'text-indigo-500'),
    'audit_log': ('/admin/audit-log', 'fa-history', 'text-gray-500'),
    'notifications': ('/admin/notifications', 'fa-bell', 'text-amber-500'),
    'approval': ('/admin/approval', 'fa-check-double', 'text-emerald-500'),
    'gm_ops': ('/admin/gm-ops', 'fa-sitemap', 'text-cyan-500'),
    'reports': ('/admin/reports', 'fa-file-alt', 'text-cyan-500'),
    'system_settings': ('/admin/settings', 'fa-cog', 'text-slate-500'),
}


def _get_csrf_token():
    try:
        from flask_wtf.csrf import generate_csrf

        return generate_csrf()
    except ImportError:
        return ''


def _clean_display_text(value, fallback=''):
    text = '' if value is None else str(value).strip()
    if not text:
        return fallback
    question_ratio = text.count('?') / max(len(text), 1)
    if question_ratio >= 0.35 or '锟' in text or '�' in text:
        return fallback or text.replace('?', '').strip() or fallback
    return text


def _visible_project_choices(username):
    rows = []
    for project_id, item in (projects_db or {}).items():
        if can_view_project(project_id, username):
            rows.append(
                {
                    'id': project_id,
                    'name': _clean_display_text((item or {}).get('name'), project_id),
                }
            )
    rows.sort(key=lambda item: (item['name'], item['id']))
    return rows


def _product_project_map():
    mapping = {}
    for item in (products_db if isinstance(products_db, list) else []):
        if not isinstance(item, dict):
            continue
        product_id = str(item.get('id') or '').strip()
        project_id = str(item.get('project_id') or '').strip()
        if product_id:
            mapping[product_id] = project_id
    return mapping


def _content_project_id(approval_type, target_id):
    product_project_map = _product_project_map()
    if approval_type == 'news_publish':
        item = next((row for row in player_news_db if isinstance(row, dict) and row.get('id') == target_id), None)
        return product_project_map.get((item or {}).get('product_id') or '', '')
    if approval_type == 'welfare_publish':
        item = next((row for row in player_welfare_db if isinstance(row, dict) and row.get('id') == target_id), None)
        return product_project_map.get((item or {}).get('product_id') or '', '')
    if approval_type == 'forum_post_publish':
        item = next((row for row in forum_posts_db if isinstance(row, dict) and row.get('id') == target_id), None)
        return product_project_map.get((item or {}).get('product_id') or '', '')
    return ''


def _approval_project_id(approval):
    target_id = str((approval or {}).get('target_id') or '').strip()
    if target_id in (projects_db or {}):
        return target_id
    return _content_project_id((approval or {}).get('type') or '', target_id)


def _admin_layout(content, title, back_href='/admin'):
    username = session.get("user") or ""
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
                            <input type="text" name="q" placeholder="全局搜索…" class="bg-transparent outline-none border-0 text-xs text-slate-50 placeholder:text-slate-400 w-40 focus:ring-0">
                        </form>
                        <a href="{back_href}" class="inline-flex items-center gap-1.5 text-xs md:text-sm font-medium text-slate-100 hover:text-white hover:underline">
                            <i class="fas fa-arrow-left text-slate-200"></i><span>返回</span>
                        </a>
                    </div>
                </div>
            </div>
        </header>
        <main class="flex-1">
            <div class="max-w-6xl mx-auto px-4 py-6 md:py-8">
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


def _admin_panel_descriptions():
    return {
        'user_management': '管理后台账号、角色、权限范围和登录安全策略。',
        'projects': '维护项目、分工、任务、版本与阶段信息。',
        'community': '按项目管理新闻、福利、官方帖子与玩家治理。',
        'build': '处理构建任务、分发链路和发布前准备。',
        'commercial_release': '商业级热更一站式工作台：计划、构建、上传、激活与回滚。',
        'dashboard': '查看数据看板、下载趋势和项目关键指标。',
        'versions': '维护版本记录、推荐包和平台分发入口。',
        'docs': '统一沉淀项目文档、规范和交付材料。',
        'jenkins': '管理 Jenkins 实例、任务和可用性状态。',
        'audit_log': '追踪关键操作、审批变更和系统审计记录。',
        'notifications': '查看站内通知、提醒和处理结果。',
        'approval': '统一提交、审核和回溯发布类审批记录。',
        'reports': '生成报表模板、导出记录与分析结果。',
        'system_settings': '配置系统开关、Webhook 和安全参数。',
    }


def _render_module_card(link, icon, color, title, description):
    return (
        f'<a href="{link}" class="admin-card block bg-white/95 rounded-2xl border border-slate-200/80 p-5 shadow-sm hover:bg-white group">'
        f'<div class="flex items-start gap-2">'
        f'<div class="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center flex-shrink-0">'
        f'<i class="fas {icon} {color} text-lg"></i>'
        f'</div>'
        f'<div class="min-w-0">'
        f'<h2 class="text-sm font-semibold text-slate-900 mb-1 group-hover:text-indigo-600">{title}</h2>'
        f'<p class="text-xs text-slate-500 leading-snug">{description}</p>'
        f'</div>'
        f'</div>'
        f'</a>'
    )


def _render_grouped_admin_sections(sections):
    parts = []
    for title, description, cards in sections:
        if not cards:
            continue
        parts.append(
            '<section class="rounded-2xl border border-slate-200/80 bg-slate-50/70 p-4">'
            f'<div class="mb-4"><h3 class="text-base font-semibold text-slate-900">{title}</h3>'
            f'<p class="mt-1 text-sm text-slate-500">{description}</p></div>'
            '<div class="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-4">'
            + ''.join(cards) +
            '</div></section>'
        )
    return ''.join(parts)


def _render_admin_dashboard_v2(summary_cards, quick_actions, todo_html, risk_html, audit_html, recent_package_rows, package_counts, cards):
    cards_html = cards if isinstance(cards, str) else ''.join(cards)
    return '''
    <section class="space-y-6"> 
        <div class="rounded-[28px] border border-slate-200/80 bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-900 p-6 md:p-7 shadow-xl shadow-slate-900/10"> 
            <div class="grid gap-6 xl:grid-cols-[1.45fr_0.95fr] xl:items-start"> 
                <div>
                    <p class="text-[11px] font-semibold tracking-[0.22em] uppercase text-slate-300/80">工作台总览</p>
                    <h2 class="mt-2 text-2xl md:text-3xl font-semibold text-white">运维、运营、开发与配置一屏总览</h2>
                    <p class="mt-3 max-w-2xl text-sm leading-6 text-slate-300">先看风险和待办，再按运维、运营、开发、配置四类中心进入模块，减少在审批、项目、版本、构建之间来回切页。</p>
                    <div class="mt-5 flex flex-wrap gap-2">''' + (''.join(quick_actions) if quick_actions else '<span class="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-slate-300">当前没有快捷操作</span>') + '''</div>
                </div>
                <div class="grid gap-3 sm:grid-cols-2">''' + ''.join(
                    f'<div class="rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur"><div class="flex items-center justify-between gap-2"><div><p class="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-300">{label}</p><p class="mt-2 text-3xl font-semibold text-white">{value}</p></div><div class="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/10 text-white"><i class="fas {icon} text-lg"></i></div></div></div>'
                    for label, value, icon, _bg_cls, _text_cls in summary_cards
                ) + '''</div>
            </div>
        </div>
        <div class="grid gap-5 xl:grid-cols-[1.55fr_0.95fr]"> 
            <div class="space-y-5"> 
                <div class="rounded-2xl border border-slate-200/80 bg-white/95 p-5 shadow-sm"> 
                    <div class="mb-4 flex flex-wrap items-center justify-between gap-2"> 
                        <div>
                            <h3 class="text-base font-semibold text-slate-900">工作优先级</h3>
                            <p class="mt-1 text-sm text-slate-500">把最影响交付和发布的事项放在第一屏。</p>
                        </div>
                        <a href="/admin/my-tasks" class="text-xs font-medium text-indigo-600 hover:underline">查看我的任务</a>
                    </div>
                    <ul class="space-y-3">''' + todo_html + '''</ul>
                </div>
                <div class="rounded-2xl border border-slate-200/80 bg-white/95 p-5 shadow-sm"> 
                    <div class="mb-4 flex flex-wrap items-center justify-between gap-2"> 
                        <div>
                            <h3 class="text-base font-semibold text-slate-900">项目优先导航</h3>
                            <p class="mt-1 text-sm text-slate-500">按运维、运营、开发、配置四个中心展示入口，每类只保留与本职责最相关的功能。</p>
                        </div>
                    </div>
                    <div class="space-y-4">''' + cards_html + '''</div>
                </div>
            </div>
            <div class="space-y-5"> 
                <div class="rounded-2xl border border-slate-200/80 bg-white/95 p-5 shadow-sm"> 
                    <div class="mb-4 flex items-center justify-between"><h3 class="text-base font-semibold text-slate-900">安装包概览</h3><a href="/download-center" class="text-xs font-medium text-indigo-600 hover:underline">查看下载中心</a></div>
                    <div class="grid grid-cols-2 gap-2"> 
                        <a href="/download-center?platform=android" class="rounded-2xl border border-slate-200 px-4 py-4 transition hover:bg-slate-50"><p class="text-xs text-slate-500">Android 包</p><p class="mt-2 text-3xl font-semibold text-slate-900">''' + str(package_counts.get('android', 0)) + '''</p><p class="mt-1 text-xs text-slate-400">可公开或内部分发</p></a>
                        <a href="/download-center?platform=ios" class="rounded-2xl border border-slate-200 px-4 py-4 transition hover:bg-slate-50"><p class="text-xs text-slate-500">iOS 包</p><p class="mt-2 text-3xl font-semibold text-slate-900">''' + str(package_counts.get('ios', 0)) + '''</p><p class="mt-1 text-xs text-slate-400">用于 TestFlight 或企业分发</p></a>
                    </div>
                </div>
                <div class="rounded-2xl border border-slate-200/80 bg-white/95 p-5 shadow-sm"> 
                    <div class="mb-4 flex items-center justify-between"><h3 class="text-base font-semibold text-slate-900">发布风险提醒</h3><a href="/admin/projects" class="text-xs font-medium text-indigo-600 hover:underline">查看项目</a></div>
                    <ul class="space-y-3">''' + risk_html + '''</ul>
                </div>
                <div class="rounded-2xl border border-slate-200/80 bg-white/95 p-5 shadow-sm"> 
                    <div class="mb-4 flex items-center justify-between"><h3 class="text-base font-semibold text-slate-900">最近审计记录</h3><a href="/admin/audit-log" class="text-xs font-medium text-indigo-600 hover:underline">查看全部</a></div>
                    <ul class="space-y-3">''' + audit_html + '''</ul>
                </div>
            </div>
        </div>
        <div class="rounded-2xl border border-slate-200/80 bg-white/95 p-5 shadow-sm"> 
            <div class="mb-4 flex flex-wrap items-center justify-between gap-2"> 
                <div>
                    <h3 class="text-base font-semibold text-slate-900">最近安装包</h3>
                    <p class="mt-1 text-sm text-slate-500">帮助你快速确认最近上传的 Android 和 iOS 包。</p>
                </div>
                <a href="/admin/versions" class="text-xs font-medium text-indigo-600 hover:underline">查看版本中心</a>
            </div>
            <div class="overflow-x-auto"><table class="min-w-full"><thead><tr class="border-b border-slate-200 text-left text-xs text-slate-500"><th class="px-4 py-2">项目</th><th class="px-4 py-2">版本</th><th class="px-4 py-2">平台</th><th class="px-4 py-2">上传时间</th></tr></thead><tbody>''' + recent_package_rows + '''</tbody></table></div>
        </div>
    </section>
    '''


@bp.route('/admin/search')
@login_required
def admin_search():
    """全局搜索：项目、任务、用户。"""
    q = (request.args.get('q') or '').strip()[:80]
    username = _current_username()
    results = {'projects': [], 'tasks': [], 'users': []}
    if q:
        ql = q.lower()
        for pid, p in projects_db.items():
            if not can_view_project(pid, username):
                continue
            if ql in (pid or '').lower() or ql in (p.get('name') or '').lower() or ql in (p.get('name_en') or '').lower() or ql in (p.get('intro') or '').lower():
                results['projects'].append({'id': pid, 'name': p.get('name', pid), 'link': '/admin/projects/%s/tasks' % pid})
        for pid, tasks in project_tasks_db.items():
            if not can_view_project(pid, username):
                continue
            for t in (tasks or []):
                if ql in (t.get('title') or '').lower() or ql in (t.get('content') or '').lower():
                    results['tasks'].append({
                        'id': t.get('id'), 'project_id': pid, 'title': (t.get('title') or '')[:60],
                        'link': '/admin/projects/%s/tasks' % pid,
                    })
        if can_edit_project(next(iter(projects_db.keys()), ''), username) or (users_db.get(username) or {}).get('role') in ('admin', 'super_admin'):
            for uname in users_db:
                if ql in (uname or '').lower():
                    results['users'].append({'id': uname, 'link': '/admin/users'})
    proj_rows = ''.join('<tr><td class="px-4 py-2"><a href="%s" class="text-indigo-600 hover:underline">%s</a></td><td class="px-4 py-1.5 text-sm text-gray-500">%s</td></tr>' % (html.escape(p['link']), html.escape(p['name']), html.escape(p['id'])) for p in results['projects'][:20])
    task_rows = ''.join('<tr><td class="px-4 py-2"><a href="%s" class="text-indigo-600 hover:underline">%s</a></td><td class="px-4 py-1.5 text-sm">%s</td></tr>' % (html.escape(t['link']), html.escape(t['title']), html.escape(t['project_id'])) for t in results['tasks'][:20])
    user_rows = ''.join('<tr><td class="px-4 py-2"><a href="%s" class="text-indigo-600 hover:underline">%s</a></td></tr>' % (html.escape(u['link']), html.escape(u['id'])) for u in results['users'][:20])
    content = '''
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <form method="get" action="/admin/search" class="p-4 border-b flex gap-2">
            <input type="text" name="q" value="''' + html.escape(q) + '''" placeholder="搜索项目、任务、用户…" class="flex-1 px-4 py-1.5 border border-gray-200 rounded-lg text-sm">
            <button type="submit" class="px-4 py-1.5 bg-indigo-600 text-white rounded-lg text-sm font-medium">搜索</button>
        </form>
        <div class="p-3 grid grid-cols-1 md:grid-cols-3 gap-4">
            <div><h3 class="font-semibold text-gray-800 mb-2">项目</h3><table class="min-w-full text-sm">''' + (proj_rows or '<tr><td class="px-4 py-2 text-gray-500">无结果</td></tr>') + '''</table></div>
            <div><h3 class="font-semibold text-gray-800 mb-2">任务</h3><table class="min-w-full text-sm">''' + (task_rows or '<tr><td class="px-4 py-2 text-gray-500">无结果</td></tr>') + '''</table></div>
            <div><h3 class="font-semibold text-gray-800 mb-2">用户</h3><table class="min-w-full text-sm">''' + (user_rows or '<tr><td class="px-4 py-2 text-gray-500">无结果</td></tr>') + '''</table></div>
        </div>
    </div>'''
    return _admin_layout(content, '全局搜索', back_href='/admin')
# 页面主入口：admin 面板首页（项目优先导航）。数据来源：projects_db / 审批与通知聚合。
@bp.route('/admin')
@admin_required()
def admin_panel():
    visible = get_visible_modules()
    desc = _admin_panel_descriptions()
    return _admin_panel_dashboard(visible, desc)


def _admin_panel_dashboard(visible, desc):
    username = _current_username()
    package_counts = {'android': 0, 'ios': 0}
    recent_packages = []
    for filename, filepath in iter_package_files():
        info = extract_package_info(filename, filepath)
        package_counts[info.get('platform', 'android')] = package_counts.get(info.get('platform', 'android'), 0) + 1
        recent_packages.append(info)
    recent_packages.sort(key=lambda item: item.get('timestamp', 0), reverse=True)

    visible_project_ids = [pid for pid in projects_db.keys() if can_view_project(pid, username)]
    pending_approvals = get_pending_approvals_for_user(username)
    user_notifications = get_notifications_for_user(username, limit=20)
    unread_notifications = [n for n in user_notifications if not n.get('read_at')]
    overdue_tasks = []
    missing_package_versions = []
    recommended_gaps = []
    for project_id in visible_project_ids:
        versions = project_versions_db.get(project_id) or []
        recommended_exists = False
        for version in versions:
            if version_is_recommended(project_id, version):
                recommended_exists = True
            if not version_has_apk(project_id, version):
                missing_package_versions.append({
                    'project_id': project_id,
                    'version_name': version.get('version_name') or version.get('version_code') or '未命名版本',
                    'platform_label': get_platform_label(get_version_platform(version)),
                })
        if versions and not recommended_exists:
            recommended_gaps.append(project_id)
        for task in (project_tasks_db.get(project_id) or []):
            current_assignee = task.get('current_assignee') or ''
            end_time = (task.get('end_time') or '')[:10]
            if current_assignee == username and end_time and task.get('status') not in ('done', 'abandoned'):
                try:
                    if date.fromisoformat(end_time) < date.today():
                        overdue_tasks.append(dict(task, project_id=project_id))
                except ValueError:
                    pass

    recent_audit = list(reversed(audit_log_db))[:6]
    jenkins_instances = load_jenkins_instances()
    running_jenkins = [inst for inst in jenkins_instances if (inst.get('status') or '').lower() == 'running']

    module_order = {
        'projects': 10,
        'versions': 20,
        'build': 30,
        'gm_ops': 40,
        'approval': 50,
        'notifications': 60,
        'reports': 70,
        'audit_log': 80,
        'system_settings': 90,
        'user_management': 100,
    }
    visible_sorted = sorted(visible, key=lambda item: (module_order.get(item[0], 999), item[1]))
    grouped_cards = {
        'project': [],
        'governance': [],
        'system': [],
    }

    project_title = '项目工作台'
    governance_title = '全局审计'
    system_title = '系统配置'

    grouped_cards['project'].append(
        _render_module_card('/admin/projects', 'fa-folder-tree', 'text-green-600', '项目管理总览', '创建/编辑项目，并从项目列表进入各项目工作台。')
    )
    grouped_cards['project'].append(
        _render_module_card('/admin/my-tasks', 'fa-list-check', 'text-indigo-600', '我的任务', '查看与处理分配给我的项目任务。')
    )
    if any(mid in ('jenkins', 'build') for mid, _, _ in visible_sorted):
        grouped_cards['project'].append(
            _render_module_card('/admin/jenkins', 'fa-server', 'text-orange-600', 'Jenkins 实例管理', '创建/维护 Jenkins 实例与构建可用性。')
        )
        grouped_cards['project'].append(
            _render_module_card('/admin/jenkins#unity-catalog', 'fa-cube', 'text-violet-600', 'Unity 版本库', '在 Jenkins 管理内维护有效/失效、分类与备注；供构建与版本编辑下拉选用。')
        )

    if any(mid == 'approval' for mid, _, _ in visible_sorted):
        grouped_cards['governance'].append(_render_module_card('/admin/approval', 'fa-check-double', 'text-emerald-500', '审批与发布管控', desc.get('approval', '')))
    if any(mid == 'notifications' for mid, _, _ in visible_sorted):
        grouped_cards['governance'].append(_render_module_card('/admin/notifications', 'fa-bell', 'text-amber-500', '通知与消息中心', desc.get('notifications', '')))
    if any(mid == 'reports' for mid, _, _ in visible_sorted):
        grouped_cards['governance'].append(_render_module_card('/admin/reports', 'fa-file-alt', 'text-cyan-500', '报表与证据包', '质量门禁、闭环证据、导出追踪。'))
    if any(mid == 'audit_log' for mid, _, _ in visible_sorted):
        grouped_cards['governance'].append(_render_module_card('/admin/audit-log', 'fa-history', 'text-gray-500', '审计与安全日志', desc.get('audit_log', '')))

    grouped_cards['system'].append(_render_module_card('/admin/site-config', 'fa-swatchbook', 'text-fuchsia-500', '官网与外部模块配置', '统一维护公司简介、玩家官网、开发者官网与外部入口'))
    grouped_cards['system'].append(_render_module_card('/admin/settings', 'fa-cog', 'text-slate-500', '系统与安全设置', '系统开关、策略、Webhook、安全参数与权限治理。'))
    grouped_cards['system'].append(_render_module_card('/workspace', 'fa-briefcase', 'text-amber-500', '个人工作区', '处理个人文件、截图、书签和协作资料'))

    cards = _render_grouped_admin_sections([
        ('项目工作台', '先选择项目，再进入该项目的构建、发布、GM运营、后端运维。', grouped_cards.get('project')),
        ('全局审计', '审批、通知、报表、审计回放等跨项目治理能力。', grouped_cards.get('governance')),
        ('系统配置', '系统级配置与账号安全能力，不承载项目执行动作。', grouped_cards.get('system')),
    ])
    summary_cards = [
        ('可见项目', len(visible_project_ids), 'fa-folder-tree', 'bg-emerald-100', 'text-emerald-700'),
        ('安装包总数', sum(package_counts.values()), 'fa-mobile-screen', 'bg-indigo-100', 'text-indigo-700'),
        ('待处理事项', len(pending_approvals) + len(unread_notifications) + len(overdue_tasks), 'fa-bell', 'bg-amber-100', 'text-amber-700'),
        ('运行中 Jenkins', len(running_jenkins), 'fa-server', 'bg-cyan-100', 'text-cyan-700'),
    ]
    quick_actions = []
    if pending_approvals:
        quick_actions.append(f'<a href="/admin/approval" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-amber-50 text-amber-800 border border-amber-100 text-sm font-medium hover:bg-amber-100">待审批 {len(pending_approvals)} 项</a>')
    if unread_notifications:
        quick_actions.append(f'<a href="/admin/notifications" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-sky-50 text-sky-800 border border-sky-100 text-sm font-medium hover:bg-sky-100">未读通知 {len(unread_notifications)} 条</a>')
    if overdue_tasks:
        quick_actions.append(f'<a href="/admin/my-tasks?quick=overdue" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-rose-50 text-rose-800 border border-rose-100 text-sm font-medium hover:bg-rose-100">超时任务 {len(overdue_tasks)} 条</a>')
    if missing_package_versions:
        quick_actions.append(f'<a href="/admin/projects" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-violet-50 text-violet-800 border border-violet-100 text-sm font-medium hover:bg-violet-100">缺安装包版本 {len(missing_package_versions)} 个</a>')

    recent_package_rows = ''.join(
        f'<tr><td class="px-4 py-3 text-sm font-medium text-slate-800">{html_module.escape(item["basename"])}</td>'
        f'<td class="px-4 py-3 text-sm text-slate-500">{html_module.escape(item["platform_label"])}</td>'
        f'<td class="px-4 py-3 text-sm text-slate-500">{item["size_mb"]} MB</td>'
        f'<td class="px-4 py-3 text-sm text-slate-500">{html_module.escape(item["date"])}</td></tr>'
        for item in recent_packages[:6]
    ) or '<tr><td colspan="4" class="px-4 py-6 text-center text-sm text-slate-500">暂无安装包</td></tr>'
    todo_html = ''.join(
        f'<li class="flex items-start justify-between gap-2"><span class="text-sm text-slate-700">审批：{html_module.escape(item.get("type",""))} / {html_module.escape(item.get("target_id",""))}</span><a href="/admin/approval" class="text-xs text-indigo-600 hover:underline">去处理</a></li>'
        for item in pending_approvals[:3]
    )
    todo_html += ''.join(
        f'<li class="flex items-start justify-between gap-2"><span class="text-sm text-slate-700">超时任务：{html_module.escape(_clean_display_text(item.get("title"), "未命名任务"))}</span><a href="/admin/my-tasks?quick=overdue" class="text-xs text-indigo-600 hover:underline">去处理</a></li>'
        for item in overdue_tasks[:3]
    )
    todo_html += ''.join(
        f'<li class="flex items-start justify-between gap-2"><span class="text-sm text-slate-700">通知：{html_module.escape(_clean_display_text(item.get("title"), "未命名通知"))}</span><a href="/admin/notifications" class="text-xs text-indigo-600 hover:underline">查看</a></li>'
        for item in unread_notifications[:2]
    )
    if not todo_html:
        todo_html = '<li class="text-sm text-slate-500">当前没有待处理事项</li>'
    risk_html = ''.join(
        f'<li class="flex items-start justify-between gap-2"><span class="text-sm text-slate-700">{html_module.escape(item["project_id"])} / {html_module.escape(item["version_name"])}</span><span class="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-600">{html_module.escape(item["platform_label"])}</span></li>'
        for item in missing_package_versions[:4]
    )
    risk_html += ''.join(
        f'<li class="flex items-start justify-between gap-2"><span class="text-sm text-slate-700">{html_module.escape(project_id)} 缺少推荐版本</span><span class="text-xs px-2 py-0.5 rounded bg-amber-100 text-amber-700">建议处理</span></li>'
        for project_id in recommended_gaps[:4]
    )
    if not risk_html:
        risk_html = '<li class="text-sm text-slate-500">当前没有明显版本风险</li>'
    audit_html = ''.join(
        f'<li class="flex items-start justify-between gap-2"><div><p class="text-sm font-medium text-slate-800">{html_module.escape(_clean_display_text(entry.get("action"), "系统操作"))}</p><p class="text-xs text-slate-500">{html_module.escape(_clean_display_text(entry.get("user"), "-"))} · {html_module.escape((entry.get("at") or entry.get("timestamp") or "")[:16])}</p></div><span class="text-xs text-slate-400 max-w-[200px] truncate">{html_module.escape(_clean_display_text(entry.get("details"), "无附加说明")[:40])}</span></li>'
        for entry in recent_audit
    ) or '<li class="text-sm text-slate-500">暂无审计记录</li>'

    return _admin_layout(
        _render_admin_dashboard_v2(
            summary_cards,
            quick_actions,
            todo_html,
            risk_html,
            audit_html,
            recent_package_rows,
            package_counts,
            cards,
        ),
        '管理中心',
        back_href='/',
    )


@bp.route('/admin/site-config')
@admin_required()
def admin_site_config_page():
    company = get_company_profile()
    player_portal = get_player_portal_content()
    dev_portal = get_dev_portal_content()
    def _safe(value, fallback=""):
        return html.escape(_clean_display_text(value, fallback))

    def _parse_ids(value):
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return [v.strip() for v in str(value or "").split(",") if v.strip()]

    def _render_product_options(selected_ids):
        options = []
        for product in (products_db if isinstance(products_db, list) else []):
            pid = str(product.get("id") or "").strip()
            if not pid:
                continue
            label = _clean_display_text(product.get("name") or product.get("title") or pid, pid)
            selected = " selected" if pid in selected_ids else ""
            options.append(f'<option value="{html.escape(pid)}"{selected}>{html.escape(label)}</option>')
        if not options:
            options.append('<option value="" disabled>暂无产品</option>')
        return ''.join(options)

    default_player_modules = [
        {"type": "hero", "title": "Hero", "enabled": True, "order": 0, "size": "full"},
        {"type": "products", "title": "产品入口", "enabled": True, "order": 1},
        {"type": "news", "title": "新闻公告", "enabled": True, "order": 2},
        {"type": "welfare", "title": "福利中心", "enabled": True, "order": 3},
        {"type": "forum", "title": "玩家论坛", "enabled": True, "order": 4},
        {"type": "company", "title": "公司简介", "enabled": True, "order": 5},
        {"type": "media", "title": "视觉展示", "enabled": True, "order": 6},
        {"type": "timeline", "title": "公司历程", "enabled": True, "order": 7},
    ]
    default_dev_modules = [
        {"type": "hero", "title": "Hero", "enabled": True, "order": 0, "size": "full"},
        {"type": "products", "title": "产品入口", "enabled": True, "order": 1},
        {"type": "company", "title": "公司简介", "enabled": True, "order": 2},
        {"type": "media", "title": "视觉展示", "enabled": True, "order": 3},
        {"type": "timeline", "title": "公司历程", "enabled": True, "order": 4},
    ]

    def _normalize_modules(modules, defaults):
        if isinstance(modules, list) and modules:
            cleaned = []
            for item in modules:
                if not isinstance(item, dict):
                    continue
                if not str(item.get("type") or "").strip():
                    continue
                cleaned.append(item)
            if cleaned:
                return cleaned
        return defaults

    module_types = [
        ("hero", "Hero"),
        ("products", "产品入口"),
        ("news", "新闻公告"),
        ("welfare", "福利中心"),
        ("forum", "玩家论坛"),
        ("company", "公司简介"),
        ("media", "视觉展示"),
        ("timeline", "公司历程"),
        ("image", "Image"),
        ("video", "Video"),
        ("text", "Text"),
        ("stat", "Stat"),
    ]

    def _module_type_options(selected):
        return ''.join(
            f'<option value="{mid}"{" selected" if mid == selected else ""}>{label}</option>'
            for mid, label in module_types
        )

    def _size_options(selected):
        sizes = [("full", "整行"), ("half", "半屏"), ("third", "三分之一")]
        return ''.join(
            f'<option value="{val}"{" selected" if val == selected else ""}>{label}</option>'
            for val, label in sizes
        )

    def _render_module_rows(modules):
        rows = []
        for idx, module in enumerate(modules):
            mtype = str(module.get("type") or "products")
            title = html.escape(str(module.get("title") or ""))
            description = html.escape(str(module.get("description") or ""))
            enabled = "checked" if module.get("enabled", True) else ""
            order = module.get("order", idx + 1)
            size = str(module.get("size") or "full")
            limit = module.get("limit", "")
            source = html.escape(str(module.get("source") or ""))
            image_url = html.escape(normalize_local_media_url(module.get("image_url")))
            video_url = html.escape(normalize_local_media_url(module.get("video_url")))
            media_urls = normalize_local_media_urls(module.get("media_urls") or [], max_count=12)
            media_urls = html.escape(", ".join(media_urls))
            cta_text = html.escape(str(module.get("cta_text") or ""))
            cta_link = html.escape(str(module.get("cta_link") or ""))
            rows.append(
                f'''
                <div class="rounded-2xl border border-slate-200 bg-white p-4 space-y-3 cursor-move" data-module-row draggable="true">
                    <div class="grid gap-3 md:grid-cols-2">
                        <div>
                            <label class="text-xs font-semibold text-slate-500">模块类型</label>
                            <select class="module-type mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm">{_module_type_options(mtype)}</select>
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">模块标题</label>
                            <input type="text" value="{title}" class="module-title mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" placeholder="展示标题">
                        </div>
                    </div>
                    <div class="grid gap-3 md:grid-cols-3">
                        <div>
                            <label class="text-xs font-semibold text-slate-500">显示</label>
                            <div class="mt-2 flex items-center gap-2">
                                <input type="checkbox" class="module-enabled" {enabled}>
                                <span class="text-xs text-slate-500">启用</span>
                            </div>
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">排序</label>
                            <input type="number" value="{order}" min="1" class="module-order mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm">
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">数量限制</label>
                            <input type="number" value="{limit}" min="1" class="module-limit mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" placeholder="可选">
                        </div>
                    </div>
                    <div>
                        <label class="text-xs font-semibold text-slate-500">模块描述</label>
                        <textarea class="module-description mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" rows="2" placeholder="模块说明">{description}</textarea>
                    </div>
                    <div class="grid gap-3 md:grid-cols-2">
                        <div>
                            <label class="text-xs font-semibold text-slate-500">样式</label>
                            <select class="module-size mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm">{_size_options(size)}</select>
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">数据来源</label>
                            <input type="text" value="{source}" class="module-source mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" placeholder="如 latest / featured">
                        </div>
                    </div>
                    <div class="grid gap-3 md:grid-cols-2">
                        <div>
                            <label class="text-xs font-semibold text-slate-500">本地图片</label>
                            <input type="text" value="{image_url}" class="module-image-url mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" placeholder="上传后自动填充本地路径" readonly>
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">本地视频</label>
                            <input type="text" value="{video_url}" class="module-video-url mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" placeholder="上传后自动填充本地路径" readonly>
                        </div>
                    </div>
                    <div>
                        <label class="text-xs font-semibold text-slate-500">本地图集</label>
                        <textarea class="module-media-urls mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" rows="2" placeholder="上传后自动填充本地路径，支持多张" readonly>{media_urls}</textarea>
                    </div>
                    <div class="grid gap-3 md:grid-cols-2">
                        <div>
                            <label class="text-xs font-semibold text-slate-500">CTA 文案</label>
                            <input type="text" value="{cta_text}" class="module-cta-text mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" placeholder="按钮文案">
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">CTA 链接</label>
                            <input type="text" value="{cta_link}" class="module-cta-link mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" placeholder="按钮链接">
                        </div>
                    </div>
                    <div class="flex items-center justify-between text-xs text-slate-400">
                        <span>拖动卡片可调整模块顺序</span>
                        <button type="button" class="remove-module text-rose-500 hover:text-rose-600">移除</button>
                    </div>
                </div>
                '''
            )
        return ''.join(rows)

    player_modules = _normalize_modules(player_portal.get("home_modules"), default_player_modules)
    dev_modules = _normalize_modules(dev_portal.get("home_modules"), default_dev_modules)
    player_featured_ids = _parse_ids(player_portal.get("featured_product_ids"))
    player_visible_ids = _parse_ids(player_portal.get("visible_product_ids"))
    dev_featured_ids = _parse_ids(dev_portal.get("featured_product_ids"))
    dev_visible_ids = _parse_ids(dev_portal.get("visible_product_ids"))
    timeline_json = html.escape(json.dumps(company.get('timeline', []), ensure_ascii=False, indent=2))
    achievements_json = html.escape(json.dumps(company.get('achievements', []), ensure_ascii=False, indent=2))
    player_options = _render_product_options(player_visible_ids)
    player_featured_options = _render_product_options(player_featured_ids)
    dev_options = _render_product_options(dev_visible_ids)
    dev_featured_options = _render_product_options(dev_featured_ids)
    template_row = _render_module_rows([{"type": "products", "title": "", "enabled": True, "order": 1, "size": "full"}])
    content = f"""
    <section class="space-y-6">
        <div class="flex items-end justify-between gap-4">
            <div>
                <p class="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">\u914d\u7f6e\u4e2d\u5fc3</p>
                <h2 class="mt-1 text-2xl font-semibold text-slate-900">\u5b98\u7f51\u4e0e\u5916\u90e8\u6a21\u5757\u914d\u7f6e</h2>
                <p class="mt-1 text-sm text-slate-500">\u5c06\u516c\u53f8\u7b80\u4ecb\u3001\u73a9\u5bb6\u5b98\u7f51\u3001\u5f00\u53d1\u8005\u5b98\u7f51\u548c\u5916\u90e8\u5165\u53e3\u7edf\u4e00\u6536\u53e3\uff0c\u907f\u514d\u7ad9\u70b9\u914d\u7f6e\u548c\u5185\u5bb9\u8fd0\u8425\u6df7\u5728\u4e00\u8d77\u3002</p>
            </div>
            <div class="flex items-center gap-2">
                <a href="/admin/site-config/editor/player" class="rounded-xl border border-violet-200 bg-violet-50 px-4 py-1.5 text-sm font-semibold text-violet-700">\u73a9\u5bb6\u5b98\u7f51\u53ef\u89c6\u5316\u7f16\u8f91\u5668</a>
                <a href="/admin/site-config/editor/dev" class="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-1.5 text-sm font-semibold text-emerald-700">\u5f00\u53d1\u8005\u5b98\u7f51\u53ef\u89c6\u5316\u7f16\u8f91\u5668</a>
                <a href="/admin" class="rounded-xl border border-slate-200 bg-white px-4 py-1.5 text-sm font-medium text-slate-700">\u8fd4\u56de\u7ba1\u7406\u4e2d\u5fc3</a>
            </div>
        </div>
        <div class="grid gap-6 xl:grid-cols-3">
            <form id="companyProfileForm" class="space-y-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 class="text-lg font-semibold text-slate-900">\u516c\u53f8\u7b80\u4ecb\u9875</h3>
                <input name="company_name" value="{_safe(company.get('company_name'), '星云游戏站')}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u516c\u53f8\u540d\u79f0">
                <input name="hero_eyebrow" value="{_safe(company.get('hero_eyebrow'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u7709\u6807\u6807\u9898">
                <textarea name="hero_title" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="3" placeholder="\u4e3b\u6807\u9898">{_safe(company.get('hero_title'))}</textarea>
                <textarea name="hero_summary" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="4" placeholder="\u54c1\u724c\u6458\u8981">{_safe(company.get('hero_summary'))}</textarea>
                <textarea name="company_intro" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="5" placeholder="\u516c\u53f8\u4ecb\u7ecd">{_safe(company.get('company_intro'))}</textarea>
                <input name="mission_title" value="{_safe(company.get('mission_title'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u4f7f\u547d\u6807\u9898">
                <textarea name="mission_body" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="4" placeholder="\u4f7f\u547d\u6b63\u6587">{_safe(company.get('mission_body'))}</textarea>
                <textarea name="timeline_json" class="w-full rounded-2xl border border-slate-200 px-4 py-3 font-mono text-xs" rows="6" placeholder="\u65f6\u95f4\u7ebf JSON">{timeline_json}</textarea>
                <textarea name="achievements_json" class="w-full rounded-2xl border border-slate-200 px-4 py-3 font-mono text-xs" rows="5" placeholder="\u6210\u5c31 JSON">{achievements_json}</textarea>
                <button class="rounded-full bg-slate-900 px-5 py-3 font-bold text-white">\u4fdd\u5b58\u516c\u53f8\u7b80\u4ecb</button>
                <div id="companyProfileResult" class="text-sm text-slate-500"></div>
            </form>
            <form id="playerPortalConfigForm" class="space-y-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 class="text-lg font-semibold text-slate-900">\u73a9\u5bb6\u5b98\u7f51\u914d\u7f6e</h3>
                <input name="site_name" value="{_safe(player_portal.get('site_name'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u7ad9\u70b9\u540d\u79f0">
                <input name="site_subtitle" value="{_safe(player_portal.get('site_subtitle'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u526f\u6807\u9898">
                <input name="logo_icon" value="{_safe(player_portal.get('logo_icon'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="Logo \u56fe\u6807">
                <input name="hero_image_url" value="{_safe(player_portal.get('hero_image_url'))}" class="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3" placeholder="Hero \u672c\u5730\u56fe\u7247\u8def\u5f84\uff08\u4e0a\u4f20\u540e\u81ea\u52a8\u586b\u5199\uff09" readonly>
                <input name="hero_video_url" value="{_safe(player_portal.get('hero_video_url'))}" class="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3" placeholder="Hero \u672c\u5730\u89c6\u9891\u8def\u5f84\uff08\u4e0a\u4f20\u540e\u81ea\u52a8\u586b\u5199\uff09" readonly>
                <textarea name="hero_gallery_urls" class="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3" rows="2" placeholder="Hero \u672c\u5730\u56fe\u96c6\u8def\u5f84\uff08\u4e0a\u4f20\u540e\u81ea\u52a8\u586b\u5199\uff09" readonly>{_safe(",".join(player_portal.get('hero_gallery_urls') or []))}</textarea>
                <p class="text-xs text-slate-500">\u8bf4\u660e\uff1a\u8fd9\u91cc\u53ea\u5141\u8bb8\u672c\u5730\u4e0a\u4f20\u5a92\u4f53\uff0c\u5916\u94fe URL \u4f1a\u88ab\u540e\u7aef\u81ea\u52a8\u8fc7\u6ee4\u3002</p>
                <input name="nav_about" value="{_safe(player_portal.get('nav_about'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u516c\u53f8\u7b80\u4ecb\u5bfc\u822a\u6587\u6848">
                <input name="nav_games" value="{_safe(player_portal.get('nav_games'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u6e38\u620f\u4ea7\u54c1\u5bfc\u822a\u6587\u6848">
                <textarea name="hero_title" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="3" placeholder="Hero \u6807\u9898">{_safe(player_portal.get('hero_title'))}</textarea>
                <textarea name="hero_description" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="4" placeholder="Hero \u63cf\u8ff0">{_safe(player_portal.get('hero_description'))}</textarea>
                <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">\u4ea7\u54c1\u5c55\u793a\u8303\u56f4</p>
                    <div class="mt-3 space-y-3">
                        <div>
                            <label class="text-xs font-semibold text-slate-500">\u5c55\u793a\u4ea7\u54c1\uff08\u591a\u9009\uff09</label>
                            <select name="visible_product_ids" multiple class="mt-2 h-28 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm">{player_options}</select>
                            <p class="mt-2 text-xs text-slate-500">\u672a\u9009\u62e9\u5219\u5c55\u793a\u5168\u90e8\u9879\u76ee</p>
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">\u4e3b\u63a8\u4ea7\u54c1\uff08\u591a\u9009\uff09</label>
                            <select name="featured_product_ids" multiple class="mt-2 h-24 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm">{player_featured_options}</select>
                            <p class="mt-2 text-xs text-slate-500">\u9996\u4e2a\u4e3b\u63a8\u4ea7\u54c1\u5c06\u4f5c\u4e3a\u9996\u9875\u4e3b\u89c6\u89c9</p>
                        </div>
                    </div>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div class="flex items-center justify-between">
                        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">\u9996\u9875\u6a21\u5757\u7f16\u6392</p>
                        <button type="button" class="add-module text-xs font-semibold text-indigo-600">\u6dfb\u52a0\u6a21\u5757</button>
                    </div>
                    <div id="playerModules" class="mt-3 space-y-3">
                        {_render_module_rows(player_modules)}
                    </div>
                </div>
                <button class="rounded-full bg-violet-600 px-5 py-3 font-bold text-white">\u4fdd\u5b58\u73a9\u5bb6\u5b98\u7f51</button>
                <div id="playerPortalConfigResult" class="text-sm text-slate-500"></div>
            </form>
            <form id="devPortalConfigForm" class="space-y-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 class="text-lg font-semibold text-slate-900">\u5f00\u53d1\u8005\u5b98\u7f51\u914d\u7f6e</h3>
                <input name="site_name" value="{_safe(dev_portal.get('site_name'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u7ad9\u70b9\u540d\u79f0">
                <input name="site_subtitle" value="{_safe(dev_portal.get('site_subtitle'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u526f\u6807\u9898">
                <input name="logo_icon" value="{_safe(dev_portal.get('logo_icon'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="Logo \u56fe\u6807">
                <input name="hero_image_url" value="{_safe(dev_portal.get('hero_image_url'))}" class="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3" placeholder="Hero \u672c\u5730\u56fe\u7247\u8def\u5f84\uff08\u4e0a\u4f20\u540e\u81ea\u52a8\u586b\u5199\uff09" readonly>
                <input name="hero_video_url" value="{_safe(dev_portal.get('hero_video_url'))}" class="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3" placeholder="Hero \u672c\u5730\u89c6\u9891\u8def\u5f84\uff08\u4e0a\u4f20\u540e\u81ea\u52a8\u586b\u5199\uff09" readonly>
                <textarea name="hero_gallery_urls" class="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3" rows="2" placeholder="Hero \u672c\u5730\u56fe\u96c6\u8def\u5f84\uff08\u4e0a\u4f20\u540e\u81ea\u52a8\u586b\u5199\uff09" readonly>{_safe(",".join(dev_portal.get('hero_gallery_urls') or []))}</textarea>
                <p class="text-xs text-slate-500">\u8bf4\u660e\uff1a\u8fd9\u91cc\u53ea\u5141\u8bb8\u672c\u5730\u4e0a\u4f20\u5a92\u4f53\uff0c\u5916\u94fe URL \u4f1a\u88ab\u540e\u7aef\u81ea\u52a8\u8fc7\u6ee4\u3002</p>
                <input name="nav_games" value="{_safe(dev_portal.get('nav_games'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u6e38\u620f\u9635\u5bb9\u6587\u6848">
                <input name="nav_showcase" value="{_safe(dev_portal.get('nav_showcase'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u89c6\u89c9\u5c55\u793a\u6587\u6848">
                <input name="nav_news" value="{_safe(dev_portal.get('nav_news'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u65b0\u95fb\u516c\u544a\u6587\u6848">
                <input name="nav_welfare" value="{_safe(dev_portal.get('nav_welfare'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u798f\u5229\u4e2d\u5fc3\u6587\u6848">
                <input name="nav_forum" value="{_safe(dev_portal.get('nav_forum'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u73a9\u5bb6\u8bba\u575b\u6587\u6848">
                <input name="nav_download" value="{_safe(dev_portal.get('nav_download'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u4e0b\u8f7d\u4e2d\u5fc3\u6587\u6848">
                <input name="workspace_badge" value="{_safe(dev_portal.get('workspace_badge'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="Workspace \u6807\u8bc6">
                <textarea name="workspace_title" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="2" placeholder="Workspace \u4e3b\u6807\u9898">{_safe(dev_portal.get('workspace_title'))}</textarea>
                <textarea name="workspace_intro" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="3" placeholder="Workspace \u7b80\u4ecb">{_safe(dev_portal.get('workspace_intro'))}</textarea>
                <textarea name="hero_title" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="3" placeholder="Hero \u6807\u9898">{_safe(dev_portal.get('hero_title'))}</textarea>
                <textarea name="hero_description" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="4" placeholder="Hero \u63cf\u8ff0">{_safe(dev_portal.get('hero_description'))}</textarea>
                <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">\u4ea7\u54c1\u5c55\u793a\u8303\u56f4</p>
                    <div class="mt-3 space-y-3">
                        <div>
                            <label class="text-xs font-semibold text-slate-500">\u5c55\u793a\u4ea7\u54c1\uff08\u591a\u9009\uff09</label>
                            <select name="visible_product_ids" multiple class="mt-2 h-28 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm">{dev_options}</select>
                            <p class="mt-2 text-xs text-slate-500">\u672a\u9009\u62e9\u5219\u5c55\u793a\u5168\u90e8\u9879\u76ee</p>
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">\u4e3b\u63a8\u4ea7\u54c1\uff08\u591a\u9009\uff09</label>
                            <select name="featured_product_ids" multiple class="mt-2 h-24 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm">{dev_featured_options}</select>
                            <p class="mt-2 text-xs text-slate-500">\u9996\u4e2a\u4e3b\u63a8\u4ea7\u54c1\u5c06\u4f5c\u4e3a\u9996\u9875\u4e3b\u89c6\u89c9</p>
                        </div>
                    </div>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div class="flex items-center justify-between">
                        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">\u9996\u9875\u6a21\u5757\u7f16\u6392</p>
                        <button type="button" class="add-module text-xs font-semibold text-indigo-600">\u6dfb\u52a0\u6a21\u5757</button>
                    </div>
                    <div id="devModules" class="mt-3 space-y-3">
                        {_render_module_rows(dev_modules)}
                    </div>
                </div>
                <button class="rounded-full bg-emerald-600 px-5 py-3 font-bold text-white">\u4fdd\u5b58\u5f00\u53d1\u8005\u5b98\u7f51</button>
                <div id="devPortalConfigResult" class="text-sm text-slate-500"></div>
            </form>
        </div>
    </section>
    <script>
    function collectModules(form) {{
        var rows = form.querySelectorAll('[data-module-row]');
        var modules = [];
        rows.forEach(function(row, index) {{
            var type = (row.querySelector('.module-type') || {{}}).value || '';
            if (!type) return;
            var orderValue = parseInt((row.querySelector('.module-order') || {{}}).value || '', 10);
            var limitValue = parseInt((row.querySelector('.module-limit') || {{}}).value || '', 10);
            modules.push({{
                type: type.trim(),
                title: ((row.querySelector('.module-title') || {{}}).value || '').trim(),
                description: ((row.querySelector('.module-description') || {{}}).value || '').trim(),
                enabled: (row.querySelector('.module-enabled') || {{}}).checked,
                order: isNaN(orderValue) ? (index + 1) : orderValue,
                limit: isNaN(limitValue) ? '' : limitValue,
                size: ((row.querySelector('.module-size') || {{}}).value || '').trim(),
                source: ((row.querySelector('.module-source') || {{}}).value || '').trim(),
                image_url: ((row.querySelector('.module-image-url') || {{}}).value || '').trim(),
                video_url: ((row.querySelector('.module-video-url') || {{}}).value || '').trim(),
                media_urls: String(((row.querySelector('.module-media-urls') || {{}}).value || '')).replace(/\\n/g, ',').split(',').map(function(item) {{ return item.trim(); }}).filter(Boolean),
                cta_text: ((row.querySelector('.module-cta-text') || {{}}).value || '').trim(),
                cta_link: ((row.querySelector('.module-cta-link') || {{}}).value || '').trim(),
            }});
        }});
        return modules;
    }}
    function bindModuleEditor(formId, containerId) {{
        var form = document.getElementById(formId);
        var container = document.getElementById(containerId);
        var addBtn = form.querySelector('.add-module');
        var dragging = null;
        function syncOrder() {{
            var rows = container.querySelectorAll('[data-module-row]');
            rows.forEach(function(row, idx) {{
                var orderInput = row.querySelector('.module-order');
                if (orderInput) orderInput.value = idx + 1;
            }});
        }}
        if (addBtn) {{
            addBtn.addEventListener('click', function() {{
                var wrapper = document.createElement('div');
                wrapper.innerHTML = `{template_row}`;
                var row = wrapper.firstElementChild;
                if (row) {{
                    container.appendChild(row);
                    enhanceModuleRow(row, 'portal-module', formId === 'playerPortalConfigForm' ? 'player-portal' : 'dev-portal');
                }}
                syncOrder();
            }});
        }}
        container.addEventListener('click', function(e) {{
            var btn = e.target.closest('.remove-module');
            if (btn) {{
                var row = btn.closest('[data-module-row]');
                if (row) row.remove();
                syncOrder();
            }}
        }});
        container.addEventListener('dragstart', function(e) {{
            var row = e.target.closest('[data-module-row]');
            if (!row) return;
            dragging = row;
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', '');
        }});
        container.addEventListener('dragover', function(e) {{
            if (!dragging) return;
            e.preventDefault();
            var row = e.target.closest('[data-module-row]');
            if (!row || row === dragging) return;
            var rect = row.getBoundingClientRect();
            var next = (e.clientY - rect.top) > rect.height / 2;
            container.insertBefore(dragging, next ? row.nextSibling : row);
        }});
        container.addEventListener('drop', function(e) {{
            if (!dragging) return;
            e.preventDefault();
            dragging = null;
            syncOrder();
        }});
        container.addEventListener('dragend', function() {{
            dragging = null;
            syncOrder();
        }});
    }}
    function collectMultiSelect(form, name) {{
        var select = form.querySelector('select[name="' + name + '"]');
        if (!select) return '';
        var values = [];
        Array.prototype.forEach.call(select.selectedOptions, function(opt) {{
            values.push(opt.value);
        }});
        return values.join(',');
    }}
    function escapeHtmlText(value) {{
        return String(value || '').replace(/[&<>"]/g, function(ch) {{
            return {{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }}[ch] || ch;
        }});
    }}
    function renderMediaPreview(target, urls, kind) {{
        if (!target) return;
        var list = Array.isArray(urls) ? urls.filter(Boolean) : (urls ? [urls] : []);
        if (!list.length) {{
            target.innerHTML = '<div class="text-xs text-slate-400">未选择本地媒体</div>';
            return;
        }}
        target.innerHTML = list.map(function(url) {{
            var safe = escapeHtmlText(url);
            if (kind === 'video') {{
                return '<div class="rounded-xl border border-slate-200 bg-slate-50 p-2"><video src="' + safe + '" controls class="h-32 w-full rounded-lg bg-black object-cover"></video><p class="mt-2 truncate text-[11px] text-slate-500">' + safe + '</p></div>';
            }}
            return '<div class="rounded-xl border border-slate-200 bg-slate-50 p-2"><img src="' + safe + '" class="h-28 w-full rounded-lg object-cover" alt=""><p class="mt-2 truncate text-[11px] text-slate-500">' + safe + '</p></div>';
        }}).join('');
    }}
    function uploadMediaFiles(files, scope, bucket) {{
        var formData = new FormData();
        Array.prototype.forEach.call(files || [], function(file) {{
            formData.append('files', file);
        }});
        formData.append('scope', scope || 'site-config');
        formData.append('bucket', bucket || 'shared');
        return fetch('/admin/media/upload', {{
            method: 'POST',
            body: formData,
            credentials: 'same-origin'
        }}).then(function(r) {{ return r.json(); }});
    }}
    function attachSingleMediaUploader(input, options) {{
        if (!input || input.dataset.uploaderReady === '1') return;
        input.dataset.uploaderReady = '1';
        var kind = options.kind === 'video' ? 'video' : 'image';
        var wrap = document.createElement('div');
        wrap.className = 'mt-2 rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-3';
        wrap.innerHTML = '' +
            '<label class="block text-xs font-semibold text-slate-500">本地' + (kind === 'video' ? '视频' : '图片') + '</label>' +
            '<input type="file" accept="' + (kind === 'video' ? 'video/*' : 'image/*') + '" class="mt-2 block w-full text-sm text-slate-600">' +
            '<div class="mt-3"></div>';
        input.insertAdjacentElement('afterend', wrap);
        var picker = wrap.querySelector('input[type="file"]');
        var preview = wrap.querySelector('div');
        renderMediaPreview(preview, input.value || '', kind);
        picker.addEventListener('change', function() {{
            if (!picker.files || !picker.files.length) return;
            preview.innerHTML = '<div class="text-xs text-slate-500">上传中...</div>';
            uploadMediaFiles(picker.files, options.scope, options.bucket).then(function(data) {{
                if (!data || data.error || !data.file) {{
                    preview.innerHTML = '<div class="text-xs text-rose-500">' + escapeHtmlText((data && data.error) || '上传失败') + '</div>';
                    return;
                }}
                input.value = data.file.url || '';
                renderMediaPreview(preview, input.value || '', kind);
            }});
        }});
    }}
    function attachGalleryUploader(textarea, options) {{
        if (!textarea || textarea.dataset.uploaderReady === '1') return;
        textarea.dataset.uploaderReady = '1';
        var wrap = document.createElement('div');
        wrap.className = 'mt-2 rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-3';
        wrap.innerHTML = '' +
            '<label class="block text-xs font-semibold text-slate-500">本地图集</label>' +
            '<input type="file" accept="image/*" multiple class="mt-2 block w-full text-sm text-slate-600">' +
            '<div class="mt-3 grid gap-3 sm:grid-cols-2"></div>';
        textarea.insertAdjacentElement('afterend', wrap);
        var picker = wrap.querySelector('input[type="file"]');
        var preview = wrap.querySelector('div');
        function readUrls() {{
            return String(textarea.value || '').replace(/\\n/g, ',').split(',').map(function(item) {{ return item.trim(); }}).filter(Boolean);
        }}
        function writeUrls(urls) {{
            textarea.value = (urls || []).join(',');
            renderMediaPreview(preview, urls || [], 'image');
        }}
        writeUrls(readUrls());
        picker.addEventListener('change', function() {{
            if (!picker.files || !picker.files.length) return;
            preview.innerHTML = '<div class="text-xs text-slate-500">上传中...</div>';
            uploadMediaFiles(picker.files, options.scope, options.bucket).then(function(data) {{
                if (!data || data.error || !data.files) {{
                    preview.innerHTML = '<div class="text-xs text-rose-500">' + escapeHtmlText((data && data.error) || '上传失败') + '</div>';
                    return;
                }}
                var urls = readUrls().concat((data.files || []).map(function(item) {{ return item.url; }}).filter(Boolean));
                writeUrls(urls);
            }});
        }});
    }}
    function enhanceModuleRow(row, scope, bucket) {{
        if (!row || row.dataset.mediaReady === '1') return;
        row.dataset.mediaReady = '1';
        attachSingleMediaUploader(row.querySelector('.module-image-url'), {{ kind: 'image', scope: scope, bucket: bucket }});
        attachSingleMediaUploader(row.querySelector('.module-video-url'), {{ kind: 'video', scope: scope, bucket: bucket }});
        attachGalleryUploader(row.querySelector('.module-media-urls'), {{ scope: scope, bucket: bucket }});
    }}
    function enhancePortalForm(formId, bucket) {{
        var form = document.getElementById(formId);
        if (!form) return;
        attachSingleMediaUploader(form.querySelector('[name="hero_image_url"]'), {{ kind: 'image', scope: 'portal', bucket: bucket }});
        attachSingleMediaUploader(form.querySelector('[name="hero_video_url"]'), {{ kind: 'video', scope: 'portal', bucket: bucket }});
        attachGalleryUploader(form.querySelector('[name="hero_gallery_urls"]'), {{ scope: 'portal', bucket: bucket }});
        form.querySelectorAll('[data-module-row]').forEach(function(row) {{
            enhanceModuleRow(row, 'portal-module', bucket);
        }});
    }}
    function bindSiteConfigForm(formId, endpoint, resultId, transform) {{
        var form = document.getElementById(formId);
        form.addEventListener('submit', function(e) {{
            e.preventDefault();
            var fd = new FormData(form);
            var payload = transform(fd, form);
            fetch(endpoint, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                credentials: 'same-origin',
                body: JSON.stringify(payload)
            }}).then(function(r) {{ return r.json(); }}).then(function(d) {{
                document.getElementById(resultId).textContent = d.error || '\u5df2\u4fdd\u5b58\uff0c\u5237\u65b0\u540e\u53ef\u67e5\u770b\u6700\u65b0\u6548\u679c';
            }});
        }});
    }}
    bindModuleEditor('playerPortalConfigForm', 'playerModules');
    bindModuleEditor('devPortalConfigForm', 'devModules');
    enhancePortalForm('playerPortalConfigForm', 'player-portal');
    enhancePortalForm('devPortalConfigForm', 'dev-portal');
    bindSiteConfigForm('companyProfileForm', '/admin/site-config/company', 'companyProfileResult', function(fd) {{
        var timeline = [];
        var achievements = [];
        try {{ timeline = JSON.parse(fd.get('timeline_json') || '[]'); }} catch (e) {{}}
        try {{ achievements = JSON.parse(fd.get('achievements_json') || '[]'); }} catch (e) {{}}
        return {{
            company_name: fd.get('company_name') || '',
            hero_eyebrow: fd.get('hero_eyebrow') || '',
            hero_title: fd.get('hero_title') || '',
            hero_summary: fd.get('hero_summary') || '',
            company_intro: fd.get('company_intro') || '',
            mission_title: fd.get('mission_title') || '',
            mission_body: fd.get('mission_body') || '',
            timeline: timeline,
            achievements: achievements
        }};
    }});
    bindSiteConfigForm('playerPortalConfigForm', '/admin/site-config/portal/player', 'playerPortalConfigResult', function(fd, form) {{
        var payload = Object.fromEntries(fd.entries());
        payload.visible_product_ids = collectMultiSelect(form, 'visible_product_ids');
        payload.featured_product_ids = collectMultiSelect(form, 'featured_product_ids');
        payload.hero_gallery_urls = String(fd.get('hero_gallery_urls') || '').replace(/\\n/g, ',').split(',').map(function(item) {{ return item.trim(); }}).filter(Boolean);
        payload.home_modules = collectModules(form);
        return payload;
    }});
    bindSiteConfigForm('devPortalConfigForm', '/admin/site-config/portal/dev', 'devPortalConfigResult', function(fd, form) {{
        var payload = Object.fromEntries(fd.entries());
        payload.visible_product_ids = collectMultiSelect(form, 'visible_product_ids');
        payload.featured_product_ids = collectMultiSelect(form, 'featured_product_ids');
        payload.hero_gallery_urls = String(fd.get('hero_gallery_urls') || '').replace(/\\n/g, ',').split(',').map(function(item) {{ return item.trim(); }}).filter(Boolean);
        payload.home_modules = collectModules(form);
        return payload;
    }});
    </script>
    """
    return _admin_layout(content, '\u5b98\u7f51\u4e0e\u5916\u90e8\u6a21\u5757\u914d\u7f6e', back_href='/admin')


def _visual_editor_default_modules(portal_kind):
    if portal_kind == 'player':
        return [
            {"type": "hero", "title": "首页主视觉", "enabled": True, "order": 1},
            {"type": "products", "title": "游戏产品", "enabled": True, "order": 2},
            {"type": "news", "title": "新闻公告", "enabled": True, "order": 3},
            {"type": "welfare", "title": "福利中心", "enabled": True, "order": 4},
            {"type": "forum", "title": "玩家论坛", "enabled": True, "order": 5},
            {"type": "company", "title": "公司简介", "enabled": True, "order": 6},
            {"type": "media", "title": "视觉展示", "enabled": True, "order": 7},
            {"type": "timeline", "title": "公司历程", "enabled": True, "order": 8},
        ]
    return [
        {"type": "hero", "title": "首页主视觉", "enabled": True, "order": 1},
        {"type": "products", "title": "产品矩阵", "enabled": True, "order": 2},
        {"type": "company", "title": "品牌介绍", "enabled": True, "order": 3},
        {"type": "media", "title": "视觉展示", "enabled": True, "order": 4},
        {"type": "timeline", "title": "发展历程", "enabled": True, "order": 5},
    ]


def _visual_editor_default_layout(module_type, index):
    defaults = {
        'hero': {'x': 1, 'y': 1, 'w': 8, 'h': 5, 'z': 1},
        'products': {'x': 1, 'y': 6, 'w': 5, 'h': 4, 'z': 1},
        'news': {'x': 6, 'y': 6, 'w': 4, 'h': 2, 'z': 2},
        'welfare': {'x': 10, 'y': 6, 'w': 3, 'h': 2, 'z': 2},
        'forum': {'x': 6, 'y': 8, 'w': 4, 'h': 3, 'z': 2},
        'company': {'x': 1, 'y': 10, 'w': 4, 'h': 3, 'z': 1},
        'media': {'x': 5, 'y': 10, 'w': 5, 'h': 3, 'z': 1},
        'timeline': {'x': 10, 'y': 8, 'w': 3, 'h': 5, 'z': 1},
        'image': {'x': 1, 'y': 14 + (index * 2), 'w': 4, 'h': 3, 'z': 1},
        'video': {'x': 5, 'y': 14 + (index * 2), 'w': 4, 'h': 3, 'z': 1},
        'text': {'x': 9, 'y': 14 + (index * 2), 'w': 4, 'h': 2, 'z': 1},
        'stat': {'x': 9, 'y': 16 + (index * 2), 'w': 4, 'h': 2, 'z': 2},
    }
    return dict(defaults.get(module_type, {'x': 1, 'y': 14 + (index * 2), 'w': 4, 'h': 3, 'z': 1}))


def _visual_editor_normalize_modules(modules, portal_kind):
    if not isinstance(modules, list) or not modules:
        modules = list(_visual_editor_default_modules(portal_kind))
    cleaned = []
    for index, item in enumerate(modules):
        if not isinstance(item, dict):
            continue
        module_type = str(item.get('type') or '').strip()
        if not module_type:
            continue
        layout = item.get('layout') if isinstance(item.get('layout'), dict) else {}
        fallback = _visual_editor_default_layout(module_type, index)

        def _layout_value(name, minimum, maximum, fallback_value):
            value = layout.get(name, item.get(name))
            try:
                value = int(value)
            except (TypeError, ValueError):
                value = fallback_value
            return max(minimum, min(maximum, value))

        width = _layout_value('w', 1, 12, fallback['w'])
        x = _layout_value('x', 1, 12, fallback['x'])
        x = min(x, max(1, 13 - width))
        height = _layout_value('h', 1, 12, fallback['h'])
        y = _layout_value('y', 1, 80, fallback['y'])
        z = _layout_value('z', 0, 20, fallback['z'])
        media_urls = normalize_local_media_urls(item.get('media_urls') or [], max_count=12)

        cleaned.append(
            {
                'id': str(item.get('id') or f'module-{uuid.uuid4().hex[:8]}'),
                'type': module_type,
                'title': str(item.get('title') or '').strip(),
                'description': str(item.get('description') or '').strip(),
                'enabled': item.get('enabled', True) is not False,
                'order': index + 1,
                'limit': item.get('limit') if str(item.get('limit') or '').strip() else '',
                'size': str(item.get('size') or 'full').strip() or 'full',
                'source': str(item.get('source') or '').strip(),
                'image_url': normalize_local_media_url(item.get('image_url')),
                'video_url': normalize_local_media_url(item.get('video_url')),
                'media_urls': media_urls,
                'cta_text': str(item.get('cta_text') or '').strip(),
                'cta_link': str(item.get('cta_link') or '').strip(),
                'layout': {'x': x, 'y': y, 'w': width, 'h': height, 'z': z},
            }
        )
    return cleaned


def _visual_editor_product_options():
    options = []
    for product in (products_db if isinstance(products_db, list) else []):
        product_id = str(product.get('id') or '').strip()
        if not product_id:
            continue
        name = _clean_display_text(product.get('name') or product.get('title') or product_id, product_id)
        options.append({'id': product_id, 'name': name})
    return options


def _visual_editor_preview_data():
    return {
        'news': list(get_latest_news(limit=6) or []),
        'welfare': list(get_active_welfare(limit=6) or []),
        'forum': list(get_forum_posts(limit=6) or []),
        'company': get_company_profile(),
    }


@bp.route('/admin/site-config/editor/<portal_kind>')
@admin_required()
def admin_site_config_visual_editor(portal_kind):
    if portal_kind not in ('player', 'dev'):
        return _admin_layout('<div class="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-rose-700">未知官网类型</div>', '可视化官网编辑器')

    company = get_company_profile()
    portal = get_player_portal_content() if portal_kind == 'player' else get_dev_portal_content()
    modules = _visual_editor_normalize_modules(portal.get('home_modules'), portal_kind)
    product_options = _visual_editor_product_options()
    portal_label = '玩家官网' if portal_kind == 'player' else '开发者官网'
    company_name = _clean_display_text(company.get('company_name') or portal.get('site_name') or '星云游戏站', '星云游戏站')
    return render_template(
        'site_visual_editor.html',
        company_name=company_name,
        portal_kind=portal_kind,
        portal_label=portal_label,
        portal_content=portal,
        modules=modules,
        module_types=[
            {'type': 'hero', 'label': '首页主视觉'},
            {'type': 'products', 'label': '产品入口'},
            {'type': 'news', 'label': '新闻公告'},
            {'type': 'welfare', 'label': '福利中心'},
            {'type': 'forum', 'label': '玩家论坛'},
            {'type': 'company', 'label': '公司简介'},
            {'type': 'media', 'label': '视觉展示'},
            {'type': 'timeline', 'label': '公司历程'},
            {'type': 'image', 'label': '图片模块'},
            {'type': 'video', 'label': '视频模块'},
            {'type': 'text', 'label': '文案模块'},
            {'type': 'stat', 'label': '指标模块'},
        ],
        product_options=product_options,
        preview_data=_visual_editor_preview_data(),
        csrf_token_value=_get_csrf_token(),
    )


    page_html = '''
    <section class="space-y-6">
        <div class="flex items-end justify-between gap-2">
            <div>
                <p class="text-[11px] font-semibold text-slate-500 tracking-[0.16em] uppercase">控制台</p>
                <h2 class="text-xl md:text-2xl font-semibold text-slate-900 mt-1">管理中心总览</h2>
                <p class="text-sm text-slate-500 mt-1">这里聚合项目、版本、构建、审批、通知与平台状态，方便快速判断下一步该处理什么。</p>
            </div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
            ''' + ''.join(
                f'<div class="stat-card rounded-2xl border border-slate-200/80 shadow-sm p-5"><div class="flex items-center justify-between"><div><p class="text-[11px] font-semibold text-slate-500 uppercase tracking-wide">{label}</p><p class="text-2xl font-bold text-slate-900 mt-1">{value}</p></div><div class="w-10 h-10 rounded-xl {bg_cls} flex items-center justify-center"><i class="fas {icon} {text_cls} text-lg"></i></div></div></div>'
                for label, value, icon, bg_cls, text_cls in summary_cards
            ) + '''
        </div>
        <div class="flex flex-wrap gap-2">''' + (''.join(quick_actions) if quick_actions else '<span class="text-sm text-slate-500">当前没有紧急待办</span>') + '''</div>
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <div class="bg-white/95 rounded-2xl border border-slate-200/80 p-5 shadow-sm">
                <div class="flex items-center justify-between mb-4"><h3 class="text-sm font-semibold text-slate-900">平台分布</h3><a href="/download-center" class="text-xs text-indigo-600 hover:underline">下载中心</a></div>
                <div class="grid grid-cols-2 gap-2">
                    <a href="/download-center?platform=android" class="rounded-xl border border-slate-200 px-4 py-4 hover:bg-slate-50 transition"><p class="text-xs text-slate-500">Android 包</p><p class="text-2xl font-bold text-slate-900 mt-1">''' + str(package_counts.get('android', 0)) + '''</p><p class="text-xs text-slate-400 mt-1">Android</p></a>
                    <a href="/download-center?platform=ios" class="rounded-xl border border-slate-200 px-4 py-4 hover:bg-slate-50 transition"><p class="text-xs text-slate-500">iOS 包</p><p class="text-2xl font-bold text-slate-900 mt-1">''' + str(package_counts.get('ios', 0)) + '''</p><p class="text-xs text-slate-400 mt-1">iOS</p></a>
                </div>
            </div>
            <div class="bg-white/95 rounded-2xl border border-slate-200/80 p-5 shadow-sm">
                <div class="flex items-center justify-between mb-4"><h3 class="text-sm font-semibold text-slate-900">待处理事项</h3><a href="/admin/my-tasks" class="text-xs text-indigo-600 hover:underline">我的任务</a></div>
                <ul class="space-y-3">''' + todo_html + '''</ul>
            </div>
            <div class="bg-white/95 rounded-2xl border border-slate-200/80 p-5 shadow-sm">
                <div class="flex items-center justify-between mb-4"><h3 class="text-sm font-semibold text-slate-900">版本与发布风险</h3><a href="/admin/projects" class="text-xs text-indigo-600 hover:underline">项目中心</a></div>
                <ul class="space-y-3">''' + risk_html + '''</ul>
            </div>
        </div>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <div class="bg-white/95 rounded-2xl border border-slate-200/80 p-5 shadow-sm">
                <div class="flex items-center justify-between mb-4"><h3 class="text-sm font-semibold text-slate-900">最近安装包</h3><a href="/admin/versions" class="text-xs text-indigo-600 hover:underline">版本管理</a></div>
                <div class="overflow-x-auto"><table class="min-w-full"><thead><tr class="text-left text-xs text-slate-500 border-b border-slate-200"><th class="px-4 py-2">文件</th><th class="px-4 py-2">平台</th><th class="px-4 py-2">大小</th><th class="px-4 py-2">更新时间</th></tr></thead><tbody>''' + recent_package_rows + '''</tbody></table></div>
            </div>
            <div class="bg-white/95 rounded-2xl border border-slate-200/80 p-5 shadow-sm">
                <div class="flex items-center justify-between mb-4"><h3 class="text-sm font-semibold text-slate-900">最近审计事件</h3><a href="/admin/audit-log" class="text-xs text-indigo-600 hover:underline">完整审计</a></div>
                <ul class="space-y-3">''' + audit_html + '''</ul>
            </div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">''' + ''.join(cards) + '''</div>
    </section>
    '''
    return _admin_layout(page_html, '管理中心', back_href='/')
    cards = []
    has_projects = any(m[0] == 'projects' for m in visible)
    for mid, name, _ in visible:
        link, icon, color = MODULE_LINKS.get(mid, ('#', 'fa-circle', 'text-gray-500'))
        cards.append(
            f'<a href="{link}" class="admin-card block bg-white/95 rounded-2xl border border-slate-200/80 p-5 shadow-sm hover:bg-white group">'
            f'<div class="flex items-start gap-2">'
            f'<div class="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center flex-shrink-0">'
            f'<i class="fas {icon} {color} text-lg"></i>'
            f'</div>'
            f'<div class="min-w-0">'
            f'<h2 class="text-sm font-semibold text-slate-900 mb-1 group-hover:text-indigo-600">{name}</h2>'
            f'<p class="text-xs text-slate-500 leading-snug">{desc.get(mid, "")}</p>'
            f'</div>'
            f'</div>'
            f'</a>'
        )
    if has_projects:
        cards.append(
            '<a href="/admin/my-tasks" class="admin-card block bg-white/95 rounded-2xl border border-slate-200/80 p-5 shadow-sm hover:bg-white group">'
            '<div class="flex items-start gap-2"><div class="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center flex-shrink-0">'
            '<i class="fas fa-tasks text-indigo-500 text-lg"></i></div>'
            '<div class="min-w-0"><h2 class="text-sm font-semibold text-slate-900 mb-1 group-hover:text-indigo-600">我的任务</h2>'
            '<p class="text-xs text-slate-500 leading-snug">查看与处理分配给自己的项目任务</p></div></div></a>'
        )
    cards.append(
        '<a href="/workspace" class="admin-card block bg-white/95 rounded-2xl border border-slate-200/80 p-5 shadow-sm hover:bg-white group">'
        '<div class="flex items-start gap-2"><div class="w-10 h-10 rounded-xl bg-amber-50 flex items-center justify-center flex-shrink-0">'
        '<i class="fas fa-briefcase text-amber-500 text-lg"></i></div>'
        '<div class="min-w-0"><h2 class="text-sm font-semibold text-slate-900 mb-1 group-hover:text-indigo-600">个人工作区</h2>'
        '<p class="text-xs text-slate-500 leading-snug">文件、图片、书签、账号密码（仅自己可见）</p></div></div></a>'
    )
    if is_super_admin_or_admin():
        cards.append(
            '<a href="/admin/products" class="admin-card block bg-white/95 rounded-2xl border border-slate-200/80 p-5 shadow-sm hover:bg-white group">'
            '<div class="flex items-start gap-2"><div class="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center flex-shrink-0">'
            '<i class="fas fa-gamepad text-emerald-500 text-lg"></i></div>'
            '<div class="min-w-0"><h2 class="text-sm font-semibold text-slate-900 mb-1 group-hover:text-indigo-600">产品管理</h2>'
            '<p class="text-xs text-slate-500 leading-snug">官网首页产品展示、封面、画廊、视频</p></div></div></a>'
        )
    html = '''
    <section class="space-y-6">
        <div class="flex items-end justify-between gap-2">
            <div>
                <p class="text-[11px] font-semibold text-slate-500 tracking-[0.16em] uppercase">控制台</p>
                <h2 class="text-xl md:text-2xl font-semibold text-slate-900 mt-1">管理中心总览</h2>
                <p class="text-sm text-slate-500 mt-1">从这里进入用户、项目、版本、构建、审批等后台模块。</p>
            </div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            ''' + ''.join(cards) + '''
        </div>
    </section>
    '''
    return _admin_layout(html, '管理中心', back_href='/')

# ---------- 用户管理 ----------
USERS_PAGE = '''
<div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
    <div class="px-6 py-4 border-b border-gray-100 flex flex-wrap items-center justify-between gap-3 bg-gray-50/50">
        <div class="space-y-0.5">
            <h2 class="text-lg font-semibold text-gray-800">用户列表</h2>
            <p class="text-xs text-gray-500">管理平台账号、模块权限与高风险操作权限。</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
            <div class="relative">
                <span class="pointer-events-none absolute inset-y-0 left-2.5 flex items-center text-gray-400 text-xs"><i class="fas fa-search"></i></span>
                <input type="text" id="userSearch" placeholder="搜索用户名、角色…" class="pl-8 pr-3 py-1.5 border border-gray-200 rounded-lg text-sm w-48 focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
            </div>
            <button type="button" onclick="document.getElementById('addUserForm').classList.toggle('hidden')" class="px-4 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition shadow-sm">+ 添加用户</button>
            <a href="/admin/users/export" class="px-4 py-2.5 bg-gray-100 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-200 transition">导出 CSV</a>
            <form id="importUserForm" class="inline" enctype="multipart/form-data">
                <input type="file" name="file" accept=".csv" id="importFile" class="hidden">
                <button type="button" onclick="document.getElementById('importFile').click()" class="px-4 py-2.5 bg-emerald-100 text-emerald-700 text-sm font-medium rounded-lg hover:bg-emerald-200 transition">批量导入</button>
            </form>
        </div>
    </div>
    <div id="addUserForm" class="px-6 py-5 border-b border-gray-100 bg-slate-50/80 hidden">
        <form onsubmit="return addUser(event)" class="space-y-5">
            <div class="grid gap-6 lg:grid-cols-3 items-start">
                <div class="lg:col-span-1 space-y-4">
                    <div>
                        <label class="block text-xs font-medium text-gray-500 mb-1">用户名</label>
                        <input type="text" id="newUsername" placeholder="用户名" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" required>
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-500 mb-1">密码（至少 {{PASSWORD_MIN}} 位）</label>
                        <input type="password" id="newPassword" placeholder="密码" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500" required minlength="{{PASSWORD_MIN}}">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-500 mb-1">角色</label>
                        <select id="newRole" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500">
                            <option value="admin">管理员</option>
                            <option value="user">普通用户</option>
                        </select>
                    </div>
                    <div>
                        <button type="submit" class="w-full lg:w-auto px-4 py-2.5 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 transition shadow-sm">添加</button>
                    </div>
                </div>
                <div class="lg:col-span-2 grid gap-6 md:grid-cols-2">
                    <div id="newUserModulesWrap" class="hidden bg-white rounded-xl border border-dashed border-gray-200 px-4 py-3">
                        <label class="block text-xs font-medium text-gray-500 mb-1">模块权限</label>
                        <label class="flex items-center gap-2 text-sm mt-1">
                            <input type="checkbox" id="newUserAllModules" checked class="rounded text-blue-600">
                            <span>除用户管理外全部</span>
                        </label>
                        <div id="newUserModulesList" class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm"></div>
                    </div>
                    <div id="newUserScopesWrap" class="hidden bg-white rounded-xl border border-dashed border-amber-200 px-4 py-3">
                        <label class="block text-xs font-medium text-gray-500 mb-1">高级操作权限（可选）</label>
                        <p class="text-[11px] text-gray-400 mb-2">用于控制谁可以触发构建、管理 Jenkins 实例、修改系统安全等高风险操作。</p>
                        <div id="newUserScopesList" class="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm"></div>
                    </div>
                </div>
            </div>
        </form>
    </div>
    <div class="overflow-x-auto">
        <table class="min-w-full">
            <thead class="bg-gray-50 border-b border-gray-200">
                <tr>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">用户名</th>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">角色</th>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">模块权限</th>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">操作权限</th>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">状态</th>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">最后登录</th>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">创建时间</th>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">操作</th>
                </tr>
            </thead>
            <tbody id="usersTable" class="divide-y divide-gray-100"></tbody>
        </table>
    </div>
</div>
<div id="editUserModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden" onclick="event.stopPropagation()">
        <div class="px-6 py-4 border-b border-gray-100 bg-gray-50/80">
            <h3 class="text-lg font-semibold text-gray-800">编辑用户权限</h3>
            <p class="text-sm text-gray-500 mt-0.5">用户：<strong id="editUserName" class="text-gray-800"></strong></p>
        </div>
        <div class="px-6 py-5 space-y-5">
            <div>
                <label class="flex items-center gap-2 cursor-pointer p-2 rounded-lg hover:bg-gray-50">
                    <input type="checkbox" id="editAllModules" class="rounded text-blue-600 w-4 h-4">
                    <span class="font-medium text-gray-700">除用户管理外全部</span>
                </label>
                <p class="text-xs text-gray-400 mt-1 ml-6">取消勾选下方某一项时，将自动取消「全部」</p>
                <div id="editModulesList" class="mt-3 ml-6 grid grid-cols-2 gap-2"></div>
            </div>
            <div class="pt-3 border-t border-gray-100">
                <h4 class="text-xs font-semibold text-gray-500 mb-1">高级操作权限（可选）</h4>
                <p class="text-[11px] text-gray-400 mb-2">用于控制谁可以执行高风险操作，如触发构建、管理 Jenkins 实例等。</p>
                <div id="editScopesList" class="ml-1 grid grid-cols-1 gap-1 text-sm"></div>
            </div>
            <div class="pt-3 border-t border-gray-100">
                <label class="flex items-center gap-2 cursor-pointer p-2 rounded-lg hover:bg-red-50">
                    <input type="checkbox" id="editDisabled" class="rounded text-red-600 w-4 h-4">
                    <span class="text-gray-700">禁用该账号</span>
                </label>
            </div>
        </div>
        <div class="px-6 py-4 border-t border-gray-100 bg-gray-50/50 flex justify-end gap-2">
            <button type="button" onclick="document.getElementById('editUserModal').classList.add('hidden')" class="px-4 py-2.5 text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 font-medium text-sm transition">取消</button>
            <button type="button" onclick="saveEditUser()" class="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm shadow-sm transition">保存</button>
        </div>
    </div>
</div>
<div id="resetPwdModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden" onclick="event.stopPropagation()">
        <div class="px-6 py-4 border-b border-gray-100 bg-gray-50/80">
            <h3 class="text-lg font-semibold text-gray-800">重置密码</h3>
            <p class="text-sm text-gray-500 mt-0.5">用户：<strong id="resetPwdUserName" class="text-gray-800"></strong>（密码已加密存储，无法查看，请设置新密码后告知用户）</p>
        </div>
        <div class="px-6 py-5 space-y-4">
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">新密码</label>
                <input type="text" id="resetPwdNew" placeholder="输入新密码" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500">
                <button type="button" onclick="genRandomPwd()" class="mt-2 text-sm text-blue-600 hover:underline">随机生成并复制到剪贴板</button>
            </div>
            <p id="resetPwdTip" class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-3 py-2 hidden">请复制上方新密码并告知用户，关闭后无法再查看。</p>
        </div>
        <div class="px-6 py-4 border-t border-gray-100 bg-gray-50/50 flex justify-end gap-2">
            <button type="button" onclick="document.getElementById('resetPwdModal').classList.add('hidden')" class="px-4 py-2.5 text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 font-medium text-sm transition">取消</button>
            <button type="button" onclick="submitResetPwd()" class="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm shadow-sm transition">确定重置</button>
        </div>
    </div>
</div>
<script>
var MODULE_IDS = ''' + __import__('json').dumps([m[0] for m in ADMIN_MODULES if m[0] != 'user_management']) + ''';
var MODULE_NAMES = ''' + __import__('json').dumps(dict((m[0], m[1]) for m in ADMIN_MODULES if m[0] != 'user_management')) + ''';
var SCOPE_IDS = ["build.trigger","build.view","jenkins.manage","approval.manage","settings.manage"];
var SCOPE_NAMES = {
  "build.trigger": "触发/停止构建",
  "build.view": "查看构建历史与日志",
  "jenkins.manage": "管理 Jenkins 实例（启动/停止/删除、环境部署）",
  "approval.manage": "审批发布与敏感操作",
  "settings.manage": "修改系统与安全设置"
};
document.getElementById('newRole').onchange=function(){
    var wrap=document.getElementById('newUserModulesWrap');
    var scopeWrap=document.getElementById('newUserScopesWrap');
    wrap.classList.toggle('hidden', this.value!=='user');
    if(scopeWrap) scopeWrap.classList.toggle('hidden', this.value!=='user');
    if(this.value==='user'){
        var list=document.getElementById('newUserModulesList');
        list.innerHTML=MODULE_IDS.map(function(id){ return '<label class="flex items-center gap-1"><input type="checkbox" class="mod-cb" value="'+id+'"> '+MODULE_NAMES[id]+'</label>'; }).join('');
        var scopeList=document.getElementById('newUserScopesList');
        if(scopeList && scopeList.children.length===0){
            SCOPE_IDS.forEach(function(id){
                var lb=document.createElement('label');
                lb.className='flex items-center gap-1';
                lb.innerHTML='<input type="checkbox" class="new-scope-cb" value="'+id+'"> '+(SCOPE_NAMES[id]||id);
                scopeList.appendChild(lb);
            });
        }
    }
};
document.getElementById('importFile').onchange=function(){
    if(!this.files||!this.files[0]) return;
    var fd=new FormData();
    fd.append('file', this.files[0]);
    fetch('/admin/users/import', { method:'POST', body: fd, credentials:'same-origin' }).then(function(r){ return r.json(); }).then(function(d){ alert(d.error||('导入完成：新增 '+d.created+' 人，跳过 '+d.skipped+' 条')); if(!d.error) loadUsers(); this.value=''; }.bind(this));
};
function collectNewUserModules(){
    if(document.getElementById('newUserAllModules').checked) return ['*'];
    return Array.from(document.querySelectorAll('#newUserModulesList .mod-cb:checked')).map(function(c){ return c.value; });
}
function collectNewUserScopes(){
    return Array.from(document.querySelectorAll('#newUserScopesList .new-scope-cb:checked')).map(function(c){ return c.value; });
}
var allUsersCache = [];
function renderUsersTable(users){
    var t=document.getElementById('usersTable');
    var q=(document.getElementById('userSearch')||{}).value||'';
    q=q.trim().toLowerCase();
    var list = q ? users.filter(function(u){ return (u.username||'').toLowerCase().indexOf(q)>=0 || (u.role||'').toLowerCase().indexOf(q)>=0; }) : users;
    var rows = list.map(function(u, i){
        var permText = u.role==='user' ? (u.allowed_modules&&u.allowed_modules.indexOf('*')>=0 ? '全部(除用户管理)' : (u.allowed_modules||[]).join(', ') || '无') : '-';
        var scopeText = u.role==='user' ? ((u.allowed_scopes||[]).length ? (u.allowed_scopes||[]).map(function(s){ return (SCOPE_NAMES[s]||s).slice(0,8); }).join(', ') : '-') : '-';
        var status = u.disabled ? '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">已禁用</span>' : '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-700">正常</span>';
        var lastLoginStr = (u.last_login||'').slice(0,19).replace('T',' ') || '-';
        var actions = [];
        if(u.role!=='super_admin' && u.username!=='admin'){
            actions.push('<button onclick="editUser(\\''+u.username+'\\')" class="px-2 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded">编辑权限</button>');
            actions.push('<button onclick="openResetPwd(\\''+u.username+'\\')" class="px-2 py-1 text-sm text-violet-600 hover:bg-violet-50 rounded">重置密码</button>');
            actions.push(u.disabled ? '<button onclick="toggleUser(\\''+u.username+'\\', false)" class="px-2 py-1 text-sm text-emerald-600 hover:bg-emerald-50 rounded">启用</button>' : '<button onclick="toggleUser(\\''+u.username+'\\', true)" class="px-2 py-1 text-sm text-amber-600 hover:bg-amber-50 rounded">禁用</button>');
            actions.push('<button onclick="deleteUser(\\''+u.username+'\\')" class="px-2 py-1 text-sm text-red-600 hover:bg-red-50 rounded">删除</button>');
        }
        var rowClass = (i%2===0) ? 'bg-white' : 'bg-gray-50/50';
        var dateStr = (u.created_at||'').slice(0,19).replace('T',' ');
        return '<tr class="'+rowClass+' hover:bg-blue-50/30" data-username="'+u.username+'"><td class="px-6 py-3.5 font-medium text-gray-900">'+u.username+'</td><td class="px-6 py-3.5 text-sm text-gray-600">'+u.role+'</td><td class="px-6 py-3.5 text-sm text-gray-600">'+permText+'</td><td class="px-6 py-3.5 text-xs text-gray-500 max-w-[140px]" title="'+((u.allowed_scopes||[]).join(', ')||'-')+'">'+scopeText+'</td><td class="px-6 py-3.5">'+status+'</td><td class="px-6 py-3.5 text-sm text-gray-500">'+lastLoginStr+'</td><td class="px-6 py-3.5 text-sm text-gray-500">'+dateStr+'</td><td class="px-6 py-3.5"><span class="inline-flex flex-wrap gap-1">'+actions.join('')+'</span></td></tr>';
    }).join('');
    t.innerHTML = rows;
}
function loadUsers(){
    fetch('/admin/users/list').then(r=>r.json()).then(d=>{
        allUsersCache = d.users||[];
        renderUsersTable(allUsersCache);
    });
}
var searchEl = document.getElementById('userSearch'); if(searchEl) searchEl.oninput = function(){ renderUsersTable(allUsersCache); };
var resetPwdUsername = null;
function openResetPwd(name){
    resetPwdUsername=name;
    document.getElementById('resetPwdUserName').textContent=name;
    document.getElementById('resetPwdNew').value='';
    document.getElementById('resetPwdTip').classList.add('hidden');
    document.getElementById('resetPwdModal').classList.remove('hidden');
}
function genRandomPwd(){
    var s='ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789';
    var p='';
    for(var i=0;i<12;i++) p+=s.charAt(Math.floor(Math.random()*s.length));
    var el=document.getElementById('resetPwdNew');
    el.value=p;
    if(navigator.clipboard&&navigator.clipboard.writeText){ navigator.clipboard.writeText(p).then(function(){ alert('已生成并复制到剪贴板：'+p); }); }
    else { alert('已生成新密码（请手动复制）：'+p); }
    document.getElementById('resetPwdTip').classList.remove('hidden');
}
function submitResetPwd(){
    if(!resetPwdUsername) return;
    var pwd=document.getElementById('resetPwdNew').value.trim();
    if(!pwd){ alert('请输入新密码'); return; }
    fetch('/admin/users/reset-password', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ username: resetPwdUsername, new_password: pwd })}).then(r=>r.json()).then(d=>{ alert(d.error||'密码已重置'); if(!d.error) { document.getElementById('resetPwdModal').classList.add('hidden'); loadUsers(); } });
}
function addUser(e){ e.preventDefault();
    var role=document.getElementById('newRole').value;
    var payload={ username: document.getElementById('newUsername').value, password: document.getElementById('newPassword').value, role: role };
    if(role==='user'){
        payload.allowed_modules=collectNewUserModules();
        var scopes=collectNewUserScopes();
        if(scopes.length) payload.allowed_scopes=scopes;
    }
    fetch('/admin/users/create', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)}).then(r=>r.json()).then(d=>{ alert(d.error||'添加成功'); if(!d.error) { loadUsers(); document.getElementById('addUserForm').classList.add('hidden'); } });
    return false;
}
var editingUsername = null;
function editUser(name){
    editingUsername=name;
    fetch('/admin/users/get/'+encodeURIComponent(name)).then(r=>r.json()).then(d=>{
        if(!d.user){ alert('用户不存在'); return; }
        var u=d.user;
        document.getElementById('editUserName').textContent=u.username;
        document.getElementById('editAllModules').checked = u.allowed_modules&&u.allowed_modules.indexOf('*')>=0;
        MODULE_IDS.forEach(function(id){
            var cb=document.querySelector('#editModulesList input[value="'+id+'"]');
            if(cb) cb.checked = u.allowed_modules&&(u.allowed_modules.indexOf('*')>=0||u.allowed_modules.indexOf(id)>=0);
        });
        // 高级操作权限
        var scopesWrap = document.getElementById('editScopesList');
        if(scopesWrap && scopesWrap.children.length === 0){
            SCOPE_IDS.forEach(function(id){
                var label=document.createElement('label');
                label.className='flex items-center gap-2 cursor-pointer py-0.5 rounded hover:bg-gray-50';
                label.innerHTML='<input type="checkbox" value="'+id+'" class="rounded text-indigo-600 w-4 h-4 edit-scope-cb"> <span class="text-sm text-gray-700">'+(SCOPE_NAMES[id]||id)+'</span>';
                scopesWrap.appendChild(label);
            });
        }
        var scopes = u.allowed_scopes||[];
        document.querySelectorAll('#editScopesList .edit-scope-cb').forEach(function(cb){
            cb.checked = scopes.indexOf(cb.value) >= 0;
        });
        document.getElementById('editDisabled').checked=!!u.disabled;
        document.getElementById('editUserModal').classList.remove('hidden');
    });
}
document.getElementById('editAllModules').onchange=function(){
    document.querySelectorAll('#editModulesList input').forEach(function(cb){ cb.checked=this.checked; }.bind(this));
};
function saveEditUser(){
    if(!editingUsername) return;
    var allCb = document.getElementById('editAllModules');
    var listCbs = document.querySelectorAll('#editModulesList input');
    var allowed = allCb.checked ? ['*'] : Array.from(listCbs).filter(function(c){ return c.checked; }).map(function(c){ return c.value; });
    var disabled = document.getElementById('editDisabled').checked;
    var scopes = Array.from(document.querySelectorAll('#editScopesList .edit-scope-cb:checked')).map(function(c){ return c.value; });
    fetch('/admin/users/update', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ username: editingUsername, allowed_modules: allowed, allowed_scopes: scopes, disabled: disabled })}).then(r=>r.json()).then(d=>{ alert(d.error||'已保存'); if(!d.error) { loadUsers(); document.getElementById('editUserModal').classList.add('hidden'); } });
}
function toggleUser(name, disable){
    fetch('/admin/users/update', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ username: name, disabled: disable })}).then(r=>r.json()).then(d=>{ alert(d.error||'已更新'); if(!d.error) loadUsers(); });
}
function deleteUser(name){
    if(!confirm('确定删除用户 '+name+'？')) return;
    fetch('/admin/users/delete/'+encodeURIComponent(name), { method:'DELETE' }).then(r=>r.json()).then(d=>{ alert(d.error||'已删除'); if(!d.error) loadUsers(); });
}
(function(){
    var list=document.getElementById('editModulesList');
    MODULE_IDS.forEach(function(id){ list.innerHTML+='<label class="flex items-center gap-2 cursor-pointer py-1 rounded hover:bg-gray-50"><input type="checkbox" value="'+id+'" class="rounded text-blue-600 w-4 h-4 edit-mod-cb"> <span class="text-sm text-gray-700">'+MODULE_NAMES[id]+'</span></label>'; });
    document.querySelectorAll('#editModulesList input').forEach(function(cb){
        cb.addEventListener('change', function(){ if(!this.checked) document.getElementById('editAllModules').checked=false; });
    });
})();
loadUsers();
</script>
'''


@bp.route('/admin/users')
@admin_required('user_management')
def admin_users_page():
    page = USERS_PAGE.replace('{{PASSWORD_MIN}}', str(_password_min_length()))
    return _admin_layout(page, '用户管理')


# ---------- 项目管理 ----------
def _safe_json_for_script(s):
    """防止 JSON 中的 </script> 提前关闭 script 标签"""
    if not isinstance(s, str):
        return s
    return re.sub(r'(?i)</script>', r'<\\u002fscript>', s)

PROJECTS_PAGE = '''
<section class="space-y-5">
    <div class="flex items-end justify-between gap-2">
        <div>
            <p class="text-[11px] font-semibold text-slate-500 tracking-[0.16em] uppercase">项目中心</p>
            <h2 class="text-xl font-semibold text-slate-900 mt-1">项目列表</h2>
            <p class="text-sm text-slate-500 mt-1">为每个 APK 项目配置成员、阶段与权限，进入项目中心管理任务与版本。</p>
        </div>
        <div class="flex items-center gap-2">
            <select id="projectStatusFilter" onchange="loadProjects()" class="px-3 py-1.5 border border-slate-200 rounded-xl text-sm bg-white shadow-sm">
                <option value="active">仅活跃</option>
                <option value="archived">仅归档</option>
                <option value="">全部</option>
            </select>
            <input type="text" id="projectSearch" placeholder="搜索项目ID、名称、英文名…" class="px-3 py-1.5 border border-slate-200 rounded-xl text-sm w-56 focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500 bg-white shadow-sm">
            <button type="button" onclick="openChannelManageModal()" class="inline-flex items-center px-3.5 py-1.5 rounded-xl border border-slate-200 bg-white text-sm text-slate-700 hover:bg-slate-50 shadow-sm">
                <i class="fas fa-layer-group mr-1.5 text-slate-500"></i> 渠道管理
            </button>
            <button type="button" onclick="var f=document.getElementById('addProjectForm'); if(f.classList.contains('hidden')){ newParticipants=[]; renderNewParticipants(); } f.classList.toggle('hidden')" class="inline-flex items-center px-4 py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-medium shadow-sm hover:bg-indigo-700 transition">
                <i class="fas fa-plus mr-1.5"></i> 添加项目
            </button>
        </div>
    </div>
    <div id="addProjectForm" class="px-6 py-5 border border-slate-200 rounded-2xl bg-white/95 shadow-sm hidden">
        <form onsubmit="return false;" class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div><label class="block text-xs font-medium text-slate-500 mb-1">项目ID（英文）</label><input type="text" id="newProjectId" placeholder="如 MyGame" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" required></div>
                <div><label class="block text-xs font-medium text-slate-500 mb-1">名称</label><input type="text" id="newProjectName" placeholder="项目名称" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" required></div>
                <div><label class="block text-xs font-medium text-slate-500 mb-1">英文名</label><input type="text" id="newProjectNameEn" placeholder="English name" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>
                <div><label class="block text-xs font-medium text-slate-500 mb-1">项目图标</label><div class="flex items-center gap-2"><input type="file" id="newProjectIconFile" accept="image/*" class="text-sm"><span id="newProjectIconPreview" class="text-slate-400 text-xs">未上传</span></div><input type="hidden" id="newProjectIcon" value=""></div>
                <div><label class="block text-xs font-medium text-slate-500 mb-1">项目阶段</label><select id="newProjectPhase" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500">''' + ''.join('<option value="%s">%s</option>' % (k, v) for k, v in PROJECT_PHASES) + '''</select></div>
                <div>
                    <label class="block text-xs font-medium text-slate-500 mb-1">gameId（唯一，必填）</label>
                    <input type="text" id="newProjectGameId" readonly class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm bg-slate-50">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-500 mb-1">gameKey（唯一，必填）</label>
                    <input type="text" id="newProjectGameKey" readonly class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm bg-slate-50">
                </div>
                <div class="flex items-end">
                    <button type="button" onclick="generateProjectCredentials()" class="w-full px-3 py-1.5 rounded-lg bg-violet-600 text-white text-sm font-medium hover:bg-violet-700">系统生成凭据</button>
                </div>
            </div>
            <div><label class="block text-xs font-medium text-slate-500 mb-1">简介</label><input type="text" id="newProjectIntro" placeholder="简短介绍" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>
            <div><label class="block text-xs font-medium text-slate-500 mb-1">详情</label><textarea id="newProjectDetail" rows="2" placeholder="详细描述" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></textarea></div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div><label class="block text-xs font-medium text-slate-500 mb-1">网络连接说明</label><input type="text" id="newProjectNetwork" placeholder="如：需内网/外网" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>
                <div><label class="block text-xs font-medium text-slate-500 mb-1">Git 地址</label><input type="text" id="newProjectGitUrl" placeholder="https://或 git@" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>
                <div class="md:col-span-2"><label class="block text-xs font-medium text-slate-500 mb-1">GitHub/SSH Key 路径</label><input type="text" id="newProjectGitSshKey" placeholder="如 /Users/xxx/.ssh/id_rsa" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div><label class="block text-xs font-medium text-slate-500 mb-1">可查看用户</label><input type="text" id="newProjectViewers" placeholder="多个用户名用逗号分隔" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>
                <div><label class="block text-xs font-medium text-slate-500 mb-1">项目参与人员（可编辑）</label><div class="flex gap-2"><input type="text" id="newParticipantUser" placeholder="输入用户名" class="flex-1 px-3 py-1.5 border border-slate-200 rounded-lg text-sm"><button type="button" onclick="addNewParticipant()" class="px-3 py-1.5 bg-indigo-50 text-indigo-700 rounded-lg text-sm">验证并添加</button></div><ul id="newParticipantsList" class="mt-2 space-y-1 text-sm"></ul></div>
            </div>
            <div id="addProjectFeedback" class="min-h-[2rem] text-sm font-medium py-1"></div>
            <div class="flex gap-2 justify-end"><button type="button" onclick="document.getElementById('addProjectForm').classList.add('hidden')" class="px-4 py-2.5 border border-slate-200 rounded-lg text-sm text-slate-700 hover:bg-slate-50">取消</button><button type="button" id="addProjectBtn" onclick="addProject()" class="px-4 py-2.5 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 transition">添加项目</button></div>
        </form>
    </div>
    <div class="bg-white/95 rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
            <h3 class="text-sm font-semibold text-slate-900">项目列表</h3>
            <p class="text-xs text-slate-500">包含当前账号可见的所有项目。</p>
        </div>
        <div class="overflow-x-auto">
            <table class="min-w-full xl:min-w-[1360px]">
                <thead class="bg-slate-50/80 border-b border-slate-200/80">
                    <tr>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">图标</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">项目ID</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">名称</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">英文名</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">阶段</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">简介</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">创建者</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">创建时间</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">任务</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">APK</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">下载量</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider w-[280px]">操作</th>
                    </tr>
                </thead>
                <tbody id="projectsTable" class="divide-y divide-slate-100"></tbody>
            </table>
        </div>
    </div>
</section>
<div id="channelManageModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-xl max-h-[90vh] overflow-hidden flex flex-col" onclick="event.stopPropagation()">
        <div class="px-6 py-4 border-b border-slate-100 bg-slate-50/80 flex items-center justify-between">
            <div>
                <h3 class="text-sm font-semibold text-slate-900">渠道管理</h3>
                <p class="text-xs text-slate-500 mt-0.5">维护版本渠道（如开发版、测试版、线上版），用于版本管理与下载中心筛选。</p>
            </div>
            <button type="button" onclick="closeChannelManageModal()" class="text-slate-400 hover:text-slate-600"><i class="fas fa-times"></i></button>
        </div>
        <div class="px-6 py-4 space-y-4 overflow-y-auto flex-1">
            <div class="border border-dashed border-slate-200 rounded-xl p-3 bg-slate-50/60">
                <div class="grid grid-cols-[1.2fr,1.2fr,0.6fr] gap-3 items-end">
                    <div>
                        <label class="block text-xs font-medium text-slate-600 mb-1">渠道 ID</label>
                        <input type="text" id="channelFormId" placeholder="如 dev / test / production" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-600 mb-1">渠道名称</label>
                        <input type="text" id="channelFormName" placeholder="如 开发版 / 测试版 / 线上版" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-600 mb-1">排序</label>
                        <input type="number" id="channelFormOrder" value="0" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500">
                    </div>
                </div>
                <div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">
                    <div><label class="block text-xs font-medium text-slate-600 mb-1">APK 子目录（可选）</label><input type="text" id="channelFormApkSubdir" placeholder="如 dev、test" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500"></div>
                    <div><label class="block text-xs font-medium text-slate-600 mb-1">构建参数（可选）</label><input type="text" id="channelFormBuildParam" placeholder="如 CHANNEL=dev" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500"></div>
                </div>
                <div class="mt-3">
                    <label class="block text-xs font-medium text-slate-600 mb-1">说明（可选）</label>
                    <textarea id="channelFormDesc" rows="2" placeholder="用于标记该渠道的用途，例如“内部联调测试”、“线上正式发布”等" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500"></textarea>
                </div>
                <div class="mt-3 flex justify-end gap-2">
                    <button type="button" onclick="resetChannelForm()" class="px-3 py-2 text-xs text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50">重置</button>
                    <button type="button" onclick="submitChannelForm()" class="px-4 py-2 text-xs font-medium rounded-lg bg-amber-600 text-white hover:bg-amber-700 shadow-sm">保存渠道</button>
                </div>
                <input type="hidden" id="channelFormEditingId" value="">
            </div>
            <div>
                <h4 class="text-xs font-semibold text-slate-500 mb-2">已有渠道</h4>
                <table class="w-full text-xs">
                    <thead class="border-b border-slate-200 text-slate-500">
                        <tr><th class="py-1.5 text-left">ID</th><th class="py-1.5 text-left">名称</th><th class="py-1.5 text-left">APK 子目录</th><th class="py-1.5 text-left">构建参数</th><th class="py-1.5 text-left w-28">操作</th></tr>
                    </thead>
                    <tbody id="channelTableBody" class="divide-y divide-slate-100"></tbody>
                </table>
                <p id="channelEmptyTip" class="py-4 text-center text-xs text-slate-400 hidden">暂无渠道，可在上方添加，例如 dev / test / production。</p>
            </div>
        </div>
        <div class="px-6 py-3 border-t border-slate-100 bg-slate-50/80 flex justify-end">
            <button type="button" onclick="closeChannelManageModal()" class="px-4 py-1.5 text-sm text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50">关闭</button>
        </div>
    </div>
</div>
<div id="participantRoleModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-xl shadow-xl w-80 p-5" onclick="event.stopPropagation()">
        <h4 class="font-semibold text-gray-800 mb-2">设定角色</h4>
        <p class="text-sm text-gray-500 mb-3">用户：<strong id="roleModalUsername"></strong></p>
        <select id="roleModalRole" class="w-full px-3 py-1.5 border rounded-lg text-sm mb-4">''' + ''.join('<option value="%s">%s</option>' % (r, r) for r in PROJECT_ROLES) + '''</select>
        <div class="flex gap-2"><button type="button" onclick="confirmParticipantRole()" class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm">确认</button><button type="button" onclick="document.getElementById('participantRoleModal').classList.add('hidden')" class="px-4 py-1.5 border rounded-lg text-sm">取消</button></div>
    </div>
</div>
<div id="editProjectModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col" onclick="event.stopPropagation()">
        <div class="px-6 py-4 border-b border-gray-100 bg-gray-50/80 flex-shrink-0"><h3 class="text-lg font-semibold text-gray-800">编辑项目</h3><p class="text-sm text-gray-500 mt-0.5">项目ID：<strong id="editProjectIdLabel" class="text-gray-800"></strong></p></div>
        <div class="px-6 py-5 overflow-y-auto flex-1 space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div><label class="block text-xs font-medium text-gray-500 mb-1">名称</label><input type="text" id="editProjectName" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>
                <div><label class="block text-xs font-medium text-gray-500 mb-1">英文名</label><input type="text" id="editProjectNameEn" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>
            </div>
            <div><label class="block text-xs font-medium text-gray-500 mb-1">项目阶段</label><select id="editProjectPhase" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500">''' + ''.join('<option value="%s">%s</option>' % (k, v) for k, v in PROJECT_PHASES) + '''</select></div>
            <div><label class="block text-xs font-medium text-gray-500 mb-1">项目图标</label><div class="flex items-center gap-2 flex-wrap"><input type="file" id="editProjectIconFile" accept="image/*" class="text-sm"><span id="editProjectIconPreview" class="text-gray-500 text-xs"></span></div><input type="hidden" id="editProjectIcon" value=""></div>
            <div><label class="block text-xs font-medium text-gray-500 mb-1">简介</label><input type="text" id="editProjectIntro" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>
            <div><label class="block text-xs font-medium text-gray-500 mb-1">详情</label><textarea id="editProjectDetail" rows="2" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></textarea></div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div><label class="block text-xs font-medium text-gray-500 mb-1">网络连接说明</label><input type="text" id="editProjectNetwork" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>
                <div><label class="block text-xs font-medium text-gray-500 mb-1">Git 地址</label><input type="text" id="editProjectGitUrl" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>
                <div class="md:col-span-2"><label class="block text-xs font-medium text-gray-500 mb-1">GitHub/SSH Key 路径</label><input type="text" id="editProjectGitSshKey" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div><label class="block text-xs font-medium text-gray-500 mb-1">可查看用户</label><input type="text" id="editProjectViewers" placeholder="多个用户名用逗号分隔" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>
                <div><label class="block text-xs font-medium text-gray-500 mb-1">项目参与人员（可编辑）</label><div class="flex gap-2"><input type="text" id="editParticipantUser" placeholder="输入用户名" class="flex-1 px-3 py-1.5 border border-gray-200 rounded-lg text-sm"><button type="button" onclick="addEditParticipant()" class="px-3 py-1.5 bg-indigo-100 text-indigo-700 rounded-lg text-sm">验证并添加</button></div><ul id="editParticipantsList" class="mt-2 space-y-1 text-sm"></ul></div>
            </div>
            <div><label class="block text-xs font-medium text-gray-500 mb-1">可用渠道（不勾选=该项目的版本可使用全部渠道）</label><div id="editProjectChannels" class="mt-2 flex flex-wrap gap-x-4 gap-y-1"></div></div>
        </div>
        <div class="px-6 py-4 border-t border-gray-100 bg-gray-50/50 flex justify-end gap-2 flex-shrink-0">
            <button type="button" onclick="document.getElementById('editProjectModal').classList.add('hidden')" class="px-4 py-2.5 text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 font-medium text-sm transition">取消</button>
            <button type="button" onclick="saveEditProject()" class="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm shadow-sm transition">保存</button>
        </div>
    </div>
</div>
<script>
var allProjectsCache = [];
var newParticipants = [];
var editParticipants = [];
var _participantCtx = '';
var _pendingParticipantUser = '';
var ROLES = ''' + _safe_json_for_script(json.dumps(PROJECT_ROLES)) + ''';
var _channelsCache = [];
var ALL_CHANNELS = ''' + _safe_json_for_script(json.dumps([
    {'id': (c.get('id') or '').strip(), 'name': (c.get('name') or c.get('id') or '').strip()}
    for c in (channels_db if isinstance(channels_db, list) else [])
    if (c.get('id') or '').strip()
])) + ''';
function parseUserList(str){ return (str||'').split(/[,，\\s]+/).map(function(s){ return s.trim(); }).filter(Boolean); }
function renderNewParticipants(){ var ul=document.getElementById('newParticipantsList'); if(!ul) return; ul.innerHTML=newParticipants.map(function(p){ return '<li class="flex justify-between items-center py-1"><span>'+p.user+' <span class="text-gray-500">('+p.role+')</span></span><span><button type="button" onclick="editParticipantRole(\\'new\\','+JSON.stringify(p.user).replace(/</g,'\\u003c')+')" class="text-blue-600 text-xs mr-1">编辑</button><button type="button" onclick="removeParticipant(\\'new\\','+JSON.stringify(p.user).replace(/</g,'\\u003c')+')" class="text-red-600 text-xs">删除</button></span></li>'; }).join('') || '<li class="text-gray-400 text-xs">暂无参与人员</li>'; }
function renderEditParticipants(){ var ul=document.getElementById('editParticipantsList'); if(!ul) return; ul.innerHTML=editParticipants.map(function(p){ return '<li class="flex justify-between items-center py-1"><span>'+p.user+' <span class="text-gray-500">('+p.role+')</span></span><span><button type="button" onclick="editParticipantRole(\\'edit\\','+JSON.stringify(p.user).replace(/</g,'\\u003c')+')" class="text-blue-600 text-xs mr-1">编辑</button><button type="button" onclick="removeParticipant(\\'edit\\','+JSON.stringify(p.user).replace(/</g,'\\u003c')+')" class="text-red-600 text-xs">删除</button></span></li>'; }).join('') || '<li class="text-gray-400 text-xs">暂无参与人员</li>'; }
function addNewParticipant(){ var u=(document.getElementById('newParticipantUser')||{}).value.trim(); if(!u){ alert('请输入用户名'); return; } fetch('/admin/projects/validate-username?username='+encodeURIComponent(u)).then(r=>r.json()).then(function(d){ if(!d.exists){ alert('用户不存在或已禁用'); return; } if(newParticipants.some(function(p){ return p.user===u; })){ alert('已添加过'); return; } _participantCtx='new'; _pendingParticipantUser=u; document.getElementById('roleModalUsername').textContent=u; document.getElementById('roleModalRole').value='其他'; document.getElementById('participantRoleModal').classList.remove('hidden'); }); }
function addEditParticipant(){ var u=(document.getElementById('editParticipantUser')||{}).value.trim(); if(!u){ alert('请输入用户名'); return; } fetch('/admin/projects/validate-username?username='+encodeURIComponent(u)).then(r=>r.json()).then(function(d){ if(!d.exists){ alert('用户不存在或已禁用'); return; } if(editParticipants.some(function(p){ return p.user===u; })){ alert('已添加过'); return; } _participantCtx='edit'; _pendingParticipantUser=u; document.getElementById('roleModalUsername').textContent=u; document.getElementById('roleModalRole').value='其他'; document.getElementById('participantRoleModal').classList.remove('hidden'); }); }
function confirmParticipantRole(){ var r=(document.getElementById('roleModalRole')||{}).value||'其他'; var arr=_participantCtx==='new'?newParticipants:editParticipants; var exists=arr.find(function(x){ return x.user===_pendingParticipantUser; }); if(exists){ exists.role=r; } else { arr.push({user:_pendingParticipantUser,role:r}); if(_participantCtx==='new') document.getElementById('newParticipantUser').value=''; else document.getElementById('editParticipantUser').value=''; } if(_participantCtx==='new') renderNewParticipants(); else renderEditParticipants(); document.getElementById('participantRoleModal').classList.add('hidden'); }
function editParticipantRole(ctx, user){ var arr=ctx==='new'?newParticipants:editParticipants; var p=arr.find(function(x){ return x.user===user; }); if(!p) return; _participantCtx=ctx; _pendingParticipantUser=user; document.getElementById('roleModalUsername').textContent=user; document.getElementById('roleModalRole').value=p.role; document.getElementById('participantRoleModal').classList.remove('hidden'); }
function removeParticipant(ctx, user){ if(ctx==='new'){ newParticipants=newParticipants.filter(function(p){ return p.user!==user; }); renderNewParticipants(); } else { editParticipants=editParticipants.filter(function(p){ return p.user!==user; }); renderEditParticipants(); } }
function setAddFeedback(msg, isError){
    var el = document.getElementById('addProjectFeedback');
    if(!el) return;
    el.textContent = msg || '';
    el.className = 'min-h-[2rem] text-sm font-medium py-1 ' + (isError ? 'text-red-600' : 'text-green-600');
    if(msg) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function addProject(){
    var btn = document.getElementById('addProjectBtn');
    try {
        if(btn){ btn.disabled=true; btn.textContent='提交中…'; }
        setAddFeedback('提交中…', false);
        var viewers = parseUserList((document.getElementById('newProjectViewers')||{}).value);
        var phaseEl = document.getElementById('newProjectPhase'); var phase = phaseEl ? phaseEl.value : 'kickoff';
        var editors = newParticipants.map(function(p){ return p.user; });
        var member_roles = {}; newParticipants.forEach(function(p){ member_roles[p.user]=p.role||'其他'; });
        var payload = { id: (document.getElementById('newProjectId')||{}).value.trim(), name: (document.getElementById('newProjectName')||{}).value.trim(), name_en: (document.getElementById('newProjectNameEn')||{}).value.trim(), phase: phase, icon: (document.getElementById('newProjectIcon')||{}).value.trim(), intro: (document.getElementById('newProjectIntro')||{}).value.trim(), detail: (document.getElementById('newProjectDetail')||{}).value.trim(), network_connection: (document.getElementById('newProjectNetwork')||{}).value.trim(), git_url: (document.getElementById('newProjectGitUrl')||{}).value.trim(), git_ssh_key_path: (document.getElementById('newProjectGitSshKey')||{}).value.trim(), player_public_url: (document.getElementById('newProjectPlayerPublicUrl')||{}).value.trim(), forum_public_url: (document.getElementById('newProjectForumPublicUrl')||{}).value.trim(), admin_public_url: (document.getElementById('newProjectAdminPublicUrl')||{}).value.trim(), viewers: viewers, editors: editors, member_roles: member_roles, game_id: (document.getElementById('newProjectGameId')||{}).value.trim(), game_key: (document.getElementById('newProjectGameKey')||{}).value.trim() };
        if(!payload.id||!payload.name){ setAddFeedback('请填写项目ID和名称', true); if(btn){ btn.disabled=false; btn.textContent='添加项目'; } return; }
        if(!payload.game_id || !payload.game_key){ setAddFeedback('请先点击“系统生成凭据”', true); if(btn){ btn.disabled=false; btn.textContent='添加项目'; } return; }
        fetch('/admin/projects/create', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload), credentials:'same-origin' })
        .then(function(r){ var ct = r.headers.get('Content-Type')||''; return r.text().then(function(t){ var d; try{ d = (ct.indexOf('json')>=0 && t) ? JSON.parse(t) : {}; } catch(e){ d = { error: t && t.length<200 ? t : (r.status===403 ? '无权限或未登录' : r.status===302 ? '请先登录' : '请求异常') }; } return { ok: r.ok, status: r.status, data: d }; }); })
        .then(function(res){ if(btn){ btn.disabled=false; btn.textContent='添加项目'; } var d=res.data; if(!res.ok || d.error){ setAddFeedback(d.error||'添加失败（'+res.status+'）', true); return; } setAddFeedback('添加成功，已刷新列表', false); loadProjects(); setTimeout(function(){ var f=document.getElementById('addProjectForm'); if(f) f.classList.add('hidden'); setAddFeedback('', false); }, 1500); })
        .catch(function(err){ if(btn){ btn.disabled=false; btn.textContent='添加项目'; } setAddFeedback('网络错误或请求失败: '+(err.message||''), true); });
    } catch(e) {
        if(btn){ btn.disabled=false; btn.textContent='添加项目'; }
        setAddFeedback('错误: ' + (e.message || String(e)), true);
    }
}
function generateProjectCredentials(){
    var pid = (document.getElementById('newProjectId')||{}).value.trim() || 'project';
    fetch('/admin/projects/generate-credentials', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ id: pid }), credentials:'same-origin' })
    .then(function(r){ return r.json(); })
    .then(function(d){
        if(d.error){ alert(d.error); return; }
        document.getElementById('newProjectGameId').value = d.game_id || '';
        document.getElementById('newProjectGameKey').value = d.game_key || '';
    })
    .catch(function(){ alert('生成凭据失败'); });
}
function uploadProjectIcon(fileInput, hiddenId, previewId, callback){
    if(!fileInput||!fileInput.files||!fileInput.files[0]) return;
    var fd=new FormData(); fd.append('icon', fileInput.files[0]);
    fetch('/admin/projects/upload-icon', { method:'POST', body: fd, credentials:'same-origin' }).then(r=>r.json()).then(function(d){ if(d.url){ var h=document.getElementById(hiddenId); if(h) h.value=d.url; var el=document.getElementById(previewId); if(el) el.innerHTML='<img src="'+d.url+'" alt="" class="h-10 w-10 rounded object-cover">'; if(callback) callback(d.url); } else alert(d.error||'上传失败'); });
}
var _el = document.getElementById('newProjectIconFile'); if(_el) _el.onchange=function(){ uploadProjectIcon(this, 'newProjectIcon', 'newProjectIconPreview'); };
_el = document.getElementById('editProjectIconFile'); if(_el) _el.onchange=function(){ uploadProjectIcon(this, 'editProjectIcon', 'editProjectIconPreview'); };
function renderProjectsTable(projects){
    var q=(document.getElementById('projectSearch')||{}).value||''; q=q.trim().toLowerCase();
    var list = q ? projects.filter(function(p){ return (p.id||'').toLowerCase().indexOf(q)>=0 || (p.name||'').toLowerCase().indexOf(q)>=0 || (p.name_en||'').toLowerCase().indexOf(q)>=0; }) : projects;
    var t=document.getElementById('projectsTable');
    t.innerHTML = list.map(function(p, i){
        var rowClass = (i%2===0) ? 'bg-white' : 'bg-slate-50/60';
        var iconHtml = p.icon ? '<img src="'+p.icon+'" alt="" class="w-8 h-8 rounded-lg object-cover ring-1 ring-slate-200/80" onerror="this.style.display=\\'none\\'">' : '<span class="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-slate-100 text-slate-400 text-xs"><i class="fas fa-folder"></i></span>';
        var phaseLabel = p.phase_label || p.phase || '-';
        var introSnip = (p.intro||'').slice(0,20); if((p.intro||'').length>20) introSnip+='…';
        var dateStr = (p.created_at||'').slice(0,19).replace('T',' ') || '-';
        var canEdit = p.can_edit;
        var statusBadge = (p.status==='archived') ? ' <span class="px-2 py-0.5 rounded text-xs bg-gray-200 text-gray-600">已归档</span>' : ((p.is_template) ? ' <span class="px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-800">模板</span>' : '');
        var archiveBtn = canEdit && p.status!=='archived'
            ? '<button onclick="archiveProject(\\''+p.id+'\\', true)" class="inline-flex items-center whitespace-nowrap px-2.5 py-1 text-xs text-slate-600 bg-slate-50 hover:bg-slate-100 rounded-lg">归档</button>'
            : (canEdit && p.status==='archived'
                ? '<button onclick="archiveProject(\\''+p.id+'\\', false)" class="inline-flex items-center whitespace-nowrap px-2.5 py-1 text-xs text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-lg">取消归档</button>'
                : '');
        var actions = '<a href="/admin/projects/'+p.id+'" class="inline-flex items-center whitespace-nowrap px-2 py-1 text-xs font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 rounded">项目中心</a>'
            + '<a href="/admin/projects/'+p.id+'/tasks" class="inline-flex items-center whitespace-nowrap px-2 py-1 text-xs text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded">任务</a>'
            + '<a href="/admin/projects/'+p.id+'/versions" class="inline-flex items-center whitespace-nowrap px-2 py-1 text-xs text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded">版本</a>';
        if(canEdit){
            actions += '<button onclick="editProject(\\''+p.id+'\\')" class="inline-flex items-center whitespace-nowrap px-2 py-1 text-xs text-blue-700 bg-blue-50 hover:bg-blue-100 rounded">编辑</button>';
            actions += '<button onclick="deleteProject(\\''+p.id+'\\')" class="inline-flex items-center whitespace-nowrap px-2 py-1 text-xs text-red-700 bg-red-50 hover:bg-red-100 rounded">删除</button>';
        } else {
            actions += '<span class="text-slate-400 text-xs whitespace-nowrap">仅查看</span>';
        }
        return '<tr class="'+rowClass+' hover:bg-indigo-50/40"><td class="px-6 py-2.5 align-middle">'+iconHtml+'</td><td class="px-6 py-2.5 align-middle font-medium text-slate-900 whitespace-nowrap">'+p.id+'</td><td class="px-6 py-2.5 align-middle text-slate-800">'+p.name+statusBadge+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-500">'+(p.name_en||'-')+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-500 whitespace-nowrap">'+phaseLabel+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-500 max-w-[140px] truncate" title="'+((p.intro||'')+'').replace(/"/g,'&quot;')+'">'+introSnip+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-500">'+(p.created_by||'-')+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-500 whitespace-nowrap">'+dateStr+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-600">'+(p.task_count||0)+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-600">'+p.apk_count+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-600">'+(p.download_count||0)+'</td><td class="px-6 py-2.5 align-middle min-w-[280px]"><div class="flex items-center gap-1.5 flex-nowrap overflow-x-auto">'+actions+'</div></td></tr>';
    }).join('');
}
function openChannelManageModal(){
    document.getElementById('channelManageModal').classList.remove('hidden');
    loadChannels();
}
function closeChannelManageModal(){
    document.getElementById('channelManageModal').classList.add('hidden');
}
function resetChannelForm(){
    document.getElementById('channelFormEditingId').value='';
    document.getElementById('channelFormId').disabled=false;
    document.getElementById('channelFormId').value='';
    document.getElementById('channelFormName').value='';
    document.getElementById('channelFormOrder').value='0';
    document.getElementById('channelFormDesc').value='';
    var apkEl=document.getElementById('channelFormApkSubdir'); if(apkEl) apkEl.value='';
    var bpEl=document.getElementById('channelFormBuildParam'); if(bpEl) bpEl.value='';
}
function fillChannelForm(ch){
    document.getElementById('channelFormEditingId').value = ch.id || '';
    var idEl = document.getElementById('channelFormId');
    idEl.value = ch.id || '';
    idEl.disabled = true;
    document.getElementById('channelFormName').value = ch.name || '';
    document.getElementById('channelFormOrder').value = (ch.order!=null ? ch.order : 0);
    document.getElementById('channelFormDesc').value = ch.description || '';
    var apkEl=document.getElementById('channelFormApkSubdir'); if(apkEl) apkEl.value=ch.apk_subdir||'';
    var bpEl=document.getElementById('channelFormBuildParam'); if(bpEl) bpEl.value=ch.build_param||'';
}
function renderChannelTable(){
    var tbody = document.getElementById('channelTableBody');
    var empty = document.getElementById('channelEmptyTip');
    if(!tbody) return;
    if(!_channelsCache || !_channelsCache.length){
        tbody.innerHTML = '';
        if(empty) empty.classList.remove('hidden');
        return;
    }
    if(empty) empty.classList.add('hidden');
    tbody.innerHTML = _channelsCache.map(function(ch){
        var subdir = (ch.apk_subdir||'').slice(0,12);
        var bp = (ch.build_param||'').slice(0,20);
        var badge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[10px]">'+(ch.id||'')+'</span>';
        var chId = (ch.id||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
        return '<tr>'
            + '<td class="py-1.5 pr-2">'+badge+'</td>'
            + '<td class="py-1.5 pr-2">'+(ch.name||'-')+'</td>'
            + '<td class="py-1.5 pr-2 text-slate-500">'+(subdir||'-')+'</td>'
            + '<td class="py-1.5 pr-2 text-slate-500">'+(bp||'-')+'</td>'
            + '<td class="py-1.5 space-x-1">'
            +   '<button type="button" class="channel-edit-btn px-2 py-0.5 text-[11px] text-blue-700 bg-blue-50 hover:bg-blue-100 rounded" data-channel-id="'+chId+'">编辑</button>'
            +   '<button type="button" class="channel-delete-btn px-2 py-0.5 text-[11px] text-red-700 bg-red-50 hover:bg-red-100 rounded" data-channel-id="'+chId+'">删除</button>'
            + '</td>'
            + '</tr>';
    }).join('');
}
function loadChannels(){
    fetch('/admin/channels', { credentials:'same-origin' }).then(function(r){ return r.json(); }).then(function(d){
        _channelsCache = d.channels || [];
        renderChannelTable();
    }).catch(function(){
        _channelsCache = [];
        renderChannelTable();
    });
}
function submitChannelForm(){
    var editingId = document.getElementById('channelFormEditingId').value || '';
    var id = document.getElementById('channelFormId').value.trim();
    var name = document.getElementById('channelFormName').value.trim();
    var order = document.getElementById('channelFormOrder').value;
    var desc = document.getElementById('channelFormDesc').value.trim();
    var apkSubdir = (document.getElementById('channelFormApkSubdir')||{}).value.trim();
    var buildParam = (document.getElementById('channelFormBuildParam')||{}).value.trim();
    if(!id || !name){
        alert('请填写渠道 ID 和名称');
        return;
    }
    var payload = { id: id, name: name, order: order, description: desc, apk_subdir: apkSubdir, build_param: buildParam };
    var url = editingId ? '/admin/channels/update' : '/admin/channels/create';
    fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload), credentials:'same-origin' }).then(function(r){ return r.json(); }).then(function(d){
        if(d.error){
            alert(d.error);
            return;
        }
        resetChannelForm();
        loadChannels();
    });
}
document.addEventListener('click', function(e){
    var editBtn = e.target.closest('.channel-edit-btn');
    if(editBtn){ var id = editBtn.getAttribute('data-channel-id'); if(id && _channelsCache){ var ch = _channelsCache.find(function(c){ return (c.id||'')===id; }); if(ch) fillChannelForm(ch); } return; }
    var delBtn = e.target.closest('.channel-delete-btn');
    if(delBtn){ var id = delBtn.getAttribute('data-channel-id'); if(id) deleteChannel(id); }
}, true);
function deleteChannel(id){
    if(!id) return;
    if(!confirm('确定删除渠道 '+id+'？若已有版本使用该渠道，将无法删除。')) return;
    fetch('/admin/channels/delete/'+encodeURIComponent(id), { method:'DELETE', credentials:'same-origin' }).then(function(r){
        var ct = (r.headers.get('Content-Type')||'').toLowerCase();
        if(ct.indexOf('application/json')<0) throw new Error('需要重新登录');
        return r.text();
    }).then(function(text){
        try{ return JSON.parse(text||'{}'); } catch(e){ throw new Error('解析失败，请刷新重试'); }
    }).then(function(d){
        if(d.error){ alert(d.error); return; }
        loadChannels();
    }).catch(function(e){ alert(e.message||'删除失败，请刷新重试'); });
}
function loadProjects(){
    var statusFilter = (document.getElementById('projectStatusFilter')||{}).value || 'active';
    fetch('/admin/projects/list?status='+encodeURIComponent(statusFilter), { credentials: 'same-origin' }).then(function(r){
        if(!r.ok) throw new Error(''+r.status);
        var ct = (r.headers.get('Content-Type')||'').toLowerCase();
        if(ct.indexOf('application/json')<0) throw new Error('需要重新登录');
        return r.text();
    }).then(function(text){
        try{ return JSON.parse(text); } catch(e){ throw new Error('解析失败，请刷新或重新登录'); }
    }).then(function(d){ allProjectsCache = d.projects||[]; renderProjectsTable(allProjectsCache); }).catch(function(e){ allProjectsCache = []; var t = document.getElementById('projectsTable'); if(t) t.innerHTML = '<tr><td colspan="12" class="px-6 py-8 text-center text-red-500">加载失败（'+ (e.message||'请刷新或重新登录') +'）</td></tr>'; });
}
function editProject(id){
    fetch('/admin/projects/get/'+encodeURIComponent(id)).then(r=>r.json()).then(d=>{
        if(d.error){ alert(d.error); return; }
        var p=d.project;
        document.getElementById('editProjectIdLabel').textContent=id;
        document.getElementById('editProjectName').value=p.name||'';
        document.getElementById('editProjectNameEn').value=p.name_en||'';
        var phaseSel=document.getElementById('editProjectPhase'); if(phaseSel) phaseSel.value=p.phase||'kickoff';
        document.getElementById('editProjectIcon').value=p.icon||'';
        editParticipants=(p.editors||[]).map(function(u){ return {user:u, role:(p.member_roles||{})[u]||'其他'}; }); renderEditParticipants();
        document.getElementById('editProjectViewers').value=(p.viewers||[]).join(', ');
        var projChans = p.channels||[];
        var chWrap = document.getElementById('editProjectChannels');
        if(chWrap && ALL_CHANNELS){
            chWrap.innerHTML = ALL_CHANNELS.map(function(c){ return '<label class="flex items-center gap-1.5"><input type="checkbox" class="edit-channel-cb" value="'+c.id+'" '+(projChans.indexOf(c.id)>=0?'checked':'')+'><span>'+c.name+'</span></label>'; }).join('');
        }
        document.getElementById('editProjectIntro').value=p.intro||'';
        document.getElementById('editProjectDetail').value=p.detail||'';
        document.getElementById('editProjectNetwork').value=p.network_connection||'';
        document.getElementById('editProjectGitUrl').value=p.git_url||'';
        document.getElementById('editProjectGitSshKey').value=p.git_ssh_key_path||'';
        var playerUrlEl = document.getElementById('editProjectPlayerPublicUrl'); if(playerUrlEl) playerUrlEl.value=p.player_public_url||'';
        var forumUrlEl = document.getElementById('editProjectForumPublicUrl'); if(forumUrlEl) forumUrlEl.value=p.forum_public_url||'';
        var adminUrlEl = document.getElementById('editProjectAdminPublicUrl'); if(adminUrlEl) adminUrlEl.value=p.admin_public_url||'';
        var prev=document.getElementById('editProjectIconPreview'); prev.innerHTML=p.icon ? '<img src="'+p.icon+'" alt="" class="h-10 w-10 rounded object-cover">' : '';
        document.getElementById('editProjectIconFile').value='';
        document.getElementById('editProjectModal').classList.remove('hidden');
    });
}
function saveEditProject(){
    var id = document.getElementById('editProjectIdLabel').textContent;
    var viewers = parseUserList(document.getElementById('editProjectViewers').value);
    var editors = editParticipants.map(function(p){ return p.user; });
    var member_roles = {}; editParticipants.forEach(function(p){ member_roles[p.user]=p.role||'其他'; });
    var phaseEl = document.getElementById('editProjectPhase'); var phase = phaseEl ? phaseEl.value : 'kickoff';
    var channels = []; document.querySelectorAll('.edit-channel-cb:checked').forEach(function(cb){ channels.push(cb.value); });
    var payload = { id: id, name: document.getElementById('editProjectName').value.trim(), name_en: document.getElementById('editProjectNameEn').value.trim(), phase: phase, icon: document.getElementById('editProjectIcon').value.trim(), intro: document.getElementById('editProjectIntro').value.trim(), detail: document.getElementById('editProjectDetail').value.trim(), network_connection: document.getElementById('editProjectNetwork').value.trim(), git_url: document.getElementById('editProjectGitUrl').value.trim(), git_ssh_key_path: document.getElementById('editProjectGitSshKey').value.trim(), player_public_url: (document.getElementById('editProjectPlayerPublicUrl')||{}).value.trim(), forum_public_url: (document.getElementById('editProjectForumPublicUrl')||{}).value.trim(), admin_public_url: (document.getElementById('editProjectAdminPublicUrl')||{}).value.trim(), viewers: viewers, editors: editors, member_roles: member_roles, channels: channels };
    fetch('/admin/projects/update', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) }).then(r=>r.json()).then(d=>{ alert(d.error||'已保存'); if(!d.error) { document.getElementById('editProjectModal').classList.add('hidden'); loadProjects(); } });
}
function archiveProject(id, archive){ fetch('/admin/projects/'+encodeURIComponent(id)+'/archive', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({archive: archive}), credentials:'same-origin' }).then(r=>r.json()).then(d=>{ alert(d.error||(archive?'已归档':'已取消归档')); if(!d.error) loadProjects(); }); }
function deleteProject(id){ if(!confirm('确定删除项目 '+id+'？')) return; fetch('/admin/projects/delete/'+encodeURIComponent(id), { method:'DELETE' }).then(r=>r.json()).then(d=>{ alert(d.error||'已删除'); if(!d.error) loadProjects(); }); }
function ensureProjectDomainFields(){
    var addViewerInput = document.getElementById('newProjectViewers');
    if(addViewerInput && !document.getElementById('newProjectPlayerPublicUrl')){
        var addRow = document.createElement('div');
        addRow.className = 'grid grid-cols-1 md:grid-cols-3 gap-4';
        addRow.innerHTML =
            '<div><label class="block text-xs font-medium text-slate-500 mb-1">玩家官网域名</label><input type="text" id="newProjectPlayerPublicUrl" placeholder="https://game.example.com" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>'
            + '<div><label class="block text-xs font-medium text-slate-500 mb-1">论坛域名</label><input type="text" id="newProjectForumPublicUrl" placeholder="https://forum.example.com" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>'
            + '<div><label class="block text-xs font-medium text-slate-500 mb-1">开发后台域名</label><input type="text" id="newProjectAdminPublicUrl" placeholder="https://studio.example.com" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>';
        var addTargetRow = addViewerInput.closest('div.grid');
        if(addTargetRow && addTargetRow.parentNode){
            addTargetRow.parentNode.insertBefore(addRow, addTargetRow);
        }
    }
    var editViewerInput = document.getElementById('editProjectViewers');
    if(editViewerInput && !document.getElementById('editProjectPlayerPublicUrl')){
        var editRow = document.createElement('div');
        editRow.className = 'grid grid-cols-1 md:grid-cols-3 gap-4';
        editRow.innerHTML =
            '<div><label class="block text-xs font-medium text-gray-500 mb-1">玩家官网域名</label><input type="text" id="editProjectPlayerPublicUrl" placeholder="https://game.example.com" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>'
            + '<div><label class="block text-xs font-medium text-gray-500 mb-1">论坛域名</label><input type="text" id="editProjectForumPublicUrl" placeholder="https://forum.example.com" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>'
            + '<div><label class="block text-xs font-medium text-gray-500 mb-1">开发后台域名</label><input type="text" id="editProjectAdminPublicUrl" placeholder="https://studio.example.com" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>';
        var editTargetRow = editViewerInput.closest('div.grid');
        if(editTargetRow && editTargetRow.parentNode){
            editTargetRow.parentNode.insertBefore(editRow, editTargetRow);
        }
    }
}
ensureProjectDomainFields();
var searchEl = document.getElementById('projectSearch'); if(searchEl) searchEl.oninput = function(){ renderProjectsTable(allProjectsCache); };
loadProjects();
</script>
'''


def _current_username():
    return session.get('user') or ''


@bp.route('/admin/projects')
@admin_required('projects')
def admin_projects_page():
    return _admin_layout(PROJECTS_PAGE, '项目管理')


# ---------- 项目详情页（商业级仪表盘、版本管理、构建入口） ----------

def _get_version_channels(project_id=None):
    """从 channels_db 生成版本渠道下拉选项；若指定 project_id 则按项目「可用渠道」过滤。"""
    chans = get_channels_for_project(project_id) if project_id else (channels_db if isinstance(channels_db, list) else [])
    if not chans and project_id:
        chans = channels_db if isinstance(channels_db, list) else []
    if chans:
        tmp = [(c.get('id', '').strip(), (c.get('name') or c.get('id', '')).strip()) for c in chans if (c.get('id') or '').strip()]
        return tmp
    return [('dev', '开发版'), ('test', '测试版'), ('production', '线上版')]

VERSION_CHANNELS = _get_version_channels()
VERSION_STAGES = [('dev', '开发'), ('test', '测试'), ('production', '线上')]
VERSION_STATUSES = [('draft', '草稿'), ('testing', '测试中'), ('active', '有效'), ('disabled', '失效'), ('archived', '归档')]
STAGE_MAP = dict(VERSION_STAGES)
VERSION_STATUS_MAP = dict(VERSION_STATUSES)
PHASE_MAP = dict(PROJECT_PHASES)
STATUS_MAP = dict(TASK_STATUSES)


def _normalize_version_status(raw_status):
    status = (raw_status or '').strip().lower()
    aliases = {
        'draft': 'draft',
        'valid': 'active',
        'enabled': 'active',
        'online': 'active',
        'deprecated': 'disabled',
        'obsolete': 'disabled',
        'invalid': 'disabled',
        'disabled': 'disabled',
        'inactive': 'disabled',
        'testing': 'testing',
        'test': 'testing',
        'beta': 'testing',
        'archived': 'archived',
        'archive': 'archived',
    }
    status = aliases.get(status, status)
    if status not in VERSION_STATUS_MAP:
        status = 'active'
    return status


def _project_download_tab_html(apk_files, project_id):
    """生成项目下载 Tab 的 APK 列表 HTML（扫码、下载、Changelog 预览）"""
    if not apk_files:
        return '<div class="py-12 text-center text-slate-500 rounded-xl border border-slate-100 bg-slate-50/50"><p class="text-sm">暂无安装包，构建或上传后将在此展示</p><a href="/admin/projects/' + html.escape(project_id) + '/build" class="mt-2 inline-block text-indigo-600 hover:underline text-sm">前往构建</a></div>'
    rows = []
    for f in apk_files:
        fname = f.get('name', '')
        ch_text, is_rec = get_changelog_for_file(fname)
        ch_text = (ch_text or '')[:60]
        rec_badge = '<span class="px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-800">推荐</span>' if is_rec else ''
        platform_badge = '<span class="px-2 py-0.5 rounded text-xs bg-sky-100 text-sky-700">' + html.escape(f.get('platform_label') or '-') + '</span>'
        dl_count = download_stats.get(fname, 0)
        down_url = '/download/' + quote(fname, safe='')
        fname_esc = fname.replace("\\", "\\\\").replace("'", "\\'")
        rows.append(
            '<div class="flex items-center justify-between py-4 border-b border-slate-100 last:border-0 hover:bg-slate-50/50 transition rounded-lg px-3 -mx-3">'
            '<div class="min-w-0 flex-1">'
            '<div class="font-medium text-slate-800 truncate">' + html.escape(fname) + ' ' + platform_badge + ' ' + rec_badge + '</div>'
            '<div class="text-xs text-slate-500 mt-0.5">' + html.escape(f.get('platform_label') or '-') + ' · v' + html.escape(str(f.get('version', '-'))) + ' · ' + str(f.get('size_mb', 0)) + ' MB · 下载 ' + str(dl_count) + ' 次</div>'
            + ('<div class="text-xs text-slate-400 mt-0.5 truncate" title="' + html.escape(ch_text) + '">' + html.escape(ch_text or '') + '</div>' if ch_text else '') +
            '</div>'
            '<div class="flex gap-2 flex-shrink-0 ml-3">'
            '<button type="button" onclick="window._showQR(\'' + fname_esc + '\')" class="px-3 py-1.5 rounded-lg border border-slate-200 text-slate-700 text-xs hover:bg-slate-50">扫码</button>'
            '<a href="' + down_url + '" class="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs hover:bg-indigo-700">下载</a>'
            '</div></div>'
        )
    return '<div class="divide-y divide-slate-100">' + ''.join(rows) + '</div>'


def _escape_script_json_for_html(s):
    """防止 JSON 中的 </script> 提前关闭 script 标签（用于 type=application/json 的 script 内）"""
    if not isinstance(s, str):
        return s
    return re.sub(r'(?i)</script>', r'<\\u002fscript>', s)


def _project_detail_html(project_id, proj, can_edit, task_stats, recent_tasks, apk_count, project_apk_files=None, is_admin_logged_in=False):
    """项目详情页：仪表盘、版本管理、构建、下载"""
    project_apk_files = project_apk_files or []
    project_name = _clean_display_text(proj.get('name'), project_id)
    versions = (project_versions_db.get(project_id) or [])
    if not isinstance(versions, list):
        versions = []
    channel_map = dict(_get_version_channels(project_id))
    proj_channel_ids = proj.get('channels') or []
    all_channels_list = [(c.get('id', '').strip(), (c.get('name') or c.get('id', '')).strip()) for c in (channels_db if isinstance(channels_db, list) else []) if (c.get('id') or '').strip()]
    proj_channels_display = [(c.get('id', '').strip(), (c.get('name') or c.get('id', '')).strip()) for c in (channels_db if isinstance(channels_db, list) else []) if (c.get('id') or '').strip() and (c.get('id') or '').strip() in proj_channel_ids] if proj_channel_ids else all_channels_list
    def _version_changelog(ver):
        key = 'version:' + project_id + ':' + (ver.get('id') or '')
        raw = changelog_db.get(key)
        if isinstance(raw, dict):
            return raw.get('text', ''), bool(raw.get('recommended'))
        return '', False
    versions_data = [{
        **v,
        'platform': get_version_platform(v),
        'platform_label': get_platform_label(get_version_platform(v)),
        'distribution_method': _normalize_distribution_method(get_version_platform(v), v.get('distribution_method')),
        'package_name': (v.get('package_name') or '').strip(),
        'min_sdk': (v.get('min_sdk') or '').strip(),
        'bundle_id': (v.get('bundle_id') or '').strip(),
        'min_ios_version': (v.get('min_ios_version') or '').strip(),
        'stage': (v.get('stage') or 'dev').strip() or 'dev',
        'stage_label': STAGE_MAP.get((v.get('stage') or 'dev').strip(), '开发'),
        'version_status': _normalize_version_status(v.get('version_status') or 'active'),
        'version_status_label': VERSION_STATUS_MAP.get(_normalize_version_status(v.get('version_status') or 'active'), '有效'),
        'channel_label': channel_map.get(v.get('channel', ''), v.get('channel', '')),
        'apk_status': 'found' if version_has_apk(project_id, v) else 'not_found',
        'download_count': get_version_download_count(project_id, v),
        'recommended': version_is_recommended(project_id, v),
        'changelog_text': _version_changelog(v)[0],
        'changelog_recommended': _version_changelog(v)[1],
    } for v in versions]
    phase_label = PHASE_MAP.get(proj.get('phase', ''), proj.get('phase') or '-')
    editors = proj.get('editors') or []
    viewers = proj.get('viewers') or []
    team = list(set(editors + viewers))
    intro = (proj.get('intro') or proj.get('detail') or '')[:200]
    created_at = (proj.get('created_at') or '')[:10]
    git_url = proj.get('git_url') or ''
    version_count = len(versions)
    # 最近任务行
    recent_rows = ''
    for t in recent_tasks[:8]:
        st = t.get('status', '')
        st_label = STATUS_MAP.get(st, st)
        title = _clean_display_text(t.get('title'), '未命名任务')[:50]
        assignee = _clean_display_text(t.get('current_assignee') or t.get('current_role'), '-') or '-'
        tid = t.get('id', '')
        recent_rows += '<tr class="border-b border-gray-100 hover:bg-indigo-50/50"><td class="py-2.5 text-sm"><a href="/admin/projects/%s/tasks" class="text-indigo-600 hover:underline font-medium">%s</a></td><td class="py-2.5 text-xs text-gray-500">%s</td><td class="py-2.5"><span class="px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-700">%s</span></td></tr>' % (project_id, html.escape(title), html.escape(assignee), st_label)
    if not recent_rows:
        recent_rows = '<tr><td colspan="3" class="py-8 text-center text-gray-500 text-sm">暂无任务</td></tr>'
    dl_count = get_project_download_count(project_id)
    # 统计卡片
    stats_html = '''<div class="grid grid-cols-2 md:grid-cols-7 gap-4 mb-6">
        <div class="stat-card rounded-2xl border border-slate-200/80 shadow-sm p-4 bg-white/95">
            <p class="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.14em]">任务总数</p>
            <p class="text-2xl font-bold text-slate-900 mt-1">%d</p>
            <a href="/admin/projects/%s/tasks" class="text-xs text-indigo-600 hover:text-indigo-700 hover:underline mt-1 inline-flex items-center gap-1">查看全部<i class="fas fa-arrow-right text-[10px]"></i></a>
        </div>
        <div class="stat-card rounded-2xl border border-indigo-100 shadow-sm p-4 bg-indigo-50/70">
            <p class="text-[11px] font-semibold text-indigo-600 uppercase tracking-[0.14em]">进行中</p>
            <p class="text-2xl font-bold text-indigo-700 mt-1">%d</p>
        </div>
        <div class="stat-card rounded-2xl border border-amber-100 shadow-sm p-4 bg-amber-50/70">
            <p class="text-[11px] font-semibold text-amber-600 uppercase tracking-[0.14em]">待验收</p>
            <p class="text-2xl font-bold text-amber-700 mt-1">%d</p>
        </div>
        <div class="stat-card rounded-2xl border border-emerald-100 shadow-sm p-4 bg-emerald-50/70">
            <p class="text-[11px] font-semibold text-emerald-600 uppercase tracking-[0.14em]">已完成</p>
            <p class="text-2xl font-bold text-emerald-700 mt-1">%d</p>
        </div>
        <div class="stat-card rounded-2xl border border-slate-200/80 shadow-sm p-4 bg-white/95">
            <p class="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.14em]">版本数</p>
            <p class="text-2xl font-bold text-slate-900 mt-1">%d</p>
        </div>
        <div class="stat-card rounded-2xl border border-slate-200/80 shadow-sm p-4 bg-white/95">
            <p class="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.14em]">安装包数</p>
            <p class="text-2xl font-bold text-slate-900 mt-1">%d</p>
        </div>
        <div class="stat-card rounded-2xl border border-slate-200/80 shadow-sm p-4 bg-white/95">
            <p class="text-[11px] font-semibold text-slate-500 uppercase tracking-[0.14em]">下载量</p>
            <p class="text-2xl font-bold text-slate-900 mt-1">%d</p>
            <p id="projectTrend7d" class="text-xs text-slate-500 mt-0.5">—</p>
        </div>
    </div>''' % (
        task_stats.get('total', 0), project_id,
        task_stats.get('in_progress', 0),
        task_stats.get('pending_review', 0),
        task_stats.get('done', 0),
        version_count,
        apk_count,
        dl_count,
    )
    return '''<div class="space-y-6">
    <style>
        .wb-action-btn {
            display: inline-flex;
            align-items: center;
            gap: 0.375rem;
            padding: 0.625rem 1rem;
            border-radius: 0.85rem;
            border: 1px solid rgba(255, 255, 255, 0.26);
            color: #ffffff;
            font-size: 0.875rem;
            font-weight: 600;
            line-height: 1;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.26), 0 7px 20px rgba(15, 23, 42, 0.28);
            transition: transform .15s ease, box-shadow .15s ease, filter .15s ease;
        }
        .wb-action-btn:hover {
            transform: translateY(-1px);
            filter: brightness(1.05);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3), 0 10px 24px rgba(15, 23, 42, 0.32);
        }
        .wb-action-btn:active {
            transform: translateY(0);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.2), 0 4px 12px rgba(15, 23, 42, 0.22);
        }
        .wb-indigo { background: linear-gradient(160deg, #4f46e5, #4338ca); }
        .wb-orange { background: linear-gradient(160deg, #f97316, #ea580c); }
        .wb-emerald { background: linear-gradient(160deg, #10b981, #059669); }
        .wb-cyan { background: linear-gradient(160deg, #06b6d4, #0891b2); }
        .wb-violet { background: linear-gradient(160deg, #8b5cf6, #7c3aed); }
        .wb-slate { background: linear-gradient(160deg, #64748b, #475569); }

        .wb-quick-btn {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.62rem 0.8rem;
            border-radius: 0.85rem;
            border: 1px solid transparent;
            color: #0f172a;
            font-size: 0.875rem;
            font-weight: 500;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.45), 0 4px 14px rgba(15, 23, 42, 0.08);
            transition: transform .15s ease, filter .15s ease, box-shadow .15s ease;
        }
        .wb-quick-btn:hover {
            transform: translateY(-1px);
            filter: brightness(1.01);
            box-shadow: inset 0 1px 0 rgba(255,255,255,.55), 0 7px 18px rgba(15, 23, 42, 0.13);
        }
        .wb-quick-indigo { background: linear-gradient(160deg, #eef2ff, #e0e7ff); border-color: #c7d2fe; }
        .wb-quick-amber { background: linear-gradient(160deg, #fffbeb, #fef3c7); border-color: #fde68a; }
        .wb-quick-orange { background: linear-gradient(160deg, #fff7ed, #ffedd5); border-color: #fdba74; }
        .wb-quick-cyan { background: linear-gradient(160deg, #ecfeff, #cffafe); border-color: #67e8f9; }
        .wb-quick-violet { background: linear-gradient(160deg, #f5f3ff, #ede9fe); border-color: #c4b5fd; }
        .module-toggle { display: inline-flex; align-items: center; gap: 4px; padding: 3px 10px; border-radius: 20px; font-size: 11px; cursor: pointer; transition: all 0.12s; border: 1px solid #e2e8f0; background: #f8fafc; }
        .module-toggle.active { background: #ede9fe; border-color: #c4b5fd; color: #6d28d9; }
        .module-remove { cursor: pointer; color: #ef4444; font-size: 14px; line-height: 1; padding: 0 2px; }

        .wb-mini-btn {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.45rem 0.78rem;
            border-radius: 0.72rem;
            border: 1px solid rgba(255, 255, 255, 0.26);
            color: #fff;
            font-size: 0.75rem;
            font-weight: 600;
            line-height: 1;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22), 0 6px 14px rgba(15, 23, 42, 0.2);
            transition: transform .15s ease, filter .15s ease;
        }
        .wb-mini-btn:hover { transform: translateY(-1px); filter: brightness(1.06); }
        .wb-mini-indigo { background: linear-gradient(160deg, #6366f1, #4f46e5); }
        .wb-mini-amber { background: linear-gradient(160deg, #f59e0b, #d97706); }

        .version-op-wrap {
            display: flex;
            flex-wrap: nowrap;
            gap: 0.45rem;
            align-items: center;
            justify-content: flex-start;
            margin-top: 0;
        }
        .version-op-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.28rem;
            padding: 0.42rem 0.55rem;
            border-radius: 0.62rem;
            border: 1px solid rgba(255, 255, 255, 0.18);
            color: #fff;
            font-size: 0.73rem;
            font-weight: 600;
            line-height: 1;
            box-shadow: inset 0 1px 0 rgba(255,255,255,.2), 0 4px 10px rgba(15, 23, 42, 0.2);
            transition: transform .15s ease, filter .15s ease;
        }
        .version-op-btn:hover { transform: translateY(-1px); filter: brightness(1.06); }
        .version-op-build { background: linear-gradient(160deg, #6366f1, #4f46e5); }
        .version-op-download { background: linear-gradient(160deg, #10b981, #059669); }
        .version-op-edit { background: linear-gradient(160deg, #0ea5e9, #0284c7); }
        .version-op-delete { background: linear-gradient(160deg, #f43f5e, #e11d48); }
    </style>
    <div class="bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden">
        <div class="border-b border-slate-200/80 bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-700 px-6 py-6">
            <div class="flex items-start justify-between flex-wrap gap-4">
                <div class="flex items-start gap-4">
                    <a href="/admin/projects" class="mt-1 inline-flex items-center justify-center w-9 h-9 rounded-xl bg-white/10 text-slate-100 hover:bg-white/20 transition">
                        <i class="fas fa-arrow-left"></i>
                    </a>
                    <div>
                        <p class="text-[11px] font-semibold text-slate-300/80 tracking-[0.18em] uppercase">项目中心</p>
                        <h2 class="text-2xl font-semibold text-white mt-1">项目工作台</h2>
                        <div class="flex flex-wrap items-center gap-2 mt-2 text-xs text-slate-200/90">
                            <span class="inline-flex items-center px-2 py-0.5 rounded-full bg-slate-900/40 font-mono tracking-wide">''' + html.escape(project_id) + '''</span>
                            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full bg-amber-400/15 text-amber-100 border border-amber-300/30"><i class="fas fa-flag-checkered mr-1 text-amber-200"></i>''' + html.escape(phase_label) + '''</span>
                            ''' + ('<span class="inline-flex items-center px-2 py-0.5 rounded-full bg-slate-900/40 text-[11px] text-slate-200/90"><i class="fas fa-clock mr-1 text-slate-300/80"></i>创建于 ' + html.escape(created_at) + '</span>' if created_at else '') + '''
                        </div>
                    </div>
                </div>
                <div class="flex items-center gap-2 flex-shrink-0">
                    <a href="/admin/projects/''' + project_id + '''/tasks" class="wb-action-btn wb-indigo"><i class="fas fa-tasks"></i>任务</a>
                    <a href="/admin/projects/''' + project_id + '''/build" class="wb-action-btn wb-orange"><i class="fas fa-cogs"></i>构建</a>
                    <a href="/admin/projects/''' + project_id + '''/versions" class="wb-action-btn wb-emerald"><i class="fas fa-layer-group"></i>版本</a>
                    <a href="/admin/gm-ops?project_id=''' + project_id + '''" class="wb-action-btn wb-cyan"><i class="fas fa-sitemap"></i>GM运营</a>
                    <a href="/admin/projects/''' + project_id + '''/tasks/stats" class="wb-action-btn wb-violet"><i class="fas fa-chart-bar"></i>统计</a>
                    <a href="/docs?module=projects" class="wb-action-btn wb-slate" title="查看项目中心相关文档"><i class="fas fa-question-circle"></i>文档</a>
                </div>
            </div>
        </div>
        <div class="p-6">
            ''' + stats_html + '''
            <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div class="lg:col-span-2 space-y-4">
                    <div class="bg-white rounded-2xl border border-slate-200/80 p-4 shadow-sm">
                        <h3 class="text-sm font-semibold text-slate-900 mb-3 flex items-center gap-2"><i class="fas fa-list text-indigo-500"></i> 最近任务</h3>
                        <div class="overflow-x-auto">
                            <table class="w-full text-sm">
                                <thead><tr class="text-left text-slate-500 border-b"><th class="pb-2 text-xs font-semibold">标题</th><th class="pb-2 text-xs font-semibold">负责人</th><th class="pb-2 text-xs font-semibold">状态</th></tr></thead>
                                <tbody>''' + recent_rows + '''</tbody>
                            </table>
                        </div>
                        <a href="/admin/projects/''' + project_id + '''/tasks" class="block text-center py-2 mt-2 text-indigo-600 hover:text-indigo-700 hover:underline text-sm">查看全部任务 →</a>
                    </div>
                    <div class="bg-white rounded-2xl border border-slate-200/80 p-4 shadow-sm">
                        <h3 class="text-sm font-semibold text-slate-900 mb-2 flex items-center gap-2"><i class="fas fa-info-circle text-slate-500"></i> 项目信息</h3>
                        <p class="text-sm text-slate-600 leading-relaxed">''' + (html.escape(intro) if intro else '<span class="text-slate-400">暂无简介</span>') + '''</p>
                        ''' + ('<p class="mt-2 text-xs"><a href="' + html.escape(git_url) + '" target="_blank" class="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-700 hover:underline"><i class="fas fa-external-link-alt"></i><span>' + html.escape(git_url[:60]) + ('…' if len(git_url) > 60 else '') + '</span></a></p>' if git_url else '') + '''
                    </div>
                </div>
                <div class="space-y-4">
                    <div class="bg-white rounded-2xl border border-slate-200/80 p-4 shadow-sm">
                        <h3 class="text-sm font-semibold text-slate-900 mb-3 flex items-center gap-2"><i class="fas fa-users text-amber-500"></i> 团队成员</h3>
                        <ul class="space-y-1.5 text-sm">''' + ''.join('<li class="flex items-center gap-2"><span class="w-7 h-7 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center text-xs font-semibold">' + (u[0].upper() if u else '?') + '</span><span class="text-slate-800">' + html.escape(u) + '</span>' + ('<span class="text-[11px] text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded-full">编辑</span>' if u in editors else '<span class="text-[11px] text-slate-400 bg-slate-50 px-1.5 py-0.5 rounded-full">查看</span>') + '</li>' for u in team[:12]) + '''</ul>
                        ''' + ('<p class="text-xs text-slate-500 mt-2">共 ' + str(len(team)) + ' 人</p>' if len(team) > 0 else '<p class="text-slate-400 text-sm">暂无成员</p>') + '''
                    </div>
                    <div class="bg-gradient-to-br from-amber-50 to-orange-50 rounded-2xl border border-amber-100 p-4">
                        <h3 class="text-sm font-semibold text-amber-900 mb-2 flex items-center justify-between">
                            <span>快捷操作</span>
                            ''' + ('<button type="button" id="btnConfigModules" class="text-[10px] text-amber-600 hover:text-amber-800 bg-amber-100 hover:bg-amber-200 px-2 py-0.5 rounded-full" onclick="toggleModuleConfig()"><i class="fas fa-cog mr-0.5"></i>配置</button>' if is_admin_logged_in else '') + '''
                        </h3>
                        <div class="space-y-2" id="quickActionsContainer">
                            <a href="/admin/projects/''' + project_id + '''/tasks" class="wb-quick-btn wb-quick-indigo"><i class="fas fa-plus text-indigo-500"></i>新建任务</a>
                            <a href="/admin/projects/''' + project_id + '''/build?type=general" class="wb-quick-btn wb-quick-orange" id="qaBuildGeneral"><i class="fas fa-cogs text-orange-500"></i>通用构建</a>
                            <a href="/admin/projects/''' + project_id + '''/build?type=commercial" class="wb-quick-btn wb-quick-violet" id="qaBuildCommercial"><i class="fas fa-rocket text-violet-500"></i>商业级发布</a>
                            <a href="/admin/projects/''' + project_id + '''/versions" class="wb-quick-btn wb-quick-amber"><i class="fas fa-layer-group text-amber-500"></i>渠道与版本</a>
                            <a href="/admin/gm-ops?project_id=''' + project_id + '''" class="wb-quick-btn wb-quick-cyan"><i class="fas fa-sitemap text-cyan-500"></i>GM运营中心</a>
                        </div>
                        <!-- 模块配置面板（仅管理员可见） -->
                        ''' + ('<div id="moduleConfigPanel" class="hidden mt-3 p-3 rounded-xl bg-white border border-amber-200 text-xs"><p class="text-slate-500 mb-2">管理快捷操作模块：</p><div class="space-y-1.5" id="moduleConfigList"></div></div>' if is_admin_logged_in else '') + '''
                    </div>
                </div>
            </div>
        </div>
    </div>
    <div class="bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden">
    <div class="p-6">
        <div id="projectTabSection" class="hidden flex border-b border-slate-200 mb-6 gap-2 items-center">
            <button type="button" onclick="switchTab('overview')" id="tabOverview" class="tab-btn px-4 py-1.5 text-sm font-medium text-amber-700 border-b-2 border-amber-600 -mb-px">仪表盘</button>
            <button type="button" onclick="switchTab('channels')" id="tabChannels" class="tab-btn px-4 py-1.5 text-sm font-medium text-slate-500 hover:text-slate-800">渠道</button>
            <a href="/docs?module=versions" class="ml-auto text-slate-400 hover:text-indigo-600 text-sm" title="渠道与版本相关文档"><i class="fas fa-question-circle"></i></a>
        </div>
        <!-- switchTab 在下方统一脚本定义，避免重复定义导致行为不一致 -->
        <div id="panelOverview" class="tab-panel">
            <p class="text-slate-500 text-sm">上方为项目仪表盘，包含任务统计、最近动态、团队成员与快捷操作。切换至「渠道」可管理项目要发布的渠道及不同阶段（开发、测试、线上）的版本配置。</p>
        </div>
        <div id="panelChannels" class="tab-panel hidden">
            <div class="mb-6 p-4 rounded-2xl bg-gradient-to-br from-slate-50 to-indigo-50/30 border border-slate-100">
                <h3 class="text-sm font-semibold text-slate-800 mb-2 flex items-center gap-2"><i class="fas fa-layer-group text-indigo-500"></i> 项目要发布的渠道 <a href="/docs?module=versions" class="text-slate-400 hover:text-indigo-600" title="帮助"><i class="fas fa-question-circle text-xs"></i></a></h3>
                <p class="text-xs text-slate-500 mb-3">选择本项目的发布渠道，每个渠道下有开发、测试、线上三阶段，可分别配置版本。</p>
                <div class="flex flex-wrap gap-2 items-center">
                    <div class="flex flex-wrap gap-2" id="projectChannelsList">''' + (''.join('<span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/80 border border-slate-200/80 text-slate-700 text-sm shadow-sm" data-channel="%s">%s' % (html.escape(cid), html.escape(cname)) + ('' if not can_edit else '<button type="button" data-channel-id="' + html.escape(cid) + '" class="remove-channel-btn text-slate-400 hover:text-red-500 -mr-0.5 transition"><i class="fas fa-times text-xs"></i></button>') + '</span>' for cid, cname in proj_channels_display) or '<span class="text-slate-400 text-sm">暂未添加渠道</span>') + '''</div>
                    ''' + ('<div class="relative"><button type="button" onclick="toggleAddChannelDropdown()" class="wb-mini-btn wb-mini-indigo"><i class="fas fa-plus"></i>添加渠道</button><div id="addChannelDropdown" class="hidden absolute left-0 top-full mt-1 bg-white border border-slate-200 rounded-xl shadow-lg py-2 z-20 min-w-[160px]"></div></div>' if can_edit else '') + '''
                </div>
            </div>
            <div class="space-y-5" id="channelsVersionsWrap"></div>
            <p id="channelsEmpty" class="py-12 text-center text-slate-500 hidden"><i class="fas fa-inbox text-4xl text-slate-200 mb-3 block"></i>请先添加项目渠道，再为各渠道创建版本</p>
        </div>
        <div id="panelBuild" class="tab-panel hidden" style="display:none">
            <div class="flex flex-col md:flex-row gap-6">
                <div class="bg-amber-50 border border-amber-100 rounded-xl p-6 max-w-lg flex-shrink-0">
                    <h3 class="text-sm font-semibold text-amber-900 mb-2 flex items-center gap-2"><i class="fas fa-cogs text-orange-500"></i> 触发构建 <a href="/docs?module=build" class="text-amber-600 hover:text-amber-800 ml-1" title="构建相关文档"><i class="fas fa-question-circle text-xs"></i></a></h3>
                    <p class="text-sm text-amber-800 mb-4">选择 Jenkins 实例并填写构建参数，触发本项目的 APK 构建。构建完成后产物将出现在版本列表与下载区域。</p>
                    <a href="/admin/projects/''' + project_id + '''/build" class="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-orange-600 text-white text-sm font-medium hover:bg-orange-700 shadow-sm transition"><i class="fas fa-play"></i> 前往构建</a>
                </div>
                <div class="flex-1 bg-white rounded-xl border border-slate-200 p-4">
                    <h3 class="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2"><i class="fas fa-history text-slate-500"></i> 最近构建</h3>
                    <ul id="projectRecentBuilds" class="space-y-2 text-sm text-slate-600">加载中…</ul>
                    <a href="/admin/projects/''' + project_id + '''/build" class="text-xs text-indigo-600 hover:underline mt-2 inline-block">查看全部 →</a>
                </div>
            </div>
        </div>
        <div id="panelDownload" class="tab-panel hidden">
            <div class="mb-4 flex items-center justify-between">
                <h3 class="text-sm font-semibold text-slate-900 flex items-center gap-2">本项目安装包 <a href="/docs?module=download" class="text-slate-400 hover:text-indigo-600" title="下载相关文档"><i class="fas fa-question-circle text-xs"></i></a></h3>
                <a href="/download-center?project=''' + html.escape(project_id) + '''" class="text-indigo-600 hover:text-indigo-700 text-sm">在下载中心查看 →</a>
            </div>
            ''' + _project_download_tab_html(project_apk_files, project_id) + '''
        </div>
    </div>
</div>
<!-- 版本编辑弹窗 -->
<div id="versionModal" class="hidden fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-start justify-center z-50 p-3 pt-6" onclick="if(event.target===this) closeVersionModal()">
<div class="bg-white rounded-2xl shadow-2xl w-full max-w-[920px] max-h-[94vh] overflow-hidden flex flex-col border border-slate-100" onclick="event.stopPropagation()">
<div class="px-5 py-2 border-b border-slate-200/60 bg-gradient-to-r from-slate-50 to-indigo-50/60 shadow-sm flex items-center justify-between shrink-0"><h3 class="font-semibold text-slate-800 text-base" id="versionModalTitle">新建版本</h3><button onclick="closeVersionModal()" class="w-7 h-7 rounded-lg hover:bg-slate-200 flex items-center justify-center text-slate-400 hover:text-slate-600 transition"><i class="fas fa-times text-xs"></i></button></div>
<div class="px-5 py-3 overflow-y-auto flex-1">
<input type="hidden" id="versionEditId" value="">
<label class="flex items-center gap-2.5 px-3 py-2 mb-3 rounded-lg border-2 border-slate-200 cursor-pointer hover:border-violet-300 transition-all" id="labelCommercialMode"><input type="checkbox" id="chkCommercialMode" class="w-4 h-4 rounded text-violet-600" onchange="toggleCommercialMode()"><div><span class="text-[14px] font-semibold text-slate-700">高级商业版本</span><span class="text-[11px] text-slate-400 ml-1.5">启用可插拔构建流水线</span></div></label>
<div class="mb-3">
<div id="versionMainTabs" class="flex gap-1 bg-slate-100 rounded-lg p-1">
<button type="button" class="flex-1 px-2.5 py-1.5 rounded-md text-xs font-semibold transition bg-white text-indigo-700 shadow-sm" data-vtab="identity" onclick="switchVersionModalTab('identity')">版本标识</button>
<button type="button" class="flex-1 px-2.5 py-1.5 rounded-md text-xs font-semibold transition text-slate-600 hover:bg-white/70" data-vtab="package" onclick="switchVersionModalTab('package')">包体配置</button>
<button type="button" class="flex-1 px-2.5 py-1.5 rounded-md text-xs font-semibold transition text-slate-600 hover:bg-white/70" data-vtab="release" onclick="switchVersionModalTab('release')">发布配置</button>
<button type="button" id="versionPipelineTabBtn" class="hidden flex-1 px-2.5 py-1.5 rounded-md text-xs font-semibold transition text-slate-600 hover:bg-white/70" data-vtab="pipeline" onclick="switchVersionModalTab('pipeline')">构建流水线</button>
</div>
</div>
<div id="vmTabIdentity" class="version-main-panel">
<div class="rounded-lg border border-slate-200 mb-2.5 overflow-hidden hover:shadow-sm transition-shadow">
<div class="px-3 py-1.5 bg-slate-50 border-b border-slate-200/80 flex items-center gap-1.5"><span class="w-5 h-5 rounded bg-indigo-500 text-white flex items-center justify-center text-[10px]"><i class="fas fa-tag"></i></span><span class="text-[13px] font-semibold text-slate-600">版本标识</span><span class="text-[11px] text-slate-400">唯一确定一个版本组的渠道、阶段与平台</span></div>
<div class="px-3 py-2 flex gap-2">
<div style="width:100px;flex-shrink:0;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;"><span style="color:#f43f5e;">*</span>渠道</span><select id="versionChannel" onchange="suggestVersionApkPath();syncDerivedVersionPaths()" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition"><option value="1001">微信</option><option value="1002">抖音</option></select></div>
<div style="width:80px;flex-shrink:0;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;"><span style="color:#f43f5e;">*</span>阶段</span><select id="versionStage" onchange="suggestVersionApkPath();syncDerivedVersionPaths()" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition"><option value="dev">开发</option><option value="test">测试</option><option value="production">线上</option></select></div>
<div style="width:90px;flex-shrink:0;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;"><span style="color:#f43f5e;">*</span>平台</span><select id="versionPlatform" onchange="suggestVersionApkPath();syncVersionPlatformFields();syncDerivedVersionPaths()" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition"><option value="android">Android</option><option value="ios">iOS</option></select></div>
<div style="width:120px;flex-shrink:0;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;"><span style="color:#f43f5e;">*</span>版本名</span><input id="versionName" onchange="syncDerivedVersionPaths()" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition" placeholder="1.0.0" value="1.0.0"></div>
<div style="width:96px;flex-shrink:0;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">状态</span><select id="versionStatus" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition"><option value="draft">草稿</option><option value="testing">测试中</option><option value="active">有效</option><option value="disabled">失效</option><option value="archived">归档</option></select></div>
</div></div>
</div>
<div id="vmTabPackage" class="version-main-panel hidden">
<div class="rounded-lg border border-slate-200 mb-2.5 overflow-hidden hover:shadow-sm transition-shadow">
<div class="px-3 py-1.5 bg-slate-50 border-b border-slate-200/80 flex items-center gap-1.5"><span class="w-5 h-5 rounded bg-amber-500 text-white flex items-center justify-center text-[10px]"><i class="fas fa-box"></i></span><span class="text-[13px] font-semibold text-slate-600">包体配置</span><span class="text-[11px] text-slate-400">分发方式、包名与文件路径</span></div>
<div class="px-3 py-2 space-y-1.5">
<div class="flex gap-2"><div style="width:110px;flex-shrink:0;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">发布方式</span><select id="versionDistributionMethod" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition"><option value="direct">直接下载</option><option value="enterprise">企业分发</option><option value="store">应用商店</option><option value="testflight">TestFlight</option><option value="internal">内部包体</option></select></div><div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">包名</span><input id="versionPackageName" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition" placeholder="com.example.app"></div><div style="width:70px;flex-shrink:0;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">最低SDK</span><input id="versionMinSdk" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition" value="24"></div></div>
<div class="flex gap-2"><div style="flex:2;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">安装包路径</span><input id="versionApkPath" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition" placeholder="输出或下载路径"></div><div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">资源路径（自动）</span><input id="versionResourcePath" readonly class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-slate-50 text-slate-700" placeholder="自动拼接"></div><div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">配置路径（自动）</span><input id="versionConfigPath" readonly class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-slate-50 text-slate-700" placeholder="自动拼接"></div></div>
<div id="androidVersionFields" style="display:none"></div><div id="iosVersionFields" class="hidden" style="display:none"></div>
</div></div>
</div>
<div id="vmTabRelease" class="version-main-panel hidden">
<div class="rounded-lg border border-slate-200 mb-2.5 overflow-hidden hover:shadow-sm transition-shadow">
<div class="px-3 py-1.5 bg-slate-50 border-b border-slate-200/80 flex items-center gap-1.5"><span class="w-5 h-5 rounded bg-emerald-500 text-white flex items-center justify-center text-[10px]"><i class="fas fa-paper-plane"></i></span><span class="text-[13px] font-semibold text-slate-600">发布配置</span><span class="text-[11px] text-slate-400">更新说明、构建参数与 Jenkins</span></div>
<div class="px-3 py-2 flex gap-3">
<div style="flex:1;" class="space-y-1.5">
<div><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">更新说明</span><textarea id="versionChangelog" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" rows="2" placeholder="版本更新内容"></textarea></div>
<div class="flex items-center gap-3"><label class="flex items-center gap-1 text-sm whitespace-nowrap"><input type="checkbox" id="versionChangelogRecommended" class="rounded"> 推荐版本</label><div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">Jenkins Job ID</span><input id="versionJenkinsJob" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition" placeholder="可选"></div></div>
<div><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">备注</span><textarea id="versionNotes" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" rows="1"></textarea></div>
</div>
<div style="width:340px;flex-shrink:0;">
<div class="grid grid-cols-3 gap-x-2 gap-y-1.5">
<div><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">Unity版本</span><div class="flex gap-1 items-center"><select id="ppApkUnity" class="flex-1 px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition"><option value="">检测中...</option></select><button type="button" id="btnRefreshUnityVersions" class="px-2 py-1.5 border border-slate-200 rounded text-xs text-slate-600 hover:bg-slate-50 whitespace-nowrap" title="重新检测本机 Unity">刷新</button></div><p id="ppApkUnityHint" class="text-[10px] text-slate-400 mt-0.5">仅显示 Jenkins 管理中标记为<strong>有效</strong>的 Unity 版本；维护请前往 <a href="/admin/jenkins#unity-catalog" class="text-indigo-600 underline" target="_blank">Unity 版本库</a>。</p></div>
<div><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">Git分支</span><input id="ppApkBranch" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition" value="main"></div>
<div><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">APP_NAME</span><input id="ppApkAppName" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition"></div>
<div class="col-span-3"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">输出目录</span><input id="ppApkOutput" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition"></div>
</div></div>
</div></div>
</div>
<div id="vmTabPipeline" class="version-main-panel hidden">
<div id="versionPipeline" class="hidden rounded-lg border border-violet-200 mb-2 overflow-hidden hover:shadow-sm transition-shadow">
<div class="px-3 py-1.5 bg-violet-50/80 border-b border-violet-100 flex items-center gap-1.5"><span class="w-5 h-5 rounded bg-violet-500 text-white flex items-center justify-center text-[10px]"><i class="fas fa-diagram-project"></i></span><span class="text-[13px] font-semibold text-violet-700">构建流水线</span><span class="text-[11px] text-violet-400">可插拔构建步骤，每步独立启用</span></div>
<div class="p-3">
<div class="flex gap-0.5 bg-slate-100 rounded-lg p-0.5 mb-2.5" id="pipelineTabs"><button class="flex-1 py-1.5 px-2 rounded text-xs font-medium bg-indigo-600 text-white shadow-sm" data-ptab="config_export" onclick="switchPipelineTab('config_export')">1.配置导出</button><button class="flex-1 py-1.5 px-2 rounded text-xs font-medium text-slate-500 hover:bg-white/60" data-ptab="resource_build" onclick="switchPipelineTab('resource_build')">2.资源打包</button><button class="flex-1 py-1.5 px-2 rounded text-xs font-medium text-slate-500 hover:bg-white/60" data-ptab="hot_release" onclick="switchPipelineTab('hot_release')">3.热更发布</button><button class="flex-1 py-1.5 px-2 rounded text-xs font-medium text-slate-500 hover:bg-white/60" data-ptab="apk_build" onclick="switchPipelineTab('apk_build')">4.APK打包</button></div>
<div id="ptabConfigExport" class="pipeline-panel"><label class="flex items-center gap-1.5 mb-1.5"><input type="checkbox" id="ppConfigExport" checked class="rounded" onchange="togglePipelineStepUI('config_export')"><span class="text-[13px] font-medium text-slate-700">配置导出发布</span><span class="text-[11px] text-slate-400">— Excel导表→manifest→上传OSS</span></label>
<div id="ppConfigExportBody" class="flex gap-2 bg-slate-50 rounded-lg p-2.5"><div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;"><span style="color:#f43f5e;">*</span>远端路径前缀</span><input id="ppCfgPrefix" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition" value="MyGame1"></div><div style="width:100px;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">客户端版本</span><input id="ppCfgClientVer" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition" value="1.0.0"></div><div class="flex items-end pb-0.5"><label class="flex items-center gap-1 text-sm whitespace-nowrap"><input type="checkbox" id="ppCfgIncludeCode" class="rounded"> 含代码</label></div></div></div>
<div id="ptabResourceBuild" class="pipeline-panel hidden"><label class="flex items-center gap-1.5 mb-1.5"><input type="checkbox" id="ppResourceBuild" checked class="rounded" onchange="togglePipelineStepUI('resource_build')"><span class="text-[13px] font-medium text-slate-700">资源打包</span><span class="text-[11px] text-slate-400">— 扫描→依赖→规则→构建→标准化产物</span></label>
<div id="ppResourceBuildBody" class="flex gap-2 bg-slate-50 rounded-lg p-2.5"><div style="width:220px;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;"><span style="color:#f43f5e;">*</span>构建引擎</span><select id="ppResProvider" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition"><option value="addressables-v2">Addressables v2（推荐）</option><option value="legacy-bundle-builder">Legacy</option></select></div><div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">场景方案</span><input id="ppResScenario" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition" value="default"></div></div></div>
<div id="ptabHotRelease" class="pipeline-panel hidden"><label class="flex items-center gap-1.5 mb-1.5"><input type="checkbox" id="ppHotRelease" checked class="rounded" onchange="togglePipelineStepUI('hot_release')"><span class="text-[13px] font-medium text-slate-700">代码+资源热更发布</span><span class="text-[11px] text-slate-400">— 压缩→加密→签名→上传→激活/回滚</span></label>
<div id="ppHotReleaseBody" class="bg-slate-50 rounded-lg p-3 space-y-2.5">
<div class="flex items-center gap-2"><span class="text-sm text-slate-600">发布对象<span style="color:#f43f5e;">*</span>:</span><span id="ppChipCode" class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-700 border-2 border-blue-300 cursor-pointer select-none" onclick="togglePpChip('code')"><i class="fas fa-code text-[10px]"></i>代码包</span><span id="ppChipResource" class="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-emerald-100 text-emerald-700 border-2 border-emerald-300 cursor-pointer select-none" onclick="togglePpChip('resource')"><i class="fas fa-cube text-[10px]"></i>资源包</span></div>
<div class="flex gap-2">

<div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">热更标签</span><input id="ppHrLabels" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition" value="hotupdate,aotmeta"></div>
<div style="width:120px;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;"><span style="color:#f43f5e;">*</span>发布模式</span><select id="ppHrMode" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition" onchange="onPpHrModeChange()"><option value="build-upload">构建并上传</option><option value="build">仅构建</option><option value="upload">仅上传</option><option value="activate">激活</option><option value="rollback">回滚</option></select></div>
<div style="width:80px;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">上传模式</span><select id="ppHrUpload" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition"><option value="incremental">增量</option><option value="full">全量</option></select></div>
<div style="width:120px;" id="ppHrRollbackWrap"><span style="display:block;font-size:11px;color:#64748b;line-height:1.3;margin-bottom:2px;">回滚目标</span><select id="ppHrRollback" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400 transition" disabled><option value="">请先选回滚模式</option><option value="previous">上一个版本</option><option value="v0.0.1">v0.0.1</option><option value="v0.0.2">v0.0.2</option><option value="custom">自定义...</option></select></div>
</div>
<div id="ppStratCode" class="rounded-lg p-2.5 bg-blue-50/60 border border-blue-200">
<p class="text-sm font-semibold text-blue-700 mb-1.5"><i class="fas fa-code mr-1"></i>代码包策略</p>
<div class="flex gap-2"><div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.2;margin-bottom:1px;">压缩</span><select id="ppHrCodeComp" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white"><option>Zip</option><option>None</option><option>Lz4</option></select></div><div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.2;margin-bottom:1px;">加密</span><select id="ppHrCodeEnc" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white"><option>Aes</option><option>None</option><option>Xor</option></select></div><div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.2;margin-bottom:1px;">签名</span><select id="ppHrCodeSig" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white"><option value="builtin-signature">启用</option><option value="">关闭</option></select></div></div>
<div class="mt-1.5"><span style="display:block;font-size:11px;color:#64748b;line-height:1.2;margin-bottom:1px;">包单元</span><input id="ppHrCodeUnits" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white" value="aotmeta, hotupdate, scriptpatch, symbols"></div>
<input type="checkbox" id="ppHrCodeEnabled" class="hidden" checked>
</div>
<div id="ppStratResource" class="rounded-lg p-2.5 bg-emerald-50/60 border border-emerald-200 mt-2">
<p class="text-sm font-semibold text-emerald-700 mb-1.5"><i class="fas fa-cube mr-1"></i>资源包策略</p>
<div class="flex gap-2"><div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.2;margin-bottom:1px;">压缩</span><select id="ppHrResComp" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white"><option>None</option><option>Zip</option><option>Lz4</option></select></div><div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.2;margin-bottom:1px;">加密</span><select id="ppHrResEnc" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white"><option>None</option><option>Aes</option></select></div><div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.2;margin-bottom:1px;">签名</span><select id="ppHrResSig" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white"><option value="builtin-signature">启用</option><option value="">关闭</option></select></div></div>
<div class="mt-1.5"><span style="display:block;font-size:11px;color:#64748b;line-height:1.2;margin-bottom:1px;">包单元</span><input id="ppHrResUnits" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white" value="addressable, hotupdate, optional, platform, hd, streaming"></div>
<input type="checkbox" id="ppHrResEnabled" class="hidden" checked>
</div>
<div class="mt-2.5 rounded-lg p-2.5 bg-slate-100/80 border border-slate-200">
<p class="text-sm font-semibold text-slate-600 mb-1.5"><i class="fas fa-sliders-h mr-1"></i>高级覆盖</p>
<div class="flex gap-2"><div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.2;margin-bottom:1px;">压缩覆盖</span><select id="ppHrCompOvr" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white"><option value="">默认</option><option>Zip</option><option>Lz4</option><option>None</option></select></div><div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.2;margin-bottom:1px;">加密覆盖</span><select id="ppHrEncOvr" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white"><option value="">默认</option><option>Aes</option><option>Xor</option><option>None</option></select></div><div style="flex:1;"><span style="display:block;font-size:11px;color:#64748b;line-height:1.2;margin-bottom:1px;">签名覆盖</span><select id="ppHrSigOvr" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white"><option value="">默认</option><option value="builtin-signature">启用</option></select></div></div>
</div>
</div></div>
<div id="ptabApkBuild" class="pipeline-panel hidden"><label class="flex items-center gap-1.5 mb-1.5"><input type="checkbox" id="ppApkBuild" class="rounded" onchange="togglePipelineStepUI('apk_build')"><span class="text-[13px] font-medium text-slate-700">APK 打包上传</span><span class="text-[11px] text-slate-400">— Unity BuildPipeline，参数已在上方配置</span></label><div id="ppApkBuildBody" class="hidden bg-slate-50 rounded-lg p-2.5"><p class="text-sm text-slate-400">此处仅控制是否执行APK打包步骤，构建参数已在「发布配置」卡片中设置。</p></div></div>
</div></div>
</div>
</div>
<div class="px-5 py-2.5 border-t border-slate-100 bg-slate-50/80 flex justify-end gap-2 shrink-0"><button type="button" onclick="closeVersionModal()" class="px-4 py-2 border border-slate-300 rounded-lg text-sm text-slate-600 hover:bg-slate-100 transition">取消</button><button type="button" onclick="saveVersion()" class="px-6 py-2 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700 shadow-md hover:shadow-lg transition-all">保存版本</button></div>
</div></div>
<!-- VersionCode 快速编辑弹窗（仅修改 code + 状态 + 版本说明） -->
<div id="versionCodeModal" class="hidden fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" onclick="if(event.target===this) closeVersionCodeModal()">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md border border-slate-100" onclick="event.stopPropagation()">
        <div class="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
            <h3 id="versionCodeModalTitle" class="font-semibold text-slate-800">编辑 VersionCode</h3>
            <button type="button" onclick="closeVersionCodeModal()" class="text-slate-400 hover:text-slate-600"><i class="fas fa-times"></i></button>
        </div>
        <div class="p-5 space-y-3">
            <input type="hidden" id="versionCodeEditId" value="">
            <input type="hidden" id="versionCodeEditMode" value="edit">
            <input type="hidden" id="versionCodeCloneFromId" value="">
            <div class="text-xs text-slate-500" id="versionCodeEditVersionName">Version: -</div>
            <div>
                <label class="block text-xs text-slate-500 mb-1">Version Code</label>
                <input id="versionCodeEditValue" class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm" placeholder="例如 100">
            </div>
            <div>
                <label class="block text-xs text-slate-500 mb-1">状态</label>
                <select id="versionCodeEditStatus" class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white">
                    <option value="draft">草稿</option>
                    <option value="testing">测试中</option>
                    <option value="active">有效</option>
                    <option value="disabled">失效</option>
                    <option value="archived">归档</option>
                </select>
            </div>
            <div>
                <label class="block text-xs text-slate-500 mb-1">版本说明</label>
                <textarea id="versionCodeEditChangelog" rows="3" class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm" placeholder="请输入本次版本说明"></textarea>
            </div>
        </div>
        <div class="px-5 py-3 border-t border-slate-100 bg-slate-50 flex justify-end gap-2">
            <button type="button" onclick="closeVersionCodeModal()" class="px-4 py-2 border border-slate-300 rounded-lg text-sm text-slate-600 hover:bg-slate-100">取消</button>
            <button type="button" onclick="saveVersionCodeModal()" class="px-5 py-2 bg-indigo-600 text-white rounded-lg text-sm font-semibold hover:bg-indigo-700">保存</button>
        </div>
    </div>
</div>
<div id="projectQRModal" class="hidden fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" onclick="if(event.target===this) document.getElementById(\'projectQRModal\').classList.add(\'hidden\')">
    <div class="bg-white rounded-2xl shadow-2xl max-w-sm w-full p-6 border border-slate-100" onclick="event.stopPropagation()">
        <h3 class="text-lg font-semibold text-slate-800 mb-4 flex items-center gap-2"><i class="fas fa-qrcode text-indigo-500"></i> 扫码下载</h3>
        <div id="projectQRCode" class="flex justify-center mb-4 min-h-[200px] items-center bg-slate-50 rounded-xl"></div>
        <button type="button" onclick="document.getElementById(\'projectQRModal\').classList.add(\'hidden\')" class="w-full py-2.5 rounded-xl border border-slate-200 text-slate-700 font-medium hover:bg-slate-50 transition">关闭</button>
    </div>
</div>
<div id="versionDownloadsModal" class="hidden fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" onclick="if(event.target===this) document.getElementById(\'versionDownloadsModal\').classList.add(\'hidden\')">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col" onclick="event.stopPropagation()">
        <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between"><h3 class="font-semibold text-slate-800"><i class="fas fa-download text-emerald-500 mr-2"></i>本版本可下载 APK</h3><button type="button" onclick="document.getElementById(\'versionDownloadsModal\').classList.add(\'hidden\')" class="text-slate-400 hover:text-slate-600"><i class="fas fa-times"></i></button></div>
        <div id="versionDownloadsList" class="p-6 overflow-y-auto flex-1">加载中…</div>
    </div>
</div>
<script type="application/json" id="project-detail-data">''' + _escape_script_json_for_html(json.dumps({
    'project_id': project_id,
    'can_edit': bool(can_edit),
    'channels_full': {c['id']: {'apk_subdir': c.get('apk_subdir', '') or '', 'build_param': c.get('build_param', '') or ''} for c in (channels_db if isinstance(channels_db, list) else [])},
    'project_channels': [{'id': cid, 'name': cname} for cid, cname in proj_channels_display],
    'all_channels': [{'id': cid, 'name': cname} for cid, cname in all_channels_list],
    'version_stages': [{'id': sid, 'name': sname} for sid, sname in VERSION_STAGES],
    'project_name_en': (proj.get('name_en') or project_id).strip(),
    'versions': versions_data,
})) + '''</script>
<script>
var _pd=(function(){var el=document.getElementById("project-detail-data");return el?JSON.parse(el.textContent):{};})();
function _normalizeProjectId(raw){
    var v = (raw == null ? '' : String(raw)).trim();
    if(!v) return '';
    if((v[0] === '"' && v[v.length-1] === '"') || (v[0] === "'" && v[v.length-1] === "'")){
        v = v.slice(1, -1).trim();
    }
    if(v === '""' || v === "''") v = '';
    return v;
}
function _projectIdFromPath(){
    try{
        var p = String(location.pathname || '');
        var marker = '/admin/projects/';
        var idx = p.indexOf(marker);
        if(idx < 0) return '';
        var rest = p.slice(idx + marker.length);
        var seg = rest.split('/')[0] || '';
        return seg ? decodeURIComponent(seg) : '';
    }catch(_e){
        return '';
    }
}
var PROJECT_ID=_normalizeProjectId(_pd.project_id)||_projectIdFromPath()||"";
var CAN_EDIT=_pd.can_edit||false;
// 快捷操作模块管理
var _projectModules={build_general:true,build_commercial:true};
function toggleModuleConfig(){var p=document.getElementById("moduleConfigPanel");if(!p)return;p.classList.toggle("hidden");if(!p.classList.contains("hidden"))renderModuleConfig();}
function renderModuleConfig(){var el=document.getElementById("moduleConfigList");if(!el)return;
var mods=[{id:"build_general",label:"通用APK构建",icon:"fa-cogs",color:"orange"},{id:"build_commercial",label:"商业级热更发布",icon:"fa-rocket",color:"violet"}];
el.innerHTML=mods.map(function(m){var a=_projectModules[m.id];
return '<div class="flex items-center justify-between py-1 px-2 rounded-lg '+(a?"bg-amber-50":"bg-slate-50")+'">'+
'<span class="flex items-center gap-1.5"><i class="fas '+m.icon+' text-'+m.color+'-500"></i>'+m.label+'</span>'+
'<span>'+(a?'<span class="text-amber-600">✓ 已添加</span> <span class="module-remove" onclick="removeModule(&#39;'+m.id+'&#39;)">×</span>':'<button onclick="addModule(&#39;'+m.id+'&#39;)" class="text-[10px] text-indigo-500 hover:text-indigo-700">+ 添加</button>')+'</span></div>';
}).join("");}
function addModule(id){_projectModules[id]=true;renderModuleConfig();updateQuickActions();}
function removeModule(id){_projectModules[id]=false;renderModuleConfig();updateQuickActions();}
function updateQuickActions(){var g=document.getElementById("qaBuildGeneral"),c=document.getElementById("qaBuildCommercial");
if(g)g.style.display=_projectModules.build_general?"":"none";
if(c)c.style.display=_projectModules.build_commercial?"":"none";}
var _versionMode = 'general';
var _ppTargets = { code: true, resource: true };
function toggleCommercialMode() {
    var cb = document.getElementById('chkCommercialMode');
    _versionMode = cb.checked ? 'commercial' : 'general';
    var pp = document.getElementById('versionPipeline');
    if(pp) pp.classList.toggle('hidden', !cb.checked);
    var pipelineTabBtn = document.getElementById('versionPipelineTabBtn');
    if (pipelineTabBtn) {
        pipelineTabBtn.style.display = cb.checked ? '' : 'none';
    }
    if (!cb.checked) {
        switchVersionModalTab('identity');
    }
    var label = document.getElementById('labelCommercialMode');
    if(label) label.className = 'flex items-center gap-2.5 px-3 py-2 rounded-lg border-2 cursor-pointer transition-all ' + (cb.checked ? 'border-violet-500 bg-violet-50 shadow-sm shadow-violet-100' : 'border-slate-200 hover:border-violet-300');
}
function switchVersionModalTab(tab) {
    var panelMap = {identity:'vmTabIdentity', package:'vmTabPackage', release:'vmTabRelease', pipeline:'vmTabPipeline'};
    if (tab === 'pipeline' && _versionMode !== 'commercial') tab = 'identity';
    document.querySelectorAll('#versionMainTabs [data-vtab]').forEach(function(btn) {
        var key = btn.getAttribute('data-vtab');
        var active = btn.getAttribute('data-vtab') === tab;
        btn.className = 'flex-1 px-2.5 py-1.5 rounded-md text-xs font-semibold transition ' + (active ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-600 hover:bg-white/70');
        if (key === 'pipeline') {
            btn.style.display = (_versionMode === 'commercial') ? '' : 'none';
        }
    });
    Object.keys(panelMap).forEach(function(k) {
        var panel = document.getElementById(panelMap[k]);
        if (panel) panel.classList.toggle('hidden', k !== tab);
    });
}
function stageToReleaseEnvironment(stage) {
    var s = String(stage || 'dev').toLowerCase();
    if (s === 'production' || s === 'prod') return 'Production';
    if (s === 'staging' || s === 'stage') return 'Staging';
    if (s === 'test' || s === 'testing') return 'Testing';
    return 'Development';
}
function mapVersionChannelToReleaseChannel(channelId) {
    var key = String(channelId || '').trim();
    if (!key) return 'common';
    var info = CHANNELS_FULL && CHANNELS_FULL[key];
    if (info && info.build_param) {
        var mapped = String(info.build_param).trim();
        if (mapped) return mapped;
    }
    return key || 'common';
}
function switchPipelineTab(tab) {
    document.querySelectorAll('#pipelineTabs [data-ptab]').forEach(function(b) {
        var isActive = b.getAttribute('data-ptab') === tab;
        b.className = 'flex-1 py-1.5 px-2 rounded text-xs font-medium transition ' + (isActive ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-500 hover:bg-white/60');
        var numSpan = b.querySelector('span');
        if(numSpan) numSpan.className = 'w-5 h-5 inline-flex items-center justify-center rounded-full text-[10px] font-bold mr-1 ' + (isActive ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-200 text-slate-500');
    });
    document.querySelectorAll('.pipeline-panel').forEach(function(p) { p.classList.add('hidden'); });
    var panelMap = {config_export:'ptabConfigExport',resource_build:'ptabResourceBuild',hot_release:'ptabHotRelease',apk_build:'ptabApkBuild'};
    var panel = document.getElementById(panelMap[tab]);
    if(panel) panel.classList.remove('hidden');
}
function togglePipelineStep(step) {
    setTimeout(function(){ togglePipelineStepUI(step); }, 50);
}
function togglePipelineStepUI(step) {
    var cbs = {config_export:'ppConfigExportBody',resource_build:'ppResourceBuildBody',hot_release:'ppHotReleaseBody',apk_build:'ppApkBuildBody'};
    var ck = {config_export:'ppConfigExport',resource_build:'ppResourceBuild',hot_release:'ppHotRelease',apk_build:'ppApkBuild'};
    var cb = document.getElementById(ck[step]);
    var body = document.getElementById(cbs[step]);
    if(body && cb) body.classList.toggle('hidden', !cb.checked);
}
function togglePpChip(k){ _ppTargets[k]=!_ppTargets[k]; updatePpChips(); }
function updatePpChips(){
    var cs={code:['ppChipCode','bg-blue-100 text-blue-700 border-blue-300','bg-slate-100 text-slate-400 border-slate-200'],
        resource:['ppChipResource','bg-emerald-100 text-emerald-700 border-emerald-300','bg-slate-100 text-slate-400 border-slate-200']};
    Object.keys(cs).forEach(function(k){
        var c=cs[k], el=document.getElementById(c[0]);
        if(el) el.className='inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium border-2 cursor-pointer select-none '+(_ppTargets[k]?c[1]:c[2]);
    });
    var codeCard=document.getElementById('ppStratCode');
    var resCard=document.getElementById('ppStratResource');
    if(codeCard) codeCard.style.display=_ppTargets.code?'':'none';
    if(resCard) resCard.style.display=_ppTargets.resource?'':'none';
    var codeEn=document.getElementById('ppHrCodeEnabled');
    var resEn=document.getElementById('ppHrResEnabled');
    if(codeEn) codeEn.checked=_ppTargets.code;
    if(resEn) resEn.checked=_ppTargets.resource;
}
function onPpHrModeChange(){
    var m=document.getElementById('ppHrMode').value;
    var rb=document.getElementById('ppHrRollback');
    if(rb) rb.disabled = m!=='rollback';
}
function collectPipeline() {
    var p = {};
    var stageEl = document.getElementById('versionStage');
    var releaseEnv = stageToReleaseEnvironment(stageEl ? stageEl.value : 'dev');
    var cfgPrefixEl = document.getElementById('ppCfgPrefix');
    var cfgPrefix = cfgPrefixEl ? String(cfgPrefixEl.value || '').trim() : '';
    cfgPrefix = cfgPrefix.replace(new RegExp('^/+|/+$', 'g'), '');
    if (cfgPrefixEl) cfgPrefixEl.value = cfgPrefix;
    var ce = document.getElementById('ppConfigExport');
    p.config_export = {
        enabled: ce ? ce.checked : false,
        environment: releaseEnv,
        platform: document.getElementById('versionPlatform').value,
        client_version: document.getElementById('ppCfgClientVer').value.trim(),
        remote_prefix: cfgPrefix,
        include_code: document.getElementById('ppCfgIncludeCode').checked
    };
    var rbCb = document.getElementById('ppResourceBuild');
    p.resource_build = {
        enabled: rbCb ? rbCb.checked : false,
        provider: document.getElementById('ppResProvider').value,
        scenario: document.getElementById('ppResScenario').value.trim()
    };
    var hrCb = document.getElementById('ppHotRelease');
    p.hot_release = {
        enabled: hrCb ? hrCb.checked : false,
        release_targets: Object.keys(_ppTargets).filter(function(k){return _ppTargets[k];}).join(','),
        release_mode: document.getElementById('ppHrMode').value,
        release_environment: releaseEnv,
        release_channel: mapVersionChannelToReleaseChannel(document.getElementById('versionChannel').value),
        release_hot_labels: document.getElementById('ppHrLabels').value.trim(),
        release_upload_mode: document.getElementById('ppHrUpload').value,
        release_rollback_target: document.getElementById('ppHrRollback').value.trim(),
        release_compression_override: document.getElementById('ppHrCompOvr').value,
        release_encryption_override: document.getElementById('ppHrEncOvr').value,
        release_signature_override: document.getElementById('ppHrSigOvr').value,
        code_enabled: document.getElementById('ppHrCodeEnabled').checked,
        code_compression: document.getElementById('ppHrCodeComp').value,
        code_encryption: document.getElementById('ppHrCodeEnc').value,
        code_signature: document.getElementById('ppHrCodeSig').value,
        code_units: document.getElementById('ppHrCodeUnits').value.trim(),
        resource_enabled: document.getElementById('ppHrResEnabled').checked,
        resource_compression: document.getElementById('ppHrResComp').value,
        resource_encryption: document.getElementById('ppHrResEnc').value,
        resource_signature: document.getElementById('ppHrResSig').value,
        resource_units: document.getElementById('ppHrResUnits').value.trim()
    };
    var abCb = document.getElementById('ppApkBuild');
    var releaseBranch = document.getElementById('ppApkBranch').value.trim();
    p.apk_build = {
        enabled: abCb ? abCb.checked : false,
        unity_version: document.getElementById('ppApkUnity').value.trim(),
        git_branch: releaseBranch,
        app_name: document.getElementById('ppApkAppName').value.trim(),
        output_base_dir: document.getElementById('ppApkOutput').value.trim()
    };
    if (releaseBranch) p.git_branch = releaseBranch;
    return p;
}
function validateCommercialPipeline(p) {
    if (!p || typeof p !== 'object') return '商业流水线参数无效';
    var hr = p.hot_release || {};
    if (hr.enabled) {
        var raw = String(hr.release_targets || '').trim().toLowerCase();
        if (!raw) return '热更发布已启用时，必须至少选择一个发布对象（代码包或资源包）';
        var arr = raw.split(',').map(function(x){ return x.trim(); }).filter(Boolean);
        var allowed = { code: true, resource: true };
        var uniq = [];
        for (var i = 0; i < arr.length; i++) {
            var t = arr[i];
            if (!allowed[t]) return '发布对象仅允许 code、resource，禁止 config 或其他值';
            if (uniq.indexOf(t) < 0) uniq.push(t);
        }
        if (uniq.length === 0) return '热更发布对象不能为空';
        hr.release_targets = uniq.join(',');
    }
    return '';
}
function restorePipeline(pipeline) {
    if(!pipeline) return;
    var restoreCfg = function(s, cb, body, fields) {
        if(!s) return;
        if(cb) cb.checked = !!s.enabled;
        if(body && cb) body.classList.toggle('hidden', !cb.checked);
        if(fields) fields.forEach(function(f) {
            var el = document.getElementById(f.id);
            if(el && s[f.key] !== undefined) {
                if(el.type==='checkbox') el.checked = !!s[f.key];
                else el.value = s[f.key] || '';
            }
        });
    };
    var ce = pipeline.config_export;
    restoreCfg(ce, document.getElementById('ppConfigExport'), document.getElementById('ppConfigExportBody'), [
        {id:'ppCfgClientVer',key:'client_version'},{id:'ppCfgPrefix',key:'remote_prefix'},
        {id:'ppCfgIncludeCode',key:'include_code'}
    ]);
    var rb = pipeline.resource_build;
    restoreCfg(rb, document.getElementById('ppResourceBuild'), document.getElementById('ppResourceBuildBody'), [
        {id:'ppResProvider',key:'provider'},{id:'ppResScenario',key:'scenario'}
    ]);
    var hr = pipeline.hot_release;
    if(hr) {
        restoreCfg(hr, document.getElementById('ppHotRelease'), document.getElementById('ppHotReleaseBody'), [
            
            {id:'ppHrLabels',key:'release_hot_labels'},{id:'ppHrMode',key:'release_mode'},
            {id:'ppHrUpload',key:'release_upload_mode'},{id:'ppHrRollback',key:'release_rollback_target'},
            {id:'ppHrCompOvr',key:'release_compression_override'},{id:'ppHrEncOvr',key:'release_encryption_override'},
            {id:'ppHrSigOvr',key:'release_signature_override'},
            {id:'ppHrCodeEnabled',key:'code_enabled'},{id:'ppHrCodeComp',key:'code_compression'},
            {id:'ppHrCodeEnc',key:'code_encryption'},{id:'ppHrCodeSig',key:'code_signature'},
            {id:'ppHrCodeUnits',key:'code_units'},
            {id:'ppHrResEnabled',key:'resource_enabled'},{id:'ppHrResComp',key:'resource_compression'},
            {id:'ppHrResEnc',key:'resource_encryption'},{id:'ppHrResSig',key:'resource_signature'},
            {id:'ppHrResUnits',key:'resource_units'}
        ]);
        if(hr.release_targets) {
            _ppTargets = {code:false,resource:false};
            hr.release_targets.split(',').forEach(function(t){ t=t.trim(); if(_ppTargets.hasOwnProperty(t)) _ppTargets[t]=true; });
            updatePpChips();
        }
        onPpHrModeChange();
    }
    var ab = pipeline.apk_build;
    if (ab && !ab.git_branch && pipeline.git_branch) ab.git_branch = pipeline.git_branch;
    restoreCfg(ab, document.getElementById('ppApkBuild'), document.getElementById('ppApkBuildBody'), [
        {id:'ppApkUnity',key:'unity_version'},{id:'ppApkBranch',key:'git_branch'},
        {id:'ppApkAppName',key:'app_name'},{id:'ppApkOutput',key:'output_base_dir'}
    ]);
    if (!document.getElementById('ppApkBranch').value && pipeline.git_branch) {
        document.getElementById('ppApkBranch').value = pipeline.git_branch;
    }
}
var CHANNELS_FULL=_pd.channels_full||{};
var PROJECT_CHANNELS=_pd.project_channels||[];
var ALL_CHANNELS=_pd.all_channels||[];
var VERSION_STAGES=_pd.version_stages||[{id:'dev',name:'开发'},{id:'test',name:'测试'},{id:'production',name:'线上'}];
var PROJECT_NAME_EN=(_pd.project_name_en||PROJECT_ID||'').replace(new RegExp("\\\\s","g"),"");
var STAGE_DIR_MAP={dev:'dev',test:'test',production:'release'};
var allVersions=(_pd.versions||[]).map(function(v){v.channel_label=v.channel_label||v.channel;v.stage=v.stage||'dev';v.stage_label=v.stage_label||'开发';return v;});
function _esc(s){if(s==null||s===undefined)return"";return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
var VERSION_STATUS_META={
    draft:{label:'草稿',badge:'bg-slate-100 text-slate-700 border border-slate-200',row:'bg-slate-50/30',panel:'bg-slate-50/40'},
    active:{label:'有效',badge:'bg-emerald-100 text-emerald-700 border border-emerald-200',row:'bg-emerald-50/35',panel:'bg-emerald-50/45'},
    testing:{label:'测试中',badge:'bg-sky-100 text-sky-700 border border-sky-200',row:'bg-sky-50/35',panel:'bg-sky-50/45'},
    disabled:{label:'失效',badge:'bg-rose-100 text-rose-700 border border-rose-200',row:'bg-rose-50/35',panel:'bg-rose-50/45'},
    archived:{label:'归档',badge:'bg-slate-200 text-slate-700 border border-slate-300',row:'bg-slate-100/65',panel:'bg-slate-100/75'}
};
function normalizeVersionStatus(s){
    s=String(s||'').toLowerCase().trim();
    if(s==='draft') return 'draft';
    if(s==='valid'||s==='enabled'||s==='online') return 'active';
    if(s==='test'||s==='beta') return 'testing';
    if(s==='deprecated'||s==='obsolete'||s==='invalid'||s==='inactive') return 'disabled';
    if(s==='archive') return 'archived';
    return VERSION_STATUS_META[s] ? s : 'active';
}
function getVersionStatusMeta(s){
    return VERSION_STATUS_META[normalizeVersionStatus(s)] || VERSION_STATUS_META.active;
}
function _getVersionFilterKey(channelId, stageId){
    return String(channelId||'') + '::' + String(stageId||'');
}
function _getVersionFilter(channelId, stageId){
    window._versionFilters = window._versionFilters || {};
    var key = _getVersionFilterKey(channelId, stageId);
    if(!window._versionFilters[key]){
        window._versionFilters[key] = { q:'', platform:'all', status:'all' };
    }
    return window._versionFilters[key];
}

window.switchTab=function switchTab(name){
    var allowed={overview:1,channels:1,build:1,download:1};
    name = String(name||'overview').toLowerCase().trim();
    if(!allowed[name]) name='overview';
    document.querySelectorAll('.tab-btn').forEach(function(b){ b.classList.remove('text-amber-600','border-b-2','border-amber-600'); b.classList.add('text-gray-500'); });
    document.querySelectorAll('.tab-panel').forEach(function(p){ p.classList.add('hidden'); });
    var btn = document.getElementById('tab' + name.charAt(0).toUpperCase() + name.slice(1));
    var panel = document.getElementById('panel' + name.charAt(0).toUpperCase() + name.slice(1));
    if(btn){ btn.classList.remove('text-gray-500'); btn.classList.add('text-amber-600','border-b-2','border-amber-600'); }
    if(panel){ panel.classList.remove('hidden'); }
    if(name==='channels'){
        try{ renderChannelsView(); }catch(e){ console.error('renderChannelsView failed', e); alert('版本页面初始化失败，请刷新后重试。'); }
        var sec=document.getElementById('projectTabSection');
        if(sec){ sec.scrollIntoView({behavior:'smooth', block:'start'}); }
    }
    if(typeof history!=='undefined'&&history.replaceState){ var u=new URL(window.location.href); u.searchParams.set('tab',name); history.replaceState(null,'',u.pathname+u.search); }
};
function loadProjectRecentBuilds(){
    var el=document.getElementById('projectRecentBuilds'); if(!el) return;
    fetch('/api/build/recent?limit=5', {credentials:'same-origin'}).then(function(r){ return r.json(); }).then(function(d){
        var builds=d.builds||[];
        if(builds.length===0){ el.innerHTML='<li class="text-slate-500">暂无构建记录，请先启动 Jenkins 并前往构建页</li>'; return; }
        var statusCls=function(r){ r=(r||'').toUpperCase(); if(r==='SUCCESS') return 'bg-green-100 text-green-800'; if(r==='FAILURE'||r==='ABORTED') return 'bg-red-100 text-red-800'; if(r==='UNSTABLE') return 'bg-yellow-100 text-yellow-800'; return 'bg-gray-100 text-gray-700'; };
        el.innerHTML=builds.map(function(b){ var badge='<span class="ml-1 px-2 py-0.5 rounded text-xs '+statusCls(b.result)+'">'+(b.result||'中')+'</span>'; return '<li><a href="/admin/projects/'+PROJECT_ID+'/build" class="text-indigo-600 hover:underline">#'+b.number+'</a> '+badge+'</li>'; }).join('');
    }).catch(function(){ el.innerHTML='<li class="text-slate-500">加载失败</li>'; });
}
window._showQR=function(filename){
    var modal=document.getElementById('projectQRModal'); var box=document.getElementById('projectQRCode');
    if(!modal||!box) return;
    box.innerHTML='<p class="text-slate-400 text-sm">加载中…</p>';
    modal.classList.remove('hidden'); modal.classList.add('flex');
    fetch('/qr/'+encodeURIComponent(filename),{credentials:'same-origin'}).then(function(r){ return r.json(); }).then(function(d){
        box.innerHTML= d.qr_code ? '<img src="'+d.qr_code+'" alt="QR" class="w-48 h-48 object-contain rounded-lg">' : '<p class="text-red-500 text-sm">加载失败</p>';
    }).catch(function(){ box.innerHTML='<p class="text-red-500 text-sm">加载失败</p>'; });
};
function openVersionDownloadsModal(vid){
    var modal=document.getElementById('versionDownloadsModal'); var list=document.getElementById('versionDownloadsList');
    if(!modal||!list) return;
    list.innerHTML='<p class="text-slate-400 text-sm">加载中…</p>';
    modal.classList.remove('hidden'); modal.classList.add('flex');
    fetch('/api/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/'+encodeURIComponent(vid)+'/downloads', {credentials:'same-origin'}).then(function(r){ return r.json(); }).then(function(d){
        var files=d.files||[];
        if(files.length===0){ list.innerHTML='<p class="text-slate-500 text-sm py-4">该版本暂无可下载的 APK</p>'; return; }
        var html='<div class="space-y-3">';
        files.forEach(function(f){
            var urlPath=f.url.replace('/pub/download/','');
            html+='<div class="flex items-center justify-between py-3 border-b border-slate-100 last:border-0"><div><p class="font-medium text-slate-800">'+_esc(f.name)+'</p><p class="text-xs text-slate-500">'+f.size_mb+' MB · 下载 '+f.downloads+' 次</p></div><div class="flex items-center gap-2"><a href="'+_esc(f.url)+'" class="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs hover:bg-indigo-700">下载</a><button type="button" data-qr-url="'+_esc(urlPath)+'" onclick="window._showQR(this.getAttribute(String.fromCharCode(100,97,116,97,45,113,114,45,117,114,108)))" class="px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600 text-xs hover:bg-slate-50">二维码</button></div></div>';
        });
        html+='</div>';
        list.innerHTML=html;
    }).catch(function(){ list.innerHTML='<p class="text-red-500 text-sm">加载失败</p>'; });
}
(function(){
    var h=window.location.hash;
    var qTab=(new URLSearchParams(window.location.search)).get('tab');
    if(qTab){ switchTab(qTab); }
    else if(h&&h.indexOf('tab=')>=0){ var m=h.match(/tab=([a-z]+)/); if(m) switchTab(m[1]); }
    else { switchTab('overview'); }
    fetch('/api/projects/'+encodeURIComponent(PROJECT_ID)+'/download-stats', {credentials:'same-origin'}).then(function(r){ return r.json(); }).then(function(d){
        var el=document.getElementById('projectTrend7d'); if(el) el.textContent = (d.sum_7d!=null) ? '最近7日：'+d.sum_7d+' 次' : '—';
    }).catch(function(){});
})();
document.addEventListener('click', function(e){
    var link = e.target.closest('a[href*="?tab=channels"]');
    if(!link) return;
    try{
        var u = new URL(link.href, window.location.origin);
        if(u.pathname === window.location.pathname){
            e.preventDefault();
            switchTab('channels');
        }
    }catch(_err){}
});

window._versionBuildState = window._versionBuildState || {};
window._versionBuildStateLoading = false;
window._versionBuildStateTimer = window._versionBuildStateTimer || null;
function _isVersionBuilding(versionId){
    if(!window._versionBuildState || typeof window._versionBuildState !== 'object'){
        window._versionBuildState = {};
    }
    var st = window._versionBuildState[String(versionId||'')] || {};
    return !!st.building;
}
function refreshVersionBuildState(){
    if(window._versionBuildStateLoading) return;
    if(!window._versionBuildState || typeof window._versionBuildState !== 'object'){
        window._versionBuildState = {};
    }
    var ids = (allVersions||[]).map(function(v){ return String(v.id||'').trim(); }).filter(Boolean);
    if(!ids.length){ window._versionBuildState = {}; return; }
    window._versionBuildStateLoading = true;
    Promise.all(ids.map(function(id){
        return fetch('/api/build/history-by-version?version_id='+encodeURIComponent(id), {credentials:'same-origin'})
            .then(function(r){ return r.json(); })
            .then(function(d){
                var builds = (d&&d.builds) ? d.builds : [];
                if(!builds.length) return [id, {building:false, build_number:null}];
                var sorted = builds.slice().sort(function(a,b){ return (parseInt(b.number||0,10)||0) - (parseInt(a.number||0,10)||0); });
                var latest = sorted[0] || {};
                var latestNo = parseInt(latest.number||0,10)||null;
                var building = !!latest.building || String(latest.result||'').toUpperCase()==='BUILDING' || String(latest.result||'').toUpperCase()==='QUEUED';
                return [id, {building: building, build_number: latestNo}];
            })
            .catch(function(){ return [id, {building:false, build_number:null}]; });
    })).then(function(rows){
        var next = {};
        rows.forEach(function(row){ next[row[0]] = row[1]; });
        var prev = JSON.stringify(window._versionBuildState||{});
        var curr = JSON.stringify(next);
        window._versionBuildState = next;
        if(prev !== curr) renderChannelsView();
    }).finally(function(){
        window._versionBuildStateLoading = false;
    });
}
function ensureVersionBuildStateTimer(){
    if(window._versionBuildStateTimer) return;
    window._versionBuildStateTimer = setInterval(refreshVersionBuildState, 5000);
}

function renderChannelsView(){
    var wrap = document.getElementById('channelsVersionsWrap');
    var empty = document.getElementById('channelsEmpty');
    if(!wrap) return;
    var chs = PROJECT_CHANNELS || [];
    var stages = VERSION_STAGES || [{id:'dev',name:'开发'},{id:'test',name:'测试'},{id:'production',name:'线上'}];
    if(chs.length===0){ wrap.innerHTML=''; if(empty) empty.classList.remove('hidden'); return; }
    if(empty) empty.classList.add('hidden');
    var activeChannelId = (window._activeChannelId || (chs[0] && chs[0].id) || '');
    var activeChannel = null;
    for(var ci=0; ci<chs.length; ci++){
        if((chs[ci].id||'') === activeChannelId){ activeChannel = chs[ci]; break; }
    }
    if(!activeChannel){ activeChannel = chs[0]; activeChannelId = activeChannel.id || ''; }
    window._activeChannelId = activeChannelId;

    var html = '<div class="channel-card bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">';
    html += '<div class="px-5 py-4 bg-gradient-to-r from-slate-50 to-white border-b border-slate-100">';
    html += '<div class="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2"><i class="fas fa-layer-group text-indigo-500"></i>发布渠道</div>';
    html += '<div class="flex flex-wrap gap-2">';
    for(var ti=0; ti<chs.length; ti++){
        var t = chs[ti]; var tid = t.id||''; var tname = t.name||tid; var on = tid===activeChannelId;
        html += '<button type="button" class="channel-main-tab px-3.5 py-1.5 rounded-lg text-sm font-medium transition '+(on?'bg-indigo-600 text-white shadow-sm':'bg-slate-100 text-slate-700 hover:bg-slate-200')+'" data-channel-id="'+_esc(tid)+'">'+_esc(tname)+'</button>';
    }
    html += '</div></div>';

    var cid = activeChannel.id||'';
    html += '<div class="px-5 py-3 border-b border-slate-50 flex justify-between items-center">';
    html += '<span class="text-xs text-slate-500">当前渠道：'+_esc(activeChannel.name||cid)+'</span>';
    html += '<div class="flex rounded-lg bg-slate-100/80 p-0.5">';
    for(var s=0;s<stages.length;s++){
        var st = stages[s]; var sid = st.id||'dev'; var sname = st.name||'开发'; var isFirst = s===0;
        html += '<button type="button" class="channel-stage-tab px-3.5 py-1.5 text-xs font-medium rounded-md transition '+(isFirst?'bg-white text-slate-800 shadow-sm':'text-slate-600 hover:text-slate-800')+'" data-block="channel-tabs" data-stage="'+_esc(sid)+'">'+_esc(sname)+'</button>';
    }
    html += '</div>';
    if(CAN_EDIT) html += '<button type="button" data-channel-id="'+_esc(cid)+'" class="ch-open-version-btn-main ml-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm transition"><i class="fas fa-plus text-[10px] mr-1"></i>新建版本</button>';
    html += '</div>';

    for(var s2=0;s2<stages.length;s2++){
        var st2 = stages[s2]; var sid2 = st2.id||'dev'; var sname2 = st2.name||'开发';
        var versAllChannel = allVersions.filter(function(v){ return ((v.channel||'').toLowerCase()===(cid||'').toLowerCase()); });
        var f = _getVersionFilter(cid, sid2);
        var kw = String(f.q||'').toLowerCase().trim();
        var fPlatform = String(f.platform||'all').toLowerCase();
        var fStatusRaw = String(f.status||'all').toLowerCase();
        var fStatus = (fStatusRaw==='all') ? 'all' : normalizeVersionStatus(fStatusRaw);
        var versFiltered = versAllChannel.filter(function(v){
            var okName = !kw || String(v.version_name||'').toLowerCase().indexOf(kw) >= 0 || String(v.version_code||'').toLowerCase().indexOf(kw) >= 0;
            var okPlatform = (fPlatform==='all') || (String(v.platform||'').toLowerCase()===fPlatform);
            var okStatus = (fStatus==='all') || (normalizeVersionStatus(v.version_status||'active')===fStatus);
            return okName && okPlatform && okStatus;
        });
        var vers = versFiltered.filter(function(v){ return (v.stage||'dev')===(sid2||'dev'); });
        var versAll = versAllChannel;
        var panelHidden = s2>0 ? ' hidden' : '';
        html += '<div class="channel-stage-panel'+panelHidden+'" data-block="channel-tabs" data-stage="'+_esc(sid2)+'">';
        html += '<div class="px-5 py-3 flex justify-between items-center border-b border-slate-50">';
        html += '<span class="text-xs text-slate-500">'+_esc(sname2)+' 阶段 · 本阶段 '+vers.length+' 条 / 渠道内 '+versFiltered.length+' 条</span>';
        html += '</div><div class="p-5">';
        html += '<div class="mb-3 grid grid-cols-1 md:grid-cols-3 gap-2" data-version-filter-wrap="1">';
        html += '<input type="text" class="version-filter-input px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500" placeholder="筛选版本号 / Version Code" value="'+_esc(f.q||'')+'" data-channel-id="'+_esc(cid)+'" data-stage="'+_esc(sid2)+'" data-filter-field="q">';
        html += '<select class="version-filter-input px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500" data-channel-id="'+_esc(cid)+'" data-stage="'+_esc(sid2)+'" data-filter-field="platform">';
        html += '<option value="all"'+(fPlatform==='all'?' selected':'')+'>全部平台</option><option value="android"'+(fPlatform==='android'?' selected':'')+'>Android</option><option value="ios"'+(fPlatform==='ios'?' selected':'')+'>iOS</option>';
        html += '</select>';
        html += '<select class="version-filter-input px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500" data-channel-id="'+_esc(cid)+'" data-stage="'+_esc(sid2)+'" data-filter-field="status">';
        html += '<option value="all"'+(fStatus==='all'?' selected':'')+'>全部状态</option><option value="draft"'+(fStatus==='draft'?' selected':'')+'>草稿</option><option value="testing"'+(fStatus==='testing'?' selected':'')+'>测试中</option><option value="active"'+(fStatus==='active'?' selected':'')+'>有效</option><option value="disabled"'+(fStatus==='disabled'?' selected':'')+'>失效</option><option value="archived"'+(fStatus==='archived'?' selected':'')+'>归档</option>';
        html += '</select>';
        html += '</div>';
        if(vers.length===0){
            html += '<div class="py-10 text-center rounded-xl bg-slate-50/60 border border-dashed border-slate-200"><i class="fas fa-cube text-3xl text-slate-200 mb-2"></i><p class="text-slate-500 text-sm">没有匹配的版本</p><p class="text-slate-400 text-xs mt-0.5">'+(versAll.length>0?'试试调整筛选条件':'点击「新建版本」添加')+'</p></div>';
        } else {
            // ---- 按版本号分组（同渠道同 version_name 跨阶段归为一组）----
            var groups = {};
            versFiltered.forEach(function(v){
                var vn = (v.version_name || '').trim() || '未命名';
                if(!groups[vn]) groups[vn] = [];
                groups[vn].push(v);
            });
            var groupKeys = Object.keys(groups).sort(function(a,b){ return b.localeCompare(a); });
            html += '<div class="space-y-3">';
            for(var gi=0; gi<groupKeys.length; gi++){
                var gName = groupKeys[gi];
                var gVersAll = groups[gName];
                var gVers = gVersAll.filter(function(x){ return (x.stage||'dev')===(sid2||'dev'); });
                var activeCount = gVersAll.filter(function(x){ return normalizeVersionStatus(x.version_status||'active')==='active'; }).length;
                var totalDownloads = gVersAll.reduce(function(s,x){ return s + (x.download_count||0); }, 0);
                var stageCountHint = (gVers.length<gVersAll.length) ? ('（本阶段 '+gVers.length+' 个）') : '';
                var hasRecommended = gVers.some(function(x){ return x.recommended; });
                var hasCommercial = gVers.some(function(x){ return (x.version_mode||'general')==='commercial'; });
                var gStatusLabel = activeCount===gVersAll.length ? '全部有效' : (activeCount>0 ? activeCount+'/'+gVersAll.length+' 有效' : '全部非有效');
                var gStatusColor = activeCount===gVersAll.length ? 'bg-emerald-100 text-emerald-700' : (activeCount>0 ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500');
                // 组级操作（编辑/删除第一个版本，或弹出批量操作）
                var firstV = gVersAll[0];
                var gActions = CAN_EDIT ? '<button type="button" data-version-name="'+_esc(gName)+'" class="version-add-code-btn version-op-btn version-op-build"><i class="fas fa-plus text-[10px]" style="pointer-events:none;"></i>增加 VersionCode</button><button type="button" data-version-id="'+_esc(firstV.id||'')+'" class="version-group-edit-btn version-op-btn version-op-edit"><i class="fas fa-pen text-[10px]" style="pointer-events:none;"></i>编辑版本</button><button type="button" data-version-name="'+_esc(gName)+'" class="version-group-delete-btn version-op-btn version-op-delete"><i class="fas fa-trash text-[10px]" style="pointer-events:none;"></i>删除组</button>' : '';
                var gRecBadge = hasRecommended ? ' <span class="px-1.5 py-0.5 rounded text-[10px] bg-amber-100 text-amber-700">推荐</span>' : '';
                var gModeBadge = hasCommercial ? ' <span class="px-1.5 py-0.5 rounded text-[10px] bg-violet-100 text-violet-700">🚀 商业版</span>' : ' <span class="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-500">📦 通用</span>';
                html += '<div class="version-group rounded-xl border overflow-hidden '+(hasCommercial?'border-violet-200 bg-violet-50/20':'border-slate-200 bg-white')+'" style="border-left:3px solid '+(hasCommercial?'#8b5cf6':'#cbd5e1')+';">';
                html += '<div class="version-group-header flex items-center justify-between px-4 py-3 bg-slate-50/60 cursor-pointer select-none" >';
                html += '<div class="flex items-center gap-2">';
                html += '<i class="fas fa-chevron-down text-[10px] text-slate-400 transition-transform version-group-arrow" style="pointer-events:none;"></i>';
                html += '<span class="font-semibold text-sm text-slate-800">'+_esc(gName)+gRecBadge+gModeBadge+'</span>';
                html += '<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] '+gStatusColor+'">'+gStatusLabel+'</span>';
                html += '<span class="text-[11px] text-slate-400">'+gVersAll.length+' 个 VersionCode'+stageCountHint+' · '+totalDownloads+' 次下载</span>';
                html += '</div>';
                html += '<div class="flex items-center gap-2">' + gActions + '</div>';
                html += '</div>';
                // 子表
                html += '<div class="version-group-body">';
                html += '<table class="w-full text-xs"><thead><tr class="border-b border-slate-100 text-left text-slate-400"><th class="px-4 py-2 font-normal">Version Code</th><th class="px-4 py-2 font-normal">阶段</th><th class="px-4 py-2 font-normal">平台</th><th class="px-4 py-2 font-normal">状态</th><th class="px-4 py-2 font-normal">安装包</th><th class="px-4 py-2 font-normal">下载</th><th class="px-4 py-2 font-normal">路径</th><th class="px-4 py-2 font-normal w-28">操作</th></tr></thead><tbody>';
                if(!gVers.length && gVersAll.length){
                    html += '<tr><td colspan="8" class="px-4 py-4 text-center text-slate-500 text-xs">本阶段暂无 VersionCode，请切换到其他阶段标签查看，或在当前阶段点击「增加 VersionCode」</td></tr>';
                }
                for(var vj=0; vj<gVers.length; vj++){
                    var v = gVers[vj]; var vid = v.id||'';
                    var isBuilding = _isVersionBuilding(vid);
                    var stMeta = getVersionStatusMeta(v.version_status);
                    var stBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] '+stMeta.badge+'">'+_esc(stMeta.label)+'</span>';
                    var apkBadge = (v.apk_status==='found') ? '<span class="text-[10px] text-emerald-600"><i class="fas fa-check-circle mr-0.5"></i>已落盘</span>' : ((v.apk_status==='not_found') ? '<span class="text-[10px] text-slate-400" style="display:block;line-height:1;margin-bottom:1px;">未找到</span>' : '—');
                    var buildCls = isBuilding ? 'text-amber-500 animate-pulse' : 'text-emerald-600 hover:text-emerald-800';
                    var buildIconCls = isBuilding ? 'fas fa-cogs fa-spin' : 'fas fa-cogs';
                    var buildTitle = isBuilding ? '构建中（仅可查看）' : '构建';
                    var vActions = '<a href="/admin/projects/'+PROJECT_ID+'/versions/'+_esc(vid)+'/workflow" class="'+buildCls+' text-[11px] mr-2" title="'+buildTitle+'"><i class="'+buildIconCls+'" style="pointer-events:none;"></i></a>';
                    if(CAN_EDIT && !isBuilding) vActions += '<button type="button" data-version-id="'+_esc(vid)+'" class="version-code-edit-btn text-indigo-500 hover:text-indigo-700 text-[11px] mr-2" title="编辑 VersionCode"><i class="fas fa-pen" style="pointer-events:none;"></i></button><button type="button" data-version-id="'+_esc(vid)+'" class="version-delete-btn text-rose-500 hover:text-rose-700 text-[11px]" title="删除"><i class="fas fa-trash" style="pointer-events:none;"></i></button>';
                    var rowBg = vj%2===0 ? 'bg-white' : 'bg-slate-50/30';
                    var isCommercialV = (v.version_mode||'general')==='commercial';
                    var vModeBg = isCommercialV ? '' : rowBg; var vModeStyle = isCommercialV ? 'background:linear-gradient(to right,#ede9fe,#f5f3ff);' : '';
                    var vModeIndicator = '';
                    var detailId = 'vd_'+_esc(vid);
                    // Build detail content
                    var dHtml = '<div class="grid grid-cols-3 gap-x-4 gap-y-1 text-xs">';
                    dHtml += '<div><span class="text-slate-400">渠道:</span> '+_esc(v.channel_label||v.channel||'-')+'</div>';
                    dHtml += '<div><span class="text-slate-400">阶段:</span> '+_esc(v.stage_label||v.stage||'-')+'</div>';
                    dHtml += '<div><span class="text-slate-400">平台:</span> '+_esc(v.platform_label||v.platform||'-')+'</div>';
                    dHtml += '<div><span class="text-slate-400">版本名:</span> '+_esc(v.version_name||'-')+'</div>';
                    dHtml += '<div><span class="text-slate-400">版本模式:</span> '+(isCommercialV?'<span class="text-violet-600 font-medium">商业版</span>':'<span class="text-slate-500">通用版</span>')+'</div>';
                    dHtml += '<div><span class="text-slate-400">发布方式:</span> '+_esc(v.distribution_method||'-')+'</div>';
                    dHtml += '<div><span class="text-slate-400">包名:</span> '+_esc(v.package_name||'-')+'</div>';
                    dHtml += '<div><span class="text-slate-400">最低SDK:</span> '+_esc(v.min_sdk||'-')+'</div>';
                    dHtml += '<div><span class="text-slate-400">Jenkins:</span> '+_esc(v.jenkins_job_id||'-')+'</div>';
                    dHtml += '<div class="col-span-3"><span class="text-slate-400">安装包:</span> '+_esc(v.apk_path||'-')+'</div>';
                    dHtml += '<div class="col-span-3"><span class="text-slate-400">资源路径:</span> '+_esc(v.resource_path||'-')+'</div>';
                    dHtml += '<div class="col-span-3"><span class="text-slate-400">配置路径:</span> '+_esc(v.config_path||'-')+'</div>';
                    if(v.changelog_text) dHtml += '<div class="col-span-3"><span class="text-slate-400">更新说明:</span> '+_esc(v.changelog_text)+'</div>';
                    if(v.notes) dHtml += '<div class="col-span-3"><span class="text-slate-400">备注:</span> '+_esc(v.notes)+'</div>';
                    if(isCommercialV && v.pipeline){
                        var pp = v.pipeline;
                        dHtml += '<div class="col-span-3 mt-1 pt-1 border-t border-slate-100"><span class="text-violet-600 font-medium">流水线参数</span></div>';
                        if(pp.config_export) dHtml += '<div class="col-span-3"><span class="text-slate-400">配置导出:</span> '+(pp.config_export.enabled?'启用':'禁用')+' | 前缀:'+_esc(pp.config_export.remote_prefix||'-')+' | 版本:'+_esc(pp.config_export.client_version||'-')+'</div>';
                        if(pp.resource_build) dHtml += '<div class="col-span-3"><span class="text-slate-400">资源打包:</span> '+(pp.resource_build.enabled?'启用':'禁用')+' | 引擎:'+_esc(pp.resource_build.provider||'-')+'</div>';
                        if(pp.hot_release){
                            var hr=pp.hot_release;
                            dHtml += '<div class="col-span-3"><span class="text-slate-400">热更发布:</span> '+(hr.enabled?'启用':'禁用')+' | 对象:'+_esc(hr.release_targets||'-')+' | 模式:'+_esc(hr.release_mode||'-')+' | 上传:'+_esc(hr.release_upload_mode||'-')+'</div>';
                            if(hr.code_enabled) dHtml += '<div class="col-span-3 pl-3"><span class="text-blue-500">代码包:</span> 压缩:'+_esc(hr.code_compression||'-')+' 加密:'+_esc(hr.code_encryption||'-')+' 签名:'+_esc(hr.code_signature||'-')+'</div>';
                            if(hr.resource_enabled) dHtml += '<div class="col-span-3 pl-3"><span class="text-emerald-500">资源包:</span> 压缩:'+_esc(hr.resource_compression||'-')+' 加密:'+_esc(hr.resource_encryption||'-')+' 签名:'+_esc(hr.resource_signature||'-')+'</div>';
                        }
                        if(pp.apk_build) dHtml += '<div class="col-span-3"><span class="text-slate-400">APK打包:</span> '+(pp.apk_build.enabled?'启用':'禁用')+'</div>';
                    }
                    dHtml += '</div>';
                    var colCount = 8;
                    
                    html += '<tr class="'+vModeBg+' '+stMeta.row+' border-b border-slate-50 hover:bg-slate-100/30 transition" style="'+vModeStyle+(isCommercialV?'border-left:3px solid #8b5cf6;':'')+'">';
                    html += '<td class="px-4 py-2 font-mono text-slate-700"><div class="flex items-center gap-1.5">'+_esc(v.version_code||'-')+vModeIndicator+'<button type="button" class="ver-expand-btn ml-1 text-slate-400 hover:text-slate-600" data-detail-id="'+detailId+'"><i class="fas fa-chevron-down text-[9px] ver-expand-arrow transition-transform" style="pointer-events:none;"></i></button></div></td>';
                    html += '<td class="px-4 py-2 text-slate-500">'+_esc(v.stage_label||v.stage||'-')+'</td>';
                    html += '<td class="px-4 py-2 text-slate-500">'+_esc(v.platform_label||v.platform||'-')+'</td>';
                    html += '<td class="px-4 py-2">'+stBadge+'</td>';
                    html += '<td class="px-4 py-2">'+apkBadge+'</td>';
                    html += '<td class="px-4 py-2 text-slate-500">'+(v.download_count||0)+'</td>';
                    html += '<td class="px-4 py-2 text-slate-400 max-w-[180px] truncate" title="'+_esc(v.apk_path||'')+'">'+_esc(v.apk_path||'-')+'</td>';
                    html += '<td class="px-4 py-2">'+vActions+'</td>';
                    html += '</tr>';
                    html += '<tr id="'+detailId+'" class="hidden"><td colspan="'+colCount+'" class="px-4 py-3" style="'+(isCommercialV?'background:#ede9fe;border-left:3px solid #8b5cf6;':'background:#f8fafc;border-left:3px solid #e2e8f0;')+'">'+dHtml+'</td></tr>';
                }
                html += '</tbody></table></div></div>';
            }
            html += '</div>';
        }
        html += '</div></div>';
    }
    html += '</div>';
    wrap.innerHTML = html;

    document.querySelectorAll('.channel-main-tab').forEach(function(btn){
        btn.onclick = function(){
            window._activeChannelId = btn.getAttribute('data-channel-id') || '';
            renderChannelsView();
        };
    });
    document.querySelectorAll('.channel-stage-tab').forEach(function(btn){
        btn.onclick = function(){
            var block = btn.getAttribute('data-block'); var stage = btn.getAttribute('data-stage');
            var card = document.querySelector('[data-block-id="'+block+'"]');
            if(!card) card = wrap;
            card.querySelectorAll('.channel-stage-tab').forEach(function(b){ b.classList.remove('bg-white','text-slate-800','shadow-sm'); b.classList.add('text-slate-600'); });
            btn.classList.add('bg-white','text-slate-800','shadow-sm'); btn.classList.remove('text-slate-600');
            card.querySelectorAll('.channel-stage-panel').forEach(function(p){ p.classList.add('hidden'); });
            var pan = card.querySelector('.channel-stage-panel[data-stage="'+stage+'"]'); if(pan) pan.classList.remove('hidden');
        };
    });
    // === 直接绑定事件（不依赖事件委托）===
    wrap.querySelectorAll('.version-group-header').forEach(function(header){
        header.onclick = function(e){
            if(e.target.closest('.version-op-btn')||e.target.closest('.version-group-delete-btn')) return;
            toggleVersionGroup(header);
        };
    });
    wrap.querySelectorAll('.version-group-delete-btn').forEach(function(btn){
        btn.onclick = function(e){
            e.stopPropagation();
            var vn=btn.getAttribute('data-version-name');
            if(vn&&requireDeleteConfirm('版本组: '+vn)){deleteVersionGroup(vn);}
        };
    });
    wrap.querySelectorAll('.version-group-edit-btn').forEach(function(btn){
        btn.onclick = function(e){
            e.stopPropagation();
            editVersion(btn.getAttribute('data-version-id'));
        };
    });
    wrap.querySelectorAll('.version-code-edit-btn').forEach(function(btn){
        btn.onclick = function(e){
            e.stopPropagation();
            openVersionCodeModal(btn.getAttribute('data-version-id'));
        };
    });
    wrap.querySelectorAll('.version-delete-btn').forEach(function(btn){
        btn.onclick = function(e){
            e.stopPropagation();
            deleteVersion(btn.getAttribute('data-version-id'));
        };
    });
    wrap.querySelectorAll('.ver-expand-btn').forEach(function(btn){
        btn.onclick = function(e){
            e.stopPropagation();
            toggleVerDetail(btn);
        };
    });
    wrap.querySelectorAll('.ch-open-version-btn-main').forEach(function(btn){
        btn.onclick = function(e){
            e.stopPropagation();
            var chId=btn.getAttribute('data-channel-id')||'';
            var activeStageBtn=document.querySelector('.channel-stage-tab.bg-white');
            var stg=activeStageBtn?activeStageBtn.getAttribute('data-stage'):'dev';
            openVersionModal(chId,stg);
        };
    });
    wrap.querySelectorAll('.ch-open-version-btn').forEach(function(btn){
        btn.onclick = function(e){
            e.stopPropagation();
            openVersionModal(btn.getAttribute('data-channel-id')||'',btn.getAttribute('data-stage')||'dev');
        };
    });
}
(function(){
var _wrap = document.getElementById('channelsVersionsWrap');
if(!_wrap) return;
_wrap.addEventListener('click', function(e){
    var t=e.target.closest('.ch-open-version-btn-main');if(t){e.stopPropagation();var chId=t.getAttribute('data-channel-id')||''; var activeStageBtn=document.querySelector('.channel-stage-tab.bg-white'); var stg=activeStageBtn?activeStageBtn.getAttribute('data-stage'):'dev'; openVersionModal(chId,stg); return;}
    t=e.target.closest('.ch-open-version-btn');
    if(t){e.stopPropagation();openVersionModal(t.getAttribute('data-channel-id')||'',t.getAttribute('data-stage')||'dev');return;}
    t=e.target.closest('.ver-expand-btn');if(t){e.stopPropagation();toggleVerDetail(t);return;}
    t=e.target.closest('.version-fold-btn');if(t){e.stopPropagation();var vid=t.getAttribute('data-version-id'); var row=document.querySelector('.version-params-row[data-version-id="'+vid+'"]'); if(row){ row.classList.toggle('hidden'); t.querySelector('i').className=row.classList.contains('hidden')?'fas fa-chevron-down text-[10px]':'fas fa-chevron-up text-[10px]'; } return;}
    t=e.target.closest('.version-downloads-btn');if(t){e.stopPropagation();openVersionDownloadsModal(t.getAttribute('data-version-id'));return;}
    t=e.target.closest('.version-group-edit-btn');if(t){e.stopPropagation();editVersion(t.getAttribute('data-version-id'));return;}
    t=e.target.closest('.version-code-edit-btn');if(t){e.stopPropagation();openVersionCodeModal(t.getAttribute('data-version-id'));return;}
    t=e.target.closest('.version-add-code-btn');if(t){e.stopPropagation();openAddVersionCodeModal(t.getAttribute('data-version-name'));return;}
    t=e.target.closest('.version-delete-btn');if(t){e.stopPropagation();deleteVersion(t.getAttribute('data-version-id'));return;}
    t=e.target.closest('.version-group-header');if(t&&!e.target.closest('.version-op-btn')&&!e.target.closest('.version-group-delete-btn')){e.stopPropagation();toggleVersionGroup(t);return;}
    t=e.target.closest('.version-group-delete-btn');if(t){e.stopPropagation();var vn=t.getAttribute('data-version-name');if(vn&&requireDeleteConfirm('版本组: '+vn)){deleteVersionGroup(vn);}}
}, true);
})();
function toggleVerDetail(btn){
    var detailId = btn.getAttribute('data-detail-id');
    var d = document.getElementById(detailId);
    if(d) d.classList.toggle('hidden');
    var a = btn.querySelector('.ver-expand-arrow');
    if(a) a.classList.toggle('rotate-180');
}
function toggleVersionGroup(header){
    var group = header.closest('.version-group');
    var body = group ? group.querySelector('.version-group-body') : null;
    var arrow = header.querySelector('.version-group-arrow');
    if(body){ body.classList.toggle('hidden'); }
    if(arrow){ arrow.classList.toggle('fa-chevron-down'); arrow.classList.toggle('fa-chevron-up'); }
}
function requireDeleteConfirm(targetLabel){
    var tip = '删除后不可恢复。\\n请输入“删除”确认删除：\\n目标：' + (targetLabel || '当前项');
    var input = window.prompt(tip, '');
    return input && String(input).trim() === '删除';
}
function deleteVersionGroup(versionName){
    var ids = allVersions.filter(function(v){ return (v.version_name||'').trim()===versionName; }).map(function(v){ return v.id||''; }).filter(Boolean);
    if(!ids.length) return;
    var deleteNext = function(idx){
        if(idx>=ids.length){ renderChannelsView(); return; }
        var vid = ids[idx];
        fetch('/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/delete/'+encodeURIComponent(vid), { method:'DELETE', credentials:'same-origin' })
        .then(function(r){ return r.json(); })
        .then(function(d){
            if(!d || !d.error){
                allVersions = allVersions.filter(function(v){ return (v.id||'') !== vid; });
            }
            deleteNext(idx+1);
        })
        .catch(function(){ deleteNext(idx+1); });
    };
    deleteNext(0);
}
document.getElementById("channelsVersionsWrap")&&document.getElementById("channelsVersionsWrap").addEventListener("input",function(e){
    var el=e.target.closest(".version-filter-input");
    if(!el) return;
    var field=el.getAttribute("data-filter-field");
    var channelId=el.getAttribute("data-channel-id")||"";
    var stageId=el.getAttribute("data-stage")||"dev";
    if(!field) return;
    var f=_getVersionFilter(channelId, stageId);
    f[field]=el.value||"";
    renderChannelsView();
});
document.getElementById("channelsVersionsWrap")&&document.getElementById("channelsVersionsWrap").addEventListener("change",function(e){
    var el=e.target.closest(".version-filter-input");
    if(!el) return;
    var field=el.getAttribute("data-filter-field");
    var channelId=el.getAttribute("data-channel-id")||"";
    var stageId=el.getAttribute("data-stage")||"dev";
    if(!field) return;
    var f=_getVersionFilter(channelId, stageId);
    f[field]=el.value||"";
    renderChannelsView();
});
function toggleAddChannelDropdown(){
    var dd = document.getElementById('addChannelDropdown');
    if(!dd) return;
    if(dd.classList.contains('hidden')){ dd.classList.remove('hidden'); dd.innerHTML = ''; var cur = (PROJECT_CHANNELS||[]).map(function(c){ return (c.id||'').toLowerCase(); }); var opts = ALL_CHANNELS||[]; for(var i=0;i<opts.length;i++){ var o=opts[i]; if(cur.indexOf((o.id||'').toLowerCase())>=0) continue; dd.innerHTML += '<button type="button" data-channel-id='+JSON.stringify(o.id||'')+' class="add-channel-btn w-full text-left px-4 py-1.5 text-sm text-slate-700 hover:bg-slate-100">'+_esc(o.name||o.id)+'</button>'; } if(dd.innerHTML==='') dd.innerHTML='<p class="px-4 py-2 text-slate-500 text-sm">无更多渠道可添加</p>'; }
    else dd.classList.add('hidden');
}
document.addEventListener('click', function(e){ var dd=document.getElementById('addChannelDropdown'); var b=e.target.closest('.add-channel-btn'); if(b&&b.closest('#addChannelDropdown')){ addProjectChannel(b.dataset.channelId); if(dd) dd.classList.add('hidden'); return; } var rb=e.target.closest('.remove-channel-btn'); if(rb){ removeProjectChannel(rb.getAttribute('data-channel-id')||''); return; } if(dd&&!dd.classList.contains('hidden')&&!e.target.closest('.relative')) dd.classList.add('hidden'); });
function addProjectChannel(cid){ fetch('/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/channels/add', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({channel_id:cid}), credentials:'same-origin' }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); return; } location.reload(); }); }
function removeProjectChannel(cid){ if(!confirm('确定从项目中移除此渠道？该渠道下的版本将不再在渠道列表中显示。')) return; fetch('/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/channels/remove', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({channel_id:cid}), credentials:'same-origin' }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); return; } location.reload(); }); }

var _unityVersionCatalog=[];
function _setUnityVersionHint(text,isErr){
    var el=document.getElementById('ppApkUnityHint');
    if(!el) return;
    el.textContent=text||'';
    el.className='text-[10px] mt-0.5 '+(isErr?'text-rose-500':'text-slate-400');
}
function fetchUnityVersionCatalog(done){
    return fetch('/api/jenkins-manage/unity-catalog?active_only=1',{credentials:'same-origin'})
    .then(function(r){ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
    .then(function(d){
        var rows=(d&&d.entries)||[];
        _unityVersionCatalog=rows.map(function(e){ return {version:e.version,path:e.path,category:e.category,note:e.note}; });
        if(done) done(_unityVersionCatalog); return _unityVersionCatalog;
    })
    .catch(function(e){ _unityVersionCatalog=[]; _setUnityVersionHint('加载 Unity 版本库失败：'+(e&&e.message?e.message:'请先在 Jenkins 管理维护'),true); if(done) done([]); return []; });
}
function renderUnityVersionSelect(selected){
    var sel=document.getElementById('ppApkUnity');
    if(!sel) return;
    var want=String(selected||sel.value||'').trim();
    var items=_unityVersionCatalog||[];
    sel.innerHTML='';
    if(!items.length){
        var empty=document.createElement('option');
        empty.value=want;
        empty.textContent=want?('已保存: '+want):'暂无有效 Unity 版本';
        sel.appendChild(empty);
        _setUnityVersionHint('版本库中无有效项，请到 Jenkins 管理 → Unity 版本库 添加',true);
        return;
    }
    var i, v, op, label;
    for(i=0;i<items.length;i++){
        v=(items[i]&&items[i].version)||'';
        if(!v) continue;
        op=document.createElement('option');
        op.value=v;
        label=v;
        if(items[i]&&items[i].category){ label+=' ['+items[i].category+']'; }
        if(items[i]&&items[i].note){ label+=' - '+items[i].note; }
        op.textContent=label;
        sel.appendChild(op);
    }
    if(want){
        var found=false;
        for(i=0;i<sel.options.length;i++){ if(sel.options[i].value===want){ found=true; break; } }
        if(!found){
            op=document.createElement('option');
            op.value=want;
            op.textContent='（已保存·可能已失效）'+want;
            sel.insertBefore(op, sel.firstChild);
        }
        sel.value=want;
    } else if(sel.options.length){ sel.selectedIndex=0; }
    _setUnityVersionHint('已加载 '+items.length+' 个有效 Unity 版本',false);
}
function ensureUnityVersionSelect(selected,done){
    var sel=document.getElementById('ppApkUnity');
    if(sel){ sel.innerHTML='<option value="">加载中...</option>'; }
    _setUnityVersionHint('正在加载 Unity 版本库...',false);
    if(_unityVersionCatalog&&_unityVersionCatalog.length){
        renderUnityVersionSelect(selected);
        if(done) done();
        return;
    }
    fetchUnityVersionCatalog(function(){ renderUnityVersionSelect(selected); if(done) done(); });
}
document.getElementById('btnRefreshUnityVersions')&&document.getElementById('btnRefreshUnityVersions').addEventListener('click',function(){
    _unityVersionCatalog=[];
    ensureUnityVersionSelect((document.getElementById('ppApkUnity')||{}).value||'');
});
function buildDerivedVersionBasePath(versionCode){
    var ch=(document.getElementById('versionChannel')||{}).value||'common';
    var st=(document.getElementById('versionStage')||{}).value||'dev';
    var platform=((document.getElementById('versionPlatform')||{}).value||'android').toLowerCase();
    var vn=((document.getElementById('versionName')||{}).value||'1.0.0').trim()||'1.0.0';
    var stageMap={dev:'Development',test:'Testing',production:'Production'};
    var env=stageMap[st]||'Development';
    var channelSeg=(function(){
        var info=CHANNELS_FULL&&CHANNELS_FULL[ch];
        var bp=(info&&info.build_param)||'';
        var m=String(bp).match(/CHANNEL\\s*=\\s*([A-Za-z0-9_.-]+)/i);
        if(m&&m[1]) return m[1];
        return ch||'common';
    })();
    var verFolder='Version_'+vn;
    var vc=String(versionCode||'').trim();
    var codeSeg=vc?('/'+vc):'';
    return env+'/'+channelSeg+'/'+platform+'/'+verFolder+codeSeg;
}
function syncDerivedVersionPaths(versionCode){
    var base=buildDerivedVersionBasePath(versionCode);
    var resEl=document.getElementById('versionResourcePath');
    var cfgEl=document.getElementById('versionConfigPath');
    if(resEl) resEl.value=base;
    if(cfgEl) cfgEl.value=base+'/config';
}
function suggestVersionApkPath(){ var ch=document.getElementById('versionChannel').value; var st=(document.getElementById('versionStage')||{}).value||'dev'; var platform=(document.getElementById('versionPlatform')||{}).value||'android'; var vn=(document.getElementById('versionName')||{}).value.trim()||'1.0.0'; var info=CHANNELS_FULL&&CHANNELS_FULL[ch]; var stageDir=STAGE_DIR_MAP[st]||'dev'; var ext=platform==='ios'?'.ipa':'.apk'; var pkgName=PROJECT_ID+'_'+vn.replace(new RegExp("\\\\s","g"),"")+ext; var sug; if(info&&info.apk_subdir){ sug=info.apk_subdir+'/'+stageDir+'/'+pkgName; } else { sug=stageDir+'/'+pkgName; } var apkEl=document.getElementById('versionApkPath'); if(apkEl&&!apkEl.value) apkEl.placeholder='建议: '+sug; }
function syncVersionPlatformFields(){ var platform=(document.getElementById('versionPlatform')||{}).value||'android'; var androidFields=document.getElementById('androidVersionFields'); var iosFields=document.getElementById('iosVersionFields'); var distribution=document.getElementById('versionDistributionMethod'); if(androidFields) androidFields.classList.toggle('hidden', platform==='ios'); if(iosFields) iosFields.classList.toggle('hidden', platform!=='ios'); if(distribution && !distribution.value){ distribution.value = platform==='ios' ? 'testflight' : 'direct'; } }
function openVersionModal(preselectedChannel, preselectedStage){ document.getElementById('versionModalTitle').textContent='新建版本'; document.getElementById('versionEditId').value=''; document.getElementById('chkCommercialMode').checked=false; toggleCommercialMode(); var defCh = preselectedChannel || ((PROJECT_CHANNELS&&PROJECT_CHANNELS[0]) ? PROJECT_CHANNELS[0].id : 'dev'); var defSt = preselectedStage || 'dev'; ['versionChannel','versionStage','versionPlatform','versionName','versionStatus','versionApkPath','versionResourcePath','versionConfigPath','versionJenkinsJob','versionChangelog','versionNotes','versionPackageName','versionMinSdk','versionBundleId','versionMinIosVersion'].forEach(function(id){ var e=document.getElementById(id); if(e) e.value=e.type==='textarea' ? '' : (id==='versionChannel' ? defCh : (id==='versionStage' ? defSt : (id==='versionPlatform' ? 'android' : (id==='versionStatus' ? 'active' : '')))); }); var distributionEl=document.getElementById('versionDistributionMethod'); if(distributionEl) distributionEl.value='direct'; var rec=document.getElementById('versionChangelogRecommended'); if(rec) rec.checked=false; syncVersionPlatformFields(); suggestVersionApkPath(); syncDerivedVersionPaths(); switchVersionModalTab('identity'); document.getElementById('versionModal').classList.remove('hidden'); ensureUnityVersionSelect(''); }
function closeVersionModal(){ document.getElementById('versionModal').classList.add('hidden'); }
function getActiveStageId(){
    var stageBtn=document.querySelector('.channel-stage-tab.bg-white');
    return (stageBtn&&stageBtn.getAttribute('data-stage'))||'dev';
}
function versionCodesInGroup(versionName){
    var vn=(versionName||'').trim();
    return allVersions.filter(function(x){ return (x.version_name||'').trim()===vn; });
}
function versionCodesInGroupForContext(versionName){
    var vn=(versionName||'').trim();
    var cid=String(window._activeChannelId||'').toLowerCase();
    var sid=getActiveStageId();
    return versionCodesInGroup(vn).filter(function(v){
        return String(v.channel||'').toLowerCase()===cid && (v.stage||'dev')===sid;
    });
}
function pickVersionGroupTemplate(versionName){
    var inCtx=versionCodesInGroupForContext(versionName);
    if(inCtx.length) return inCtx[0];
    var cid=String(window._activeChannelId||'').toLowerCase();
    var anyChannel=versionCodesInGroup(versionName).filter(function(v){
        return String(v.channel||'').toLowerCase()===cid;
    });
    if(anyChannel.length) return anyChannel[0];
    var all=versionCodesInGroup(versionName);
    return all.length?all[0]:null;
}
function enrichVersionRow(v){
    v.stage=v.stage||'dev';
    var st=(VERSION_STAGES||[]).find(function(s){ return (s.id||'')===v.stage; });
    v.stage_label=v.stage_label||(st&&st.name)||v.stage;
    var ch=(PROJECT_CHANNELS||[]).find(function(c){ return String(c.id||'')===String(v.channel||''); });
    if(!ch&&CHANNELS_FULL&&CHANNELS_FULL[v.channel]) ch={id:v.channel,name:CHANNELS_FULL[v.channel].name||v.channel};
    v.channel_label=v.channel_label||(ch&&ch.name)||v.channel;
    return v;
}
function reloadProjectVersions(){
    return fetch('/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/list', {credentials:'same-origin'})
        .then(function(r){ return r.json(); })
        .then(function(d){
            if(!d||!d.versions) return;
            allVersions=(d.versions||[]).map(enrichVersionRow);
        });
}
function hasDuplicateVersionCode(versionName, versionCode, excludeId){
    var vc=String(versionCode||'').trim();
    if(!vc) return false;
    return versionCodesInGroup(versionName).some(function(x){
        if(excludeId&&(x.id||'')===excludeId) return false;
        return String(x.version_code||'').trim()===vc;
    });
}
function suggestNextVersionCode(versionName){
    var maxN=0;
    versionCodesInGroupForContext(versionName).forEach(function(x){
        var n=parseInt(String(x.version_code||'').trim(),10);
        if(!isNaN(n)&&n>maxN) maxN=n;
    });
    return String(maxN+1);
}
function openVersionCodeModal(id){
    var v=allVersions.find(function(x){ return (x.id||'')===id; });
    if(!v) return;
    var codeEl=document.getElementById('versionCodeEditValue');
    var statusEl=document.getElementById('versionCodeEditStatus');
    var changeEl=document.getElementById('versionCodeEditChangelog');
    document.getElementById('versionCodeEditId').value=v.id||'';
    document.getElementById('versionCodeEditMode').value='edit';
    document.getElementById('versionCodeCloneFromId').value='';
    var titleEl=document.getElementById('versionCodeModalTitle');
    if(titleEl) titleEl.textContent='编辑 VersionCode';
    document.getElementById('versionCodeEditVersionName').textContent='Version: '+(v.version_name||'-');
    if(codeEl) codeEl.value=v.version_code||'';
    if(statusEl) statusEl.value=normalizeVersionStatus(v.version_status||'active');
    if(changeEl) changeEl.value=v.changelog_text||'';
    document.getElementById('versionCodeModal').classList.remove('hidden');
}
function openAddVersionCodeModal(versionName){
    var template=pickVersionGroupTemplate(versionName);
    if(!template){ alert('未找到该版本组，请先在当前渠道/阶段创建至少一个版本'); return; }
    var stageLabel=template.stage_label||template.stage||'dev';
    var chLabel=template.channel_label||template.channel||'';
    document.getElementById('versionCodeEditId').value='';
    document.getElementById('versionCodeEditMode').value='add';
    document.getElementById('versionCodeCloneFromId').value=template.id||'';
    var titleEl=document.getElementById('versionCodeModalTitle');
    if(titleEl) titleEl.textContent='新增 VersionCode';
    document.getElementById('versionCodeEditVersionName').textContent='Version: '+(versionName||'-')+' · 将添加到「'+chLabel+' / '+stageLabel+'」';
    var codeEl=document.getElementById('versionCodeEditValue');
    var statusEl=document.getElementById('versionCodeEditStatus');
    var changeEl=document.getElementById('versionCodeEditChangelog');
    if(codeEl) codeEl.value=suggestNextVersionCode(versionName);
    if(statusEl) statusEl.value='active';
    if(changeEl) changeEl.value='';
    document.getElementById('versionCodeModal').classList.remove('hidden');
}
function closeVersionCodeModal(){ document.getElementById('versionCodeModal').classList.add('hidden'); }
function saveVersionCodeModal(){
    var mode=((document.getElementById('versionCodeEditMode')||{}).value||'edit').trim();
    var versionCode=((document.getElementById('versionCodeEditValue')||{}).value||'').trim();
    if(!versionCode){ alert('Version Code 不能为空'); return; }
    var versionStatus=normalizeVersionStatus(((document.getElementById('versionCodeEditStatus')||{}).value||'active'));
    var changelog=((document.getElementById('versionCodeEditChangelog')||{}).value||'').trim();
    if(mode==='add'){
        var cloneId=((document.getElementById('versionCodeCloneFromId')||{}).value||'').trim();
        var template=allVersions.find(function(x){ return (x.id||'')===cloneId; });
        if(!template){ alert('模板版本不存在'); return; }
        var vn=(template.version_name||'').trim();
        if(hasDuplicateVersionCode(vn, versionCode, '')){
            alert('版本 '+vn+' 下已存在 Version Code「'+versionCode+'」，请修改后再保存');
            return;
        }
        var payload={
            channel:template.channel||'',
            stage:template.stage||'dev',
            platform:template.platform||'android',
            version_status:versionStatus,
            version_name:vn,
            version_mode:template.version_mode||'general',
            version_code:versionCode,
            distribution_method:template.distribution_method||'',
            package_name:template.package_name||'',
            min_sdk:template.min_sdk||'',
            bundle_id:template.bundle_id||'',
            min_ios_version:template.min_ios_version||'',
            apk_path:template.apk_path||'',
            resource_path:template.resource_path||'',
            config_path:template.config_path||'',
            jenkins_job_id:template.jenkins_job_id||'',
            changelog:changelog,
            changelog_recommended:false,
            notes:template.notes||''
        };
        if((template.version_mode||'general')==='commercial'&&template.pipeline){
            try{ payload.pipeline=JSON.parse(JSON.stringify(template.pipeline)); }catch(e){ payload.pipeline=template.pipeline; }
        }
        fetch('/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/create', {
            method:'POST',
            headers:{ 'Content-Type':'application/json' },
            body:JSON.stringify(payload),
            credentials:'same-origin'
        }).then(function(r){ return r.json(); }).then(function(d){
            if(d.error){ alert(d.error); return; }
            reloadProjectVersions().then(function(){
                closeVersionCodeModal();
                renderChannelsView();
            });
        });
        return;
    }
    var id=(document.getElementById('versionCodeEditId')||{}).value||'';
    var v=allVersions.find(function(x){ return (x.id||'')===id; });
    if(!v){ alert('版本不存在'); return; }
    var vn=(v.version_name||'').trim();
    if(hasDuplicateVersionCode(vn, versionCode, id)){
        alert('版本 '+vn+' 下已存在 Version Code「'+versionCode+'」，无法保存');
        return;
    }
    var payload={
        id:v.id||'',
        channel:v.channel||'',
        stage:v.stage||'dev',
        platform:v.platform||'android',
        version_status:versionStatus,
        version_name:vn,
        version_mode:v.version_mode||'general',
        version_code:versionCode,
        distribution_method:v.distribution_method||'',
        package_name:v.package_name||'',
        min_sdk:v.min_sdk||'',
        bundle_id:v.bundle_id||'',
        min_ios_version:v.min_ios_version||'',
        apk_path:v.apk_path||'',
        resource_path:v.resource_path||'',
        config_path:v.config_path||'',
        jenkins_job_id:v.jenkins_job_id||'',
        changelog:changelog,
        changelog_recommended:!!v.changelog_recommended,
        notes:v.notes||''
    };
    payload.edit_scope='version_code';
    if((v.version_mode||'general')==='commercial'){ payload.pipeline=v.pipeline||{}; }
    fetch('/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/update', {
        method:'POST',
        headers:{ 'Content-Type':'application/json' },
        body:JSON.stringify(payload),
        credentials:'same-origin'
    }).then(function(r){ return r.json(); }).then(function(d){
        if(d.error){ alert(d.error); return; }
        reloadProjectVersions().then(function(){
            closeVersionCodeModal();
            renderChannelsView();
        });
    });
}

function editVersion(id){ var v=allVersions.find(function(x){ return (x.id||'')===id; }); if(!v) return; document.getElementById('versionModalTitle').textContent='编辑版本'; document.getElementById('versionEditId').value=v.id||''; var vm = v.version_mode || 'general'; document.getElementById('chkCommercialMode').checked = (vm==='commercial'); toggleCommercialMode(); document.getElementById('versionChannel').value=v.channel||'dev'; var stageEl=document.getElementById('versionStage'); if(stageEl) stageEl.value=v.stage||'dev'; var platformEl=document.getElementById('versionPlatform'); if(platformEl) platformEl.value=v.platform||'android'; var statusEl=document.getElementById('versionStatus'); if(statusEl) statusEl.value=normalizeVersionStatus(v.version_status||'active'); document.getElementById('versionName').value=v.version_name||''; document.getElementById('versionApkPath').value=v.apk_path||''; document.getElementById('versionResourcePath').value=v.resource_path||''; document.getElementById('versionConfigPath').value=v.config_path||''; document.getElementById('versionJenkinsJob').value=v.jenkins_job_id||''; document.getElementById('versionChangelog').value=v.changelog_text||''; document.getElementById('versionChangelogRecommended').checked=!!v.changelog_recommended; document.getElementById('versionNotes').value=v.notes||''; var distributionEl=document.getElementById('versionDistributionMethod'); if(distributionEl) distributionEl.value=v.distribution_method||''; var packageNameEl=document.getElementById('versionPackageName'); if(packageNameEl) packageNameEl.value=v.package_name||''; var minSdkEl=document.getElementById('versionMinSdk'); if(minSdkEl) minSdkEl.value=v.min_sdk||''; var bundleIdEl=document.getElementById('versionBundleId'); if(bundleIdEl) bundleIdEl.value=v.bundle_id||''; var minIosEl=document.getElementById('versionMinIosVersion'); if(minIosEl) minIosEl.value=v.min_ios_version||''; // 商业级参数回填
    var pipeline=v.pipeline||{}; if(pipeline) restorePipeline(pipeline);
    var savedUnity=(pipeline.apk_build&&pipeline.apk_build.unity_version)||'';
    syncVersionPlatformFields(); suggestVersionApkPath(); syncDerivedVersionPaths(v.version_code||''); switchVersionModalTab('identity'); document.getElementById('versionModal').classList.remove('hidden'); ensureUnityVersionSelect(savedUnity); }

function deleteVersion(id){ if(!requireDeleteConfirm('VersionCode: '+id)) return; fetch('/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/delete/'+encodeURIComponent(id), { method: 'DELETE', credentials: 'same-origin' }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); return; } allVersions = allVersions.filter(function(x){ return (x.id||'')!==id; }); renderChannelsView(); }); }

function saveVersion(){ var id=document.getElementById('versionEditId').value; var current=id?allVersions.find(function(x){ return (x.id||'')===id; }):null; var ch=document.getElementById('versionChannel').value; var stageEl=document.getElementById('versionStage'); var stageVal=stageEl?stageEl.value:'dev'; var platform=document.getElementById('versionPlatform').value||'android'; var versionStatus=normalizeVersionStatus((document.getElementById('versionStatus')||{}).value||'active'); var vn=document.getElementById('versionName').value.trim()||'1.0.0'; var apkPath=document.getElementById('versionApkPath').value.trim(); if(!apkPath){ var info=CHANNELS_FULL&&CHANNELS_FULL[ch]; var sd=STAGE_DIR_MAP[stageVal]||'dev'; var ext=platform==='ios'?'.ipa':'.apk'; var an=PROJECT_ID+'_'+vn.replace(new RegExp("\\\\s","g"),"")+ext; apkPath=(info&&info.apk_subdir)?(info.apk_subdir+'/'+sd+'/'+an):(sd+'/'+an); } var fixedVersionCode=(current&&current.version_code)?String(current.version_code).trim():''; syncDerivedVersionPaths(fixedVersionCode); var payload={ channel: ch, stage: stageVal, platform: platform, version_status: versionStatus, version_name: vn, version_mode: _versionMode, version_code: fixedVersionCode, distribution_method: (document.getElementById('versionDistributionMethod')||{}).value||'', package_name: (document.getElementById('versionPackageName')||{}).value||'', min_sdk: (document.getElementById('versionMinSdk')||{}).value||'', bundle_id: (document.getElementById('versionBundleId')||{}).value||'', min_ios_version: (document.getElementById('versionMinIosVersion')||{}).value||'', apk_path: apkPath, resource_path: document.getElementById('versionResourcePath').value.trim(), config_path: document.getElementById('versionConfigPath').value.trim(), jenkins_job_id: document.getElementById('versionJenkinsJob').value.trim(), changelog: document.getElementById('versionChangelog').value.trim(), changelog_recommended: !!document.getElementById('versionChangelogRecommended').checked, notes: document.getElementById('versionNotes').value.trim(), edit_scope:'version_group' }; if(_versionMode==='commercial'){ payload.pipeline=collectPipeline(); var err=validateCommercialPipeline(payload.pipeline); if(err){ alert(err); return; } } var url='/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/create'; var method='POST'; if(id){ payload.id=id; url='/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/update'; } fetch(url, { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), credentials: 'same-origin' }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); return; } if(d.version){ var chOpt=document.getElementById('versionChannel'); d.version.channel_label=chOpt&&chOpt.options[chOpt.selectedIndex]?chOpt.options[chOpt.selectedIndex].text:d.version.channel; d.version.stage=stageVal; d.version.stage_label=(stageEl&&stageEl.options[stageEl.selectedIndex]?stageEl.options[stageEl.selectedIndex].text:'开发'); d.version.platform=platform; d.version.platform_label=platform==='ios'?'iOS':'Android'; d.version.version_status=versionStatus; d.version.version_mode=_versionMode; d.version.commercial_release=payload.commercial_release||null; d.version.distribution_method=payload.distribution_method || (platform==='ios'?'testflight':'direct'); d.version.package_name=payload.package_name; d.version.min_sdk=payload.min_sdk; d.version.bundle_id=payload.bundle_id; d.version.min_ios_version=payload.min_ios_version; d.version.changelog_text=payload.changelog; d.version.changelog_recommended=payload.changelog_recommended; var idx=allVersions.findIndex(function(x){ return (x.id||'')===(d.version.id||''); }); if(idx>=0) allVersions[idx]=d.version; else allVersions.push(d.version); } closeVersionModal(); renderChannelsView(); }); }

renderChannelsView();
refreshVersionBuildState();
ensureVersionBuildStateTimer();
syncVersionPlatformFields();
fetchUnityVersionCatalog(function(){ renderUnityVersionSelect(''); });
</script>
'''



@bp.route('/admin/projects/<project_id>/workspace')
@admin_required('projects')
def admin_project_workspace(project_id):
    username = _current_username()
    pid = resolve_project_id((project_id or '').strip()) or ''
    if not pid or not can_view_project(pid, username):
        return _admin_layout('<div class=\"rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-700\">无权限或项目不存在</div>', '项目工作台')

    p = projects_db.get(pid) or {}
    project_name = _clean_display_text(p.get('name'), pid)
    links = [
        ('构建与流水线', f'/admin/build?project_id={pid}', 'fa-cogs', 'text-orange-500', '项目专属构建任务、Jenkins 导出与产物链路。'),
        ('版本与发布', f'/admin/projects/{pid}/versions', 'fa-code-branch', 'text-teal-500', '项目版本、发布单、回滚与对账。'),
        ('GM运营中心', f'/admin/gm-ops?project_id={pid}', 'fa-sitemap', 'text-cyan-500', '项目专属 GM、运维、运营与参数闭环。'),
        ('后端运维', f'/admin/gm-ops?project_id={pid}#ops', 'fa-server', 'text-indigo-500', '开停服、维护、限流、健康与存储指标。'),
        ('观测与审计', f'/admin/audit-log?project_id={pid}', 'fa-history', 'text-gray-500', '项目级操作审计、风险追踪与回放。'),
        ('项目设置', f'/admin/projects/{pid}', 'fa-sliders-h', 'text-slate-500', '基础信息、渠道、凭据与默认策略。'),
    ]
    cards = ''.join(_render_module_card(link, icon, color, title, desc) for title, link, icon, color, desc in links)
    content = f'''<section class="space-y-5"><div class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"><p class="text-[11px] font-semibold tracking-[0.16em] uppercase text-slate-500">Project Workspace</p><h2 class="mt-1 text-xl font-semibold text-slate-900">{html.escape(project_name)} · 项目工作台</h2><p class="mt-1 text-sm text-slate-500">所有构建、发布、GM、运维动作均在项目上下文内执行，避免跨项目误操作。</p></div><div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">{cards}</div></section>'''
    return _admin_layout(content, '项目工作台', back_href='/admin')
@bp.route('/admin/projects/<project_id>')
@admin_required('projects')
def project_detail_page(project_id):
    """项目详情页：商业级仪表盘、版本管理、任务与构建入口"""
    if project_id not in projects_db:
        abort(404)
    if not can_view_project(project_id, _current_username()):
        abort(403)
    proj = projects_db[project_id]
    can_edit = can_edit_project(project_id, _current_username())
    is_admin_logged_in = can_edit  # 有编辑权限即可管理模块
    # 任务统计
    tasks = (project_tasks_db.get(project_id) or [])
    task_stats = {'total': len(tasks), 'in_progress': 0, 'pending_review': 0, 'done': 0}
    for t in tasks:
        s = t.get('status', '')
        if s == 'in_progress':
            task_stats['in_progress'] += 1
        elif s == 'pending_review':
            task_stats['pending_review'] += 1
        elif s == 'done' or s == 'review_passed':
            task_stats['done'] += 1
    # 最近任务（按 updated_at 或 created_at 排序）
    recent_tasks = sorted(tasks, key=lambda x: (x.get('updated_at') or x.get('created_at') or ''), reverse=True)[:8]
    apk_count = get_project_apk_count(project_id)
    project_apk_files = []
    if os.path.exists(Config.APK_DIR):
        for fn, path in iter_package_files():
            if extract_project_name(fn) == project_id:
                info = extract_package_info(fn, path)
                info['download_count'] = download_stats.get(fn, download_stats.get(os.path.basename(fn), 0))
                project_apk_files.append(info)
    project_apk_files.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    content = _project_detail_html(project_id, proj, can_edit, task_stats, recent_tasks, apk_count, project_apk_files, is_admin_logged_in)
    return _admin_layout(content, '项目工作台', back_href='/admin/projects')


@bp.route('/api/admin/unity-versions/detect')
@admin_required_any('projects', 'jenkins')
def api_admin_detect_unity_versions():
    """兼容旧接口：返回版本库中有效项（version/path/category/note）。"""
    from services.unity_version_catalog_service import list_active_for_selectors
    versions = list_active_for_selectors()
    return jsonify({'success': True, 'versions': versions})


@bp.route('/admin/projects/<project_id>/versions')
@admin_required('projects')
def project_versions_page(project_id):
    """项目内版本管理独立页（复用完整版本管理逻辑）。"""
    if project_id not in projects_db:
        abort(404)
    if not can_view_project(project_id, _current_username()):
        abort(403)
    proj = projects_db[project_id]
    can_edit = can_edit_project(project_id, _current_username())
    is_admin_logged_in = can_edit
    tasks = (project_tasks_db.get(project_id) or [])
    task_stats = {'total': len(tasks), 'in_progress': 0, 'pending_review': 0, 'done': 0}
    for t in tasks:
        s = t.get('status', '')
        if s == 'in_progress':
            task_stats['in_progress'] += 1
        elif s == 'pending_review':
            task_stats['pending_review'] += 1
        elif s == 'done' or s == 'review_passed':
            task_stats['done'] += 1
    recent_tasks = sorted(tasks, key=lambda x: (x.get('updated_at') or x.get('created_at') or ''), reverse=True)[:8]
    apk_count = get_project_apk_count(project_id)
    project_apk_files = []
    if os.path.exists(Config.APK_DIR):
        for fn, path in iter_package_files():
            if extract_project_name(fn) == project_id:
                info = extract_package_info(fn, path)
                info['download_count'] = download_stats.get(fn, download_stats.get(os.path.basename(fn), 0))
                project_apk_files.append(info)
    project_apk_files.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

    content = _project_detail_html(project_id, proj, can_edit, task_stats, recent_tasks, apk_count, project_apk_files, is_admin_logged_in)
    # 独立页仅保留版本面板，其它内容隐藏；仍复用完整版本管理脚本与弹窗能力。
    content += '''
    <style>
      .project-version-standalone .tab-btn:not(#tabChannels){ display:none !important; }
      .project-version-standalone #tabChannels{ margin-left:0 !important; }
      .project-version-standalone #panelOverview,
      .project-version-standalone #panelBuild,
      .project-version-standalone #panelDownload{ display:none !important; }
      .project-version-standalone .bg-gradient-to-r.from-slate-900.via-slate-800.to-indigo-700,
      .project-version-standalone .grid.grid-cols-2.md\\:grid-cols-7.gap-4.mb-6,
      .project-version-standalone .grid.grid-cols-1.lg\\:grid-cols-3.gap-6{ display:none !important; }
    </style>
    <script>
      (function(){
        try{
          document.body.classList.add('project-version-standalone');
          if(window.switchTab){ window.switchTab('channels'); }
          var title = document.querySelector('h2.text-2xl.font-semibold.text-white');
          if(title){ title.textContent = '项目版本管理'; }
        }catch(e){ console.warn(e); }
      })();
    </script>
    '''
    return _admin_layout(content, '项目版本管理', back_href=f'/admin/projects/{project_id}')


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


def _normalize_distribution_method(platform, distribution_method):
    method = (distribution_method or '').strip().lower()
    allowed = {'direct', 'enterprise', 'store', 'testflight', 'internal'}
    if method in allowed:
        return method
    return 'testflight' if platform == 'ios' else 'direct'


def _clean_version_platform_fields(data, platform, current=None):
    current = current or {}
    cleaned = {
        'distribution_method': _normalize_distribution_method(platform, data.get('distribution_method') or current.get('distribution_method')),
        'package_name': '',
        'min_sdk': '',
        'bundle_id': '',
        'min_ios_version': '',
    }
    if platform == 'ios':
        cleaned['bundle_id'] = (data.get('bundle_id') or current.get('bundle_id') or '').strip()
        cleaned['min_ios_version'] = (data.get('min_ios_version') or current.get('min_ios_version') or '').strip()
    else:
        cleaned['package_name'] = (data.get('package_name') or current.get('package_name') or '').strip()
        cleaned['min_sdk'] = (data.get('min_sdk') or current.get('min_sdk') or '').strip()
    return cleaned


def _validate_version_payload(platform, version):
    apk_path = (version.get('apk_path') or '').strip()
    package_name = (version.get('package_name') or '').strip()
    min_sdk = (version.get('min_sdk') or '').strip()
    bundle_id = (version.get('bundle_id') or '').strip()
    min_ios_version = (version.get('min_ios_version') or '').strip()
    if platform == 'ios':
        if apk_path and not apk_path.lower().endswith('.ipa'):
            return 'iOS 版本的安装包路径必须以 .ipa 结尾'
        if bundle_id and not re.match(r'^[A-Za-z0-9]+(\.[A-Za-z0-9_-]+)+$', bundle_id):
            return 'Bundle ID 格式不正确'
        if min_ios_version and not re.match(r'^\d+(\.\d+){0,2}$', min_ios_version):
            return '最低 iOS 版本格式应为 16 或 16.4'
    else:
        if apk_path and not apk_path.lower().endswith('.apk'):
            return 'Android 版本的安装包路径必须以 .apk 结尾'
        if package_name and not re.match(r'^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$', package_name):
            return 'Android 包名格式不正确'
        if min_sdk and not re.match(r'^\d{1,2}$', min_sdk):
            return '最低 Android SDK 应为数字'
    return None


def _is_task_in_date(task, d):
    """任务是否在日期 d 当天（开始或结束在该日）。"""
    st = _parse_task_date(task, 'start_time')
    et = _parse_task_date(task, 'end_time')
    return st == d or et == d


def _task_in_range(task, start_d, end_d):
    """任务开始或结束是否在 [start_d, end_d] 内。"""
    st = _parse_task_date(task, 'start_time')
    et = _parse_task_date(task, 'end_time')
    for d in (st, et):
        if d and start_d <= d <= end_d:
            return True
    return False


@bp.route('/admin/my-tasks')
@admin_required('projects')
def my_tasks_page():
    """跨项目汇总：当前用户作为当前负责人的任务。"""
    username = _current_username()
    my_tasks = []
    for pid, proj in projects_db.items():
        if not can_view_project(pid, username):
            continue
        for t in (project_tasks_db.get(pid) or []):
            cur = t.get('current_assignee') or (_role_to_first_assignee(pid, t.get('current_role')) if t.get('current_role') else '')
            if cur == username:
                task = dict(t, project_id=pid, project_name=proj.get('name', pid))
                if task.get('urgency') is None or not (1 <= int(task.get('urgency', 1)) <= 5):
                    task['urgency'] = 1
                my_tasks.append(task)
    projects_for_filter = []
    seen_pid = set()
    for t in my_tasks:
        pid = t.get('project_id')
        if pid and pid not in seen_pid:
            seen_pid.add(pid)
            projects_for_filter.append({'id': pid, 'name': t.get('project_name', pid)})
    project_filter = request.args.get('project', '')
    urgency_filter = request.args.get('urgency', '')
    status_filter = request.args.get('status', '')
    overdue_filter = request.args.get('overdue', '')
    quick_filter = request.args.get('quick', '').strip()
    if quick_filter:
        if quick_filter == 'doing':
            my_tasks = [t for t in my_tasks if t.get('status') in ('not_started', 'in_progress')]
        elif quick_filter == 'review':
            my_tasks = [t for t in my_tasks if t.get('status') == 'pending_review']
        elif quick_filter == 'overdue':
            overdue_filter = 'overdue'
        elif quick_filter == 'soon':
            overdue_filter = 'soon'
    if project_filter:
        my_tasks = [t for t in my_tasks if t.get('project_id') == project_filter]
    if urgency_filter:
        try:
            u = int(urgency_filter)
            if 1 <= u <= 5:
                my_tasks = [t for t in my_tasks if (int(t.get('urgency', 1)) or 1) == u]
        except ValueError:
            pass
    if status_filter:
        my_tasks = [t for t in my_tasks if t.get('status') == status_filter]
    from datetime import date, timedelta
    view_range = request.args.get('view', '')  # today | week | all
    _today = date.today()
    soon_count = sum(1 for t in my_tasks if _task_row_bg_and_progress(t)[1] == '即将超时')
    overdue_count = sum(1 for t in my_tasks if _task_row_bg_and_progress(t)[1] in ('超时', '严重超时'))
    if view_range == 'today':
        my_tasks = [t for t in my_tasks if _is_task_in_date(t, _today)]
    elif view_range == 'week':
        week_end = _today + timedelta(days=6 - _today.weekday())
        week_start = week_end - timedelta(days=6)
        my_tasks = [t for t in my_tasks if _task_in_range(t, week_start, week_end)]
    plan_filter = request.args.get('plan', '').strip()
    for t in my_tasks:
        t['user_plan'] = get_task_plan(username, t.get('project_id'), t.get('id'))
    if plan_filter == '__none__':
        my_tasks = [t for t in my_tasks if not t.get('user_plan')]
    elif plan_filter and plan_filter in ('today_todo', 'today_done', 'tomorrow_plan', 'backlog'):
        my_tasks = [t for t in my_tasks if t.get('user_plan') == plan_filter]
    if overdue_filter and overdue_filter in ('normal', 'soon', 'overdue'):
        today = _today
        in3 = today + timedelta(days=3)
        def _end_date(t):
            et = t.get('end_time') or ''
            if not et or len(et) < 10:
                return None
            try:
                return date(int(et[:4]), int(et[5:7]), int(et[8:10]))
            except Exception:
                return None
        def _keep_overdue(t):
            if t.get('status') in ('done', 'abandoned'):
                return True
            ed = _end_date(t)
            if not ed:
                return overdue_filter == 'normal'
            if overdue_filter == 'normal':
                return ed >= today and (ed - today).days > 3
            if overdue_filter == 'soon':
                return ed >= today and (ed - today).days <= 3
            return ed < today
        my_tasks = [t for t in my_tasks if _keep_overdue(t)]
    sort_by = (request.args.get('sort') or 'remaining').strip()
    sort2 = (request.args.get('sort2') or '').strip()
    def _end_tuple(x):
        return (x.get('end_time') or '', x.get('created_at') or '')
    def _prim(x):
        if sort_by == 'status': return (x.get('status') or '',)
        if sort_by == 'urgency': return (-(int(x.get('urgency', 1)) or 1),)
        if sort_by == 'start_time': return (x.get('start_time') or '',)
        if sort_by == 'role': return (x.get('current_assignee') or '',)
        return _end_tuple(x)
    def _sec(x):
        if sort2 == 'status': return (x.get('status') or '',)
        if sort2 == 'urgency': return (-(int(x.get('urgency', 1)) or 1),)
        if sort2 == 'start_time': return (x.get('start_time') or '',)
        if sort2 == 'role': return (x.get('current_assignee') or '',)
        if sort2 == 'remaining': return _end_tuple(x)
        return ()
    def _tid(x):
        return (x.get('id') or '',)
    my_tasks.sort(key=lambda x: _prim(x) + _sec(x) + _end_tuple(x) + _tid(x))
    content = _my_tasks_html(my_tasks, sort_by, sort2, project_filter, urgency_filter, status_filter, overdue_filter, projects_for_filter, view_range, soon_count, overdue_count, plan_filter, quick_filter)
    return _admin_layout(content, '我的任务', back_href='/admin')


def _task_row_bg_and_progress(task):
    """Return (tr_bg_class, progress_label or '') for status/urgency row styling. progress_label only for in_progress."""
    from datetime import date
    status = task.get('status') or 'not_started'
    status_bg = {
        'abandoned': 'bg-gray-100',
        'not_started': 'bg-slate-50',
        'in_progress': 'bg-blue-50',
        'pending_review': 'bg-violet-50',
        'review_passed': 'bg-green-50',
        'review_failed': 'bg-orange-50',
    }
    bg = status_bg.get(status, 'bg-white')
    progress_label = ''
    if status == 'in_progress' and task.get('end_time'):
        try:
            end_d = date.fromisoformat((task.get('end_time') or '')[:10])
            today = date.today()
            if end_d < today:
                delta = (today - end_d).days
                if delta >= 7:
                    bg, progress_label = 'bg-red-200', '严重超时'
                else:
                    bg, progress_label = 'bg-red-50', '超时'
            else:
                delta = (end_d - today).days
                if delta <= 3:
                    bg, progress_label = 'bg-amber-50', '即将超时'
                else:
                    bg, progress_label = 'bg-emerald-50', '正常'
        except Exception:
            bg, progress_label = status_bg.get(status, 'bg-blue-50'), '正常'
    elif status != 'in_progress':
        bg = status_bg.get(status, 'bg-white')
    return bg, progress_label


PLAN_LABELS = {'today_todo': '今日代办', 'today_done': '今日完成', 'tomorrow_plan': '明日计划', 'backlog': '之前代办'}


def _my_tasks_html(tasks, sort_by='remaining', sort2='', project_filter='', urgency_filter='', status_filter='', overdue_filter='', projects_for_filter=None, view_range='', soon_count=0, overdue_count=0, plan_filter='', quick_filter=''):
    import html
    from urllib.parse import urlencode
    projects_for_filter = projects_for_filter or []
    status_labels = dict(TASK_STATUSES)
    status_badge_cls = {
        'abandoned': 'bg-gray-200 text-gray-600',
        'not_started': 'bg-slate-100 text-slate-600',
        'in_progress': 'bg-blue-100 text-blue-700',
        'pending_review': 'bg-violet-100 text-violet-700',
        'review_passed': 'bg-green-100 text-green-700',
        'review_failed': 'bg-orange-100 text-orange-700',
        'done': 'bg-emerald-100 text-emerald-700',
    }
    def urgency_stars(u):
        u = 1 if u is None else max(1, min(5, int(u)))
        return ('🌟' * u) + ('☆' * (5 - u))
    def qs(extra):
        p = {'sort': sort_by}
        if sort2:
            p['sort2'] = sort2
        if project_filter:
            p['project'] = project_filter
        if urgency_filter:
            p['urgency'] = urgency_filter
        if status_filter:
            p['status'] = status_filter
        if overdue_filter:
            p['overdue'] = overdue_filter
        if view_range:
            p['view'] = view_range
        if plan_filter:
            p['plan'] = plan_filter
        if quick_filter:
            p['quick'] = quick_filter
        p.update(extra)
        return urlencode(p)
    rows = []
    for t in tasks:
        row_bg, progress_label = _task_row_bg_and_progress(t)
        status_text = status_labels.get(t.get('status', ''), t.get('status', ''))
        if progress_label:
            status_text += ' · ' + progress_label
        overdue_badge = ''
        if progress_label == '超时' or progress_label == '严重超时':
            overdue_badge = ' <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-red-600 text-white uppercase">' + ('严重超时' if progress_label == '严重超时' else '已超时') + '</span>'
        elif progress_label == '即将超时':
            overdue_badge = ' <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-amber-500 text-white">即将超时</span>'
        elif progress_label == '正常' and t.get('status') == 'in_progress':
            overdue_badge = ' <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-500 text-white">正常</span>'
        tr_extra = ' border-l-4 border-l-red-600' if progress_label in ('超时', '严重超时') else (' border-l-4 border-l-amber-500' if progress_label == '即将超时' else '')
        comments = t.get('comments') or []
        last_comment = comments[-1] if comments else None
        comment_summary = str(len(comments)) + '条评论'
        if last_comment:
            content_preview = (last_comment.get('content') or '')[:8]
            if len(last_comment.get('content') or '') > 8:
                content_preview += '…'
            comment_summary += ' 最后: ' + html.escape(last_comment.get('user') or '') + ' ' + html.escape(content_preview)
        up = t.get('user_plan') or ''
        plan_opts = ''.join(
            '<option value="%s"%s>%s</option>' % (k, ' selected' if up == k else '', v)
            for k, v in PLAN_LABELS.items()
        ) + '<option value=""' + (' selected' if not up else '') + '>未规划</option>'
        plan_sel = '<select class="task-plan-sel text-xs border rounded px-1 py-0.5" data-pid="%s" data-tid="%s" data-current="%s">%s</select>' % (html.escape(t.get('project_id', '')), html.escape(t.get('id', '')), html.escape(up or ''), plan_opts)
        sbadge = status_badge_cls.get(t.get('status', ''), 'bg-slate-100 text-slate-700')
        row_fmt = '<tr class="border-b border-gray-100 transition ' + row_bg + tr_extra + '"><td class="px-4 py-3 text-sm text-gray-800">{0}</td><td class="px-4 py-3 font-medium text-gray-900">{1}</td><td class="px-4 py-3 text-amber-500" title="紧急程度">{2}</td><td class="px-4 py-3 text-sm text-gray-600">{3}</td><td class="px-4 py-3"><span class="inline-flex px-2 py-0.5 rounded text-xs font-medium ' + sbadge + '">{4}</span>{5}</td><td class="px-4 py-3 text-sm text-gray-500">{6} ~ {7}</td><td class="px-4 py-3"><span class="mr-2">{8}</span><a href="/admin/projects/{9}/tasks" class="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 transition mr-2">进入项目</a><button type="button" class="my-task-edit-btn inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 transition" data-project-id="{10}" data-task-id="{11}">编辑任务</button><span class="text-xs text-gray-500 block mt-1">{12}</span></td></tr>'
        rows.append(row_fmt.format(
            html.escape(t.get('project_name', '')),
            html.escape(t.get('title', '')),
            urgency_stars(t.get('urgency', 1)),
            html.escape(t.get('current_assignee', t.get('current_role', ''))),
            html.escape(status_text),
            overdue_badge,
            (t.get('start_time') or '')[:10],
            (t.get('end_time') or '')[:10],
            plan_sel,
            html.escape(t.get('project_id', '')),
            html.escape(t.get('project_id', '')),
            html.escape(t.get('id', '')),
            comment_summary,
        ))
    empty_html = '<tr><td colspan="7" class="px-4 py-16 text-center"><div class="max-w-sm mx-auto"><div class="text-5xl text-slate-300 mb-4"><i class="fas fa-clipboard-list"></i></div><p class="text-gray-600 font-medium mb-1">暂无符合条件的任务</p><p class="text-sm text-gray-400 mb-4">您负责的任务会在此展示。试试切换筛选条件，或前往项目管理查看任务。</p><a href="/admin/projects" class="inline-flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 transition"><i class="fas fa-folder-open"></i>进入项目管理</a></div></td></tr>'
    rows_html = ''.join(rows) if rows else empty_html
    sort_links = []
    for val, label in [('remaining', '剩余时间'), ('status', '状态'), ('urgency', '紧急程度'), ('start_time', '开始时间'), ('role', '负责人')]:
        cls = 'font-medium text-indigo-600' if sort_by == val else 'text-gray-600 hover:text-indigo-600'
        sort_links.append('<a href="/admin/my-tasks?' + qs({'sort': val}) + '" class="' + cls + ' text-sm">' + label + '</a>')
    sort_bar = '首要：' + (' | '.join(sort_links))
    sort2_opts = '<option value="">无</option>' + ''.join(
        '<option value="%s"%s>%s</option>' % (v, ' selected' if sort2 == v else '', l)
        for v, l in [('remaining', '剩余时间'), ('status', '状态'), ('urgency', '紧急程度'), ('start_time', '开始时间'), ('role', '负责人')]
    )
    sort_bar += ' &nbsp; 次要：<form method="get" action="/admin/my-tasks" class="inline-flex items-center gap-1 ml-2"><input type="hidden" name="sort" value="' + html.escape(sort_by) + '"><input type="hidden" name="project" value="' + html.escape(project_filter) + '"><input type="hidden" name="urgency" value="' + html.escape(urgency_filter) + '"><input type="hidden" name="status" value="' + html.escape(status_filter) + '"><input type="hidden" name="overdue" value="' + html.escape(overdue_filter) + '"><input type="hidden" name="view" value="' + html.escape(view_range) + '"><input type="hidden" name="plan" value="' + html.escape(plan_filter) + '"><input type="hidden" name="quick" value="' + html.escape(quick_filter) + '"><select name="sort2" class="px-2 py-1 border border-gray-200 rounded text-sm" onchange="this.form.submit()">' + sort2_opts + '</select></form>'
    quick_tabs = '<div class="flex gap-2 mb-3 flex-wrap items-center"><span class="text-xs font-medium text-gray-500 mr-1">快速筛选：</span><a href="/admin/my-tasks?' + qs({'quick': ''}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-slate-700 text-white' if not quick_filter else 'bg-slate-100 text-slate-600 hover:bg-slate-200') + '">全部</a><a href="/admin/my-tasks?' + qs({'quick': 'doing'}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-blue-600 text-white' if quick_filter == 'doing' else 'bg-blue-50 text-blue-700 hover:bg-blue-100') + '"><i class="fas fa-play-circle text-xs mr-1"></i>待办</a><a href="/admin/my-tasks?' + qs({'quick': 'review'}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-violet-600 text-white' if quick_filter == 'review' else 'bg-violet-50 text-violet-700 hover:bg-violet-100') + '"><i class="fas fa-clipboard-check text-xs mr-1"></i>待验收</a><a href="/admin/my-tasks?' + qs({'quick': 'soon'}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-amber-600 text-white' if quick_filter == 'soon' else 'bg-amber-50 text-amber-700 hover:bg-amber-100') + '" title="' + str(soon_count) + ' 条"><i class="fas fa-clock text-xs mr-1"></i>即将超时</a><a href="/admin/my-tasks?' + qs({'quick': 'overdue'}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-red-600 text-white' if quick_filter == 'overdue' else 'bg-red-50 text-red-700 hover:bg-red-100') + '" title="' + str(overdue_count) + ' 条"><i class="fas fa-exclamation-triangle text-xs mr-1"></i>已超时</a></div>'
    plan_tabs = '<div class="flex gap-2 mb-3 flex-wrap"><a href="/admin/my-tasks?' + qs({'plan': ''}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-indigo-600 text-white' if not plan_filter else 'bg-gray-100 text-gray-700 hover:bg-gray-200') + '">全部</a><a href="/admin/my-tasks?' + qs({'plan': '__none__'}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-indigo-600 text-white' if plan_filter == '__none__' else 'bg-gray-100 text-gray-700 hover:bg-gray-200') + '">未规划</a>' + ''.join('<a href="/admin/my-tasks?' + qs({'plan': k}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-indigo-600 text-white' if plan_filter == k else 'bg-gray-100 text-gray-700 hover:bg-gray-200') + '">' + html.escape(v) + '</a>' for k, v in PLAN_LABELS.items()) + '</div>'
    view_opts = '<option value="">全部</option><option value="today"' + (' selected' if view_range == 'today' else '') + '>今日</option><option value="week"' + (' selected' if view_range == 'week' else '') + '>本周</option>'
    project_opts = '<option value="">全部项目</option>' + ''.join(
        '<option value="%s"%s>%s</option>' % (html.escape(p['id']), ' selected' if p['id'] == project_filter else '', html.escape(p['name']))
        for p in projects_for_filter
    )
    urgency_opts = '<option value="">全部紧急程度</option>' + ''.join(
        '<option value="%s"%s>%s星</option>' % (i, ' selected' if urgency_filter == str(i) else '', i) for i in range(1, 6)
    )
    status_opts = '<option value="">全部状态</option>' + ''.join(
        '<option value="%s"%s>%s</option>' % (html.escape(k), ' selected' if status_filter == k else '', html.escape(v))
        for k, v in TASK_STATUSES
    )
    overdue_opts = '<option value="">是否超时</option><option value="normal"%s>正常</option><option value="soon"%s>即将超时</option><option value="overdue"%s>超时</option>' % (
        ' selected' if overdue_filter == 'normal' else '', ' selected' if overdue_filter == 'soon' else '', ' selected' if overdue_filter == 'overdue' else ''
    )
    plan_opts_filter = '<option value="">全部</option><option value="__none__"' + (' selected' if plan_filter == '__none__' else '') + '>未规划</option>' + ''.join('<option value="%s"%s>%s</option>' % (k, ' selected' if plan_filter == k else '', v) for k, v in PLAN_LABELS.items())
    filter_form = '<form method="get" action="/admin/my-tasks" class="flex flex-wrap gap-3 items-center mt-2"><input type="hidden" name="sort" value="' + html.escape(sort_by) + '"><input type="hidden" name="sort2" value="' + html.escape(sort2) + '"><input type="hidden" name="quick" value="' + html.escape(quick_filter) + '"><select name="plan" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm">' + plan_opts_filter + '</select><select name="view" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm">' + view_opts + '</select><select name="project" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm">' + project_opts + '</select><select name="urgency" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm">' + urgency_opts + '</select><select name="status" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm">' + status_opts + '</select><select name="overdue" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm">' + overdue_opts + '</select><button type="submit" class="px-3 py-1.5 bg-indigo-100 text-indigo-700 rounded-lg text-sm font-medium">筛选</button></form>'
    reminder = ''
    if soon_count or overdue_count:
        reminder = '<p class="text-sm text-amber-700 mt-2">任务提醒：即将超时 <strong>%d</strong> 条，已超时 <strong>%d</strong> 条</p>' % (soon_count, overdue_count)
    return '''
<div class="bg-white rounded-2xl shadow-md border border-gray-200 overflow-hidden">
    <div class="px-6 py-6 border-b border-gray-100 bg-gradient-to-r from-slate-50 to-white">
        <div class="flex justify-between items-center flex-wrap gap-2">
            <h2 class="text-xl font-semibold text-gray-800">我的任务</h2>
            <a href="/admin" class="inline-flex items-center px-4 py-1.5 rounded-lg text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 transition">← 返回管理中心</a>
        </div>
        ''' + reminder + '''
        ''' + quick_tabs + '''
        ''' + plan_tabs + '''
        <div class="mt-4 p-4 bg-white/80 rounded-xl border border-gray-100">
            <div class="text-sm font-medium text-gray-700 mb-2">筛选</div>
            ''' + filter_form + '''
        </div>
        <div class="mt-4 p-3 bg-white/60 rounded-lg border border-gray-100 text-sm text-gray-600">排序：''' + sort_bar + '''</div>
    </div>
    <div class="overflow-x-auto p-2">
        <table class="min-w-full"><thead class="bg-gray-50"><tr>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">项目</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">任务</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">紧急程度</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">当前负责人</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">状态</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">时间</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">操作</th>
        </tr></thead><tbody>''' + rows_html + '''</tbody></table>
    </div>
</div>
<div id="myTaskEditModal" class="hidden fixed inset-0 bg-black/50 flex items-center justify-center z-[70] p-4 overflow-y-auto" onclick="if(event.target===this) document.getElementById('myTaskEditModal').classList.add('hidden')">
    <div id="myTaskEditModalContent" class="bg-white rounded-2xl shadow-2xl max-w-lg w-full my-4 p-6 max-h-[90vh] overflow-y-auto" onclick="event.stopPropagation()">
        <h4 class="text-lg font-semibold text-gray-800 mb-4">编辑任务</h4>
        <div class="space-y-3 text-sm">
            <div><label class="block text-gray-600 mb-1 font-medium">任务名称</label><input type="text" id="myTaskEditTitle" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"></div>
            <div><label class="block text-gray-600 mb-1 font-medium">具体内容</label><textarea id="myTaskEditContent" rows="3" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500"></textarea></div>
            <div class="grid grid-cols-2 gap-2"><div><label class="block text-gray-600 mb-1 font-medium">开始时间</label><input type="date" id="myTaskEditStart" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg"></div><div><label class="block text-gray-600 mb-1 font-medium">完成时间</label><input type="date" id="myTaskEditEnd" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg"></div></div>
            <div><label class="block text-gray-600 mb-1 font-medium">紧急程度</label><div id="myTaskEditUrgency" class="flex gap-1"><span class="my-edit-urgency-star cursor-pointer text-2xl text-amber-400" data-urgency="1">🌟</span><span class="my-edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="2">🌟</span><span class="my-edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="3">🌟</span><span class="my-edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="4">🌟</span><span class="my-edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="5">🌟</span></div><input type="hidden" id="myTaskEditUrgencyVal" value="1"></div>
            <div id="myTaskEditStatusWrap" class="hidden"><div class="grid grid-cols-2 gap-2"><div><label class="block text-gray-600 mb-1 font-medium">状态</label><select id="myTaskEditStatus" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg"></select></div><div><label class="block text-gray-600 mb-1 font-medium">当前负责人</label><select id="myTaskEditAssignee" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg"></select></div></div></div>
            <div><label class="block text-gray-600 mb-1 font-medium">附件</label><div id="myTaskEditAttachmentList" class="mb-1 text-xs text-gray-500 space-y-1"></div><input type="file" id="myTaskEditFileInput" multiple class="text-sm"></div>
            <div class="border-t pt-3 mt-3"><label class="block text-gray-600 mb-1 font-medium">评论</label><div id="myTaskEditCommentsList" class="mb-2 max-h-32 overflow-y-auto text-xs space-y-1.5 border border-gray-100 rounded p-2 bg-gray-50"></div><div class="flex gap-2"><input type="text" id="myTaskEditNewComment" placeholder="追加评论…" class="flex-1 px-3 py-1.5 border rounded text-sm"><button type="button" id="myTaskEditBtnComment" class="px-3 py-2 bg-blue-600 text-white rounded text-sm">发送</button></div></div>
        </div>
        <div class="flex gap-3 mt-6"><button type="button" onclick="saveMyTaskEdit()" class="flex-1 px-4 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition">保存</button><button type="button" onclick="document.getElementById('myTaskEditModal').classList.add('hidden')" class="px-4 py-2.5 border border-gray-200 rounded-lg text-gray-700 hover:bg-gray-50 transition">取消</button></div>
    </div>
</div>
<script>
var STATUS_LABELS_MY = ''' + json.dumps(dict(TASK_STATUSES)).replace('<', '\\u003c') + ''';
function escAttr(s){ var x=(s||"").toString(); return x.replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function renderMyTaskEditComments(comments){ var el=document.getElementById("myTaskEditCommentsList"); if(!el) return; var c=comments||[]; el.innerHTML=c.length ? c.map(function(e){ return '<div class="py-0.5"><span class="font-medium">'+escAttr(e.user||"")+'</span> <span class="text-gray-400">'+(e.at?e.at.slice(0,16):"")+'</span><br>'+escAttr(e.content||"")+'</div>'; }).join("") : '<div class="text-gray-500">暂无评论</div>'; }
document.querySelectorAll(".my-task-edit-btn").forEach(function(btn){ btn.onclick=function(){ openMyTaskEdit(btn.getAttribute("data-project-id"), btn.getAttribute("data-task-id")); }; });
document.addEventListener("change", function(e){ var sel=e.target; if(!sel||!sel.classList||!sel.classList.contains("task-plan-sel")) return; var pid=sel.getAttribute("data-pid"), tid=sel.getAttribute("data-tid"), plan=sel.value||"", orig=sel.getAttribute("data-current")||""; fetch("/admin/my-tasks/set-plan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project_id: pid, task_id: tid, plan_type: plan }), credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); sel.value=orig; return; } sel.setAttribute("data-current", plan); location.reload(); }); });
(function(){ function setMyUrgencyStars(contentEl, value){ if(!contentEl) return; var h=document.getElementById("myTaskEditUrgencyVal"); if(h) h.value=String(value); var v=Math.max(1, Math.min(5, value)); contentEl.querySelectorAll(".my-edit-urgency-star").forEach(function(s){ var su=parseInt(s.getAttribute("data-urgency"),10)||1; s.classList.remove("text-amber-400","text-gray-300"); s.classList.add(su<=v ? "text-amber-400" : "text-gray-300"); }); } var overlay=document.getElementById("myTaskEditModal"); if(!overlay) return; overlay.addEventListener("click", function(e){ var star=e.target.closest(".my-edit-urgency-star"); if(!star) return; var content=document.getElementById("myTaskEditModalContent"); if(!content||!content.contains(star)) return; var u=parseInt(star.getAttribute("data-urgency"),10)||1; setMyUrgencyStars(content, u); }, true); window._setMyUrgencyStars=setMyUrgencyStars; })();
var myTaskEditBtnComment=document.getElementById("myTaskEditBtnComment");
if(myTaskEditBtnComment) myTaskEditBtnComment.onclick=function(){ var content=(document.getElementById("myTaskEditNewComment")||{}).value.trim(); if(!content){ alert("请输入评论"); return; } var pid=window._myEditProjectId, tid=window._myEditTaskId; if(!pid||!tid) return; fetch("/admin/projects/"+encodeURIComponent(pid)+"/tasks/"+encodeURIComponent(tid)+"/comment", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content: content }), credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); return; } window._myEditComments=window._myEditComments||[]; window._myEditComments.push({ user: d.user||"", content: content, at: d.at||"" }); renderMyTaskEditComments(window._myEditComments); document.getElementById("myTaskEditNewComment").value=""; }); };
function openMyTaskEdit(projectId, taskId){
  fetch("/admin/projects/"+encodeURIComponent(projectId)+"/tasks/list", { credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){
    if(d.error){ alert(d.error); return; }
    var t=(d.tasks||[]).find(function(x){ return x.id===taskId; });
    if(!t){ alert("任务不存在"); return; }
    window._myEditProjectId=projectId; window._myEditTaskId=taskId; window._myEditParticipants=d.participants||[]; window._myEditComments=(t.comments||[]).slice();
    document.getElementById("myTaskEditTitle").value=t.title||"";
    document.getElementById("myTaskEditContent").value=t.content||"";
    document.getElementById("myTaskEditStart").value=(t.start_time||"").slice(0,10);
    document.getElementById("myTaskEditEnd").value=(t.end_time||"").slice(0,10);
    var raw=t.urgency; var u=Math.max(1, Math.min(5, (typeof raw==="number"&&!isNaN(raw)) ? raw : (parseInt(raw,10)||Number(raw)||1)));
    var contentEl=document.getElementById("myTaskEditModalContent");
    if(window._setMyUrgencyStars) window._setMyUrgencyStars(contentEl, u);
    else { document.getElementById("myTaskEditUrgencyVal").value=String(u); contentEl&&contentEl.querySelectorAll(".my-edit-urgency-star").forEach(function(s){ var su=parseInt(s.getAttribute("data-urgency"),10)||1; s.classList.remove("text-amber-400","text-gray-300"); s.classList.add(su<=u ? "text-amber-400" : "text-gray-300"); }); }
    renderMyTaskEditComments(window._myEditComments);
    document.getElementById("myTaskEditNewComment").value="";
    var wrap=document.getElementById("myTaskEditStatusWrap");
    var canSA=t.can_edit_status_assignee;
    wrap.classList.toggle("hidden",!canSA);
    if(canSA){
      var selS=document.getElementById("myTaskEditStatus"); selS.innerHTML="";
      for(var k in STATUS_LABELS_MY){ var o=document.createElement("option"); o.value=k; o.textContent=STATUS_LABELS_MY[k]; if(t.status===k) o.selected=true; selS.appendChild(o); }
      var selA=document.getElementById("myTaskEditAssignee"); selA.innerHTML="";
      (window._myEditParticipants||[]).forEach(function(p){ var o=document.createElement("option"); o.value=p.user; o.textContent=p.user+" ("+p.role+")"; if(t.current_assignee===p.user) o.selected=true; selA.appendChild(o); });
    }
    window._myEditAttachments=(t.attachments||[]).slice();
    var listEl=document.getElementById("myTaskEditAttachmentList"); listEl.innerHTML="";
    (window._myEditAttachments||[]).forEach(function(a){ var span=document.createElement("span"); span.className="block"; span.innerHTML='<a href="'+escAttr(a.url)+'" target="_blank" class="text-blue-600">'+escAttr(a.name)+'</a> <a href="#" class="text-red-500 text-xs">移除</a>'; var link=span.querySelector('a[href="#"]'); if(link) link.onclick=function(){ window._myEditAttachments=window._myEditAttachments.filter(function(x){return x.url!==a.url;}); span.remove(); return false; }; listEl.appendChild(span); });
    document.getElementById("myTaskEditModal").classList.remove("hidden");
    setTimeout(function(){ if(window._setMyUrgencyStars) window._setMyUrgencyStars(contentEl, u); }, 0);
  });
}
function saveMyTaskEdit(){
  var pid=window._myEditProjectId, id=window._myEditTaskId;
  if(!pid||!id) return;
  var urgencyEl=document.getElementById("myTaskEditUrgencyVal"); var urgency=urgencyEl ? Math.max(1, Math.min(5, parseInt(urgencyEl.value,10)||1)) : 1;
  var payload={ title: document.getElementById("myTaskEditTitle").value.trim(), content: document.getElementById("myTaskEditContent").value.trim(), start_time: document.getElementById("myTaskEditStart").value, end_time: document.getElementById("myTaskEditEnd").value, urgency: urgency, attachments: window._myEditAttachments||[] };
  if(document.getElementById("myTaskEditStatusWrap")&&!document.getElementById("myTaskEditStatusWrap").classList.contains("hidden")){ payload.status=document.getElementById("myTaskEditStatus").value; payload.current_assignee=document.getElementById("myTaskEditAssignee").value; }
  fetch("/admin/projects/"+encodeURIComponent(pid)+"/tasks/"+encodeURIComponent(id), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); return; } document.getElementById("myTaskEditModal").classList.add("hidden"); location.reload(); });
}
var myTaskFileInput=document.getElementById("myTaskEditFileInput");
if(myTaskFileInput) myTaskFileInput.onchange=function(){ var files=this.files, pid=window._myEditProjectId; if(!files||!files.length||!pid) return; for(var i=0;i<files.length;i++){ (function(f){ var fd=new FormData(); fd.append("file", f); fetch("/admin/projects/"+encodeURIComponent(pid)+"/tasks/upload", { method: "POST", body: fd, credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.url){ window._myEditAttachments=window._myEditAttachments||[]; window._myEditAttachments.push({ name: d.name||f.name, url: d.url }); var span=document.createElement("span"); span.className="block"; span.innerHTML=escAttr(d.name||f.name)+' <a href="#" class="text-red-500 text-xs">移除</a>'; var link=span.querySelector('a[href="#"]'); if(link) link.onclick=function(){ window._myEditAttachments=window._myEditAttachments.filter(function(x){ return x.url!==d.url; }); span.remove(); return false; }; document.getElementById("myTaskEditAttachmentList").appendChild(span); } else alert(d.error||"上传失败"); }); })(files[i]); } this.value=""; };
</script>
'''


@bp.route('/admin/projects/<project_id>/tasks')
@admin_required('projects')
def project_tasks_page(project_id):
    if project_id not in projects_db or not can_view_project(project_id, _current_username()):
        return '无权限或项目不存在', 403
    proj = projects_db[project_id]
    editors = proj.get('editors') or []
    member_roles = proj.get('member_roles') or {}
    participants = [{'user': u, 'role': member_roles.get(u, '其他')} for u in editors]
    username = _current_username()
    if can_edit_project(project_id, username) and username and not any(p['user'] == username for p in participants):
        participants.insert(0, {'user': username, 'role': member_roles.get(username, '其他')})
    status_opts = ''.join('<option value="%s">%s</option>' % (k, v) for k, v in TASK_STATUSES)
    participants_opts = ''.join('<option value="%s">%s (%s)</option>' % (p['user'], p['user'], p['role']) for p in participants)
    content = _project_tasks_html(project_id, proj.get('name', project_id), status_opts, participants_opts)
    return _admin_layout(content, '项目任务 - %s' % proj.get('name', project_id), back_href='/admin/projects')


@bp.route('/admin/projects/<project_id>/tasks/stats')
@admin_required('projects')
def project_tasks_stats_page(project_id):
    if project_id not in projects_db or not can_view_project(project_id, _current_username()):
        return '无权限或项目不存在', 403
    proj = projects_db[project_id]
    content = _project_tasks_stats_html(project_id, proj.get('name', project_id))
    return _admin_layout(content, '任务统计 - %s' % proj.get('name', project_id), back_href='/admin/projects/%s/tasks' % project_id)


def _project_tasks_stats_html(project_id, project_name):
    status_list = json.dumps([{'id': k, 'label': v} for k, v in TASK_STATUSES])
    return '''
<div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-4">
        <h2 class="text-xl font-semibold text-gray-800">任务统计 · ''' + project_name + '''</h2>
        <a href="/admin/projects/''' + project_id + '''/tasks" class="inline-flex items-center px-4 py-1.5 rounded-lg text-sm font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 transition">← 返回任务列表</a>
    </div>
    <div id="statsLoading" class="text-center py-12 text-gray-500">加载中…</div>
    <div id="statsContent" class="hidden space-y-8">
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="bg-white rounded-xl border border-gray-100 p-4 shadow-sm"><div class="text-sm text-gray-500">总任务数</div><div id="statTotal" class="text-2xl font-bold text-gray-800 mt-1">0</div></div>
            <div class="bg-white rounded-xl border border-gray-100 p-4 shadow-sm"><div class="text-sm text-gray-500">已超时</div><div id="statOverdue" class="text-2xl font-bold text-red-600 mt-1">0</div></div>
            <div class="bg-white rounded-xl border border-gray-100 p-4 shadow-sm"><div class="text-sm text-gray-500">即将超时</div><div id="statSoonOverdue" class="text-2xl font-bold text-amber-600 mt-1">0</div></div>
            <div class="bg-white rounded-xl border border-gray-100 p-4 shadow-sm"><div class="text-sm text-gray-500">已完成</div><div id="statDone" class="text-2xl font-bold text-green-600 mt-1">0</div></div>
        </div>
        <div class="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden p-6 max-w-3xl">
            <h3 class="text-lg font-semibold text-gray-800 mb-4">按状态分布（柱状图）</h3>
            <div class="h-64"><canvas id="chartByStatus"></canvas></div>
        </div>
        <div class="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden p-6 max-w-md mx-auto">
            <h3 class="text-lg font-semibold text-gray-800 mb-4">按状态分布（饼图）</h3>
            <div class="h-64 flex justify-center"><canvas id="chartPieStatus" class="max-w-xs"></canvas></div>
        </div>
        <div class="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden p-6 max-w-3xl">
            <h3 class="text-lg font-semibold text-gray-800 mb-4">各参与者任务状态（堆叠柱状图）</h3>
            <div class="h-80"><canvas id="chartByAssignee"></canvas></div>
        </div>
        <div class="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden p-6 max-w-md">
            <h3 class="text-lg font-semibold text-gray-800 mb-4">超时与即将超时</h3>
            <div class="h-48"><canvas id="chartOverdue"></canvas></div>
        </div>
    </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
var PROJECT_ID_STATS = ''' + json.dumps(project_id).replace('<', '\\u003c') + ''';
var STATUS_LIST = ''' + status_list + ''';
fetch("/admin/projects/"+PROJECT_ID_STATS+"/tasks/list", { credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){
    if(d.error){ document.getElementById("statsLoading").textContent=d.error; return; }
    document.getElementById("statsLoading").classList.add("hidden"); document.getElementById("statsContent").classList.remove("hidden");
    var tasks=d.tasks||[]; var now=new Date(); now.setHours(0,0,0,0); var in3=new Date(now); in3.setDate(in3.getDate()+3);
    var byStatus={}; var byAssignee={}; var overdue=0, soonOverdue=0, done=0;
    STATUS_LIST.forEach(function(s){ byStatus[s.id]=0; });
    tasks.forEach(function(t){
        var s=t.status||"not_started"; if(s in byStatus) byStatus[s]++; else byStatus[s]=1;
        var u=t.current_assignee||"未分配"; if(!byAssignee[u]) byAssignee[u]={}; STATUS_LIST.forEach(function(x){ byAssignee[u][x.id]=0; }); byAssignee[u][s]= (byAssignee[u][s]||0)+1;
        if(["done","abandoned"].indexOf(s)>=0) done++; else if(t.end_time){ var et=new Date(t.end_time.slice(0,10)); et.setHours(0,0,0,0); if(et<now) overdue++; else if(et<=in3) soonOverdue++; }
    });
    document.getElementById("statTotal").textContent=tasks.length; document.getElementById("statOverdue").textContent=overdue; document.getElementById("statSoonOverdue").textContent=soonOverdue; document.getElementById("statDone").textContent=done;
    var statusLabels=STATUS_LIST.map(function(s){ return s.label; }); var statusIds=STATUS_LIST.map(function(s){ return s.id; });
    var barData=statusIds.map(function(id){ return byStatus[id]||0; });
    new Chart(document.getElementById("chartByStatus"), { type: "bar", data: { labels: statusLabels, datasets: [{ label: "任务数", data: barData, backgroundColor: "rgba(99,102,241,0.7)", borderColor: "rgb(99,102,241)", borderWidth: 1, maxBarThickness: 36 }] }, options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { display: false }, ticks: { maxRotation: 45 } }, y: { beginAtZero: true, ticks: { stepSize: 1 } } }, plugins: { legend: { display: false } } } });
    var pieColors=["#ef4444","#f59e0b","#22c55e","#3b82f6","#8b5cf6","#ec4899","#14b8a6"];
    new Chart(document.getElementById("chartPieStatus"), { type: "doughnut", data: { labels: statusLabels, datasets: [{ data: barData, backgroundColor: pieColors.slice(0, statusLabels.length), borderWidth: 2 }] }, options: { responsive: true, maintainAspectRatio: true } });
    var assignees=Object.keys(byAssignee); var datasets=STATUS_LIST.map(function(s,i){ return { label: s.label, data: assignees.map(function(u){ return byAssignee[u][s.id]||0; }), backgroundColor: pieColors[i%pieColors.length], maxBarThickness: 32 }; });
    new Chart(document.getElementById("chartByAssignee"), { type: "bar", data: { labels: assignees, datasets: datasets }, options: { responsive: true, maintainAspectRatio: false, scales: { x: { stacked: true, grid: { display: false }, ticks: { maxRotation: 45 } }, y: { stacked: true, beginAtZero: true, ticks: { stepSize: 1 } } } } });
    new Chart(document.getElementById("chartOverdue"), { type: "bar", data: { labels: ["已超时","即将超时(3天内)"], datasets: [{ label: "任务数", data: [overdue, soonOverdue], backgroundColor: ["rgba(239,68,68,0.8)","rgba(245,158,11,0.8)"], borderWidth: 1, maxBarThickness: 48 }] }, options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { display: false } }, y: { beginAtZero: true, ticks: { stepSize: 1 } } }, plugins: { legend: { display: false } } } });
});
</script>
'''


def _project_tasks_html(project_id, project_name, status_opts, participants_opts):
    return '''
<div class="bg-white rounded-2xl shadow-md border border-gray-200 overflow-hidden">
    <div class="px-6 py-5 border-b border-gray-100 bg-gradient-to-r from-slate-50 to-white flex flex-wrap items-center justify-between gap-4">
        <h2 class="text-xl font-semibold text-gray-800">任务列表 · ''' + project_name + '''</h2>
        <div class="flex items-center gap-2">
            <a href="/admin/projects/''' + project_id + '''/tasks/stats" class="inline-flex items-center px-4 py-2.5 rounded-lg text-sm font-medium text-violet-700 bg-violet-50 hover:bg-violet-100 transition">📊 任务统计</a>
            <a href="/admin/projects" class="inline-flex items-center px-4 py-2.5 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 transition">← 返回项目列表</a>
        </div>
    </div>
    <div class="p-5 md:p-6 border-b bg-slate-50/60">
        <div class="flex flex-wrap gap-3 items-end mb-3">
            <input type="text" id="taskFilter" placeholder="筛选任务名称、内容…" class="px-3 py-2.5 border border-gray-200 rounded-lg text-sm w-52 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500">
            <select id="taskFilterStatus" class="px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"><option value="">全部状态</option>''' + status_opts + '''</select>
            <select id="taskFilterUrgency" class="px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"><option value="">全部紧急程度</option><option value="1">1星</option><option value="2">2星</option><option value="3">3星</option><option value="4">4星</option><option value="5">5星</option></select>
            <select id="taskFilterOverdue" class="px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"><option value="">是否超时</option><option value="normal">正常</option><option value="soon">即将超时</option><option value="overdue">超时</option></select>
            <div class="flex rounded-lg overflow-hidden border border-gray-200 bg-white">
                <button type="button" id="btnMyTasks" class="px-4 py-2.5 text-sm font-medium bg-indigo-100 text-indigo-700">仅我的任务</button>
                <button type="button" id="btnAllTasks" class="px-4 py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-50">全部任务</button>
            </div>
            <div class="flex rounded-lg overflow-hidden border border-gray-200 bg-white">
                <button type="button" id="btnViewList" class="px-4 py-2.5 text-sm font-medium bg-indigo-100 text-indigo-700">列表</button>
                <button type="button" id="btnViewThumb" class="px-4 py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-50">缩略图</button>
            </div>
            <button type="button" id="btnBatchDelete" class="px-4 py-2.5 rounded-lg text-sm font-medium text-red-700 bg-red-50 hover:bg-red-100 transition ml-auto hidden">批量删除</button>
        </div>
        <div class="flex flex-wrap gap-3 items-center mt-2">
            <label class="text-sm text-gray-600">排序：</label>
            <select id="taskSortBy" class="px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500">
                <option value="default">默认</option>
                <option value="status">状态</option>
                <option value="urgency">紧急程度</option>
                <option value="start_time">开始时间</option>
                <option value="remaining">剩余时间</option>
                <option value="role">当前负责人</option>
            </select>
        </div>
        <div id="taskStats" class="text-sm text-gray-600 mt-2"></div>
    </div>
    <div class="p-4 md:p-5 flex justify-end">
        <button type="button" id="btnOpenCreateTask" class="px-6 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 transition shadow-md">+ 创建任务</button>
    </div>
    <div id="createTaskModal" class="hidden fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-4 overflow-y-auto" onclick="if(event.target===this) document.getElementById('createTaskModal').classList.add('hidden')">
        <div id="createTaskModalContent" class="bg-white rounded-2xl shadow-xl max-w-lg w-full my-4 p-6" onclick="event.stopPropagation()">
            <h4 class="text-lg font-semibold text-gray-800 mb-4">创建任务</h4>
            <div class="space-y-3 text-sm">
                <div><label class="block text-gray-600 mb-1 font-medium">任务名称</label><input type="text" id="newTaskTitle" placeholder="任务名称" class="w-full px-3 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-emerald-500"></div>
                <div><label class="block text-gray-600 mb-1 font-medium">流转给（选择参与人）</label><select id="newTaskAssignUser" class="w-full px-3 py-2.5 border border-gray-200 rounded-lg"><option value="">请选择</option>''' + participants_opts + '''</select></div>
                <div class="grid grid-cols-2 gap-2"><div><label class="block text-gray-600 mb-1 font-medium">开始时间</label><input type="date" id="newTaskStart" class="w-full px-3 py-2.5 border border-gray-200 rounded-lg"></div><div><label class="block text-gray-600 mb-1 font-medium">完成时间</label><input type="date" id="newTaskEnd" class="w-full px-3 py-2.5 border border-gray-200 rounded-lg"></div></div>
                <div><label class="block text-gray-600 mb-1 font-medium">紧急程度</label><div id="newTaskUrgency" class="flex gap-1"><span class="urgency-star cursor-pointer text-2xl text-amber-400" data-urgency="1">🌟</span><span class="urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="2">🌟</span><span class="urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="3">🌟</span><span class="urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="4">🌟</span><span class="urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="5">🌟</span></div><input type="hidden" id="newTaskUrgencyVal" value="1"></div>
                <div><label class="block text-gray-600 mb-1 font-medium">具体内容</label><textarea id="newTaskContent" placeholder="具体内容、需要对接角色" rows="2" class="w-full px-3 py-2.5 border border-gray-200 rounded-lg"></textarea></div>
                <div><label class="block text-gray-600 mb-1 font-medium">附件</label><div id="newTaskAttachmentList" class="mb-1 text-xs text-gray-500 space-y-1"></div><input type="file" id="newTaskFileInput" multiple class="text-sm"></div>
            </div>
            <div class="flex gap-3 mt-5"><button type="button" id="btnCreateTask" class="flex-1 px-4 py-2.5 bg-emerald-600 text-white rounded-lg font-medium hover:bg-emerald-700 transition">创建</button><button type="button" onclick="document.getElementById('createTaskModal').classList.add('hidden')" class="px-4 py-2.5 border border-gray-200 rounded-lg hover:bg-gray-50 transition">取消</button></div>
        </div>
    </div>
    <div class="p-5 md:p-6">
        <ul id="taskList" class="space-y-4"></ul>
    </div>
</div>
<div id="flowLogModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[80vh] overflow-hidden flex flex-col" onclick="event.stopPropagation()">
        <div class="px-4 py-3 border-b font-semibold">任务流转日志</div>
        <div id="flowLogContent" class="p-4 overflow-y-auto text-sm"></div>
        <div class="p-4 border-t"><button type="button" onclick="document.getElementById('flowLogModal').classList.add('hidden')" class="px-4 py-1.5 border rounded text-sm">关闭</button></div>
    </div>
</div>
<div id="commentModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[80vh] overflow-hidden flex flex-col" onclick="event.stopPropagation()">
        <div class="px-4 py-3 border-b font-semibold">任务评论</div>
        <div id="commentList" class="p-4 overflow-y-auto text-sm flex-1"></div>
        <div class="p-4 border-t flex gap-2">
            <input type="text" id="newCommentContent" placeholder="输入评论…" class="flex-1 px-3 py-1.5 border rounded text-sm">
            <button type="button" id="btnAddComment" class="px-4 py-2 bg-blue-600 text-white rounded text-sm">发送</button>
        </div>
    </div>
</div>
<div id="statusModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-xl shadow-xl w-80 p-5" onclick="event.stopPropagation()">
        <h4 class="font-semibold mb-2">标记状态</h4>
        <select id="statusModalSelect" class="w-full px-3 py-1.5 border rounded text-sm mb-3"></select>
        <div class="flex gap-2"><button type="button" onclick="confirmStatusChange()" class="flex-1 px-4 py-2 bg-blue-600 text-white rounded text-sm">确认</button><button type="button" onclick="document.getElementById('statusModal').classList.add('hidden')" class="px-4 py-1.5 border rounded text-sm">取消</button></div>
    </div>
</div>
<div id="handoffModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-xl shadow-xl w-80 p-5" onclick="event.stopPropagation()">
        <h4 class="font-semibold mb-2">流转给</h4>
        <select id="handoffModalSelect" class="w-full px-3 py-1.5 border rounded text-sm mb-3"></select>
        <div class="flex gap-2"><button type="button" onclick="confirmHandoff()" class="flex-1 px-4 py-2 bg-blue-600 text-white rounded text-sm">确认</button><button type="button" onclick="document.getElementById('handoffModal').classList.add('hidden')" class="px-4 py-1.5 border rounded text-sm">取消</button></div>
    </div>
</div>
<div id="editTaskModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4 overflow-y-auto" onclick="if(event.target===this) this.classList.add('hidden')">
    <div id="editTaskModalContent" class="bg-white rounded-xl shadow-xl max-w-lg w-full my-4 p-5 max-h-[90vh] overflow-y-auto" onclick="event.stopPropagation()">
        <h4 class="font-semibold mb-3">编辑任务</h4>
        <div class="space-y-2 text-sm">
            <div><label class="block text-gray-600 mb-1">任务名称</label><input type="text" id="editTaskTitle" class="w-full px-3 py-1.5 border rounded"></div>
            <div><label class="block text-gray-600 mb-1">具体内容</label><textarea id="editTaskContent" rows="3" class="w-full px-3 py-1.5 border rounded"></textarea></div>
            <div class="grid grid-cols-2 gap-2"><div><label class="block text-gray-600 mb-1">开始时间</label><input type="date" id="editTaskStart" class="w-full px-3 py-1.5 border rounded"></div><div><label class="block text-gray-600 mb-1">完成时间</label><input type="date" id="editTaskEnd" class="w-full px-3 py-1.5 border rounded"></div></div>
            <div><label class="block text-gray-600 mb-1">紧急程度</label><div id="editTaskUrgency" class="flex gap-1"><span class="edit-urgency-star cursor-pointer text-2xl" data-urgency="1">🌟</span><span class="edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="2">🌟</span><span class="edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="3">🌟</span><span class="edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="4">🌟</span><span class="edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="5">🌟</span></div><input type="hidden" id="editTaskUrgencyVal" value="1"></div>
            <div id="editTaskStatusAssigneeWrap" class="hidden"><div class="grid grid-cols-2 gap-2"><div><label class="block text-gray-600 mb-1">状态</label><select id="editTaskStatus" class="w-full px-3 py-1.5 border rounded"></select></div><div><label class="block text-gray-600 mb-1">当前负责人</label><select id="editTaskAssignee" class="w-full px-3 py-1.5 border rounded"></select></div></div></div>
            <div><label class="block text-gray-600 mb-1">附件</label><div id="editTaskAttachmentList" class="mb-1 text-xs text-gray-500 space-y-1"></div><input type="file" id="editTaskFileInput" multiple class="text-sm"><span class="text-gray-400 text-xs ml-1">可传图片或文件</span></div>
            <div class="border-t pt-3 mt-3"><label class="block text-gray-600 mb-1 font-medium">评论</label><div id="editTaskCommentsList" class="mb-2 max-h-32 overflow-y-auto text-xs space-y-1.5 border border-gray-100 rounded p-2 bg-gray-50"></div><div class="flex gap-2"><input type="text" id="editTaskNewComment" placeholder="追加评论…" class="flex-1 px-3 py-1.5 border rounded text-sm"><button type="button" id="editTaskBtnComment" class="px-3 py-2 bg-blue-600 text-white rounded text-sm">发送</button></div></div>
        </div>
        <div class="flex gap-2 mt-4"><button type="button" onclick="saveEditTask()" class="flex-1 px-4 py-2 bg-blue-600 text-white rounded text-sm">保存</button><button type="button" onclick="document.getElementById('editTaskModal').classList.add('hidden')" class="px-4 py-1.5 border rounded text-sm">取消</button></div>
    </div>
</div>
<script>
var PROJECT_ID = ''' + json.dumps(project_id).replace('<', '\\u003c') + ''';
var STATUS_LABELS = ''' + json.dumps(dict(TASK_STATUSES)).replace('<', '\\u003c') + ''';
function escAttr(s){ var x=(s||"").toString(); return x.replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function escJs(s){ var x=(s||"").toString(); return x.replace(/\\\\/g,"\\\\\\\\").replace(/'/g,"\\\\'"); }
function loadTasks(){
    return fetch('/admin/projects/'+PROJECT_ID+'/tasks/list', { credentials:'same-origin' }).then(function(r){ return r.json().then(function(d){ return { ok: r.ok, data: d }; }).catch(function(){ return { ok: false, data: { error: "解析失败" } }; }); }).then(function(res){
        var d = res.data;
        if(!res.ok || d.error){ document.getElementById('taskList').innerHTML='<li class="text-gray-500">'+(d.error||'加载失败')+'</li>'; return; }
        window._allTasks = d.tasks||[]; window._myUsername = d.my_username||''; window._participants = d.participants||[];
        renderTasks(window._allTasks);
        var s = d.stats||{}; document.getElementById('taskStats').textContent = '共 '+s.total+' 个任务 · 已作废 '+s.abandoned+' · 尚未开始 '+s.not_started+' · 进行中 '+s.in_progress+' · 待验收 '+s.pending_review+' · 验收通过 '+s.review_passed+' · 验收未通过 '+s.review_failed+' · 已完成 '+s.done+' · 已超时 '+s.overdue+' · 即将超时 '+s.soon_overdue;
        var hasDel = (window._allTasks||[]).some(function(t){ return t.can_delete; }); document.getElementById('btnBatchDelete').classList.toggle('hidden', !hasDel);
    });
}
function taskRowBgAndProgress(t){
    var status=t.status||'not_started'; var bg='bg-white';
    var statusBg={ abandoned:'bg-gray-100', not_started:'bg-slate-50', in_progress:'bg-blue-50', pending_review:'bg-violet-50', review_passed:'bg-green-50', review_failed:'bg-orange-50' };
    bg=statusBg[status]||bg; var progressLabel='';
    if(status==='in_progress'&&t.end_time){ var now=new Date(); now.setHours(0,0,0,0); var et=new Date(t.end_time.slice(0,10)); et.setHours(0,0,0,0);
        if(et<now){ var days=(now-et)/86400000; bg=days>=7?'bg-red-200':'bg-red-50'; progressLabel=days>=7?'严重超时':'超时'; }
        else{ var days=(et-now)/86400000; if(days<=3){ bg='bg-amber-50'; progressLabel='即将超时'; } else{ bg='bg-emerald-50'; progressLabel='正常'; } }
    }
    return { bg: bg, progress: progressLabel };
}
function renderTasks(tasks){
    var list = document.getElementById('taskList');
    var filter = (document.getElementById('taskFilter')||{}).value.toLowerCase();
    var statusFilter = (document.getElementById('taskFilterStatus')||{}).value;
    var urgencyFilter = (document.getElementById('taskFilterUrgency')||{}).value;
    var overdueFilter = (document.getElementById('taskFilterOverdue')||{}).value;
    var sortBy = (document.getElementById('taskSortBy')||{}).value || 'default';
    var showOnlyMine = window._showOnlyMine;
    var myUser = window._myUsername||'';
    var now = new Date(); now.setHours(0,0,0,0);
    var in3 = new Date(now); in3.setDate(in3.getDate()+3);
    var arr = (tasks||[]).filter(function(t){
        if(showOnlyMine && t.current_assignee !== myUser) return false;
        if(filter && (t.title||'').toLowerCase().indexOf(filter)<0 && (t.content||'').toLowerCase().indexOf(filter)<0) return false;
        if(statusFilter && t.status!==statusFilter) return false;
        if(urgencyFilter){ var u=Number(t.urgency)||1; if(u!==Number(urgencyFilter)) return false; }
        if(overdueFilter&&t.status!=='done'&&t.status!=='abandoned'){ var et=t.end_time?new Date(t.end_time.slice(0,10)):null; if(et) et.setHours(0,0,0,0);
            if(overdueFilter==='normal'){ if(!t.end_time) return true; if(et<now) return false; if(et<=in3) return false; }
            else if(overdueFilter==='soon'){ if(!t.end_time) return false; if(et<now||et>in3) return false; }
            else if(overdueFilter==='overdue'){ if(!t.end_time) return false; if(et>=now) return false; }
        }
        return true;
    });
    arr.sort(function(a,b){
        if(sortBy==='status') return (a.status||'').localeCompare(b.status||'');
        if(sortBy==='urgency') return (b.urgency||1) - (a.urgency||1);
        if(sortBy==='start_time') return (a.start_time||'').localeCompare(b.start_time||'');
        if(sortBy==='remaining'){
            var ea = a.end_time ? new Date(a.end_time).getTime() : 0; var eb = b.end_time ? new Date(b.end_time).getTime() : 0;
            return ea - eb;
        }
        if(sortBy==='role') return (a.current_assignee||'').localeCompare(b.current_assignee||'');
        return 0;
    });
    var viewMode = window._taskViewMode || 'list';
    var cardCls = viewMode==='thumb' ? 'w-full max-w-[280px] min-h-[200px] flex flex-col' : '';
    list.className = viewMode==='thumb' ? 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5 max-w-7xl' : 'space-y-4';
    list.innerHTML = arr.map(function(t){
        var overdue = t.end_time && new Date(t.end_time) < new Date() && t.status!=='done' && t.status!=='abandoned';
        var rowStyle = taskRowBgAndProgress(t);
        var statusLabel = STATUS_LABELS[t.status] || t.status;
        var overdueBadge = '';
        if(rowStyle.progress==='超时'||rowStyle.progress==='严重超时') overdueBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-red-600 text-white uppercase ml-1">'+(rowStyle.progress==='严重超时'?'严重超时':'已超时')+'</span>';
        else if(rowStyle.progress==='即将超时') overdueBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-amber-500 text-white ml-1">即将超时</span>';
        else if(rowStyle.progress==='正常'&&t.status==='in_progress') overdueBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-500 text-white ml-1">正常</span>';
        if(rowStyle.progress) statusLabel += ' · '+rowStyle.progress;
        var isAssignee = t.current_assignee === myUser;
        var urgencyVal = Math.max(1, Math.min(5, parseInt(t.urgency,10)||1));
        var urgencyStars = ''; for(var i=1;i<=5;i++) urgencyStars += i<=urgencyVal ? '🌟' : '☆'; urgencyStars = '<span class="text-amber-500" title="紧急程度 '+urgencyVal+'">'+urgencyStars+'</span>';
        var actions = [];
        if(t.can_edit){ actions.push('<button onclick="openEditTask(\\''+escJs(t.id)+'\\')" class="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 transition">编辑</button>'); }
        if(isAssignee){ actions.push('<button onclick="openStatusModal(\\''+escJs(t.id)+'\\')" class="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 transition">标记状态</button>'); actions.push('<button onclick="openHandoffModal(\\''+escJs(t.id)+'\\')" class="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 transition">流转</button>'); }
        if(t.can_delete){ actions.push('<button onclick="deleteTask(\\''+escJs(t.id)+'\\')" class="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium text-red-700 bg-red-50 hover:bg-red-100 transition">删除</button>'); }
        actions.push('<button onclick="showFlowLog(\\''+escJs(t.id)+'\\')" class="inline-flex items-center px-3 py-1.5 rounded-lg text-sm text-gray-600 bg-gray-100 hover:bg-gray-200 transition" title="流转日志">📋</button>');
        var comments=t.comments||[]; var lastC=comments.length ? comments[comments.length-1] : null; var commentTxt=(comments.length||0)+'条评论'+(lastC ? ' 最后: '+escAttr(lastC.user||'')+' '+(lastC.content ? escAttr(lastC.content.slice(0,8))+(lastC.content.length>8 ? '…' : '') : '') : '');
        actions.push('<button onclick="showComments(\\''+escJs(t.id)+'\\')" class="inline-flex items-center px-3 py-1.5 rounded-lg text-sm text-gray-600 bg-gray-100 hover:bg-gray-200 transition" title="评论">💬</button><span class="text-xs text-gray-500 ml-1">'+commentTxt+'</span>');
        var assigneeRole = ''; for(var i=0;i<(window._participants||[]).length;i++){ var p=window._participants[i]; if(p.user===t.current_assignee){ assigneeRole=p.role; break; } }
        var assigneeText = t.current_assignee ? (t.current_assignee+(assigneeRole?' ('+assigneeRole+')':'')) : '-';
        var attHtml = (t.attachments||[]).length ? '<div class="text-xs mt-1">附件: '+ (t.attachments||[]).map(function(a){ return '<a href="'+escAttr(a.url)+'" target="_blank" class="text-blue-600 mr-2">'+escAttr(a.name)+'</a>'; }).join('') +'</div>' : '';
        var overdueCls = overdue ? ' text-red-600 font-medium' : '';
        var contentPreview = viewMode==='thumb' ? (t.content||'').slice(0,60)+(t.content&&t.content.length>60?'…':'') : (t.content||'');
        var borderCls = (rowStyle.progress==='超时'||rowStyle.progress==='严重超时') ? ' border-l-4 border-l-red-600' : (rowStyle.progress==='即将超时' ? ' border-l-4 border-l-amber-500' : '');
        return '<li class="'+rowStyle.bg+' border border-gray-200 rounded-xl p-5 shadow-sm hover:shadow-md transition '+cardCls+borderCls+'"><label class="flex items-start gap-3 flex-1"><input type="checkbox" class="task-check mt-1.5 flex-shrink-0" data-task-id="'+escAttr(t.id)+'" '+(t.can_delete?'':'disabled')+' style="display:'+(t.can_delete?'inline-block':'none')+'"> <div class="flex-1 min-w-0"><div class="flex flex-wrap justify-between items-start gap-2"><span class="font-semibold text-gray-900 text-base">'+escAttr(t.title||'')+'</span> <span class="text-sm'+overdueCls+'">'+urgencyStars+' '+escAttr(assigneeText)+' · <span class="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">'+statusLabel+(overdue?' · 超时':'')+'</span>'+overdueBadge+'</span></div><div class="text-sm text-gray-600 mt-2 line-clamp-2">'+escAttr(contentPreview)+'</div>'+attHtml+'<div class="text-xs text-gray-400 mt-2">'+(t.start_time||'')+' ~ '+(t.end_time||'')+'</div><div class="mt-4 flex flex-wrap gap-2">'+actions.join('')+'</div></div></label></li>';
    }).join('') || '<li class="text-gray-500 col-span-full">暂无任务</li>';
}
var btnOpenCreate = document.getElementById('btnOpenCreateTask');
if(btnOpenCreate) btnOpenCreate.onclick=function(){ document.getElementById('newTaskTitle').value=''; document.getElementById('newTaskContent').value=''; var s=document.getElementById('newTaskStart'); var e=document.getElementById('newTaskEnd'); if(s)s.value=''; if(e)e.value=''; var createContent=document.getElementById('createTaskModalContent')||document.querySelector('#createTaskModalContent'); setUrgencyStars(createContent, '.urgency-star', 1, 'newTaskUrgencyVal'); window._newTaskAttachments=[]; var list=document.getElementById('newTaskAttachmentList'); if(list) list.innerHTML=''; document.getElementById('createTaskModal').classList.remove('hidden'); };
document.getElementById('btnCreateTask').onclick=function(){
    var title = document.getElementById('newTaskTitle').value.trim();
    var assignUser = (document.getElementById('newTaskAssignUser')||{}).value.trim();
    if(!title){ alert('请输入任务名称'); return; }
    if(!assignUser){ alert('请选择流转给的参与人'); return; }
    var startEl = document.getElementById('newTaskStart'); var endEl = document.getElementById('newTaskEnd');
    var urgencyEl = document.getElementById('newTaskUrgencyVal'); var urgency = urgencyEl ? Math.max(1, Math.min(5, parseInt(urgencyEl.value,10)||1)) : 1;
    var payload = { title: title, content: document.getElementById('newTaskContent').value.trim(), assign_to_user: assignUser, start_time: startEl ? startEl.value : '', end_time: endEl ? endEl.value : '', urgency: urgency, attachments: window._newTaskAttachments || [] };
    fetch('/admin/projects/'+PROJECT_ID+'/tasks/create', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload), credentials:'same-origin' }).then(function(r){ return r.json().then(function(d){ return { ok: r.ok, data: d }; }).catch(function(){ return { ok: false, data: {} }; }); }).then(function(res){ var d=res.data; if(d.error){ alert(d.error); return; } document.getElementById('createTaskModal').classList.add('hidden'); document.getElementById('newTaskTitle').value=''; document.getElementById('newTaskContent').value=''; if(startEl) startEl.value=''; if(endEl) endEl.value=''; window._newTaskAttachments=[]; var list=document.getElementById('newTaskAttachmentList'); if(list) list.innerHTML=''; loadTasks().then(function(){ alert('已创建'); }); });
};
document.getElementById('btnMyTasks').onclick=function(){ window._showOnlyMine=true; renderTasks(window._allTasks||[]); document.getElementById('btnMyTasks').classList.add('bg-indigo-100','text-indigo-700'); document.getElementById('btnMyTasks').classList.remove('border'); document.getElementById('btnAllTasks').classList.remove('bg-indigo-100','text-indigo-700'); document.getElementById('btnAllTasks').classList.add('border'); };
document.getElementById('btnAllTasks').onclick=function(){ window._showOnlyMine=false; renderTasks(window._allTasks||[]); document.getElementById('btnAllTasks').classList.add('bg-indigo-100','text-indigo-700'); document.getElementById('btnAllTasks').classList.remove('border'); document.getElementById('btnMyTasks').classList.remove('bg-indigo-100','text-indigo-700'); document.getElementById('btnMyTasks').classList.add('border'); };
document.getElementById('btnBatchDelete').onclick=function(){ var ids=[]; document.querySelectorAll('.task-check:checked').forEach(function(c){ ids.push(c.getAttribute('data-task-id')); }); if(!ids.length){ alert('请勾选要删除的任务'); return; } if(!confirm('确定删除 '+ids.length+' 个任务？')) return; fetch('/admin/projects/'+PROJECT_ID+'/tasks/batch-delete', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({task_ids: ids}), credentials:'same-origin' }).then(r=>r.json()).then(function(d){ alert(d.error||'已删除'); if(!d.error) loadTasks(); }); };
['taskFilter','taskFilterStatus','taskFilterUrgency','taskFilterOverdue','taskSortBy'].forEach(function(id){ var el=document.getElementById(id); if(el) el.oninput=el.onchange=function(){ renderTasks(window._allTasks||[]); }; });
document.getElementById('btnViewList').onclick=function(){ window._taskViewMode='list'; document.getElementById('btnViewList').classList.add('bg-indigo-100','text-indigo-700'); document.getElementById('btnViewList').classList.remove('border'); document.getElementById('btnViewThumb').classList.remove('bg-indigo-100','text-indigo-700'); document.getElementById('btnViewThumb').classList.add('border'); renderTasks(window._allTasks||[]); };
document.getElementById('btnViewThumb').onclick=function(){ window._taskViewMode='thumb'; document.getElementById('btnViewThumb').classList.add('bg-indigo-100','text-indigo-700'); document.getElementById('btnViewThumb').classList.remove('border'); document.getElementById('btnViewList').classList.remove('bg-indigo-100','text-indigo-700'); document.getElementById('btnViewList').classList.add('border'); renderTasks(window._allTasks||[]); };
function setUrgencyStars(contentEl, starSelector, value, hiddenId){ if(!contentEl) return; var h=document.getElementById(hiddenId); if(h) h.value=String(value); var v=Math.max(1, Math.min(5, value)); contentEl.querySelectorAll(starSelector).forEach(function(s){ var su=parseInt(s.getAttribute('data-urgency'),10)||1; s.classList.remove('text-amber-400','text-gray-300'); s.classList.add(su<=v ? 'text-amber-400' : 'text-gray-300'); }); }
function bindUrgencyStarsCapture(overlayId, contentSelector, starSelector, hiddenId){ var overlay=document.getElementById(overlayId); if(!overlay) return; overlay.addEventListener('click', function(e){ var star=e.target.closest(starSelector); if(!star) return; var content=document.querySelector(contentSelector); if(!content||!content.contains(star)) return; var u=parseInt(star.getAttribute('data-urgency'),10)||1; setUrgencyStars(content, starSelector, u, hiddenId); }, true); }
bindUrgencyStarsCapture('createTaskModal','#createTaskModalContent','.urgency-star','newTaskUrgencyVal');
bindUrgencyStarsCapture('editTaskModal','#editTaskModalContent','.edit-urgency-star','editTaskUrgencyVal');
function showFlowLog(taskId){ var t=(window._allTasks||[]).find(function(x){ return x.id===taskId; }); if(!t) return; var log = t.flow_log||[]; var labels = window.STATUS_LABELS||{}; document.getElementById('flowLogContent').innerHTML = log.length ? log.map(function(e){ var st = e.status ? (labels[e.status]||e.status) : ''; return '<div class="py-1 border-b border-gray-100">'+(e.at?e.at.slice(0,19):'')+' · '+e.from_user+' → '+e.to_user+(st ? ' ['+st+']' : '')+'</div>'; }).join('') : '<div class="text-gray-500">暂无流转记录</div>'; document.getElementById('flowLogModal').classList.remove('hidden'); }
function showComments(taskId){ window._commentTaskId=taskId; var t=(window._allTasks||[]).find(function(x){ return x.id===taskId; }); if(!t) return; var c = t.comments||[]; document.getElementById('commentList').innerHTML = c.length ? c.map(function(e){ return '<div class="py-1"><span class="font-medium">'+e.user+'</span> <span class="text-gray-400 text-xs">'+e.at+'</span><br>'+e.content+'</div>'; }).join('') : '<div class="text-gray-500">暂无评论</div>'; document.getElementById('newCommentContent').value=''; document.getElementById('commentModal').classList.remove('hidden'); }
document.getElementById('btnAddComment').onclick=function(){ var content=(document.getElementById('newCommentContent')||{}).value.trim(); if(!content){ alert('请输入评论'); return; } var tid=window._commentTaskId; if(!tid) return; fetch('/admin/projects/'+PROJECT_ID+'/tasks/'+tid+'/comment', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content: content}), credentials:'same-origin' }).then(r=>r.json()).then(function(d){ alert(d.error||'已添加'); if(!d.error){ var t=(window._allTasks||[]).find(function(x){ return x.id===tid; }); if(t){ t.comments=t.comments||[]; t.comments.push({user: d.user||'', content: content, at: d.at||''}); } showComments(tid); loadTasks(); } }); };
function openStatusModal(id){ var t=(window._allTasks||[]).find(function(x){ return x.id===id; }); if(!t||t.current_assignee!==window._myUsername) return; window._statusModalTaskId=id; var sel=document.getElementById('statusModalSelect'); sel.innerHTML=''; for(var k in STATUS_LABELS){ var opt=document.createElement('option'); opt.value=k; opt.textContent=STATUS_LABELS[k]; if(t.status===k) opt.selected=true; sel.appendChild(opt); } document.getElementById('statusModal').classList.remove('hidden'); }
function confirmStatusChange(){ var id=window._statusModalTaskId; var v=(document.getElementById('statusModalSelect')||{}).value; if(!id||!v) return; fetch('/admin/projects/'+PROJECT_ID+'/tasks/'+id+'/update-status', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({status: v}), credentials:'same-origin' }).then(r=>r.json()).then(function(d){ alert(d.error||'已更新'); if(!d.error){ loadTasks(); document.getElementById('statusModal').classList.add('hidden'); } }); }
function openHandoffModal(id){ var t=(window._allTasks||[]).find(function(x){ return x.id===id; }); if(!t||t.current_assignee!==window._myUsername) return; window._handoffModalTaskId=id; var sel=document.getElementById('handoffModalSelect'); sel.innerHTML='<option value="">选择参与人</option>'; (window._participants||[]).filter(function(p){ return p.user!==window._myUsername; }).forEach(function(p){ var opt=document.createElement('option'); opt.value=p.user; opt.textContent=p.user+' ('+p.role+')'; sel.appendChild(opt); }); document.getElementById('handoffModal').classList.remove('hidden'); }
function confirmHandoff(){ var id=window._handoffModalTaskId; var to=(document.getElementById('handoffModalSelect')||{}).value.trim(); if(!id||!to){ alert('请选择流转对象'); return; } fetch('/admin/projects/'+PROJECT_ID+'/tasks/'+id+'/handoff', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({passed_to_user: to}), credentials:'same-origin' }).then(r=>r.json()).then(function(d){ alert(d.error||'已流转'); if(!d.error){ loadTasks(); document.getElementById('handoffModal').classList.add('hidden'); } }); }
function deleteTask(id){ if(!confirm('确定删除该任务？')) return; fetch('/admin/projects/'+PROJECT_ID+'/tasks/'+id, { method:'DELETE', credentials:'same-origin' }).then(r=>r.json()).then(function(d){ alert(d.error||'已删除'); if(!d.error) loadTasks(); }); }
window._newTaskAttachments = [];
function uploadTaskFile(file, taskId, isNew, callback){ var fd=new FormData(); fd.append('file', file); var url='/admin/projects/'+PROJECT_ID+'/tasks/upload'; if(taskId) fd.append('task_id', taskId); fetch(url, { method:'POST', body: fd, credentials:'same-origin' }).then(r=>r.json()).then(function(d){ if(d.url){ if(callback) callback(d.url, d.name||file.name); } else alert(d.error||'上传失败'); }).catch(function(){ alert('上传失败'); }); }
var newFileEl = document.getElementById('newTaskFileInput');
if(newFileEl) newFileEl.onchange=function(){
  var files=this.files; if(!files||!files.length) return;
  for(var i=0;i<files.length;i++){ (function(f){
    uploadTaskFile(f, null, true, function(url, name){
      window._newTaskAttachments = window._newTaskAttachments||[];
      window._newTaskAttachments.push({name:name, url:url});
      var list=document.getElementById('newTaskAttachmentList');
      if(list){ var span=document.createElement('span'); span.className='block';
        span.innerHTML=name+' <a href="#" class="text-red-500">移除</a>';
        span.querySelector('a').onclick=function(){ window._newTaskAttachments=window._newTaskAttachments.filter(function(x){return x.url!==url;}); span.remove(); return false; };
        list.appendChild(span);
      }
    });
  })(files[i]); }
  this.value='';
};
function renderEditTaskComments(comments){
  var el=document.getElementById('editTaskCommentsList'); if(!el) return;
  var c=comments||[];
  el.innerHTML= c.length ? c.map(function(e){ return '<div class="py-0.5"><span class="font-medium">'+escAttr(e.user||'')+'</span> <span class="text-gray-400">'+(e.at?e.at.slice(0,16):'')+'</span><br>'+escAttr(e.content||'')+'</div>'; }).join('') : '<div class="text-gray-500">暂无评论</div>';
}
function openEditTask(id){
  var t=(window._allTasks||[]).find(function(x){ return x.id===id; });
  if(!t||!t.can_edit) return;
  window._editTaskId=id;
  document.getElementById('editTaskTitle').value=t.title||'';
  document.getElementById('editTaskContent').value=t.content||'';
  document.getElementById('editTaskStart').value=(t.start_time||'').slice(0,10);
  document.getElementById('editTaskEnd').value=(t.end_time||'').slice(0,10);
  var raw=t.urgency; var u=Math.max(1, Math.min(5, (typeof raw==='number'&&!isNaN(raw)) ? raw : (parseInt(raw,10)||Number(raw)||1)));
  var contentEl=document.getElementById('editTaskModalContent')||document.querySelector('#editTaskModalContent');
  setUrgencyStars(contentEl, '.edit-urgency-star', u, 'editTaskUrgencyVal');
  renderEditTaskComments(t.comments||[]);
  var newC=document.getElementById('editTaskNewComment'); if(newC) newC.value='';
  var wrap=document.getElementById('editTaskStatusAssigneeWrap');
  var canSA=t.can_edit_status_assignee;
  wrap.classList.toggle('hidden',!canSA);
  if(canSA){
    var selS=document.getElementById('editTaskStatus'); selS.innerHTML='';
    for(var k in STATUS_LABELS){ var o=document.createElement('option'); o.value=k; o.textContent=STATUS_LABELS[k]; if(t.status===k) o.selected=true; selS.appendChild(o); }
    var selA=document.getElementById('editTaskAssignee'); selA.innerHTML='';
    (window._participants||[]).forEach(function(p){ var o=document.createElement('option'); o.value=p.user; o.textContent=p.user+' ('+p.role+')'; if(t.current_assignee===p.user) o.selected=true; selA.appendChild(o); });
  }
  window._editTaskAttachments = (t.attachments||[]).slice();
  var listEl=document.getElementById('editTaskAttachmentList');
  listEl.innerHTML='';
  (window._editTaskAttachments||[]).forEach(function(a){
    var span=document.createElement('span'); span.className='block';
    span.setAttribute('data-url', a.url);
    span.innerHTML='<a href="'+escAttr(a.url)+'" target="_blank" class="text-blue-600">'+escAttr(a.name)+'</a> <a href="#" class="text-red-500 text-xs">移除</a>';
    var link=span.querySelector('a[href="#"]');
    if(link){ link.onclick=function(){ window._editTaskAttachments=window._editTaskAttachments.filter(function(x){return x.url!==a.url;}); span.remove(); return false; }; }
    listEl.appendChild(span);
  });
  document.getElementById('editTaskModal').classList.remove('hidden');
  setTimeout(function(){ setUrgencyStars(contentEl, '.edit-urgency-star', u, 'editTaskUrgencyVal'); }, 0);
}
var editTaskBtnComment=document.getElementById('editTaskBtnComment');
if(editTaskBtnComment) editTaskBtnComment.onclick=function(){ var content=(document.getElementById('editTaskNewComment')||{}).value.trim(); if(!content){ alert('请输入评论'); return; } var tid=window._editTaskId; if(!tid) return; fetch('/admin/projects/'+PROJECT_ID+'/tasks/'+tid+'/comment', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content: content}), credentials:'same-origin' }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); return; } var t=(window._allTasks||[]).find(function(x){ return x.id===tid; }); if(t){ t.comments=t.comments||[]; t.comments.push({user: d.user||'', content: content, at: d.at||''}); } renderEditTaskComments(t.comments); document.getElementById('editTaskNewComment').value=''; }); };
var editFileEl=document.getElementById('editTaskFileInput');
if(editFileEl) editFileEl.onchange=function(){
  var files=this.files; if(!files||!files.length) return;
  for(var i=0;i<files.length;i++){ (function(f){
    uploadTaskFile(f, window._editTaskId, false, function(url, name){
      window._editTaskAttachments=window._editTaskAttachments||[];
      window._editTaskAttachments.push({name:name, url:url});
      var list=document.getElementById('editTaskAttachmentList');
      var span=document.createElement('span'); span.className='block';
      span.innerHTML=escAttr(name)+' <a href="#" class="text-red-500 text-xs" data-url="'+escAttr(url)+'">移除</a>';
      var a=span.querySelector('a');
      if(a){ a.onclick=function(){ window._editTaskAttachments=window._editTaskAttachments.filter(function(x){return x.url!==url;}); span.remove(); return false; }; }
      list.appendChild(span);
    });
  })(files[i]); }
  this.value='';
};
function saveEditTask(){
  var id=window._editTaskId; if(!id) return;
  var task=(window._allTasks||[]).find(function(t){return t.id===id;});
  var urgencyEl=document.getElementById('editTaskUrgencyVal'); var urgency=urgencyEl ? Math.max(1, Math.min(5, parseInt(urgencyEl.value,10)||1)) : 1;
  var payload={ title: document.getElementById('editTaskTitle').value.trim(), content: document.getElementById('editTaskContent').value.trim(), start_time: document.getElementById('editTaskStart').value, end_time: document.getElementById('editTaskEnd').value, urgency: urgency, attachments: window._editTaskAttachments||[] };
  if(task&&task.can_edit_status_assignee){ payload.status=document.getElementById('editTaskStatus').value; payload.current_assignee=document.getElementById('editTaskAssignee').value; }
  fetch('/admin/projects/'+PROJECT_ID+'/tasks/'+id, { method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload), credentials:'same-origin' }).then(r=>r.json()).then(function(d){ if(d.error){ alert(d.error); return; } var task=(window._allTasks||[]).find(function(x){ return x.id===id; }); if(task){ task.urgency=urgency; task.title=payload.title; task.content=payload.content; task.start_time=payload.start_time; task.end_time=payload.end_time; if(payload.status!==undefined) task.status=payload.status; if(payload.current_assignee!==undefined) task.current_assignee=payload.current_assignee; task.attachments=payload.attachments||[]; } document.getElementById('editTaskModal').classList.add('hidden'); loadTasks(); alert('已保存'); });
}
loadTasks();
</script>
'''


def _role_to_first_assignee(project_id, role):
    """兼容：旧任务按角色，返回第一个该角色的参与人作为 current_assignee。"""
    proj = projects_db.get(project_id) or {}
    mr = proj.get('member_roles') or {}
    for u, r in mr.items():
        if r == role:
            return u
    return list(mr.keys())[0] if mr else ''


# ---------- 操作日志 ----------
# 敏感操作（用于行高亮）
AUDIT_SENSITIVE_ACTIONS = {'delete_user', 'delete_project', 'task_delete', 'task_batch_delete'}


def _filter_audit_entries(entries, user_filter, action_filter, date_from, date_to, keyword=None):
    """兼容旧调用，转发到 service 层。"""
    return audit_service.filter_entries(entries, user_filter, action_filter, date_from, date_to, keyword or '')


@bp.route('/admin/audit-log')
@admin_required('audit_log')
def admin_audit_log_page():
    from flask import request
    user_filter = (request.args.get('user') or '').strip()
    action_filter = (request.args.get('action') or '').strip()
    date_from = (request.args.get('date_from') or '').strip()[:10]
    date_to = (request.args.get('date_to') or '').strip()[:10]
    keyword = (request.args.get('keyword') or '').strip()
    page = max(0, int(request.args.get('page') or 0))
    page_size = min(100, max(20, int(request.args.get('page_size') or 50)))
    entries = list(reversed(audit_log_db))
    entries = _filter_audit_entries(entries, user_filter, action_filter, date_from, date_to, keyword)
    total = len(entries)
    entries = entries[page * page_size:(page + 1) * page_size]
    actions_set = sorted(set(e.get('action', '') or '' for e in audit_log_db))
    action_opts = ''.join(
        f'<option value="{html.escape(a)}"' + (' selected' if a == action_filter else '') + f'>{html.escape(a) or "（空）"}</option>'
        for a in actions_set if a is not None
    )
    users_set = sorted(set((e.get('user') or '').strip() for e in audit_log_db if (e.get('user') or '').strip()))
    user_opts = ''.join(
        f'<option value="{html.escape(u)}"' + (' selected' if u == user_filter else '') + f'>{html.escape(u)}</option>'
        for u in users_set
    )
    rows = []
    for e in entries:
        action = e.get('action', '-')
        sensitive = 'bg-red-50 border-l-4 border-l-red-400' if action in AUDIT_SENSITIVE_ACTIONS else ''
        badge_cls = 'px-2 py-1 rounded text-xs bg-red-100 text-red-800' if action in AUDIT_SENSITIVE_ACTIONS else 'px-2 py-1 rounded text-xs bg-gray-100'
        rows.append(
            f'<tr class="{sensitive}"><td class="px-6 py-4 text-sm text-gray-500">{html.escape((e.get("timestamp") or "-")[:19])}</td>'
            f'<td class="px-6 py-4">{html.escape(e.get("user") or "-")}</td>'
            f'<td class="px-6 py-4"><span class="{badge_cls}">{html.escape(action)}</span></td>'
            f'<td class="px-6 py-4 text-sm text-gray-600">{html.escape(str(e.get("details") or "-"))}</td>'
            f'<td class="px-6 py-4 text-sm text-gray-500">{html.escape(e.get("ip") or "-")}</td></tr>'
        )
    rows_html = ''.join(rows)
    export_params = '&'.join([f'{k}={quote(v)}' for k, v in [('user', user_filter), ('action', action_filter), ('date_from', date_from), ('date_to', date_to), ('keyword', keyword)] if v])
    export_params = '?' + export_params if export_params else ''
    pagination = ''
    if total > page_size:
        prev_dis = ' disabled' if page == 0 else ''
        next_dis = ' disabled' if (page + 1) * page_size >= total else ''
        base = f'/admin/audit-log?user={quote(user_filter)}&action={quote(action_filter)}&date_from={quote(date_from)}&date_to={quote(date_to)}&keyword={quote(keyword)}&page_size={page_size}'
        pagination = f'<div class="px-4 py-3 border-t flex justify-between items-center text-sm"><span class="text-gray-500">共 {total} 条，第 {page+1} 页（每页 {page_size} 条）</span><div><a href="{base}&page={page-1}" class="px-3 py-1 rounded border mr-2{prev_dis}">上一页</a><a href="{base}&page={page+1}" class="px-3 py-1 rounded border{next_dis}">下一页</a></div></div>'
    content = f'''
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div class="p-4 border-b bg-gray-50/50">
            <h2 class="text-lg font-semibold text-gray-800 mb-3">操作记录</h2>
            <form method="get" action="/admin/audit-log" class="flex flex-wrap gap-3 items-end">
                <div><label class="block text-xs text-gray-500 mb-1">关键字</label><input type="text" name="keyword" value="{html.escape(keyword)}" placeholder="用户/操作/详情/IP" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm w-40"></div>
                <div><label class="block text-xs text-gray-500 mb-1">用户</label><select name="user" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm"><option value="">全部</option>{user_opts}</select></div>
                <div><label class="block text-xs text-gray-500 mb-1">操作类型</label><select name="action" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm"><option value="">全部</option>{action_opts}</select></div>
                <div><label class="block text-xs text-gray-500 mb-1">开始日期</label><input type="date" name="date_from" value="{html.escape(date_from)}" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm"></div>
                <div><label class="block text-xs text-gray-500 mb-1">结束日期</label><input type="date" name="date_to" value="{html.escape(date_to)}" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm"></div>
                <input type="hidden" name="page_size" value="{page_size}">
                <button type="submit" class="px-4 py-1.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700">筛选</button>
                <a href="/admin/audit-log/export{export_params}" class="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700">导出 CSV</a>
            </form>
            <p class="text-xs text-gray-500 mt-2">支持关键字搜索（用户、操作、详情、IP）；分页展示；敏感操作以红底标出。</p>
        </div>
        <div class="overflow-x-auto">
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50"><tr>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">时间</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">用户</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">操作</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">详情</th>
                    <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">IP</th>
                </tr></thead>
                <tbody class="bg-white divide-y divide-gray-200">{rows_html}</tbody>
            </table>
        </div>
        {pagination}
    </div>'''
    return _admin_layout(content, '操作日志')


# ---------- 通知中心 ----------


@bp.route('/admin/notifications')
@admin_required('notifications')
def admin_notifications_page():
    username = _current_username()
    type_filter = request.args.get('type', '').strip()
    view_model = notification_page_service.build_notifications_view_model(username, type_filter)
    type_opts = view_model['type_options']
    rows_html = view_model['rows_html']
    content = f'''
    <section class="space-y-5">
        <div>
            <p class="text-[11px] font-semibold text-slate-500 tracking-[0.16em] uppercase">消息中心</p>
            <h2 class="text-xl font-semibold text-slate-900 mt-1">通知列表</h2>
            <p class="text-sm text-slate-500 mt-1">任务分配、审批结果、构建完成等提醒，支持按类型筛选与全部标为已读。</p>
        </div>
    <div class="bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden">
        <div class="p-4 border-b border-slate-100 flex flex-wrap gap-3 items-center">
            <h3 class="text-sm font-semibold text-slate-900">通知</h3>
            <form method="get" action="/admin/notifications" class="flex gap-2 items-center">
                <select name="type" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm" onchange="this.form.submit()">{type_opts}</select>
            </form>
            <button type="button" onclick="markAllRead()" class="px-3 py-1.5 bg-indigo-100 text-indigo-700 rounded-lg text-sm font-medium hover:bg-indigo-200">全部标为已读</button>
        </div>
        <div class="overflow-x-auto">
            <table class="min-w-full"><thead class="bg-gray-50"><tr>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">时间</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">类型</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">标题</th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">操作</th>
            </tr></thead><tbody>{rows_html}</tbody></table>
        </div>
    </div>
    </section>
    <script>
    function markRead(id) {{ fetch("/admin/notifications/" + id + "/read", {{ method: "POST", credentials: "same-origin" }}).then(function(r) {{ if (r.ok) location.reload(); }}); }}
    function markAllRead() {{ fetch("/admin/notifications/read-all", {{ method: "POST", credentials: "same-origin" }}).then(function(r) {{ if (r.ok) location.reload(); }}); }}
    </script>'''
    return _admin_layout(content, '通知中心')


# ---------- 审批管理 ----------
@bp.route('/admin/approval')
@admin_required('approval')
def admin_approval_page():
    username = _current_username()
    selected_project_id = resolve_project_id((request.args.get('project_id') or '').strip()) or ''
    pending = get_pending_approvals_for_user(username)
    my_list = [a for a in approvals_db if a.get('applicant') == username]
    def approval_project_id(approval):
        explicit_project_id = resolve_project_id((approval or {}).get('project_id')) or ''
        if explicit_project_id:
            return explicit_project_id
        inferred_project_id = _approval_project_id(approval)
        return resolve_project_id(inferred_project_id) or str(inferred_project_id or '').strip()
    if selected_project_id:
        pending = [a for a in pending if approval_project_id(a) == selected_project_id]
        my_list = [a for a in my_list if approval_project_id(a) == selected_project_id]
    my_list.sort(key=lambda x: x.get('updated_at') or x.get('created_at') or '', reverse=True)
    type_labels = dict(APPROVAL_TYPES)
    project_choices = _visible_project_choices(username)
    project_opts = ''.join(
        f'<option value="{html.escape(item["id"])}">{html.escape(item["name"])}</option>'
        for item in project_choices
    )
    project_filter_opts = ''.join(
        f'<option value="{html.escape(item["id"])}"' + (' selected' if selected_project_id == item['id'] else '') + f'>{html.escape(item["name"])}</option>'
        for item in ([{'id': '', 'name': '全部项目'}] + project_choices)
    )

    def project_label(project_id):
        resolved_id = resolve_project_id(project_id)
        payload = (projects_db.get(resolved_id) if resolved_id else None) or {}
        return _clean_display_text(payload.get('name') if isinstance(payload, dict) else '', resolved_id or project_id or '未绑定项目')

    def row_pending(a):
        aid = a.get('id', '')
        type_name = _clean_display_text(type_labels.get(a.get('type', ''), a.get('type', '')), '审批事项')
        target_type = _clean_display_text(a.get("target_type"), "对象")
        target_id = _clean_display_text(a.get("target_id"), "未命名对象")
        reason = _clean_display_text(a.get("reason"), "未填写申请说明")
        project_name = project_label(approval_project_id(a))
        target_text = _clean_display_text(a.get('target_id'), 'ID')
        type_text = _clean_display_text(type_labels.get(a.get('type', ''), a.get('type', '')), '\u5ba1\u6279\u4e8b\u9879')
        return (
            f'<tr><td class="px-4 py-3 text-sm">{(a.get("created_at") or "")[:19].replace("T", " ")}</td>'
            f'<td class="px-4 py-3"><span class="rounded bg-gray-100 px-2 py-0.5 text-xs">{html.escape(type_name)}</span></td>'
            f'<td class="px-4 py-3">{html.escape(_clean_display_text(a.get("applicant"), "-"))}</td>'
            f'<td class="px-4 py-3 text-sm">{html.escape(project_name)}</td>'
            f'<td class="px-4 py-3 text-sm">{html.escape(target_type + " / " + target_id)}</td>'
            f'<td class="px-4 py-3 text-sm">{html.escape(reason)[:80]}</td>'
            f'<td class="px-4 py-3"><button type="button" onclick="approve(\'{aid}\', true)" class="rounded px-2 py-1 text-sm text-green-600 hover:bg-green-50">\u901a\u8fc7</button> '
            f'<button type="button" onclick="approve(\'{aid}\', false)" class="rounded px-2 py-1 text-sm text-red-600 hover:bg-red-50">\u9a73\u56de</button></td></tr>'
        )

    pending_html = ''.join(row_pending(a) for a in pending[:50]) if pending else '<tr><td colspan="7" class="px-4 py-8 text-center text-gray-500">\u6682\u65e0\u5f85\u5ba1\u6279</td></tr>'

    def row_my(a):
        status = a.get('status', '')
        status_labels = {'pending': '\u5f85\u5ba1\u6279', 'approved': '\u5df2\u901a\u8fc7', 'rejected': '\u5df2\u9a73\u56de'}
        status_text = status_labels.get(status, status)
        status_cls = 'text-green-600' if status == 'approved' else ('text-red-600' if status == 'rejected' else 'text-amber-600')
        project_name = project_label(approval_project_id(a))
        return (
            f'<tr><td class="px-4 py-3 text-sm">{(a.get("created_at") or "")[:19].replace("T", " ")}</td>'
            f'<td class="px-4 py-3">{html.escape(_clean_display_text(type_labels.get(a.get("type",""), a.get("type","")), "审批事项"))}</td>'
            f'<td class="px-4 py-3 text-sm">{html.escape(_clean_display_text(a.get("target_id"), "未命名对象"))}</td>'
            f'<td class="px-4 py-3"><span class="{status_cls}">{html.escape(status_text)}</span></td></tr>'
        )

    my_html = ''.join(row_my(a) for a in my_list[:50]) if my_list else '<tr><td colspan="4" class="px-4 py-8 text-center text-gray-500">\u6682\u65e0\u7533\u8bf7\u8bb0\u5f55</td></tr>'
    type_opts = ''.join(f'<option value="{t}">{html.escape(l)}</option>' for t, l in APPROVAL_TYPES)
    content = f'''
    <section class="space-y-6">
        <div>
            <p class="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">\u53d1\u5e03\u7ba1\u63a7</p>
            <h2 class="mt-1 text-xl font-semibold text-slate-900">\u5ba1\u6279\u7ba1\u7406</h2>
            <p class="mt-1 text-sm text-slate-500">\u5904\u7406\u7248\u672c\u53d1\u5e03\u3001\u654f\u611f\u64cd\u4f5c\u7b49\u5ba1\u6279\u7533\u8bf7\uff1b\u6709 approval.manage \u6743\u9650\u8005\u53ef\u6267\u884c\u901a\u8fc7\u6216\u9a73\u56de\u3002</p>
        </div>
        <form class="flex flex-wrap items-end gap-3 rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm" method="get">
            <div>
                <label class="mb-1 block text-xs text-gray-500">\u6309\u9879\u76ee\u67e5\u770b</label>
                <select name="project_id" class="w-64 rounded-lg border px-3 py-1.5 text-sm">{project_filter_opts}</select>
            </div>
            <button type="submit" class="rounded-lg bg-slate-900 px-4 py-1.5 text-sm font-medium text-white">\u7b5b\u9009</button>
            <a href="/admin/approval" class="rounded-lg border border-slate-200 px-4 py-1.5 text-sm font-medium text-slate-700">\u91cd\u7f6e</a>
        </form>
        <div id="approvalFeedback" class="hidden rounded-2xl border px-4 py-3">
            <div class="flex items-start gap-2">
                <div id="approvalFeedbackIcon" class="mt-0.5 text-sm text-slate-600"><i class="fas fa-circle-info"></i></div>
                <div class="min-w-0 flex-1"><p id="approvalFeedbackText" class="text-sm font-medium text-slate-800"></p></div>
            </div>
        </div>
        <div class="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
            <div class="border-b border-slate-100 p-4"><h3 class="text-sm font-semibold text-slate-900">\u5f85\u6211\u5ba1\u6279</h3></div>
            <div class="overflow-x-auto">
                <table class="min-w-full"><thead class="bg-gray-50"><tr>
                    <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">\u7533\u8bf7\u65f6\u95f4</th>
                    <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">\u7c7b\u578b</th>
                    <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">\u7533\u8bf7\u4eba</th>
                    <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">\u9879\u76ee</th>
                    <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">\u5bf9\u8c61</th>
                    <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">\u8bf4\u660e</th>
                    <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">\u64cd\u4f5c</th>
                </tr></thead><tbody>{pending_html}</tbody></table>
            </div>
        </div>
        <div class="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
            <div class="flex items-center justify-between border-b border-slate-100 p-4">
                <h3 class="text-sm font-semibold text-slate-900">\u6211\u7684\u7533\u8bf7</h3>
                <button type="button" onclick="document.getElementById('createApprovalForm').classList.toggle('hidden')" class="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700">+ \u53d1\u8d77\u7533\u8bf7</button>
            </div>
            <div id="createApprovalForm" class="hidden border-b bg-gray-50/50 p-4">
                <form onsubmit="return submitApproval(event)">
                    <div class="mb-3 grid grid-cols-1 gap-3 md:grid-cols-3">
                        <div><label class="mb-1 block text-xs text-gray-500">\u5ba1\u6279\u7c7b\u578b</label><select id="approvalType" class="w-full rounded-lg border px-3 py-1.5 text-sm" required>{type_opts}</select></div>
                        <div><label class="mb-1 block text-xs text-gray-500">\u6240\u5c5e\u9879\u76ee</label><select id="approvalProjectId" class="w-full rounded-lg border px-3 py-1.5 text-sm"><option value="">\u672a\u7ed1\u5b9a\u9879\u76ee</option>{project_opts}</select></div>
                        <div><label class="mb-1 block text-xs text-gray-500">\u5173\u8054\u5bf9\u8c61 ID\uff08\u5982\u9879\u76ee ID\u3001\u7248\u672c\u53f7\uff09</label><input type="text" id="approvalTargetId" class="w-full rounded-lg border px-3 py-1.5 text-sm" placeholder="\u5982 MyProject \u6216 1.0.0"></div>
                    </div>
                    <div class="mb-3"><label class="mb-1 block text-xs text-gray-500">\u7533\u8bf7\u8bf4\u660e</label><input type="text" id="approvalReason" class="w-full rounded-lg border px-3 py-1.5 text-sm" placeholder="\u7b80\u8981\u8bf4\u660e"></div>
                    <button type="submit" class="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white">\u63d0\u4ea4</button>
                </form>
            </div>
            <div class="overflow-x-auto">
                <table class="min-w-full"><thead class="bg-gray-50"><tr>
                    <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">\u7533\u8bf7\u65f6\u95f4</th>
                    <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">\u7c7b\u578b</th>
                    <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">\u5bf9\u8c61</th>
                    <th class="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">\u72b6\u6001</th>
                </tr></thead><tbody>{my_html}</tbody></table>
            </div>
        </div>
        <div id="approveModal" class="fixed inset-0 z-50 hidden items-center justify-center bg-black/50 p-4">
            <div class="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
                <h3 class="mb-2 font-semibold">\u5ba1\u6279\u610f\u89c1</h3>
                <input type="hidden" id="approveId">
                <input type="hidden" id="approveAction">
                <textarea id="approveComment" class="mb-4 w-full rounded-lg border px-3 py-1.5 text-sm" rows="2" placeholder="\u9009\u586b"></textarea>
                <div class="flex gap-2"><button type="button" onclick="submitApprove()" class="flex-1 rounded-lg bg-indigo-600 py-1.5 text-sm text-white">\u786e\u5b9a</button><button type="button" onclick="document.getElementById('approveModal').classList.add('hidden')" class="rounded-lg border px-4 py-1.5 text-sm">\u53d6\u6d88</button></div>
            </div>
        </div>
        <meta name="csrf-token" content="{html.escape(_get_csrf_token())}">
        <script>
        var approvalTokenEl = document.querySelector('meta[name="csrf-token"]');
        var approvalCsrfHeaders = {{}};
        if (approvalTokenEl && approvalTokenEl.content) approvalCsrfHeaders['X-CSRFToken'] = approvalTokenEl.content;
        function showApprovalFeedback(kind, message) {{
            var box = document.getElementById('approvalFeedback');
            var text = document.getElementById('approvalFeedbackText');
            var icon = document.getElementById('approvalFeedbackIcon');
            if (!box || !text || !icon) return;
            box.classList.remove('hidden', 'border-green-200', 'bg-green-50', 'border-red-200', 'bg-red-50', 'border-slate-200', 'bg-slate-50');
            if (kind === 'success') {{
                box.classList.add('border-green-200', 'bg-green-50');
                icon.className = 'mt-0.5 text-sm text-green-600';
                icon.innerHTML = '<i class="fas fa-circle-check"></i>';
            }} else if (kind === 'error') {{
                box.classList.add('border-red-200', 'bg-red-50');
                icon.className = 'mt-0.5 text-sm text-red-600';
                icon.innerHTML = '<i class="fas fa-circle-exclamation"></i>';
            }} else {{
                box.classList.add('border-slate-200', 'bg-slate-50');
                icon.className = 'mt-0.5 text-sm text-slate-600';
                icon.innerHTML = '<i class="fas fa-circle-info"></i>';
            }}
            text.textContent = message || '';
        }}
        function approve(id, isApprove) {{
            document.getElementById('approveId').value = id;
            document.getElementById('approveAction').value = isApprove ? 'approve' : 'reject';
            document.getElementById('approveModal').classList.remove('hidden');
        }}
        function submitApprove() {{
            var id = document.getElementById('approveId').value;
            var action = document.getElementById('approveAction').value;
            var comment = document.getElementById('approveComment').value;
            fetch('/admin/approval/' + id + '/' + action, {{ method: 'POST', headers: Object.assign({{ 'Content-Type': 'application/json' }}, approvalCsrfHeaders), credentials: 'same-origin', body: JSON.stringify({{ comment: comment }}) }})
                .then(function(r) {{ return r.json(); }})
                .then(function(d) {{
                    if (d.error) {{ showApprovalFeedback('error', d.error); return; }}
                    showApprovalFeedback('success', action === 'approve' ? '\u5ba1\u6279\u5df2\u901a\u8fc7\uff0c\u5217\u8868\u5373\u5c06\u5237\u65b0\u3002' : '\u5ba1\u6279\u5df2\u9a73\u56de\uff0c\u5217\u8868\u5373\u5c06\u5237\u65b0\u3002');
                    setTimeout(function() {{ location.reload(); }}, 700);
                }});
            document.getElementById('approveModal').classList.add('hidden');
        }}
        function submitApproval(e) {{
            e.preventDefault();
            var type = document.getElementById('approvalType').value;
            var projectId = document.getElementById('approvalProjectId').value;
            var targetId = document.getElementById('approvalTargetId').value;
            var reason = document.getElementById('approvalReason').value;
            if (!targetId.trim()) {{ showApprovalFeedback('error', '\u8bf7\u586b\u5199\u5173\u8054\u5bf9\u8c61 ID'); return false; }}
            fetch('/admin/approval/create', {{ method: 'POST', headers: Object.assign({{ 'Content-Type': 'application/json' }}, approvalCsrfHeaders), credentials: 'same-origin', body: JSON.stringify({{ type: type, target_type: type, target_id: targetId, reason: reason, project_id: projectId }}) }})
                .then(function(r) {{ return r.json(); }})
                .then(function(d) {{
                    if (d.error) {{ showApprovalFeedback('error', d.error); }}
                    else {{ showApprovalFeedback('success', '\u5ba1\u6279\u7533\u8bf7\u5df2\u63d0\u4ea4\uff0c\u5217\u8868\u5373\u5c06\u5237\u65b0\u3002'); setTimeout(function() {{ location.reload(); }}, 700); }}
                }});
            return false;
        }}
        </script>
    </section>'''
    return _admin_layout(content, '\u5ba1\u6279\u7ba1\u7406')


# ---------- 报表中心 ----------
@bp.route('/admin/reports')
@admin_required('reports')
def admin_reports_page():
    username = _current_username()
    selected_project_id = resolve_project_id((request.args.get('project_id') or '').strip()) or ''
    project_choices = _visible_project_choices(username)

    def project_label(project_id):
        resolved_id = resolve_project_id(project_id)
        payload = (projects_db.get(resolved_id) if resolved_id else None) or {}
        return _clean_display_text(payload.get('name') if isinstance(payload, dict) else '', resolved_id or project_id or '全部项目')
    def template_project_id(item):
        return resolve_project_id((((item.get('config') or {}).get('project_id')) or item.get('project_id') or '').strip()) or ''

    all_templates = list(report_templates_db)
    template_project_map = {
        str(item.get('id') or '').strip(): template_project_id(item)
        for item in all_templates
        if isinstance(item, dict)
    }
    templates = list(all_templates)
    if selected_project_id:
        templates = [item for item in templates if template_project_id(item) == selected_project_id]
    templates.sort(key=lambda x: x.get('created_at') or '', reverse=True)
    recs = [r for r in export_records_db if r.get('user') == username][-50:]
    def export_project_id(item):
        resolved = resolve_project_id((item.get('project_id') or ((item.get('params') or {}).get('project_id')) or '').strip()) or ''
        if resolved:
            return resolved
        template_id = str(item.get('template_id') or '').strip()
        return template_project_map.get(template_id, '')
    if selected_project_id:
        recs = [item for item in recs if export_project_id(item) == selected_project_id]
    recs.reverse()
    project_filter_opts = ''.join(
        f'<option value="{html.escape(item["id"])}"' + (' selected' if selected_project_id == item['id'] else '') + f'>{html.escape(item["name"])}</option>'
        for item in ([{'id': '', 'name': '\u5168\u90e8\u9879\u76ee'}] + project_choices)
    )
    project_create_opts = project_filter_opts
    report_filter_html = (
        '<form class="flex flex-wrap items-end gap-3 rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm" method="get">'
        '<div><label class="mb-1 block text-xs text-gray-500">\u6309\u9879\u76ee\u67e5\u770b</label>'
        f'<select name="project_id" class="w-64 rounded-lg border px-3 py-1.5 text-sm">{project_filter_opts}</select></div>'
        '<button type="submit" class="rounded-lg bg-slate-900 px-4 py-1.5 text-sm font-medium text-white">\u7b5b\u9009</button>'
        '<a href="/admin/reports" class="rounded-lg border border-slate-200 px-4 py-1.5 text-sm font-medium text-slate-700">\u91cd\u7f6e</a>'
        '</form>'
    )
    project_filter_opts = ''.join(
        f'<option value="{html.escape(item["id"])}"' + (' selected' if selected_project_id == item['id'] else '') + f'>{html.escape(item["name"])}</option>'
        for item in ([{'id': '', 'name': '全部项目'}] + project_choices)
    )
    trows = ''.join(
        f'<tr><td class="px-4 py-3">{html.escape(t.get("name") or "")}</td><td class="px-4 py-3 text-sm">{html.escape(project_label(template_project_id(t)))}</td><td class="px-4 py-3 text-sm text-gray-500">{html.escape((t.get("created_at") or "")[:19])}</td>'
        f'<td class="px-4 py-3"><a href="/admin/reports/run/{t.get("id")}" class="text-indigo-600 hover:underline">一键生成</a></td></tr>'
        for t in templates[:20]
    ) if templates else '<tr><td colspan="3" class="px-4 py-8 text-center text-gray-500">暂无模板，请先创建</td></tr>'
    rrows = ''.join(
        f'<tr><td class="px-4 py-1.5 text-sm">{(r.get("exported_at") or "")[:19]}</td><td class="px-4 py-1.5 text-sm">{html.escape(r.get("template_name") or "")}</td><td class="px-4 py-1.5 text-sm">{html.escape(project_label(export_project_id(r)))}</td><td class="px-4 py-1.5 text-sm">{r.get("format", "csv")}</td></tr>'
        for r in recs
    ) if recs else '<tr><td colspan="3" class="px-4 py-8 text-center text-gray-500">暂无导出记录</td></tr>'
    content = f'''
    <section class="space-y-6">
        <div>
            <p class="text-[11px] font-semibold text-slate-500 tracking-[0.16em] uppercase">数据与洞察</p>
            <h2 class="text-xl font-semibold text-slate-900 mt-1">报表中心</h2>
            <p class="text-sm text-slate-500 mt-1">创建报表模板、一键生成 CSV；亦可跳转至数据分析页导出。导出记录便于追溯。</p>
        </div>
    {report_filter_html}
    <div class="bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden">
        <div class="p-4 border-b border-slate-100 flex justify-between items-center">
            <h3 class="text-sm font-semibold text-slate-900">报表模板</h3>
            <a href="/dashboard/export" class="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200">数据分析 · 导出 CSV</a>
        </div>
        <div class="p-4 border-b bg-gray-50/50">
            <form id="reportTemplateForm" class="flex flex-wrap gap-3 items-end">
                <div><label class="block text-xs text-gray-500 mb-1">\u6240\u5c5e\u9879\u76ee</label><select id="tplProjectId" class="px-3 py-1.5 border rounded-lg text-sm min-w-[220px]">{project_create_opts}</select></div>
                <div><label class="block text-xs text-gray-500 mb-1">模板名称</label><input type="text" id="tplName" class="px-3 py-1.5 border rounded-lg text-sm" placeholder="如：周报汇总" required></div>
                <div><label class="block text-xs text-gray-500 mb-1">说明</label><input type="text" id="tplDesc" class="px-3 py-1.5 border rounded-lg text-sm" placeholder="选填"></div>
                <button type="submit" class="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700">创建模板</button>
            </form>
        </div>
        <div class="overflow-x-auto">
            <table class="min-w-full"><thead class="bg-gray-50"><tr><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">名称</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">创建时间</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">操作</th></tr></thead><tbody>{trows}</tbody></table>
        </div>
    </div>
    <div class="bg-white rounded-2xl shadow-sm border border-slate-200/80 overflow-hidden">
        <div class="p-4 border-b border-slate-100"><h3 class="text-sm font-semibold text-slate-900">导出记录</h3></div>
        <div class="overflow-x-auto">
            <table class="min-w-full"><thead class="bg-gray-50"><tr><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">导出时间</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">模板</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">格式</th></tr></thead><tbody>{rrows}</tbody></table>
        </div>
    </div>
    </section>
    <script>
    document.getElementById("reportTemplateForm").onsubmit = function(e) {{
        e.preventDefault();
        var name = document.getElementById("tplName").value.trim();
        var desc = document.getElementById("tplDesc").value.trim();
        var projectId = document.getElementById("tplProjectId").value;
        fetch("/admin/reports/templates", {{ method: "POST", headers: {{ "Content-Type": "application/json" }}, credentials: "same-origin", body: JSON.stringify({{ name: name, description: desc, project_id: projectId, config: {{ project_id: projectId }} }}) }})
        .then(function(r) {{ return r.json(); }}).then(function(d) {{ if (d.error) alert(d.error); else location.reload(); }});
        return false;
    }};
    </script>'''
    content = content.replace(
        '<th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">名称</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">创建时间</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">操作</th>',
        '<th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">名称</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">项目</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">创建时间</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">操作</th>',
        1
    )
    content = content.replace(
        '<th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">导出时间</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">模板</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">格式</th>',
        '<th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">导出时间</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">模板</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">项目</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">格式</th>',
        1
    )
    content = content.replace('colspan="3"', 'colspan="4"')
    return _admin_layout(content, '报表中心')


# ---------- 系统设置 ----------
DEFAULT_SYSTEM_KEYS = [
    ('LOGIN_ATTEMPTS_LIMIT', '登录失败次数上限', 'number', '5', '超过此次数将锁定账号'),
    ('LOGIN_LOCKOUT_MINUTES', '锁定时长（分钟）', 'number', '15', '锁定后等待分钟数'),
    ('AUDIT_LOG_RETENTION_DAYS', '操作日志保留天数', 'number', '365', '超期可归档或清理'),
    ('NOTIFICATION_SITE_ENABLED', '站内通知开关', 'boolean', 'true', '是否启用站内通知'),
    ('PASSWORD_MIN_LENGTH', '密码最小长度', 'number', '6', '新建/重置密码时的最小长度'),
    ('REQUIRE_APPROVAL_FOR_DELETE', '高危操作需审批', 'boolean', 'false', '开启后：删除项目、删除版本、删除 Jenkins 实例需先提交审批并通过'),
    ('webhook_url', 'Webhook URL', 'string', '', '构建/版本等事件推送地址，留空不启用'),
    ('USE_SQLITE', '启用 SQLite', 'boolean', 'true', '核心 JSON 数据与审计日志同步到 SQLite，便于长期留存与恢复'),
]


def _password_min_length():
    v = get_system_config('PASSWORD_MIN_LENGTH')
    try:
        return max(4, int(v)) if v is not None and str(v).strip() else 6
    except (ValueError, TypeError):
        return 6


def _register_split_api_routes():
    register_media_api_routes(bp)
    register_site_config_api_routes(bp, _visual_editor_normalize_modules)
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


@bp.route('/admin/settings')
@admin_required('system_settings')
def admin_settings_page():
    import sys
    values = {}
    for key, *_ in DEFAULT_SYSTEM_KEYS:
        v = get_system_config(key)
        if v is not None:
            values[key] = v
        else:
            if key == 'LOGIN_ATTEMPTS_LIMIT':
                values[key] = getattr(Config, 'LOGIN_ATTEMPTS_LIMIT', 5)
            elif key == 'LOGIN_LOCKOUT_MINUTES':
                values[key] = getattr(Config, 'LOGIN_LOCKOUT_MINUTES', 15)
            elif key == 'webhook_url':
                values[key] = get_system_config('webhook_url') or ''
            elif key == 'USE_SQLITE':
                values[key] = get_system_config('USE_SQLITE') or 'false'
            elif key == 'REQUIRE_APPROVAL_FOR_DELETE':
                values[key] = get_system_config('REQUIRE_APPROVAL_FOR_DELETE') or 'false'
            else:
                values[key] = '365' if key == 'AUDIT_LOG_RETENTION_DAYS' else 'true'
    rows = []
    for key, label, vtype, default, desc in DEFAULT_SYSTEM_KEYS:
        val = values.get(key, default)
        if key == 'webhook_url':
            val = get_system_config('webhook_url') or default
        if vtype == 'boolean':
            inp = f'<input type="checkbox" name="{key}" value="true" class="rounded" ' + ('checked' if str(val).lower() in ('true', '1', 'yes') else '') + '>'
        elif vtype == 'string':
            inp = f'<input type="text" name="{key}" value="{html.escape(str(val))}" class="w-full max-w-md px-3 py-1.5 border rounded-lg text-sm" placeholder="https://...">'
        else:
            inp = f'<input type="number" name="{key}" value="{html.escape(str(val))}" class="w-32 px-3 py-1.5 border rounded-lg text-sm" min="1">'
        rows.append(f'<tr><td class="px-4 py-3 font-medium text-gray-700">{html.escape(label)}</td><td class="px-4 py-3">{inp}</td><td class="px-4 py-3 text-sm text-gray-500">{html.escape(desc)}</td></tr>')
    table_rows = ''.join(rows)
    content = f'''
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden mb-6">
        <div class="p-6 border-b">
            <h2 class="text-lg font-semibold text-gray-800">登录与安全</h2>
            <p class="text-sm text-gray-500 mt-1">修改后立即生效。</p>
        </div>
        <form id="settingsForm" class="p-6">
            <table class="min-w-full"><thead class="bg-gray-50"><tr><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">配置项</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">值</th><th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">说明</th></tr></thead><tbody>{table_rows}</tbody></table>
            <button type="submit" class="mt-4 px-4 py-1.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700">保存</button>
        </form>
    </div>
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        <div class="p-6 border-b"><h3 class="font-medium text-gray-700">环境信息（只读）</h3></div>
        <div class="p-6">
            <ul class="text-sm text-gray-600 space-y-1">
                <li>Python: {sys.version.split()[0]}</li>
                <li>数据目录: {html.escape(DATA_DIR)}</li>
                <li>APK 目录: {html.escape(Config.APK_DIR)}</li>
            </ul>
        </div>
    </div>
    <script>
    document.getElementById("settingsForm").onsubmit = function(e) {{
        e.preventDefault();
        var form = this;
        var data = {{}};
        [].forEach.call(form.querySelectorAll("input[name]"), function(inp) {{
            if (inp.type === "checkbox") data[inp.name] = inp.checked ? "true" : "false";
            else data[inp.name] = inp.value;
        }});
        fetch("/admin/settings/save", {{ method: "POST", headers: {{ "Content-Type": "application/json" }}, credentials: "same-origin", body: JSON.stringify(data) }})
        .then(function(r) {{ return r.json(); }}).then(function(d) {{ if (d.error) alert(d.error); else alert("已保存"); }});
    }};
    </script>'''
    return _admin_layout(content, '系统设置')

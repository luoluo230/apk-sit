# -*- coding: utf-8 -*-
"""Admin dashboard rendering helpers."""

import html as html_module
from datetime import date

from data.audit import audit_log_db
from data.builds import load_jenkins_instances
from data.packages import extract_package_info, get_platform_label, iter_package_files
from data.projects import can_view_project, projects_db
from data.tasks import project_tasks_db
from data.approvals import get_pending_approvals_for_user
from data.notifications import get_notifications_for_user
from data.versions import (
    get_version_platform,
    project_versions_db,
    version_has_apk,
    version_is_recommended,
)


def _clean_display_text(value, fallback=''):
    text = '' if value is None else str(value).strip()
    if not text:
        return fallback
    question_ratio = text.count('?') / max(len(text), 1)
    if question_ratio >= 0.35 or '锟' in text or '�' in text:
        return fallback or text.replace('?', '').strip() or fallback
    return text


def admin_panel_descriptions():
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


def render_module_card(link, icon, color, title, description):
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


def render_grouped_admin_sections(sections):
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


def render_admin_dashboard_v2(summary_cards, quick_actions, todo_html, risk_html, audit_html, recent_package_rows, package_counts, cards):
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


def render_admin_panel_dashboard(visible, desc, username, admin_layout):
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
    from services import jenkins_manager as jm
    jenkins_instances = jm.list_instances()
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

    grouped_cards['project'].append(
        render_module_card('/admin/projects', 'fa-folder-tree', 'text-green-600', '项目管理总览', '创建/编辑项目，并从项目列表进入各项目工作台。')
    )
    grouped_cards['project'].append(
        render_module_card('/admin/my-tasks', 'fa-list-check', 'text-indigo-600', '我的任务', '查看与处理分配给我的项目任务。')
    )
    if any(mid in ('jenkins', 'build') for mid, _, _ in visible_sorted):
        grouped_cards['project'].append(
            render_module_card('/admin/jenkins', 'fa-server', 'text-orange-600', 'Jenkins 实例管理', '创建/维护 Jenkins 实例与构建可用性。')
        )
        grouped_cards['project'].append(
            render_module_card('/admin/jenkins#unity-catalog', 'fa-cube', 'text-violet-600', 'Unity 版本库', '在 Jenkins 管理内维护有效/失效、分类与备注；供构建与版本编辑下拉选用。')
        )

    if any(mid == 'approval' for mid, _, _ in visible_sorted):
        grouped_cards['governance'].append(render_module_card('/admin/approval', 'fa-check-double', 'text-emerald-500', '审批与发布管控', desc.get('approval', '')))
    if any(mid == 'notifications' for mid, _, _ in visible_sorted):
        grouped_cards['governance'].append(render_module_card('/admin/notifications', 'fa-bell', 'text-amber-500', '通知与消息中心', desc.get('notifications', '')))
    if any(mid == 'reports' for mid, _, _ in visible_sorted):
        grouped_cards['governance'].append(render_module_card('/admin/reports', 'fa-file-alt', 'text-cyan-500', '报表与证据包', '质量门禁、闭环证据、导出追踪。'))
    if any(mid == 'audit_log' for mid, _, _ in visible_sorted):
        grouped_cards['governance'].append(render_module_card('/admin/audit-log', 'fa-history', 'text-gray-500', '审计与安全日志', desc.get('audit_log', '')))

    grouped_cards['system'].append(render_module_card('/admin/site-config', 'fa-swatchbook', 'text-fuchsia-500', '官网与外部模块配置', '统一维护公司简介、玩家官网、开发者官网与外部入口'))
    grouped_cards['system'].append(render_module_card('/admin/settings', 'fa-cog', 'text-slate-500', '系统与安全设置', '系统开关、策略、Webhook、安全参数与权限治理。'))
    grouped_cards['system'].append(render_module_card('/workspace', 'fa-briefcase', 'text-amber-500', '个人工作区', '处理个人文件、截图、书签和协作资料'))

    cards = render_grouped_admin_sections([
        ('项目工作台', '先选择项目，再进入该项目的构建、发布、GM工作台与运维中心。', grouped_cards.get('project')),
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

    return admin_layout(
        render_admin_dashboard_v2(
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

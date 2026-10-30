# -*- coding: utf-8 -*-
"""Admin workbench: inbox tabs + shortcuts + recent projects."""

import html as html_module
from datetime import date

from flask import session

from data.packages import get_platform_label
from data.projects import can_view_project, projects_db
from data.tasks import project_tasks_db
from data.approvals import get_pending_approvals_for_user
from data.notifications import get_notifications_for_user
from data.versions import (
    get_version_platform,
    project_versions_db,
    version_has_apk,
)
from services.admin import user_favorites_service
from services.ops.topology_registry import _resolve_ops_env_key

_PREVIEW = 5
_MAX_ROWS = 20


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


def _esc(value, fallback=''):
    text = '' if value is None else str(value).strip()
    if not text:
        text = fallback
    return html_module.escape(text)


_APPROVAL_TYPE_ZH = {
    'news_publish': '新闻发布',
    'forum_post_publish': '官方帖子发布',
    'welfare_publish': '福利发布',
    'release_publish': '发版审批',
    'ops_action': '运维动作',
    'change_request': '变更申请',
}


def _approval_type_label(value):
    key = str(value or '').strip()
    if not key:
        return '审批'
    return _APPROVAL_TYPE_ZH.get(key, key.replace('_', ' '))


def _todo_row(title, meta, href, index, tag='', tag_tone='muted'):
    hidden = ' is-collapsed' if index >= _PREVIEW else ''
    tag_html = ''
    if tag:
        tone = tag_tone if tag_tone in ('success', 'warning', 'danger', 'official', 'muted') else 'muted'
        tag_html = f'<span class="pm-tag pm-tag--{tone}">{_esc(tag)}</span>'
    return (
        f'<li class="studio-todo{hidden}" data-todo-index="{index}"><div><strong>'
        + _esc(title)
        + '</strong>'
        + tag_html
        + '<span>'
        + _esc(meta)
        + '</span></div><a class="pm-btn pm-btn--compact" href="'
        + _esc(href)
        + '">去处理</a></li>'
    )


def _grouped_approval_rows(pending):
    """按类型聚合，避免审批票据墙。"""
    buckets = {}
    order = []
    for item in pending or []:
        label = _approval_type_label(item.get('type'))
        if label not in buckets:
            buckets[label] = []
            order.append(label)
        buckets[label].append(item)
    rows = []
    for idx, label in enumerate(order[:_MAX_ROWS]):
        items = buckets[label]
        latest = items[0]
        when = str(latest.get('created_at') or '')[:16].replace('T', ' ')
        meta = f'{len(items)} 条待审' + (f' · 最近 {when}' if when else '')
        rows.append(
            _todo_row(label, meta, '/admin/approval', idx, tag=str(len(items)), tag_tone='warning')
        )
    return rows


def _grouped_risk_rows(missing, env_key):
    """按项目聚合缺包风险。"""
    buckets = {}
    order = []
    for item in missing or []:
        pid = str(item.get('project_id') or '')
        if not pid:
            continue
        if pid not in buckets:
            buckets[pid] = []
            order.append(pid)
        buckets[pid].append(item)
    rows = []
    for idx, pid in enumerate(order[:_MAX_ROWS]):
        items = buckets[pid]
        name = items[0].get('project_name') or pid
        platforms = sorted({str(x.get('platform_label') or '') for x in items if x.get('platform_label')})
        plat_txt = '、'.join(platforms[:3]) if platforms else ''
        meta = f'{len(items)} 个版本缺包' + (f' · {plat_txt}' if plat_txt else '')
        href = (
            f'/admin/projects/{html_module.escape(pid)}/versions'
            f'?env_key={html_module.escape(env_key)}'
        )
        rows.append(_todo_row(name, meta, href, idx, tag='缺包', tag_tone='danger'))
    return rows


def _collect_work_items(username, visible_project_ids):
    pending_approvals = get_pending_approvals_for_user(username) or []
    user_notifications = get_notifications_for_user(username, limit=50) or []
    unread_notifications = [n for n in user_notifications if not n.get('read_at')]
    my_tasks = []
    missing_package_versions = []
    for project_id in visible_project_ids:
        project_name = (projects_db.get(project_id) or {}).get('name') or project_id
        versions = project_versions_db.get(project_id) or []
        for version in versions:
            if not version_has_apk(project_id, version):
                missing_package_versions.append({
                    'project_id': project_id,
                    'project_name': project_name,
                    'version_name': version.get('version_name') or version.get('version_code') or '未命名版本',
                    'platform_label': get_platform_label(get_version_platform(version)),
                })
        for task in (project_tasks_db.get(project_id) or []):
            if task.get('current_assignee') != username:
                continue
            if task.get('status') in ('done', 'abandoned'):
                continue
            end_time = (task.get('end_time') or '')[:10]
            overdue = False
            if end_time:
                try:
                    overdue = date.fromisoformat(end_time) < date.today()
                except ValueError:
                    overdue = False
            my_tasks.append(dict(task, project_id=project_id, project_name=project_name, overdue=overdue))
    my_tasks.sort(key=lambda t: (0 if t.get('overdue') else 1, t.get('end_time') or '9999'))
    return pending_approvals, my_tasks, unread_notifications, missing_package_versions


def _recent_projects(username, visible_project_ids, env_key):
    fav = user_favorites_service.get_user_favorites(username) or {}
    favorite_ids = [pid for pid in (fav.get('project_favorites') or []) if pid in visible_project_ids]
    last_id = str(session.get('ops_last_project') or '').strip()
    ordered = []
    for pid in favorite_ids + ([last_id] if last_id else []) + list(visible_project_ids):
        if pid in visible_project_ids and pid not in ordered:
            ordered.append(pid)
        if len(ordered) >= 4:
            break
    cards = []
    for pid in ordered:
        proj = projects_db.get(pid) or {}
        name = proj.get('name') or pid
        href = f'/admin/projects/{html_module.escape(pid)}/overview?env_key={html_module.escape(env_key)}'
        cards.append(
            '<a class="studio-project-card" href="'
            + href
            + '"><strong>'
            + _esc(name)
            + '</strong><span>'
            + _esc(pid)
            + '</span></a>'
        )
    return cards


def _inbox_panel(tab_id, label, rows, total, more_href, more_label, active):
    hidden = '' if active else ' is-hidden'
    row_count = len(rows or [])
    if not rows:
        body = '<p class="studio-empty">这一类当前没有事项。</p>'
        actions = ''
    else:
        body = '<ul class="studio-todo-list" data-todo-list="' + _esc(tab_id) + '">' + ''.join(rows) + '</ul>'
        more_btn = ''
        if row_count > _PREVIEW:
            more_btn = (
                '<button type="button" class="pm-btn" data-todo-more="'
                + _esc(tab_id)
                + '">展开更多（'
                + str(row_count - _PREVIEW)
                + '）</button>'
            )
        actions = (
            '<div class="studio-inbox-actions">'
            + more_btn
            + '<a class="pm-btn pm-btn--primary" href="'
            + _esc(more_href)
            + '">'
            + _esc(more_label)
            + '</a></div>'
        )
    return (
        f'<div class="studio-inbox-panel{hidden}" data-inbox-panel="{_esc(tab_id)}">'
        f'<div class="studio-section-head"><h2>{_esc(label)}</h2>'
        f'<span class="text-sm text-gray-500">共 {total} 条</span></div>'
        + body
        + actions
        + '</div>'
    )


def render_admin_panel_dashboard(visible, desc, username, admin_layout):
    del visible, desc
    env_key = _resolve_ops_env_key('')
    visible_project_ids = [pid for pid in projects_db.keys() if can_view_project(pid, username)]
    pending, my_tasks, unread, missing = _collect_work_items(username, visible_project_ids)
    last_project = str(session.get('ops_last_project') or '').strip()
    if last_project not in visible_project_ids:
        last_project = visible_project_ids[0] if visible_project_ids else ''
    release_href = (
        f'/admin/projects/{html_module.escape(last_project)}/release-hub?env_key={html_module.escape(env_key)}'
        if last_project
        else '/admin/projects'
    )

    tabs = [
        {
            'id': 'approvals',
            'label': '待审批',
            'total': len(pending),
            'href': '/admin/approval',
            'more': '打开审批中心',
            'rows': _grouped_approval_rows(pending),
        },
        {
            'id': 'tasks',
            'label': '我的任务',
            'total': len(my_tasks),
            'href': '/admin/my-tasks',
            'more': '打开我的任务',
            'rows': [
                _todo_row(
                    item.get('title') or '未命名任务',
                    f'{item.get("project_name") or item.get("project_id") or ""} · {(item.get("end_time") or "")}',
                    f'/admin/projects/{html_module.escape(str(item.get("project_id") or ""))}/tasks',
                    idx,
                    tag='逾期' if item.get('overdue') else '进行中',
                    tag_tone='danger' if item.get('overdue') else 'official',
                )
                for idx, item in enumerate(my_tasks[:_MAX_ROWS])
            ],
        },
        {
            'id': 'notices',
            'label': '未读通知',
            'total': len(unread),
            'href': '/admin/notifications',
            'more': '打开消息',
            'rows': [
                _todo_row(
                    str(item.get('title') or '未命名通知'),
                    str(item.get('created_at') or '')[:16].replace('T', ' '),
                    '/admin/notifications',
                    idx,
                    tag='未读',
                    tag_tone='official',
                )
                for idx, item in enumerate(unread[:_MAX_ROWS])
            ],
        },
        {
            'id': 'risks',
            'label': '发版风险',
            'total': len(missing),
            'href': '/admin/projects',
            'more': '打开项目列表',
            'rows': _grouped_risk_rows(missing, env_key),
        },
    ]

    default_tab = 'approvals'
    for tab in tabs:
        if tab['total'] > 0:
            default_tab = tab['id']
            break

    tab_buttons = ''.join(
        '<button type="button" class="studio-inbox-tab'
        + (' is-active' if tab['id'] == default_tab else '')
        + '" data-inbox-tab="'
        + _esc(tab['id'])
        + '">'
        + _esc(tab['label'])
        + '<em>'
        + str(tab['total'])
        + '</em></button>'
        for tab in tabs
    )
    panels = ''.join(
        _inbox_panel(
            tab['id'],
            tab['label'],
            tab['rows'],
            tab['total'],
            tab['href'],
            tab['more'],
            tab['id'] == default_tab,
        )
        for tab in tabs
    )
    total_open = sum(tab['total'] for tab in tabs)
    primary = next((t for t in tabs if t['id'] == default_tab), tabs[0])
    if total_open <= 0:
        focus_html = (
            '<div class="studio-focus studio-focus--clear">'
            '<strong>暂无待办</strong>'
            '<span>可以从项目列表或发版入口继续推进。</span>'
            '<a class="pm-btn pm-btn--primary" href="/admin/projects">打开项目列表</a>'
            '</div>'
        )
    else:
        focus_html = (
            '<div class="studio-focus">'
            '<div class="studio-focus-copy"><strong>今天优先：'
            + _esc(primary['label'])
            + ' '
            + str(primary['total'])
            + ' 条</strong>'
            '<span>合计 '
            + str(total_open)
            + ' 条待处理；先处理最高优先类，其余可切换查看。</span></div>'
            '<a class="pm-btn pm-btn--primary" href="'
            + _esc(primary['href'])
            + '">'
            + _esc(primary['more'])
            + '</a></div>'
        )
    summary_chips = ''.join(
        '<button type="button" class="studio-summary-chip'
        + (' is-active' if tab['id'] == default_tab else '')
        + '" data-inbox-tab="'
        + _esc(tab['id'])
        + '"><span>'
        + _esc(tab['label'])
        + '</span><em>'
        + str(tab['total'])
        + '</em></button>'
        for tab in tabs
    )

    shortcuts = [
        ('项目列表', '进入多项目交付', '/admin/projects'),
        ('发版', '版本、构建与发布', release_href),
        ('审批中心', '待审与已审记录', '/admin/approval'),
        ('打包机', 'Jenkins 实例', '/admin/jenkins'),
    ]
    shortcut_html = ''.join(
        '<a class="studio-shortcut" href="'
        + _esc(href)
        + '"><strong>'
        + _esc(title)
        + '</strong><span>'
        + _esc(meta)
        + '</span></a>'
        for title, meta, href in shortcuts
    )
    recent_cards = _recent_projects(username, visible_project_ids, env_key)
    recent_html = (
        ''.join(recent_cards)
        if recent_cards
        else '<p class="studio-empty">还没有可打开的项目。</p>'
    )

    content = (
        '<header class="pm-page-head"><div class="pm-page-head-copy"><div>'
        '<h1>工作台</h1><p>先看今天优先事项，再进中心处理。</p>'
        '</div></div>'
        '<div class="pm-page-head-actions">'
        '<a class="pm-btn" href="/admin/my-tasks">我的任务</a>'
        '<a class="pm-btn pm-btn--primary" href="/admin/projects">项目列表</a>'
        '</div></header>'
        '<div class="studio-workbench">'
        '<section class="studio-workbench-main">'
        + focus_html
        + '<div class="studio-summary-row" role="tablist" aria-label="待办分类">'
        + summary_chips
        + '</div>'
        '<section class="studio-section studio-inbox-section">'
        '<div class="studio-inbox-tabs is-hidden" aria-hidden="true">'
        + tab_buttons
        + '</div>'
        + panels
        + '</section></section>'
        '<aside class="studio-workbench-side">'
        '<section class="studio-section"><div class="studio-section-head"><h2>快捷入口</h2></div>'
        '<div class="studio-shortcut-stack">'
        + shortcut_html
        + '</div></section>'
        '<section class="studio-section"><div class="studio-section-head"><h2>最近项目</h2>'
        '<a class="studio-section-more" href="/admin/projects">全部</a></div>'
        '<div class="studio-project-stack">'
        + recent_html
        + '</div></section>'
        '</aside></div>'
        '''<script>
(function(){
  var root=document.querySelector('.studio-workbench');
  if(!root) return;
  function activate(id){
    root.querySelectorAll('[data-inbox-tab]').forEach(function(b){
      b.classList.toggle('is-active', b.getAttribute('data-inbox-tab')===id);
    });
    root.querySelectorAll('[data-inbox-panel]').forEach(function(p){
      p.classList.toggle('is-hidden', p.getAttribute('data-inbox-panel')!==id);
    });
  }
  root.querySelectorAll('[data-inbox-tab]').forEach(function(btn){
    btn.addEventListener('click', function(){ activate(btn.getAttribute('data-inbox-tab')); });
  });
  root.querySelectorAll('[data-todo-more]').forEach(function(btn){
    btn.addEventListener('click', function(){
      var id=btn.getAttribute('data-todo-more');
      var list=root.querySelector('[data-todo-list="'+id+'"]');
      if(!list) return;
      list.querySelectorAll('.studio-todo.is-collapsed').forEach(function(li){ li.classList.remove('is-collapsed'); });
      btn.classList.add('is-hidden');
    });
  });
})();
</script>'''
    )
    return admin_layout(content, '工作台', back_href='/admin')

# -*- coding: utf-8 -*-
"""Admin audit log page."""

import html
from urllib.parse import quote

from services.admin import audit_service

AUDIT_SENSITIVE_ACTIONS = {"delete_user", "delete_project", "task_delete", "task_batch_delete"}

AUDIT_ACTION_ZH = {
    "create_task": "创建任务",
    "task_delete": "删除任务",
    "task_batch_delete": "批量删除任务",
    "create_project": "创建项目",
    "delete_project": "删除项目",
    "create_project_version": "创建版本",
    "change_password": "修改密码",
    "approval_create": "发起审批",
    "approval_approve": "通过审批",
    "approval_reject": "驳回审批",
    "channel_create": "创建渠道",
    "channel_update": "更新渠道",
    "channel_delete": "删除渠道",
    "commercial_release": "商业发布",
    "ops_platform_change_freeze": "变更冻结",
    "delete_user": "删除用户",
    "create_user": "创建用户",
    "update_user": "更新用户",
    "login": "登录",
    "logout": "退出登录",
}


def _action_label(action: str) -> str:
    key = str(action or "").strip()
    if not key or key == "-":
        return "暂无"
    return AUDIT_ACTION_ZH.get(key, key.replace("_", " "))


def _filter_audit_entries(entries, user_filter, action_filter, date_from, date_to, keyword=None):
    return audit_service.filter_entries(entries, user_filter, action_filter, date_from, date_to, keyword or "")


def render_audit_log_page(request, audit_log_db):
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
        f'<option value="{html.escape(a)}"' + (' selected' if a == action_filter else '') + f'>{html.escape(_action_label(a))}</option>'
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
        sensitive = 'is-sensitive' if action in AUDIT_SENSITIVE_ACTIONS else ''
        badge = 'pm-tag--danger' if action in AUDIT_SENSITIVE_ACTIONS else 'pm-tag--muted'
        rows.append(
            f'<tr class="{sensitive}">'
            f'<td>{html.escape(((e.get("timestamp") or "-")[:19]).replace("T", " "))}</td>'
            f'<td>{html.escape(e.get("user") or "-")}</td>'
            f'<td><span class="pm-tag {badge}" title="{html.escape(action)}">{html.escape(_action_label(action))}</span></td>'
            f'<td>{html.escape(str(e.get("details") or "暂无"))}</td>'
            f'<td>{html.escape(e.get("ip") or "暂无")}</td></tr>'
        )
    rows_html = ''.join(rows) if rows else (
        '<tr><td colspan="5"><div class="pm-placeholder-page">'
        '<h2>暂无操作记录</h2><p>调整筛选条件后再试，或导出全部日志。</p></div></td></tr>'
    )
    export_params = '&'.join(
        f'{k}={quote(v)}'
        for k, v in [
            ('user', user_filter),
            ('action', action_filter),
            ('date_from', date_from),
            ('date_to', date_to),
            ('keyword', keyword),
        ]
        if v
    )
    export_params = '?' + export_params if export_params else ''
    pagination = ''
    if total > page_size:
        prev_dis = ' aria-disabled="true"' if page == 0 else ''
        next_dis = ' aria-disabled="true"' if (page + 1) * page_size >= total else ''
        base = (
            f'/admin/audit-log?user={quote(user_filter)}&action={quote(action_filter)}'
            f'&date_from={quote(date_from)}&date_to={quote(date_to)}'
            f'&keyword={quote(keyword)}&page_size={page_size}'
        )
        pagination = (
            f'<div class="pm-table-pagination"><span>共 {total} 条，第 {page + 1} 页（每页 {page_size} 条）</span>'
            f'<nav><a class="pm-btn pm-btn--compact" href="{base}&page={max(page - 1, 0)}"{prev_dis}>上一页</a>'
            f'<a class="pm-btn pm-btn--compact" href="{base}&page={page + 1}"{next_dis}>下一页</a></nav></div>'
        )
    return f'''
    <header class="pm-page-head">
      <div class="pm-page-head-copy"><div>
        <h1>操作日志</h1>
        <p>按用户、操作类型与时间追溯关键变更；敏感操作会标红。</p>
      </div></div>
      <div class="pm-page-head-actions">
        <a class="pm-btn pm-btn--primary" href="/admin/audit-log/export{export_params}">导出 CSV</a>
      </div>
    </header>
    <form method="get" action="/admin/audit-log" class="pm-filter-bar">
      <div class="pm-filter-search"><input type="text" name="keyword" value="{html.escape(keyword)}" placeholder="搜索用户、操作、详情、IP"></div>
      <select name="user"><option value="">全部用户</option>{user_opts}</select>
      <select name="action"><option value="">全部操作</option>{action_opts}</select>
      <input type="date" name="date_from" value="{html.escape(date_from)}">
      <input type="date" name="date_to" value="{html.escape(date_to)}">
      <input type="hidden" name="page_size" value="{page_size}">
      <button type="submit" class="pm-btn pm-btn--primary">筛选</button>
      <a class="pm-btn" href="/admin/audit-log">重置</a>
    </form>
    <div class="pm-table-panel">
      <table class="pm-table">
        <thead><tr><th>时间</th><th>用户</th><th>操作</th><th>详情</th><th>IP</th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
      {pagination}
    </div>
    '''

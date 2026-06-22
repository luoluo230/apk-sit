# -*- coding: utf-8 -*-
"""Admin audit log page."""

import html
from urllib.parse import quote

from services.admin import audit_service

AUDIT_SENSITIVE_ACTIONS = {"delete_user", "delete_project", "task_delete", "task_batch_delete"}


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
    return content


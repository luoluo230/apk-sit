# -*- coding: utf-8 -*-
"""Admin notifications page."""

from services.admin import notification_page_service

def render_notifications_page(username, type_filter):
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
    return content


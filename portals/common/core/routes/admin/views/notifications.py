# -*- coding: utf-8 -*-
"""Admin notifications page."""

from services.admin import notification_page_service


def render_notifications_page(username, type_filter):
    view_model = notification_page_service.build_notifications_view_model(username, type_filter)
    type_opts = view_model["type_options"]
    rows_html = view_model["rows_html"]
    content = f"""
    <header class="pm-page-head">
        <div class="pm-page-head-copy"><div>
            <h1>消息</h1>
            <p>任务分配、审批结果、构建完成等提醒。</p>
        </div></div>
        <div class="pm-page-head-actions">
            <button type="button" class="pm-btn" onclick="markAllRead()">全部标为已读</button>
        </div>
    </header>
    <form class="pm-filter-bar" method="get" action="/admin/notifications">
        <label class="pm-filter-item"><span class="pm-filter-label">类型</span>
        <select name="type" onchange="this.form.submit()">{type_opts}</select></label>
    </form>
    <div class="pm-table-panel overflow-x-auto">
        <table class="pm-table"><thead><tr>
            <th>时间</th><th>类型</th><th>标题</th><th>操作</th>
        </tr></thead><tbody>{rows_html}</tbody></table>
    </div>
    <script>
    function markRead(id) {{
      fetch("/admin/notifications/" + id + "/read", {{ method: "POST", credentials: "same-origin" }})
        .then(function(r) {{ if (r.ok) location.reload(); }});
    }}
    function markAllRead() {{
      fetch("/admin/notifications/read-all", {{ method: "POST", credentials: "same-origin" }})
        .then(function(r) {{ if (r.ok) location.reload(); }});
    }}
    </script>"""
    return content

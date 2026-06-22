# -*- coding: utf-8 -*-
"""Admin reports page."""

import html

from models.data import export_records_db, projects_db, report_templates_db, resolve_project_id
from routes.admin.views.common import clean_display_text, visible_project_choices

def render_reports_page(username, selected_project_id):
    project_choices = visible_project_choices(username)

    def project_label(project_id):
        resolved_id = resolve_project_id(project_id)
        payload = (projects_db.get(resolved_id) if resolved_id else None) or {}
        return clean_display_text(payload.get('name') if isinstance(payload, dict) else '', resolved_id or project_id or '全部项目')
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
    return content


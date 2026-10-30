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
        return clean_display_text(
            payload.get('name') if isinstance(payload, dict) else '',
            resolved_id or project_id or '全部项目',
        )

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
        f'<option value="{html.escape(item["id"])}"'
        + (' selected' if selected_project_id == item['id'] else '')
        + f'>{html.escape(item["name"])}</option>'
        for item in ([{'id': '', 'name': '全部项目'}] + project_choices)
    )
    project_create_opts = project_filter_opts

    trows = ''.join(
        '<tr>'
        f'<td>{html.escape(t.get("name") or "")}</td>'
        f'<td>{html.escape(project_label(template_project_id(t)))}</td>'
        f'<td>{html.escape((t.get("created_at") or "")[:19])}</td>'
        f'<td><a class="pm-btn pm-btn--compact" href="/admin/reports/run/{t.get("id")}">一键生成</a></td>'
        '</tr>'
        for t in templates[:20]
    ) if templates else (
        '<tr><td colspan="4"><div class="pm-placeholder-page">'
        '<h2>暂无模板</h2><p>先创建报表模板，再一键生成 CSV。</p></div></td></tr>'
    )
    rrows = ''.join(
        '<tr>'
        f'<td>{(r.get("exported_at") or "")[:19]}</td>'
        f'<td>{html.escape(r.get("template_name") or "")}</td>'
        f'<td>{html.escape(project_label(export_project_id(r)))}</td>'
        f'<td>{html.escape(str(r.get("format") or "csv"))}</td>'
        '</tr>'
        for r in recs
    ) if recs else (
        '<tr><td colspan="4"><div class="pm-placeholder-page">'
        '<h2>暂无导出记录</h2><p>生成模板后会出现在这里。</p></div></td></tr>'
    )

    return f'''
    <header class="pm-page-head">
      <div class="pm-page-head-copy"><div>
        <h1>报表中心</h1>
        <p>创建报表模板并一键生成 CSV，也可跳转数据分析导出。</p>
      </div></div>
      <div class="pm-page-head-actions">
        <a class="pm-btn" href="/dashboard/export">数据分析导出</a>
      </div>
    </header>
    <form class="pm-filter-bar" method="get">
      <select name="project_id">{project_filter_opts}</select>
      <button type="submit" class="pm-btn pm-btn--primary">筛选</button>
      <a class="pm-btn" href="/admin/reports">重置</a>
    </form>
    <section class="studio-section">
      <div class="studio-section-head"><h2>报表模板</h2></div>
      <div class="studio-config-panel">
        <form id="reportTemplateForm" class="studio-form-grid">
          <div class="studio-form-field"><label>所属项目</label><select id="tplProjectId">{project_create_opts}</select></div>
          <div class="studio-form-field"><label>模板名称</label><input type="text" id="tplName" placeholder="如：周报汇总" required></div>
          <div class="studio-form-field"><label>说明</label><input type="text" id="tplDesc" placeholder="选填"></div>
          <div class="studio-form-field"><label>&nbsp;</label><button type="submit" class="pm-btn pm-btn--primary">创建模板</button></div>
        </form>
      </div>
      <div class="pm-table-panel overflow-x-auto">
        <table class="pm-table">
          <thead><tr><th>名称</th><th>项目</th><th>创建时间</th><th>操作</th></tr></thead>
          <tbody>{trows}</tbody>
        </table>
      </div>
    </section>
    <section class="studio-section">
      <div class="studio-section-head"><h2>导出记录</h2></div>
      <div class="pm-table-panel overflow-x-auto">
        <table class="pm-table">
          <thead><tr><th>导出时间</th><th>模板</th><th>项目</th><th>格式</th></tr></thead>
          <tbody>{rrows}</tbody>
        </table>
      </div>
    </section>
    <script>
    document.getElementById("reportTemplateForm").onsubmit = function(e) {{
      e.preventDefault();
      var name = document.getElementById("tplName").value.trim();
      var desc = document.getElementById("tplDesc").value.trim();
      var projectId = document.getElementById("tplProjectId").value;
      fetch("/admin/reports/templates", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        credentials: "same-origin",
        body: JSON.stringify({{ name: name, description: desc, project_id: projectId, config: {{ project_id: projectId }} }})
      }}).then(function(r) {{ return r.json(); }}).then(function(d) {{
        if (d.error) alert(d.error); else location.reload();
      }});
      return false;
    }};
    </script>
    '''

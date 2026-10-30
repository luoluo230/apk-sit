# -*- coding: utf-8 -*-
"""Admin approval page."""

import html

from models.data import (
    APPROVAL_TYPES,
    approvals_db,
    get_pending_approvals_for_user,
    projects_db,
    resolve_project_id,
)
from routes.admin.views.common import (
    approval_project_id as resolve_approval_project_id,
    clean_display_text,
    visible_project_choices,
)


def _approval_project_id_for_row(approval):
    explicit_project_id = resolve_project_id((approval or {}).get('project_id')) or ''
    if explicit_project_id:
        return explicit_project_id
    inferred_project_id = resolve_approval_project_id(approval)
    return resolve_project_id(inferred_project_id) or str(inferred_project_id or '').strip()


def render_approval_page(username, selected_project_id, get_csrf_token):
    pending = get_pending_approvals_for_user(username)
    my_list = [a for a in approvals_db if a.get('applicant') == username]
    if selected_project_id:
        pending = [a for a in pending if _approval_project_id_for_row(a) == selected_project_id]
        my_list = [a for a in my_list if _approval_project_id_for_row(a) == selected_project_id]
    my_list.sort(key=lambda x: x.get('updated_at') or x.get('created_at') or '', reverse=True)
    type_labels = dict(APPROVAL_TYPES)
    project_choices = visible_project_choices(username)
    project_opts = ''.join(
        f'<option value="{html.escape(item["id"])}">{html.escape(item["name"])}</option>'
        for item in project_choices
    )
    project_filter_opts = ''.join(
        f'<option value="{html.escape(item["id"])}"'
        + (' selected' if selected_project_id == item['id'] else '')
        + f'>{html.escape(item["name"])}</option>'
        for item in ([{'id': '', 'name': '全部项目'}] + project_choices)
    )

    def project_label(project_id):
        resolved_id = resolve_project_id(project_id)
        payload = (projects_db.get(resolved_id) if resolved_id else None) or {}
        return clean_display_text(
            payload.get('name') if isinstance(payload, dict) else '',
            resolved_id or project_id or '未绑定项目',
        )

    def row_pending(a, collapsed=False):
        aid = a.get('id', '')
        type_key = str(a.get('type') or '')
        type_name = clean_display_text(type_labels.get(type_key, type_key), '审批事项')
        target_type = clean_display_text(a.get('target_type'), '对象')
        target_id = clean_display_text(a.get('target_id'), '未命名对象')
        reason = clean_display_text(a.get('reason'), '未填写申请说明')
        project_name = project_label(_approval_project_id_for_row(a))
        cls = ' class="ap-row is-collapsed"' if collapsed else ' class="ap-row"'
        return (
            f'<tr{cls} data-ap-type="{html.escape(type_key)}">'
            f'<td>{(a.get("created_at") or "")[:19].replace("T", " ")}</td>'
            f'<td><span class="pm-tag pm-tag--muted">{html.escape(type_name)}</span></td>'
            f'<td>{html.escape(clean_display_text(a.get("applicant"), "-"))}</td>'
            f'<td>{html.escape(project_name)}</td>'
            f'<td>{html.escape(target_type + " / " + target_id)}</td>'
            f'<td>{html.escape(reason)[:80]}</td>'
            '<td><div class="pm-table-actions">'
            f'<button type="button" class="pm-btn pm-btn--compact pm-btn--primary" onclick="approve(\'{aid}\', true)">通过</button>'
            f'<button type="button" class="pm-btn pm-btn--compact" onclick="approve(\'{aid}\', false)">驳回</button>'
            '</div></td></tr>'
        )

    _PREVIEW_PENDING = 8
    type_counts = {}
    for item in pending:
        key = str(item.get('type') or '')
        type_counts[key] = type_counts.get(key, 0) + 1
    type_filter_chips = (
        '<button type="button" class="ap-type-chip is-active" data-ap-filter="">全部 · '
        + str(len(pending))
        + '</button>'
        + ''.join(
            '<button type="button" class="ap-type-chip" data-ap-filter="'
            + html.escape(key)
            + '">'
            + html.escape(clean_display_text(type_labels.get(key, key), key or '其他'))
            + ' · '
            + str(count)
            + '</button>'
            for key, count in sorted(type_counts.items(), key=lambda x: (-x[1], x[0]))
        )
    ) if pending else ''

    if pending:
        head_rows = ''.join(row_pending(a, False) for a in pending[:_PREVIEW_PENDING])
        rest = pending[_PREVIEW_PENDING:]
        rest_rows = ''.join(row_pending(a, True) for a in rest)
        more_btn = (
            f'<tr class="ap-more-row"><td colspan="7">'
            f'<button type="button" class="pm-btn" id="apShowMore">展开其余 {len(rest)} 条</button>'
            f'</td></tr>'
            if rest else ''
        )
        pending_html = head_rows + rest_rows + more_btn
    else:
        pending_html = (
            '<tr><td colspan="7"><div class="pm-placeholder-page">'
            '<h2>暂无待审批</h2><p>当前筛选下没有需要你处理的审批。</p>'
            '<a class="pm-btn" href="/admin">返回工作台</a></div></td></tr>'
        )

    def row_my(a):
        status = a.get('status', '')
        status_labels = {'pending': '待审批', 'approved': '已通过', 'rejected': '已驳回'}
        status_text = status_labels.get(status, status)
        tag = (
            'pm-tag--success' if status == 'approved'
            else ('pm-tag--danger' if status == 'rejected' else 'pm-tag--warning')
        )
        return (
            '<tr>'
            f'<td>{(a.get("created_at") or "")[:19].replace("T", " ")}</td>'
            f'<td>{html.escape(clean_display_text(type_labels.get(a.get("type",""), a.get("type","")), "审批事项"))}</td>'
            f'<td>{html.escape(clean_display_text(a.get("target_id"), "未命名对象"))}</td>'
            f'<td><span class="pm-tag {tag}">{html.escape(status_text)}</span></td></tr>'
        )

    my_html = (
        ''.join(row_my(a) for a in my_list[:50])
        if my_list
        else (
            '<tr><td colspan="4"><div class="pm-placeholder-page">'
            '<h2>暂无申请记录</h2><p>点击「发起申请」提交第一条审批。</p></div></td></tr>'
        )
    )
    type_opts = ''.join(f'<option value="{t}">{html.escape(l)}</option>' for t, l in APPROVAL_TYPES)
    content = f'''
    <header class="pm-page-head">
      <div class="pm-page-head-copy"><div>
        <h1>审批中心</h1>
        <p>处理版本发布、社区内容与敏感操作的审批申请。</p>
      </div></div>
      <div class="pm-page-head-actions">
        <button type="button" class="pm-btn pm-btn--primary" onclick="document.getElementById('createApprovalForm').classList.toggle('is-hidden')">发起申请</button>
      </div>
    </header>
    <form class="pm-filter-bar" method="get">
      <select name="project_id">{project_filter_opts}</select>
      <button type="submit" class="pm-btn">按项目筛选</button>
      <a class="pm-btn" href="/admin/approval">重置</a>
    </form>
    <div id="approvalFeedback" class="studio-feedback is-hidden">
      <p id="approvalFeedbackText"></p>
    </div>
    <section class="studio-section">
      <div class="studio-section-head"><h2>待我审批</h2><span class="text-sm text-gray-500">{len(pending)} 条</span></div>
      <div class="ap-type-chips" role="tablist" aria-label="按类型筛选">{type_filter_chips}</div>
      <div class="pm-table-panel overflow-x-auto">
        <table class="pm-table" id="apPendingTable">
          <thead><tr>
            <th>申请时间</th><th>类型</th><th>申请人</th><th>项目</th><th>对象</th><th>说明</th><th>操作</th>
          </tr></thead>
          <tbody>{pending_html}</tbody>
        </table>
      </div>
    </section>
    <section class="studio-section">
      <div class="studio-section-head"><h2>我的申请</h2></div>
      <div id="createApprovalForm" class="studio-config-panel is-hidden">
        <form onsubmit="return submitApproval(event)" class="studio-form-grid">
          <div class="studio-form-field"><label>审批类型</label><select id="approvalType" required>{type_opts}</select></div>
          <div class="studio-form-field"><label>所属项目</label><select id="approvalProjectId"><option value="">未绑定项目</option>{project_opts}</select></div>
          <div class="studio-form-field"><label>关联对象 ID</label><input type="text" id="approvalTargetId" placeholder="如项目 ID 或版本号"></div>
          <div class="studio-form-field studio-form-field--full"><label>申请说明</label><input type="text" id="approvalReason" placeholder="简要说明"></div>
          <div class="studio-form-field studio-form-field--full"><button type="submit" class="pm-btn pm-btn--primary">提交申请</button></div>
        </form>
      </div>
      <div class="pm-table-panel overflow-x-auto">
        <table class="pm-table">
          <thead><tr><th>申请时间</th><th>类型</th><th>对象</th><th>状态</th></tr></thead>
          <tbody>{my_html}</tbody>
        </table>
      </div>
    </section>
    <div id="approveModal" class="pm-modal-root is-hidden" onclick="if(event.target===this) this.classList.add('is-hidden')">
      <div class="pm-modal-mask"></div>
      <div class="pm-modal pm-modal--480" onclick="event.stopPropagation()">
        <div class="pm-modal-head"><div><h2>审批意见</h2><p>可选填写说明后确认。</p></div></div>
        <div class="pm-modal-body">
          <input type="hidden" id="approveId">
          <input type="hidden" id="approveAction">
          <div class="studio-form-field"><label>意见</label><textarea id="approveComment" rows="3" placeholder="选填"></textarea></div>
        </div>
        <div class="pm-modal-foot">
          <button type="button" class="pm-btn" onclick="document.getElementById('approveModal').classList.add('is-hidden')">取消</button>
          <button type="button" class="pm-btn pm-btn--primary" onclick="submitApprove()">确定</button>
        </div>
      </div>
    </div>
    <meta name="csrf-token" content="{html.escape(get_csrf_token())}">
    <script>
    var approvalTokenEl = document.querySelector('meta[name="csrf-token"]');
    var approvalCsrfHeaders = {{}};
    if (approvalTokenEl && approvalTokenEl.content) approvalCsrfHeaders['X-CSRFToken'] = approvalTokenEl.content;
    function showApprovalFeedback(kind, message) {{
      var box = document.getElementById('approvalFeedback');
      var text = document.getElementById('approvalFeedbackText');
      if (!box || !text) return;
      box.classList.remove('is-hidden', 'is-success', 'is-error');
      box.classList.add(kind === 'success' ? 'is-success' : (kind === 'error' ? 'is-error' : ''));
      text.textContent = message || '';
    }}
    function approve(id, isApprove) {{
      document.getElementById('approveId').value = id;
      document.getElementById('approveAction').value = isApprove ? 'approve' : 'reject';
      document.getElementById('approveComment').value = '';
      document.getElementById('approveModal').classList.remove('is-hidden');
    }}
    function submitApprove() {{
      var id = document.getElementById('approveId').value;
      var action = document.getElementById('approveAction').value;
      var comment = document.getElementById('approveComment').value;
      fetch('/admin/approval/' + id + '/' + action, {{
        method: 'POST',
        headers: Object.assign({{ 'Content-Type': 'application/json' }}, approvalCsrfHeaders),
        credentials: 'same-origin',
        body: JSON.stringify({{ comment: comment }})
      }}).then(function(r) {{ return r.json(); }}).then(function(d) {{
        if (d.error) {{ showApprovalFeedback('error', d.error); return; }}
        showApprovalFeedback('success', action === 'approve' ? '审批已通过，列表即将刷新。' : '审批已驳回，列表即将刷新。');
        setTimeout(function() {{ location.reload(); }}, 700);
      }});
      document.getElementById('approveModal').classList.add('is-hidden');
    }}
    function submitApproval(e) {{
      e.preventDefault();
      var type = document.getElementById('approvalType').value;
      var projectId = document.getElementById('approvalProjectId').value;
      var targetId = document.getElementById('approvalTargetId').value;
      var reason = document.getElementById('approvalReason').value;
      if (!targetId.trim()) {{ showApprovalFeedback('error', '请填写关联对象 ID'); return false; }}
      fetch('/admin/approval/create', {{
        method: 'POST',
        headers: Object.assign({{ 'Content-Type': 'application/json' }}, approvalCsrfHeaders),
        credentials: 'same-origin',
        body: JSON.stringify({{ type: type, target_type: type, target_id: targetId, reason: reason, project_id: projectId }})
      }}).then(function(r) {{ return r.json(); }}).then(function(d) {{
        if (d.error) {{ showApprovalFeedback('error', d.error); }}
        else {{ showApprovalFeedback('success', '审批申请已提交，列表即将刷新。'); setTimeout(function() {{ location.reload(); }}, 700); }}
      }});
      return false;
    }}
    (function() {{
      var more = document.getElementById('apShowMore');
      if (more) {{
        more.addEventListener('click', function() {{
          document.querySelectorAll('#apPendingTable .ap-row.is-collapsed').forEach(function(row) {{
            row.classList.remove('is-collapsed');
          }});
          var wrap = more.closest('tr');
          if (wrap) wrap.remove();
        }});
      }}
      document.querySelectorAll('.ap-type-chip').forEach(function(btn) {{
        btn.addEventListener('click', function() {{
          var key = btn.getAttribute('data-ap-filter') || '';
          document.querySelectorAll('.ap-type-chip').forEach(function(b) {{
            b.classList.toggle('is-active', b === btn);
          }});
          document.querySelectorAll('#apPendingTable .ap-row').forEach(function(row) {{
            var match = !key || row.getAttribute('data-ap-type') === key;
            row.classList.toggle('is-type-hidden', !match);
            if (match) row.classList.remove('is-collapsed');
          }});
          var moreRow = document.querySelector('.ap-more-row');
          if (moreRow) moreRow.classList.toggle('is-type-hidden', !!key);
        }});
      }});
    }})();
    </script>
    <style>
    .ap-type-chips{{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px}}
    .ap-type-chip{{border:1px solid #e5eaf3;border-radius:999px;padding:6px 12px;background:#fff;font-size:12px;font-weight:600;color:#475467;cursor:pointer}}
    .ap-type-chip.is-active{{border-color:#1677ff;background:#e6f4ff;color:#0958d9}}
    #apPendingTable .ap-row.is-collapsed,
    #apPendingTable .ap-row.is-type-hidden,
    #apPendingTable .ap-more-row.is-type-hidden{{display:none}}
    </style>
    '''
    return content

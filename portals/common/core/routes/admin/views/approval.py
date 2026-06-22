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
        f'<option value="{html.escape(item["id"])}"' + (' selected' if selected_project_id == item['id'] else '') + f'>{html.escape(item["name"])}</option>'
        for item in ([{'id': '', 'name': '全部项目'}] + project_choices)
    )

    def project_label(project_id):
        resolved_id = resolve_project_id(project_id)
        payload = (projects_db.get(resolved_id) if resolved_id else None) or {}
        return clean_display_text(payload.get('name') if isinstance(payload, dict) else '', resolved_id or project_id or '未绑定项目')

    def row_pending(a):
        aid = a.get('id', '')
        type_name = clean_display_text(type_labels.get(a.get('type', ''), a.get('type', '')), '审批事项')
        target_type = clean_display_text(a.get("target_type"), "对象")
        target_id = clean_display_text(a.get("target_id"), "未命名对象")
        reason = clean_display_text(a.get("reason"), "未填写申请说明")
        project_name = project_label(_approval_project_id_for_row(a))
        target_text = clean_display_text(a.get('target_id'), 'ID')
        type_text = clean_display_text(type_labels.get(a.get('type', ''), a.get('type', '')), '\u5ba1\u6279\u4e8b\u9879')
        return (
            f'<tr><td class="px-4 py-3 text-sm">{(a.get("created_at") or "")[:19].replace("T", " ")}</td>'
            f'<td class="px-4 py-3"><span class="rounded bg-gray-100 px-2 py-0.5 text-xs">{html.escape(type_name)}</span></td>'
            f'<td class="px-4 py-3">{html.escape(clean_display_text(a.get("applicant"), "-"))}</td>'
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
        project_name = project_label(_approval_project_id_for_row(a))
        return (
            f'<tr><td class="px-4 py-3 text-sm">{(a.get("created_at") or "")[:19].replace("T", " ")}</td>'
            f'<td class="px-4 py-3">{html.escape(clean_display_text(type_labels.get(a.get("type",""), a.get("type","")), "审批事项"))}</td>'
            f'<td class="px-4 py-3 text-sm">{html.escape(clean_display_text(a.get("target_id"), "未命名对象"))}</td>'
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
        <meta name="csrf-token" content="{html.escape(get_csrf_token())}">
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
    return content


# -*- coding: utf-8 -*-
"""Admin my-tasks page."""

import html
import json
from datetime import date, timedelta
from urllib.parse import urlencode

from models.data import can_view_project, get_task_plan, project_tasks_db, projects_db

TASK_STATUSES = [
    ("abandoned", "已作废"),
    ("not_started", "尚未开始"),
    ("in_progress", "进行中"),
    ("pending_review", "待验收"),
    ("review_passed", "验收通过"),
    ("review_failed", "验收未通过"),
    ("done", "已完成"),
]

PLAN_LABELS = {
    "today_todo": "今日代办",
    "today_done": "今日完成",
    "tomorrow_plan": "明日计划",
    "backlog": "之前代办",
}


def _parse_task_date(t, key):
    """Return date or None from task start_time/end_time."""
    s = (t.get(key) or '')[:10]
    if len(s) < 10:
        return None
    try:
        return date(int(s[:4]), int(s[5:7]), int(s[8:10]))
    except (ValueError, TypeError):
        return None


def _is_task_in_date(task, d):
    """任务是否在日期 d 当天（开始或结束在该日）。"""
    st = _parse_task_date(task, 'start_time')
    et = _parse_task_date(task, 'end_time')
    return st == d or et == d


def _task_in_range(task, start_d, end_d):
    """任务开始或结束是否在 [start_d, end_d] 内。"""
    st = _parse_task_date(task, 'start_time')
    et = _parse_task_date(task, 'end_time')
    for d in (st, et):
        if d and start_d <= d <= end_d:
            return True
    return False


def _task_row_bg_and_progress(task):
    """Return (tr_bg_class, progress_label or '') for status/urgency row styling. progress_label only for in_progress."""
    from datetime import date
    status = task.get('status') or 'not_started'
    status_bg = {
        'abandoned': 'bg-gray-100',
        'not_started': 'bg-slate-50',
        'in_progress': 'bg-blue-50',
        'pending_review': 'bg-violet-50',
        'review_passed': 'bg-green-50',
        'review_failed': 'bg-orange-50',
    }
    bg = status_bg.get(status, 'bg-white')
    progress_label = ''
    if status == 'in_progress' and task.get('end_time'):
        try:
            end_d = date.fromisoformat((task.get('end_time') or '')[:10])
            today = date.today()
            if end_d < today:
                delta = (today - end_d).days
                if delta >= 7:
                    bg, progress_label = 'bg-red-200', '严重超时'
                else:
                    bg, progress_label = 'bg-red-50', '超时'
            else:
                delta = (end_d - today).days
                if delta <= 3:
                    bg, progress_label = 'bg-amber-50', '即将超时'
                else:
                    bg, progress_label = 'bg-emerald-50', '正常'
        except Exception:
            bg, progress_label = status_bg.get(status, 'bg-blue-50'), '正常'
    elif status != 'in_progress':
        bg = status_bg.get(status, 'bg-white')
    return bg, progress_label


def _my_tasks_html(tasks, sort_by='remaining', sort2='', project_filter='', urgency_filter='', status_filter='', overdue_filter='', projects_for_filter=None, view_range='', soon_count=0, overdue_count=0, plan_filter='', quick_filter=''):
    import html
    from urllib.parse import urlencode
    projects_for_filter = projects_for_filter or []
    status_labels = dict(TASK_STATUSES)
    status_badge_cls = {
        'abandoned': 'bg-gray-200 text-gray-600',
        'not_started': 'bg-slate-100 text-slate-600',
        'in_progress': 'bg-blue-100 text-blue-700',
        'pending_review': 'bg-violet-100 text-violet-700',
        'review_passed': 'bg-green-100 text-green-700',
        'review_failed': 'bg-orange-100 text-orange-700',
        'done': 'bg-emerald-100 text-emerald-700',
    }
    def urgency_stars(u):
        u = 1 if u is None else max(1, min(5, int(u)))
        return ('🌟' * u) + ('☆' * (5 - u))
    def qs(extra):
        p = {'sort': sort_by}
        if sort2:
            p['sort2'] = sort2
        if project_filter:
            p['project'] = project_filter
        if urgency_filter:
            p['urgency'] = urgency_filter
        if status_filter:
            p['status'] = status_filter
        if overdue_filter:
            p['overdue'] = overdue_filter
        if view_range:
            p['view'] = view_range
        if plan_filter:
            p['plan'] = plan_filter
        if quick_filter:
            p['quick'] = quick_filter
        p.update(extra)
        return urlencode(p)
    rows = []
    for t in tasks:
        row_bg, progress_label = _task_row_bg_and_progress(t)
        status_text = status_labels.get(t.get('status', ''), t.get('status', ''))
        if progress_label:
            status_text += ' · ' + progress_label
        overdue_badge = ''
        if progress_label == '超时' or progress_label == '严重超时':
            overdue_badge = ' <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-red-600 text-white uppercase">' + ('严重超时' if progress_label == '严重超时' else '已超时') + '</span>'
        elif progress_label == '即将超时':
            overdue_badge = ' <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-amber-500 text-white">即将超时</span>'
        elif progress_label == '正常' and t.get('status') == 'in_progress':
            overdue_badge = ' <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-500 text-white">正常</span>'
        tr_extra = ' border-l-4 border-l-red-600' if progress_label in ('超时', '严重超时') else (' border-l-4 border-l-amber-500' if progress_label == '即将超时' else '')
        comments = t.get('comments') or []
        last_comment = comments[-1] if comments else None
        comment_summary = str(len(comments)) + '条评论'
        if last_comment:
            content_preview = (last_comment.get('content') or '')[:8]
            if len(last_comment.get('content') or '') > 8:
                content_preview += '…'
            comment_summary += ' 最后: ' + html.escape(last_comment.get('user') or '') + ' ' + html.escape(content_preview)
        up = t.get('user_plan') or ''
        plan_opts = ''.join(
            '<option value="%s"%s>%s</option>' % (k, ' selected' if up == k else '', v)
            for k, v in PLAN_LABELS.items()
        ) + '<option value=""' + (' selected' if not up else '') + '>未规划</option>'
        plan_sel = '<select class="task-plan-sel text-xs border rounded px-1 py-0.5" data-pid="%s" data-tid="%s" data-current="%s">%s</select>' % (html.escape(t.get('project_id', '')), html.escape(t.get('id', '')), html.escape(up or ''), plan_opts)
        sbadge = status_badge_cls.get(t.get('status', ''), 'bg-slate-100 text-slate-700')
        row_fmt = '<tr class="border-b border-gray-100 transition ' + row_bg + tr_extra + '"><td class="px-4 py-3 text-sm text-gray-800">{0}</td><td class="px-4 py-3 font-medium text-gray-900">{1}</td><td class="px-4 py-3 text-amber-500" title="紧急程度">{2}</td><td class="px-4 py-3 text-sm text-gray-600">{3}</td><td class="px-4 py-3"><span class="inline-flex px-2 py-0.5 rounded text-xs font-medium ' + sbadge + '">{4}</span>{5}</td><td class="px-4 py-3 text-sm text-gray-500">{6} ~ {7}</td><td class="px-4 py-3"><span class="mr-2">{8}</span><a href="/admin/projects/{9}/tasks" class="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 transition mr-2">进入项目</a><button type="button" class="my-task-edit-btn inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 transition" data-project-id="{10}" data-task-id="{11}">编辑任务</button><span class="text-xs text-gray-500 block mt-1">{12}</span></td></tr>'
        rows.append(row_fmt.format(
            html.escape(t.get('project_name', '')),
            html.escape(t.get('title', '')),
            urgency_stars(t.get('urgency', 1)),
            html.escape(t.get('current_assignee', t.get('current_role', ''))),
            html.escape(status_text),
            overdue_badge,
            (t.get('start_time') or '')[:10],
            (t.get('end_time') or '')[:10],
            plan_sel,
            html.escape(t.get('project_id', '')),
            html.escape(t.get('project_id', '')),
            html.escape(t.get('id', '')),
            comment_summary,
        ))
    empty_html = '<tr><td colspan="7" class="px-4 py-16 text-center"><div class="max-w-sm mx-auto"><div class="text-5xl text-slate-300 mb-4"><i class="fas fa-clipboard-list"></i></div><p class="text-gray-600 font-medium mb-1">暂无符合条件的任务</p><p class="text-sm text-gray-400 mb-4">您负责的任务会在此展示。试试切换筛选条件，或前往项目管理查看任务。</p><a href="/admin/projects" class="inline-flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 transition"><i class="fas fa-folder-open"></i>进入项目管理</a></div></td></tr>'
    rows_html = ''.join(rows) if rows else empty_html
    sort_links = []
    for val, label in [('remaining', '剩余时间'), ('status', '状态'), ('urgency', '紧急程度'), ('start_time', '开始时间'), ('role', '负责人')]:
        cls = 'font-medium text-indigo-600' if sort_by == val else 'text-gray-600 hover:text-indigo-600'
        sort_links.append('<a href="/admin/my-tasks?' + qs({'sort': val}) + '" class="' + cls + ' text-sm">' + label + '</a>')
    sort_bar = '首要：' + (' | '.join(sort_links))
    sort2_opts = '<option value="">无</option>' + ''.join(
        '<option value="%s"%s>%s</option>' % (v, ' selected' if sort2 == v else '', l)
        for v, l in [('remaining', '剩余时间'), ('status', '状态'), ('urgency', '紧急程度'), ('start_time', '开始时间'), ('role', '负责人')]
    )
    sort_bar += ' &nbsp; 次要：<form method="get" action="/admin/my-tasks" class="inline-flex items-center gap-1 ml-2"><input type="hidden" name="sort" value="' + html.escape(sort_by) + '"><input type="hidden" name="project" value="' + html.escape(project_filter) + '"><input type="hidden" name="urgency" value="' + html.escape(urgency_filter) + '"><input type="hidden" name="status" value="' + html.escape(status_filter) + '"><input type="hidden" name="overdue" value="' + html.escape(overdue_filter) + '"><input type="hidden" name="view" value="' + html.escape(view_range) + '"><input type="hidden" name="plan" value="' + html.escape(plan_filter) + '"><input type="hidden" name="quick" value="' + html.escape(quick_filter) + '"><select name="sort2" class="px-2 py-1 border border-gray-200 rounded text-sm" onchange="this.form.submit()">' + sort2_opts + '</select></form>'
    quick_tabs = '<div class="flex gap-2 mb-3 flex-wrap items-center"><span class="text-xs font-medium text-gray-500 mr-1">快速筛选：</span><a href="/admin/my-tasks?' + qs({'quick': ''}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-slate-700 text-white' if not quick_filter else 'bg-slate-100 text-slate-600 hover:bg-slate-200') + '">全部</a><a href="/admin/my-tasks?' + qs({'quick': 'doing'}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-blue-600 text-white' if quick_filter == 'doing' else 'bg-blue-50 text-blue-700 hover:bg-blue-100') + '"><i class="fas fa-play-circle text-xs mr-1"></i>待办</a><a href="/admin/my-tasks?' + qs({'quick': 'review'}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-violet-600 text-white' if quick_filter == 'review' else 'bg-violet-50 text-violet-700 hover:bg-violet-100') + '"><i class="fas fa-clipboard-check text-xs mr-1"></i>待验收</a><a href="/admin/my-tasks?' + qs({'quick': 'soon'}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-amber-600 text-white' if quick_filter == 'soon' else 'bg-amber-50 text-amber-700 hover:bg-amber-100') + '" title="' + str(soon_count) + ' 条"><i class="fas fa-clock text-xs mr-1"></i>即将超时</a><a href="/admin/my-tasks?' + qs({'quick': 'overdue'}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-red-600 text-white' if quick_filter == 'overdue' else 'bg-red-50 text-red-700 hover:bg-red-100') + '" title="' + str(overdue_count) + ' 条"><i class="fas fa-exclamation-triangle text-xs mr-1"></i>已超时</a></div>'
    plan_tabs = '<div class="flex gap-2 mb-3 flex-wrap"><a href="/admin/my-tasks?' + qs({'plan': ''}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-indigo-600 text-white' if not plan_filter else 'bg-gray-100 text-gray-700 hover:bg-gray-200') + '">全部</a><a href="/admin/my-tasks?' + qs({'plan': '__none__'}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-indigo-600 text-white' if plan_filter == '__none__' else 'bg-gray-100 text-gray-700 hover:bg-gray-200') + '">未规划</a>' + ''.join('<a href="/admin/my-tasks?' + qs({'plan': k}) + '" class="px-3 py-1.5 rounded-lg text-sm font-medium ' + ('bg-indigo-600 text-white' if plan_filter == k else 'bg-gray-100 text-gray-700 hover:bg-gray-200') + '">' + html.escape(v) + '</a>' for k, v in PLAN_LABELS.items()) + '</div>'
    view_opts = '<option value="">全部</option><option value="today"' + (' selected' if view_range == 'today' else '') + '>今日</option><option value="week"' + (' selected' if view_range == 'week' else '') + '>本周</option>'
    project_opts = '<option value="">全部项目</option>' + ''.join(
        '<option value="%s"%s>%s</option>' % (html.escape(p['id']), ' selected' if p['id'] == project_filter else '', html.escape(p['name']))
        for p in projects_for_filter
    )
    urgency_opts = '<option value="">全部紧急程度</option>' + ''.join(
        '<option value="%s"%s>%s星</option>' % (i, ' selected' if urgency_filter == str(i) else '', i) for i in range(1, 6)
    )
    status_opts = '<option value="">全部状态</option>' + ''.join(
        '<option value="%s"%s>%s</option>' % (html.escape(k), ' selected' if status_filter == k else '', html.escape(v))
        for k, v in TASK_STATUSES
    )
    overdue_opts = '<option value="">是否超时</option><option value="normal"%s>正常</option><option value="soon"%s>即将超时</option><option value="overdue"%s>超时</option>' % (
        ' selected' if overdue_filter == 'normal' else '', ' selected' if overdue_filter == 'soon' else '', ' selected' if overdue_filter == 'overdue' else ''
    )
    plan_opts_filter = '<option value="">全部</option><option value="__none__"' + (' selected' if plan_filter == '__none__' else '') + '>未规划</option>' + ''.join('<option value="%s"%s>%s</option>' % (k, ' selected' if plan_filter == k else '', v) for k, v in PLAN_LABELS.items())
    filter_form = '<form method="get" action="/admin/my-tasks" class="flex flex-wrap gap-3 items-center mt-2"><input type="hidden" name="sort" value="' + html.escape(sort_by) + '"><input type="hidden" name="sort2" value="' + html.escape(sort2) + '"><input type="hidden" name="quick" value="' + html.escape(quick_filter) + '"><select name="plan" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm">' + plan_opts_filter + '</select><select name="view" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm">' + view_opts + '</select><select name="project" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm">' + project_opts + '</select><select name="urgency" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm">' + urgency_opts + '</select><select name="status" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm">' + status_opts + '</select><select name="overdue" class="px-3 py-1.5 border border-gray-200 rounded-lg text-sm">' + overdue_opts + '</select><button type="submit" class="px-3 py-1.5 bg-indigo-100 text-indigo-700 rounded-lg text-sm font-medium">筛选</button></form>'
    reminder = ''
    if soon_count or overdue_count:
        reminder = '<p class="text-sm text-amber-700 mt-2">任务提醒：即将超时 <strong>%d</strong> 条，已超时 <strong>%d</strong> 条</p>' % (soon_count, overdue_count)
    return '''
<div class="bg-white rounded-2xl shadow-md border border-gray-200 overflow-hidden">
    <div class="px-6 py-6 border-b border-gray-100 bg-gradient-to-r from-slate-50 to-white">
        <div class="flex justify-between items-center flex-wrap gap-2">
            <h2 class="text-xl font-semibold text-gray-800">我的任务</h2>
            <a href="/admin" class="inline-flex items-center px-4 py-1.5 rounded-lg text-sm font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 transition">← 返回管理中心</a>
        </div>
        ''' + reminder + '''
        ''' + quick_tabs + '''
        ''' + plan_tabs + '''
        <div class="mt-4 p-4 bg-white/80 rounded-xl border border-gray-100">
            <div class="text-sm font-medium text-gray-700 mb-2">筛选</div>
            ''' + filter_form + '''
        </div>
        <div class="mt-4 p-3 bg-white/60 rounded-lg border border-gray-100 text-sm text-gray-600">排序：''' + sort_bar + '''</div>
    </div>
    <div class="overflow-x-auto p-2">
        <table class="min-w-full"><thead class="bg-gray-50"><tr>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">项目</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">任务</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">紧急程度</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">当前负责人</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">状态</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">时间</th>
            <th class="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">操作</th>
        </tr></thead><tbody>''' + rows_html + '''</tbody></table>
    </div>
</div>
<div id="myTaskEditModal" class="hidden fixed inset-0 bg-black/50 flex items-center justify-center z-[70] p-4 overflow-y-auto" onclick="if(event.target===this) document.getElementById('myTaskEditModal').classList.add('hidden')">
    <div id="myTaskEditModalContent" class="bg-white rounded-2xl shadow-2xl max-w-lg w-full my-4 p-6 max-h-[90vh] overflow-y-auto" onclick="event.stopPropagation()">
        <h4 class="text-lg font-semibold text-gray-800 mb-4">编辑任务</h4>
        <div class="space-y-3 text-sm">
            <div><label class="block text-gray-600 mb-1 font-medium">任务名称</label><input type="text" id="myTaskEditTitle" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"></div>
            <div><label class="block text-gray-600 mb-1 font-medium">具体内容</label><textarea id="myTaskEditContent" rows="3" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500"></textarea></div>
            <div class="grid grid-cols-2 gap-2"><div><label class="block text-gray-600 mb-1 font-medium">开始时间</label><input type="date" id="myTaskEditStart" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg"></div><div><label class="block text-gray-600 mb-1 font-medium">完成时间</label><input type="date" id="myTaskEditEnd" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg"></div></div>
            <div><label class="block text-gray-600 mb-1 font-medium">紧急程度</label><div id="myTaskEditUrgency" class="flex gap-1"><span class="my-edit-urgency-star cursor-pointer text-2xl text-amber-400" data-urgency="1">🌟</span><span class="my-edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="2">🌟</span><span class="my-edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="3">🌟</span><span class="my-edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="4">🌟</span><span class="my-edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="5">🌟</span></div><input type="hidden" id="myTaskEditUrgencyVal" value="1"></div>
            <div id="myTaskEditStatusWrap" class="hidden"><div class="grid grid-cols-2 gap-2"><div><label class="block text-gray-600 mb-1 font-medium">状态</label><select id="myTaskEditStatus" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg"></select></div><div><label class="block text-gray-600 mb-1 font-medium">当前负责人</label><select id="myTaskEditAssignee" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg"></select></div></div></div>
            <div><label class="block text-gray-600 mb-1 font-medium">附件</label><div id="myTaskEditAttachmentList" class="mb-1 text-xs text-gray-500 space-y-1"></div><input type="file" id="myTaskEditFileInput" multiple class="text-sm"></div>
            <div class="border-t pt-3 mt-3"><label class="block text-gray-600 mb-1 font-medium">评论</label><div id="myTaskEditCommentsList" class="mb-2 max-h-32 overflow-y-auto text-xs space-y-1.5 border border-gray-100 rounded p-2 bg-gray-50"></div><div class="flex gap-2"><input type="text" id="myTaskEditNewComment" placeholder="追加评论…" class="flex-1 px-3 py-1.5 border rounded text-sm"><button type="button" id="myTaskEditBtnComment" class="px-3 py-2 bg-blue-600 text-white rounded text-sm">发送</button></div></div>
        </div>
        <div class="flex gap-3 mt-6"><button type="button" onclick="saveMyTaskEdit()" class="flex-1 px-4 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition">保存</button><button type="button" onclick="document.getElementById('myTaskEditModal').classList.add('hidden')" class="px-4 py-2.5 border border-gray-200 rounded-lg text-gray-700 hover:bg-gray-50 transition">取消</button></div>
    </div>
</div>
<script>
var STATUS_LABELS_MY = ''' + json.dumps(dict(TASK_STATUSES)).replace('<', '\\u003c') + ''';
function escAttr(s){ var x=(s||"").toString(); return x.replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function renderMyTaskEditComments(comments){ var el=document.getElementById("myTaskEditCommentsList"); if(!el) return; var c=comments||[]; el.innerHTML=c.length ? c.map(function(e){ return '<div class="py-0.5"><span class="font-medium">'+escAttr(e.user||"")+'</span> <span class="text-gray-400">'+(e.at?e.at.slice(0,16):"")+'</span><br>'+escAttr(e.content||"")+'</div>'; }).join("") : '<div class="text-gray-500">暂无评论</div>'; }
document.querySelectorAll(".my-task-edit-btn").forEach(function(btn){ btn.onclick=function(){ openMyTaskEdit(btn.getAttribute("data-project-id"), btn.getAttribute("data-task-id")); }; });
document.addEventListener("change", function(e){ var sel=e.target; if(!sel||!sel.classList||!sel.classList.contains("task-plan-sel")) return; var pid=sel.getAttribute("data-pid"), tid=sel.getAttribute("data-tid"), plan=sel.value||"", orig=sel.getAttribute("data-current")||""; fetch("/admin/my-tasks/set-plan", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project_id: pid, task_id: tid, plan_type: plan }), credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); sel.value=orig; return; } sel.setAttribute("data-current", plan); location.reload(); }); });
(function(){ function setMyUrgencyStars(contentEl, value){ if(!contentEl) return; var h=document.getElementById("myTaskEditUrgencyVal"); if(h) h.value=String(value); var v=Math.max(1, Math.min(5, value)); contentEl.querySelectorAll(".my-edit-urgency-star").forEach(function(s){ var su=parseInt(s.getAttribute("data-urgency"),10)||1; s.classList.remove("text-amber-400","text-gray-300"); s.classList.add(su<=v ? "text-amber-400" : "text-gray-300"); }); } var overlay=document.getElementById("myTaskEditModal"); if(!overlay) return; overlay.addEventListener("click", function(e){ var star=e.target.closest(".my-edit-urgency-star"); if(!star) return; var content=document.getElementById("myTaskEditModalContent"); if(!content||!content.contains(star)) return; var u=parseInt(star.getAttribute("data-urgency"),10)||1; setMyUrgencyStars(content, u); }, true); window._setMyUrgencyStars=setMyUrgencyStars; })();
var myTaskEditBtnComment=document.getElementById("myTaskEditBtnComment");
if(myTaskEditBtnComment) myTaskEditBtnComment.onclick=function(){ var content=(document.getElementById("myTaskEditNewComment")||{}).value.trim(); if(!content){ alert("请输入评论"); return; } var pid=window._myEditProjectId, tid=window._myEditTaskId; if(!pid||!tid) return; fetch("/admin/projects/"+encodeURIComponent(pid)+"/tasks/"+encodeURIComponent(tid)+"/comment", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ content: content }), credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); return; } window._myEditComments=window._myEditComments||[]; window._myEditComments.push({ user: d.user||"", content: content, at: d.at||"" }); renderMyTaskEditComments(window._myEditComments); document.getElementById("myTaskEditNewComment").value=""; }); };
function openMyTaskEdit(projectId, taskId){
  fetch("/admin/projects/"+encodeURIComponent(projectId)+"/tasks/list", { credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){
    if(d.error){ alert(d.error); return; }
    var t=(d.tasks||[]).find(function(x){ return x.id===taskId; });
    if(!t){ alert("任务不存在"); return; }
    window._myEditProjectId=projectId; window._myEditTaskId=taskId; window._myEditParticipants=d.participants||[]; window._myEditComments=(t.comments||[]).slice();
    document.getElementById("myTaskEditTitle").value=t.title||"";
    document.getElementById("myTaskEditContent").value=t.content||"";
    document.getElementById("myTaskEditStart").value=(t.start_time||"").slice(0,10);
    document.getElementById("myTaskEditEnd").value=(t.end_time||"").slice(0,10);
    var raw=t.urgency; var u=Math.max(1, Math.min(5, (typeof raw==="number"&&!isNaN(raw)) ? raw : (parseInt(raw,10)||Number(raw)||1)));
    var contentEl=document.getElementById("myTaskEditModalContent");
    if(window._setMyUrgencyStars) window._setMyUrgencyStars(contentEl, u);
    else { document.getElementById("myTaskEditUrgencyVal").value=String(u); contentEl&&contentEl.querySelectorAll(".my-edit-urgency-star").forEach(function(s){ var su=parseInt(s.getAttribute("data-urgency"),10)||1; s.classList.remove("text-amber-400","text-gray-300"); s.classList.add(su<=u ? "text-amber-400" : "text-gray-300"); }); }
    renderMyTaskEditComments(window._myEditComments);
    document.getElementById("myTaskEditNewComment").value="";
    var wrap=document.getElementById("myTaskEditStatusWrap");
    var canSA=t.can_edit_status_assignee;
    wrap.classList.toggle("hidden",!canSA);
    if(canSA){
      var selS=document.getElementById("myTaskEditStatus"); selS.innerHTML="";
      for(var k in STATUS_LABELS_MY){ var o=document.createElement("option"); o.value=k; o.textContent=STATUS_LABELS_MY[k]; if(t.status===k) o.selected=true; selS.appendChild(o); }
      var selA=document.getElementById("myTaskEditAssignee"); selA.innerHTML="";
      (window._myEditParticipants||[]).forEach(function(p){ var o=document.createElement("option"); o.value=p.user; o.textContent=p.user+" ("+p.role+")"; if(t.current_assignee===p.user) o.selected=true; selA.appendChild(o); });
    }
    window._myEditAttachments=(t.attachments||[]).slice();
    var listEl=document.getElementById("myTaskEditAttachmentList"); listEl.innerHTML="";
    (window._myEditAttachments||[]).forEach(function(a){ var span=document.createElement("span"); span.className="block"; span.innerHTML='<a href="'+escAttr(a.url)+'" target="_blank" class="text-blue-600">'+escAttr(a.name)+'</a> <a href="#" class="text-red-500 text-xs">移除</a>'; var link=span.querySelector('a[href="#"]'); if(link) link.onclick=function(){ window._myEditAttachments=window._myEditAttachments.filter(function(x){return x.url!==a.url;}); span.remove(); return false; }; listEl.appendChild(span); });
    document.getElementById("myTaskEditModal").classList.remove("hidden");
    setTimeout(function(){ if(window._setMyUrgencyStars) window._setMyUrgencyStars(contentEl, u); }, 0);
  });
}
function saveMyTaskEdit(){
  var pid=window._myEditProjectId, id=window._myEditTaskId;
  if(!pid||!id) return;
  var urgencyEl=document.getElementById("myTaskEditUrgencyVal"); var urgency=urgencyEl ? Math.max(1, Math.min(5, parseInt(urgencyEl.value,10)||1)) : 1;
  var payload={ title: document.getElementById("myTaskEditTitle").value.trim(), content: document.getElementById("myTaskEditContent").value.trim(), start_time: document.getElementById("myTaskEditStart").value, end_time: document.getElementById("myTaskEditEnd").value, urgency: urgency, attachments: window._myEditAttachments||[] };
  if(document.getElementById("myTaskEditStatusWrap")&&!document.getElementById("myTaskEditStatusWrap").classList.contains("hidden")){ payload.status=document.getElementById("myTaskEditStatus").value; payload.current_assignee=document.getElementById("myTaskEditAssignee").value; }
  fetch("/admin/projects/"+encodeURIComponent(pid)+"/tasks/"+encodeURIComponent(id), { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); return; } document.getElementById("myTaskEditModal").classList.add("hidden"); location.reload(); });
}
var myTaskFileInput=document.getElementById("myTaskEditFileInput");
if(myTaskFileInput) myTaskFileInput.onchange=function(){ var files=this.files, pid=window._myEditProjectId; if(!files||!files.length||!pid) return; for(var i=0;i<files.length;i++){ (function(f){ var fd=new FormData(); fd.append("file", f); fetch("/admin/projects/"+encodeURIComponent(pid)+"/tasks/upload", { method: "POST", body: fd, credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.url){ window._myEditAttachments=window._myEditAttachments||[]; window._myEditAttachments.push({ name: d.name||f.name, url: d.url }); var span=document.createElement("span"); span.className="block"; span.innerHTML=escAttr(d.name||f.name)+' <a href="#" class="text-red-500 text-xs">移除</a>'; var link=span.querySelector('a[href="#"]'); if(link) link.onclick=function(){ window._myEditAttachments=window._myEditAttachments.filter(function(x){ return x.url!==d.url; }); span.remove(); return false; }; document.getElementById("myTaskEditAttachmentList").appendChild(span); } else alert(d.error||"上传失败"); }); })(files[i]); } this.value=""; };
</script>
'''


def build_my_tasks_page_content(request, username, role_to_first_assignee):
    """跨项目汇总：当前用户作为当前负责人的任务。"""
    username = _current_username()
    my_tasks = []
    for pid, proj in projects_db.items():
        if not can_view_project(pid, username):
            continue
        for t in (project_tasks_db.get(pid) or []):
            cur = t.get('current_assignee') or (role_to_first_assignee(pid, t.get('current_role')) if t.get('current_role') else '')
            if cur == username:
                task = dict(t, project_id=pid, project_name=proj.get('name', pid))
                if task.get('urgency') is None or not (1 <= int(task.get('urgency', 1)) <= 5):
                    task['urgency'] = 1
                my_tasks.append(task)
    projects_for_filter = []
    seen_pid = set()
    for t in my_tasks:
        pid = t.get('project_id')
        if pid and pid not in seen_pid:
            seen_pid.add(pid)
            projects_for_filter.append({'id': pid, 'name': t.get('project_name', pid)})
    project_filter = request.args.get('project', '')
    urgency_filter = request.args.get('urgency', '')
    status_filter = request.args.get('status', '')
    overdue_filter = request.args.get('overdue', '')
    quick_filter = request.args.get('quick', '').strip()
    if quick_filter:
        if quick_filter == 'doing':
            my_tasks = [t for t in my_tasks if t.get('status') in ('not_started', 'in_progress')]
        elif quick_filter == 'review':
            my_tasks = [t for t in my_tasks if t.get('status') == 'pending_review']
        elif quick_filter == 'overdue':
            overdue_filter = 'overdue'
        elif quick_filter == 'soon':
            overdue_filter = 'soon'
    if project_filter:
        my_tasks = [t for t in my_tasks if t.get('project_id') == project_filter]
    if urgency_filter:
        try:
            u = int(urgency_filter)
            if 1 <= u <= 5:
                my_tasks = [t for t in my_tasks if (int(t.get('urgency', 1)) or 1) == u]
        except ValueError:
            pass
    if status_filter:
        my_tasks = [t for t in my_tasks if t.get('status') == status_filter]
    from datetime import date, timedelta
    view_range = request.args.get('view', '')  # today | week | all
    _today = date.today()
    soon_count = sum(1 for t in my_tasks if _task_row_bg_and_progress(t)[1] == '即将超时')
    overdue_count = sum(1 for t in my_tasks if _task_row_bg_and_progress(t)[1] in ('超时', '严重超时'))
    if view_range == 'today':
        my_tasks = [t for t in my_tasks if _is_task_in_date(t, _today)]
    elif view_range == 'week':
        week_end = _today + timedelta(days=6 - _today.weekday())
        week_start = week_end - timedelta(days=6)
        my_tasks = [t for t in my_tasks if _task_in_range(t, week_start, week_end)]
    plan_filter = request.args.get('plan', '').strip()
    for t in my_tasks:
        t['user_plan'] = get_task_plan(username, t.get('project_id'), t.get('id'))
    if plan_filter == '__none__':
        my_tasks = [t for t in my_tasks if not t.get('user_plan')]
    elif plan_filter and plan_filter in ('today_todo', 'today_done', 'tomorrow_plan', 'backlog'):
        my_tasks = [t for t in my_tasks if t.get('user_plan') == plan_filter]
    if overdue_filter and overdue_filter in ('normal', 'soon', 'overdue'):
        today = _today
        in3 = today + timedelta(days=3)
        def _end_date(t):
            et = t.get('end_time') or ''
            if not et or len(et) < 10:
                return None
            try:
                return date(int(et[:4]), int(et[5:7]), int(et[8:10]))
            except Exception:
                return None
        def _keep_overdue(t):
            if t.get('status') in ('done', 'abandoned'):
                return True
            ed = _end_date(t)
            if not ed:
                return overdue_filter == 'normal'
            if overdue_filter == 'normal':
                return ed >= today and (ed - today).days > 3
            if overdue_filter == 'soon':
                return ed >= today and (ed - today).days <= 3
            return ed < today
        my_tasks = [t for t in my_tasks if _keep_overdue(t)]
    sort_by = (request.args.get('sort') or 'remaining').strip()
    sort2 = (request.args.get('sort2') or '').strip()
    def _end_tuple(x):
        return (x.get('end_time') or '', x.get('created_at') or '')
    def _prim(x):
        if sort_by == 'status': return (x.get('status') or '',)
        if sort_by == 'urgency': return (-(int(x.get('urgency', 1)) or 1),)
        if sort_by == 'start_time': return (x.get('start_time') or '',)
        if sort_by == 'role': return (x.get('current_assignee') or '',)
        return _end_tuple(x)
    def _sec(x):
        if sort2 == 'status': return (x.get('status') or '',)
        if sort2 == 'urgency': return (-(int(x.get('urgency', 1)) or 1),)
        if sort2 == 'start_time': return (x.get('start_time') or '',)
        if sort2 == 'role': return (x.get('current_assignee') or '',)
        if sort2 == 'remaining': return _end_tuple(x)
        return ()
    def _tid(x):
        return (x.get('id') or '',)
    my_tasks.sort(key=lambda x: _prim(x) + _sec(x) + _end_tuple(x) + _tid(x))
    content = _my_tasks_html(my_tasks, sort_by, sort2, project_filter, urgency_filter, status_filter, overdue_filter, projects_for_filter, view_range, soon_count, overdue_count, plan_filter, quick_filter)
    return content


def render_my_tasks_page(request, username, role_to_first_assignee):
    return build_my_tasks_page_content(request, username, role_to_first_assignee)

# -*- coding: utf-8 -*-
"""Admin project tasks pages."""

import json

from models.data import can_edit_project, can_view_project, projects_db
from routes.admin.views.my_tasks import TASK_STATUSES

def _project_tasks_stats_html(project_id, project_name):
    status_list = json.dumps([{'id': k, 'label': v} for k, v in TASK_STATUSES])
    return '''
<div class="space-y-6">
    <div class="flex flex-wrap items-center justify-between gap-4">
        <h2 class="text-xl font-semibold text-gray-800">任务统计 · ''' + project_name + '''</h2>
        <a href="/admin/projects/''' + project_id + '''/tasks" class="inline-flex items-center px-4 py-1.5 rounded-lg text-sm font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 transition">← 返回任务列表</a>
    </div>
    <div id="statsLoading" class="text-center py-12 text-gray-500">加载中…</div>
    <div id="statsContent" class="hidden space-y-8">
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div class="bg-white rounded-xl border border-gray-100 p-4 shadow-sm"><div class="text-sm text-gray-500">总任务数</div><div id="statTotal" class="text-2xl font-bold text-gray-800 mt-1">0</div></div>
            <div class="bg-white rounded-xl border border-gray-100 p-4 shadow-sm"><div class="text-sm text-gray-500">已超时</div><div id="statOverdue" class="text-2xl font-bold text-red-600 mt-1">0</div></div>
            <div class="bg-white rounded-xl border border-gray-100 p-4 shadow-sm"><div class="text-sm text-gray-500">即将超时</div><div id="statSoonOverdue" class="text-2xl font-bold text-amber-600 mt-1">0</div></div>
            <div class="bg-white rounded-xl border border-gray-100 p-4 shadow-sm"><div class="text-sm text-gray-500">已完成</div><div id="statDone" class="text-2xl font-bold text-green-600 mt-1">0</div></div>
        </div>
        <div class="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden p-6 max-w-3xl">
            <h3 class="text-lg font-semibold text-gray-800 mb-4">按状态分布（柱状图）</h3>
            <div class="h-64"><canvas id="chartByStatus"></canvas></div>
        </div>
        <div class="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden p-6 max-w-md mx-auto">
            <h3 class="text-lg font-semibold text-gray-800 mb-4">按状态分布（饼图）</h3>
            <div class="h-64 flex justify-center"><canvas id="chartPieStatus" class="max-w-xs"></canvas></div>
        </div>
        <div class="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden p-6 max-w-3xl">
            <h3 class="text-lg font-semibold text-gray-800 mb-4">各参与者任务状态（堆叠柱状图）</h3>
            <div class="h-80"><canvas id="chartByAssignee"></canvas></div>
        </div>
        <div class="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden p-6 max-w-md">
            <h3 class="text-lg font-semibold text-gray-800 mb-4">超时与即将超时</h3>
            <div class="h-48"><canvas id="chartOverdue"></canvas></div>
        </div>
    </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script>
var PROJECT_ID_STATS = ''' + json.dumps(project_id).replace('<', '\\u003c') + ''';
var STATUS_LIST = ''' + status_list + ''';
fetch("/admin/projects/"+PROJECT_ID_STATS+"/tasks/list", { credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){
    if(d.error){ document.getElementById("statsLoading").textContent=d.error; return; }
    document.getElementById("statsLoading").classList.add("hidden"); document.getElementById("statsContent").classList.remove("hidden");
    var tasks=d.tasks||[]; var now=new Date(); now.setHours(0,0,0,0); var in3=new Date(now); in3.setDate(in3.getDate()+3);
    var byStatus={}; var byAssignee={}; var overdue=0, soonOverdue=0, done=0;
    STATUS_LIST.forEach(function(s){ byStatus[s.id]=0; });
    tasks.forEach(function(t){
        var s=t.status||"not_started"; if(s in byStatus) byStatus[s]++; else byStatus[s]=1;
        var u=t.current_assignee||"未分配"; if(!byAssignee[u]) byAssignee[u]={}; STATUS_LIST.forEach(function(x){ byAssignee[u][x.id]=0; }); byAssignee[u][s]= (byAssignee[u][s]||0)+1;
        if(["done","abandoned"].indexOf(s)>=0) done++; else if(t.end_time){ var et=new Date(t.end_time.slice(0,10)); et.setHours(0,0,0,0); if(et<now) overdue++; else if(et<=in3) soonOverdue++; }
    });
    document.getElementById("statTotal").textContent=tasks.length; document.getElementById("statOverdue").textContent=overdue; document.getElementById("statSoonOverdue").textContent=soonOverdue; document.getElementById("statDone").textContent=done;
    var statusLabels=STATUS_LIST.map(function(s){ return s.label; }); var statusIds=STATUS_LIST.map(function(s){ return s.id; });
    var barData=statusIds.map(function(id){ return byStatus[id]||0; });
    new Chart(document.getElementById("chartByStatus"), { type: "bar", data: { labels: statusLabels, datasets: [{ label: "任务数", data: barData, backgroundColor: "rgba(99,102,241,0.7)", borderColor: "rgb(99,102,241)", borderWidth: 1, maxBarThickness: 36 }] }, options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { display: false }, ticks: { maxRotation: 45 } }, y: { beginAtZero: true, ticks: { stepSize: 1 } } }, plugins: { legend: { display: false } } } });
    var pieColors=["#ef4444","#f59e0b","#22c55e","#3b82f6","#8b5cf6","#ec4899","#14b8a6"];
    new Chart(document.getElementById("chartPieStatus"), { type: "doughnut", data: { labels: statusLabels, datasets: [{ data: barData, backgroundColor: pieColors.slice(0, statusLabels.length), borderWidth: 2 }] }, options: { responsive: true, maintainAspectRatio: true } });
    var assignees=Object.keys(byAssignee); var datasets=STATUS_LIST.map(function(s,i){ return { label: s.label, data: assignees.map(function(u){ return byAssignee[u][s.id]||0; }), backgroundColor: pieColors[i%pieColors.length], maxBarThickness: 32 }; });
    new Chart(document.getElementById("chartByAssignee"), { type: "bar", data: { labels: assignees, datasets: datasets }, options: { responsive: true, maintainAspectRatio: false, scales: { x: { stacked: true, grid: { display: false }, ticks: { maxRotation: 45 } }, y: { stacked: true, beginAtZero: true, ticks: { stepSize: 1 } } } } });
    new Chart(document.getElementById("chartOverdue"), { type: "bar", data: { labels: ["已超时","即将超时(3天内)"], datasets: [{ label: "任务数", data: [overdue, soonOverdue], backgroundColor: ["rgba(239,68,68,0.8)","rgba(245,158,11,0.8)"], borderWidth: 1, maxBarThickness: 48 }] }, options: { responsive: true, maintainAspectRatio: false, scales: { x: { grid: { display: false } }, y: { beginAtZero: true, ticks: { stepSize: 1 } } }, plugins: { legend: { display: false } } } });
});
</script>
'''


def _project_tasks_html(project_id, project_name, status_opts, participants_opts):
    return '''
<div class="bg-white rounded-2xl shadow-md border border-gray-200 overflow-hidden">
    <div class="px-6 py-5 border-b border-gray-100 bg-gradient-to-r from-slate-50 to-white flex flex-wrap items-center justify-between gap-4">
        <h2 class="text-xl font-semibold text-gray-800">任务列表 · ''' + project_name + '''</h2>
        <div class="flex items-center gap-2">
            <a href="/admin/projects/''' + project_id + '''/tasks/stats" class="inline-flex items-center px-4 py-2.5 rounded-lg text-sm font-medium text-violet-700 bg-violet-50 hover:bg-violet-100 transition">📊 任务统计</a>
            <a href="/admin/projects" class="inline-flex items-center px-4 py-2.5 rounded-lg text-sm font-medium text-gray-700 bg-white border border-gray-200 hover:bg-gray-50 transition">← 返回项目列表</a>
        </div>
    </div>
    <div class="p-5 md:p-6 border-b bg-slate-50/60">
        <div class="flex flex-wrap gap-3 items-end mb-3">
            <input type="text" id="taskFilter" placeholder="筛选任务名称、内容…" class="px-3 py-2.5 border border-gray-200 rounded-lg text-sm w-52 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500">
            <select id="taskFilterStatus" class="px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"><option value="">全部状态</option>''' + status_opts + '''</select>
            <select id="taskFilterUrgency" class="px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"><option value="">全部紧急程度</option><option value="1">1星</option><option value="2">2星</option><option value="3">3星</option><option value="4">4星</option><option value="5">5星</option></select>
            <select id="taskFilterOverdue" class="px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"><option value="">是否超时</option><option value="normal">正常</option><option value="soon">即将超时</option><option value="overdue">超时</option></select>
            <div class="flex rounded-lg overflow-hidden border border-gray-200 bg-white">
                <button type="button" id="btnMyTasks" class="px-4 py-2.5 text-sm font-medium bg-indigo-100 text-indigo-700">仅我的任务</button>
                <button type="button" id="btnAllTasks" class="px-4 py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-50">全部任务</button>
            </div>
            <div class="flex rounded-lg overflow-hidden border border-gray-200 bg-white">
                <button type="button" id="btnViewList" class="px-4 py-2.5 text-sm font-medium bg-indigo-100 text-indigo-700">列表</button>
                <button type="button" id="btnViewThumb" class="px-4 py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-50">缩略图</button>
            </div>
            <button type="button" id="btnBatchDelete" class="px-4 py-2.5 rounded-lg text-sm font-medium text-red-700 bg-red-50 hover:bg-red-100 transition ml-auto hidden">批量删除</button>
        </div>
        <div class="flex flex-wrap gap-3 items-center mt-2">
            <label class="text-sm text-gray-600">排序：</label>
            <select id="taskSortBy" class="px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500">
                <option value="default">默认</option>
                <option value="status">状态</option>
                <option value="urgency">紧急程度</option>
                <option value="start_time">开始时间</option>
                <option value="remaining">剩余时间</option>
                <option value="role">当前负责人</option>
            </select>
        </div>
        <div id="taskStats" class="text-sm text-gray-600 mt-2"></div>
    </div>
    <div class="p-4 md:p-5 flex justify-end">
        <button type="button" id="btnOpenCreateTask" class="px-6 py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-medium hover:bg-emerald-700 transition shadow-md">+ 创建任务</button>
    </div>
    <div id="createTaskModal" class="hidden fixed inset-0 bg-black/50 flex items-center justify-center z-[60] p-4 overflow-y-auto" onclick="if(event.target===this) document.getElementById('createTaskModal').classList.add('hidden')">
        <div id="createTaskModalContent" class="bg-white rounded-2xl shadow-xl max-w-lg w-full my-4 p-6" onclick="event.stopPropagation()">
            <h4 class="text-lg font-semibold text-gray-800 mb-4">创建任务</h4>
            <div class="space-y-3 text-sm">
                <div><label class="block text-gray-600 mb-1 font-medium">任务名称</label><input type="text" id="newTaskTitle" placeholder="任务名称" class="w-full px-3 py-2.5 border border-gray-200 rounded-lg focus:ring-2 focus:ring-emerald-500"></div>
                <div><label class="block text-gray-600 mb-1 font-medium">流转给（选择参与人）</label><select id="newTaskAssignUser" class="w-full px-3 py-2.5 border border-gray-200 rounded-lg"><option value="">请选择</option>''' + participants_opts + '''</select></div>
                <div class="grid grid-cols-2 gap-2"><div><label class="block text-gray-600 mb-1 font-medium">开始时间</label><input type="date" id="newTaskStart" class="w-full px-3 py-2.5 border border-gray-200 rounded-lg"></div><div><label class="block text-gray-600 mb-1 font-medium">完成时间</label><input type="date" id="newTaskEnd" class="w-full px-3 py-2.5 border border-gray-200 rounded-lg"></div></div>
                <div><label class="block text-gray-600 mb-1 font-medium">紧急程度</label><div id="newTaskUrgency" class="flex gap-1"><span class="urgency-star cursor-pointer text-2xl text-amber-400" data-urgency="1">🌟</span><span class="urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="2">🌟</span><span class="urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="3">🌟</span><span class="urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="4">🌟</span><span class="urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="5">🌟</span></div><input type="hidden" id="newTaskUrgencyVal" value="1"></div>
                <div><label class="block text-gray-600 mb-1 font-medium">具体内容</label><textarea id="newTaskContent" placeholder="具体内容、需要对接角色" rows="2" class="w-full px-3 py-2.5 border border-gray-200 rounded-lg"></textarea></div>
                <div><label class="block text-gray-600 mb-1 font-medium">附件</label><div id="newTaskAttachmentList" class="mb-1 text-xs text-gray-500 space-y-1"></div><input type="file" id="newTaskFileInput" multiple class="text-sm"></div>
            </div>
            <div class="flex gap-3 mt-5"><button type="button" id="btnCreateTask" class="flex-1 px-4 py-2.5 bg-emerald-600 text-white rounded-lg font-medium hover:bg-emerald-700 transition">创建</button><button type="button" onclick="document.getElementById('createTaskModal').classList.add('hidden')" class="px-4 py-2.5 border border-gray-200 rounded-lg hover:bg-gray-50 transition">取消</button></div>
        </div>
    </div>
    <div class="p-5 md:p-6">
        <ul id="taskList" class="space-y-4"></ul>
    </div>
</div>
<div id="flowLogModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[80vh] overflow-hidden flex flex-col" onclick="event.stopPropagation()">
        <div class="px-4 py-3 border-b font-semibold">任务流转日志</div>
        <div id="flowLogContent" class="p-4 overflow-y-auto text-sm"></div>
        <div class="p-4 border-t"><button type="button" onclick="document.getElementById('flowLogModal').classList.add('hidden')" class="px-4 py-1.5 border rounded text-sm">关闭</button></div>
    </div>
</div>
<div id="commentModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[80vh] overflow-hidden flex flex-col" onclick="event.stopPropagation()">
        <div class="px-4 py-3 border-b font-semibold">任务评论</div>
        <div id="commentList" class="p-4 overflow-y-auto text-sm flex-1"></div>
        <div class="p-4 border-t flex gap-2">
            <input type="text" id="newCommentContent" placeholder="输入评论…" class="flex-1 px-3 py-1.5 border rounded text-sm">
            <button type="button" id="btnAddComment" class="px-4 py-2 bg-blue-600 text-white rounded text-sm">发送</button>
        </div>
    </div>
</div>
<div id="statusModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-xl shadow-xl w-80 p-5" onclick="event.stopPropagation()">
        <h4 class="font-semibold mb-2">标记状态</h4>
        <select id="statusModalSelect" class="w-full px-3 py-1.5 border rounded text-sm mb-3"></select>
        <div class="flex gap-2"><button type="button" onclick="confirmStatusChange()" class="flex-1 px-4 py-2 bg-blue-600 text-white rounded text-sm">确认</button><button type="button" onclick="document.getElementById('statusModal').classList.add('hidden')" class="px-4 py-1.5 border rounded text-sm">取消</button></div>
    </div>
</div>
<div id="handoffModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-xl shadow-xl w-80 p-5" onclick="event.stopPropagation()">
        <h4 class="font-semibold mb-2">流转给</h4>
        <select id="handoffModalSelect" class="w-full px-3 py-1.5 border rounded text-sm mb-3"></select>
        <div class="flex gap-2"><button type="button" onclick="confirmHandoff()" class="flex-1 px-4 py-2 bg-blue-600 text-white rounded text-sm">确认</button><button type="button" onclick="document.getElementById('handoffModal').classList.add('hidden')" class="px-4 py-1.5 border rounded text-sm">取消</button></div>
    </div>
</div>
<div id="editTaskModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4 overflow-y-auto" onclick="if(event.target===this) this.classList.add('hidden')">
    <div id="editTaskModalContent" class="bg-white rounded-xl shadow-xl max-w-lg w-full my-4 p-5 max-h-[90vh] overflow-y-auto" onclick="event.stopPropagation()">
        <h4 class="font-semibold mb-3">编辑任务</h4>
        <div class="space-y-2 text-sm">
            <div><label class="block text-gray-600 mb-1">任务名称</label><input type="text" id="editTaskTitle" class="w-full px-3 py-1.5 border rounded"></div>
            <div><label class="block text-gray-600 mb-1">具体内容</label><textarea id="editTaskContent" rows="3" class="w-full px-3 py-1.5 border rounded"></textarea></div>
            <div class="grid grid-cols-2 gap-2"><div><label class="block text-gray-600 mb-1">开始时间</label><input type="date" id="editTaskStart" class="w-full px-3 py-1.5 border rounded"></div><div><label class="block text-gray-600 mb-1">完成时间</label><input type="date" id="editTaskEnd" class="w-full px-3 py-1.5 border rounded"></div></div>
            <div><label class="block text-gray-600 mb-1">紧急程度</label><div id="editTaskUrgency" class="flex gap-1"><span class="edit-urgency-star cursor-pointer text-2xl" data-urgency="1">🌟</span><span class="edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="2">🌟</span><span class="edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="3">🌟</span><span class="edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="4">🌟</span><span class="edit-urgency-star cursor-pointer text-2xl text-gray-300" data-urgency="5">🌟</span></div><input type="hidden" id="editTaskUrgencyVal" value="1"></div>
            <div id="editTaskStatusAssigneeWrap" class="hidden"><div class="grid grid-cols-2 gap-2"><div><label class="block text-gray-600 mb-1">状态</label><select id="editTaskStatus" class="w-full px-3 py-1.5 border rounded"></select></div><div><label class="block text-gray-600 mb-1">当前负责人</label><select id="editTaskAssignee" class="w-full px-3 py-1.5 border rounded"></select></div></div></div>
            <div><label class="block text-gray-600 mb-1">附件</label><div id="editTaskAttachmentList" class="mb-1 text-xs text-gray-500 space-y-1"></div><input type="file" id="editTaskFileInput" multiple class="text-sm"><span class="text-gray-400 text-xs ml-1">可传图片或文件</span></div>
            <div class="border-t pt-3 mt-3"><label class="block text-gray-600 mb-1 font-medium">评论</label><div id="editTaskCommentsList" class="mb-2 max-h-32 overflow-y-auto text-xs space-y-1.5 border border-gray-100 rounded p-2 bg-gray-50"></div><div class="flex gap-2"><input type="text" id="editTaskNewComment" placeholder="追加评论…" class="flex-1 px-3 py-1.5 border rounded text-sm"><button type="button" id="editTaskBtnComment" class="px-3 py-2 bg-blue-600 text-white rounded text-sm">发送</button></div></div>
        </div>
        <div class="flex gap-2 mt-4"><button type="button" onclick="saveEditTask()" class="flex-1 px-4 py-2 bg-blue-600 text-white rounded text-sm">保存</button><button type="button" onclick="document.getElementById('editTaskModal').classList.add('hidden')" class="px-4 py-1.5 border rounded text-sm">取消</button></div>
    </div>
</div>
<script>
var PROJECT_ID = ''' + json.dumps(project_id).replace('<', '\\u003c') + ''';
var STATUS_LABELS = ''' + json.dumps(dict(TASK_STATUSES)).replace('<', '\\u003c') + ''';
function escAttr(s){ var x=(s||"").toString(); return x.replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function escJs(s){ var x=(s||"").toString(); return x.replace(/\\\\/g,"\\\\\\\\").replace(/'/g,"\\\\'"); }
function loadTasks(){
    return fetch('/admin/projects/'+PROJECT_ID+'/tasks/list', { credentials:'same-origin' }).then(function(r){ return r.json().then(function(d){ return { ok: r.ok, data: d }; }).catch(function(){ return { ok: false, data: { error: "解析失败" } }; }); }).then(function(res){
        var d = res.data;
        if(!res.ok || d.error){ document.getElementById('taskList').innerHTML='<li class="text-gray-500">'+(d.error||'加载失败')+'</li>'; return; }
        window._allTasks = d.tasks||[]; window._myUsername = d.my_username||''; window._participants = d.participants||[];
        renderTasks(window._allTasks);
        var s = d.stats||{}; document.getElementById('taskStats').textContent = '共 '+s.total+' 个任务 · 已作废 '+s.abandoned+' · 尚未开始 '+s.not_started+' · 进行中 '+s.in_progress+' · 待验收 '+s.pending_review+' · 验收通过 '+s.review_passed+' · 验收未通过 '+s.review_failed+' · 已完成 '+s.done+' · 已超时 '+s.overdue+' · 即将超时 '+s.soon_overdue;
        var hasDel = (window._allTasks||[]).some(function(t){ return t.can_delete; }); document.getElementById('btnBatchDelete').classList.toggle('hidden', !hasDel);
    });
}
function taskRowBgAndProgress(t){
    var status=t.status||'not_started'; var bg='bg-white';
    var statusBg={ abandoned:'bg-gray-100', not_started:'bg-slate-50', in_progress:'bg-blue-50', pending_review:'bg-violet-50', review_passed:'bg-green-50', review_failed:'bg-orange-50' };
    bg=statusBg[status]||bg; var progressLabel='';
    if(status==='in_progress'&&t.end_time){ var now=new Date(); now.setHours(0,0,0,0); var et=new Date(t.end_time.slice(0,10)); et.setHours(0,0,0,0);
        if(et<now){ var days=(now-et)/86400000; bg=days>=7?'bg-red-200':'bg-red-50'; progressLabel=days>=7?'严重超时':'超时'; }
        else{ var days=(et-now)/86400000; if(days<=3){ bg='bg-amber-50'; progressLabel='即将超时'; } else{ bg='bg-emerald-50'; progressLabel='正常'; } }
    }
    return { bg: bg, progress: progressLabel };
}
function renderTasks(tasks){
    var list = document.getElementById('taskList');
    var filter = (document.getElementById('taskFilter')||{}).value.toLowerCase();
    var statusFilter = (document.getElementById('taskFilterStatus')||{}).value;
    var urgencyFilter = (document.getElementById('taskFilterUrgency')||{}).value;
    var overdueFilter = (document.getElementById('taskFilterOverdue')||{}).value;
    var sortBy = (document.getElementById('taskSortBy')||{}).value || 'default';
    var showOnlyMine = window._showOnlyMine;
    var myUser = window._myUsername||'';
    var now = new Date(); now.setHours(0,0,0,0);
    var in3 = new Date(now); in3.setDate(in3.getDate()+3);
    var arr = (tasks||[]).filter(function(t){
        if(showOnlyMine && t.current_assignee !== myUser) return false;
        if(filter && (t.title||'').toLowerCase().indexOf(filter)<0 && (t.content||'').toLowerCase().indexOf(filter)<0) return false;
        if(statusFilter && t.status!==statusFilter) return false;
        if(urgencyFilter){ var u=Number(t.urgency)||1; if(u!==Number(urgencyFilter)) return false; }
        if(overdueFilter&&t.status!=='done'&&t.status!=='abandoned'){ var et=t.end_time?new Date(t.end_time.slice(0,10)):null; if(et) et.setHours(0,0,0,0);
            if(overdueFilter==='normal'){ if(!t.end_time) return true; if(et<now) return false; if(et<=in3) return false; }
            else if(overdueFilter==='soon'){ if(!t.end_time) return false; if(et<now||et>in3) return false; }
            else if(overdueFilter==='overdue'){ if(!t.end_time) return false; if(et>=now) return false; }
        }
        return true;
    });
    arr.sort(function(a,b){
        if(sortBy==='status') return (a.status||'').localeCompare(b.status||'');
        if(sortBy==='urgency') return (b.urgency||1) - (a.urgency||1);
        if(sortBy==='start_time') return (a.start_time||'').localeCompare(b.start_time||'');
        if(sortBy==='remaining'){
            var ea = a.end_time ? new Date(a.end_time).getTime() : 0; var eb = b.end_time ? new Date(b.end_time).getTime() : 0;
            return ea - eb;
        }
        if(sortBy==='role') return (a.current_assignee||'').localeCompare(b.current_assignee||'');
        return 0;
    });
    var viewMode = window._taskViewMode || 'list';
    var cardCls = viewMode==='thumb' ? 'w-full max-w-[280px] min-h-[200px] flex flex-col' : '';
    list.className = viewMode==='thumb' ? 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5 max-w-7xl' : 'space-y-4';
    list.innerHTML = arr.map(function(t){
        var overdue = t.end_time && new Date(t.end_time) < new Date() && t.status!=='done' && t.status!=='abandoned';
        var rowStyle = taskRowBgAndProgress(t);
        var statusLabel = STATUS_LABELS[t.status] || t.status;
        var overdueBadge = '';
        if(rowStyle.progress==='超时'||rowStyle.progress==='严重超时') overdueBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-red-600 text-white uppercase ml-1">'+(rowStyle.progress==='严重超时'?'严重超时':'已超时')+'</span>';
        else if(rowStyle.progress==='即将超时') overdueBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-amber-500 text-white ml-1">即将超时</span>';
        else if(rowStyle.progress==='正常'&&t.status==='in_progress') overdueBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-500 text-white ml-1">正常</span>';
        if(rowStyle.progress) statusLabel += ' · '+rowStyle.progress;
        var isAssignee = t.current_assignee === myUser;
        var urgencyVal = Math.max(1, Math.min(5, parseInt(t.urgency,10)||1));
        var urgencyStars = ''; for(var i=1;i<=5;i++) urgencyStars += i<=urgencyVal ? '🌟' : '☆'; urgencyStars = '<span class="text-amber-500" title="紧急程度 '+urgencyVal+'">'+urgencyStars+'</span>';
        var actions = [];
        if(t.can_edit){ actions.push('<button onclick="openEditTask(\\''+escJs(t.id)+'\\')" class="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium text-blue-700 bg-blue-50 hover:bg-blue-100 transition">编辑</button>'); }
        if(isAssignee){ actions.push('<button onclick="openStatusModal(\\''+escJs(t.id)+'\\')" class="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 transition">标记状态</button>'); actions.push('<button onclick="openHandoffModal(\\''+escJs(t.id)+'\\')" class="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium text-indigo-700 bg-indigo-50 hover:bg-indigo-100 transition">流转</button>'); }
        if(t.can_delete){ actions.push('<button onclick="deleteTask(\\''+escJs(t.id)+'\\')" class="inline-flex items-center px-3 py-1.5 rounded-lg text-sm font-medium text-red-700 bg-red-50 hover:bg-red-100 transition">删除</button>'); }
        actions.push('<button onclick="showFlowLog(\\''+escJs(t.id)+'\\')" class="inline-flex items-center px-3 py-1.5 rounded-lg text-sm text-gray-600 bg-gray-100 hover:bg-gray-200 transition" title="流转日志">📋</button>');
        var comments=t.comments||[]; var lastC=comments.length ? comments[comments.length-1] : null; var commentTxt=(comments.length||0)+'条评论'+(lastC ? ' 最后: '+escAttr(lastC.user||'')+' '+(lastC.content ? escAttr(lastC.content.slice(0,8))+(lastC.content.length>8 ? '…' : '') : '') : '');
        actions.push('<button onclick="showComments(\\''+escJs(t.id)+'\\')" class="inline-flex items-center px-3 py-1.5 rounded-lg text-sm text-gray-600 bg-gray-100 hover:bg-gray-200 transition" title="评论">💬</button><span class="text-xs text-gray-500 ml-1">'+commentTxt+'</span>');
        var assigneeRole = ''; for(var i=0;i<(window._participants||[]).length;i++){ var p=window._participants[i]; if(p.user===t.current_assignee){ assigneeRole=p.role; break; } }
        var assigneeText = t.current_assignee ? (t.current_assignee+(assigneeRole?' ('+assigneeRole+')':'')) : '-';
        var attHtml = (t.attachments||[]).length ? '<div class="text-xs mt-1">附件: '+ (t.attachments||[]).map(function(a){ return '<a href="'+escAttr(a.url)+'" target="_blank" class="text-blue-600 mr-2">'+escAttr(a.name)+'</a>'; }).join('') +'</div>' : '';
        var overdueCls = overdue ? ' text-red-600 font-medium' : '';
        var contentPreview = viewMode==='thumb' ? (t.content||'').slice(0,60)+(t.content&&t.content.length>60?'…':'') : (t.content||'');
        var borderCls = (rowStyle.progress==='超时'||rowStyle.progress==='严重超时') ? ' border-l-4 border-l-red-600' : (rowStyle.progress==='即将超时' ? ' border-l-4 border-l-amber-500' : '');
        return '<li class="'+rowStyle.bg+' border border-gray-200 rounded-xl p-5 shadow-sm hover:shadow-md transition '+cardCls+borderCls+'"><label class="flex items-start gap-3 flex-1"><input type="checkbox" class="task-check mt-1.5 flex-shrink-0" data-task-id="'+escAttr(t.id)+'" '+(t.can_delete?'':'disabled')+' style="display:'+(t.can_delete?'inline-block':'none')+'"> <div class="flex-1 min-w-0"><div class="flex flex-wrap justify-between items-start gap-2"><span class="font-semibold text-gray-900 text-base">'+escAttr(t.title||'')+'</span> <span class="text-sm'+overdueCls+'">'+urgencyStars+' '+escAttr(assigneeText)+' · <span class="inline-flex px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">'+statusLabel+(overdue?' · 超时':'')+'</span>'+overdueBadge+'</span></div><div class="text-sm text-gray-600 mt-2 line-clamp-2">'+escAttr(contentPreview)+'</div>'+attHtml+'<div class="text-xs text-gray-400 mt-2">'+(t.start_time||'')+' ~ '+(t.end_time||'')+'</div><div class="mt-4 flex flex-wrap gap-2">'+actions.join('')+'</div></div></label></li>';
    }).join('') || '<li class="text-gray-500 col-span-full">暂无任务</li>';
}
var btnOpenCreate = document.getElementById('btnOpenCreateTask');
if(btnOpenCreate) btnOpenCreate.onclick=function(){ document.getElementById('newTaskTitle').value=''; document.getElementById('newTaskContent').value=''; var s=document.getElementById('newTaskStart'); var e=document.getElementById('newTaskEnd'); if(s)s.value=''; if(e)e.value=''; var createContent=document.getElementById('createTaskModalContent')||document.querySelector('#createTaskModalContent'); setUrgencyStars(createContent, '.urgency-star', 1, 'newTaskUrgencyVal'); window._newTaskAttachments=[]; var list=document.getElementById('newTaskAttachmentList'); if(list) list.innerHTML=''; document.getElementById('createTaskModal').classList.remove('hidden'); };
var btnCreateTask = document.getElementById('btnCreateTask');
if(btnCreateTask) btnCreateTask.onclick=function(){
    var title = document.getElementById('newTaskTitle').value.trim();
    var assignUser = (document.getElementById('newTaskAssignUser')||{}).value.trim();
    if(!title){ alert('请输入任务名称'); return; }
    if(!assignUser){ alert('请选择流转给的参与人'); return; }
    var startEl = document.getElementById('newTaskStart'); var endEl = document.getElementById('newTaskEnd');
    var urgencyEl = document.getElementById('newTaskUrgencyVal'); var urgency = urgencyEl ? Math.max(1, Math.min(5, parseInt(urgencyEl.value,10)||1)) : 1;
    var payload = { title: title, content: document.getElementById('newTaskContent').value.trim(), assign_to_user: assignUser, start_time: startEl ? startEl.value : '', end_time: endEl ? endEl.value : '', urgency: urgency, attachments: window._newTaskAttachments || [] };
    fetch('/admin/projects/'+PROJECT_ID+'/tasks/create', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload), credentials:'same-origin' }).then(function(r){ return r.json().then(function(d){ return { ok: r.ok, data: d }; }).catch(function(){ return { ok: false, data: {} }; }); }).then(function(res){ var d=res.data; if(d.error){ alert(d.error); return; } document.getElementById('createTaskModal').classList.add('hidden'); document.getElementById('newTaskTitle').value=''; document.getElementById('newTaskContent').value=''; if(startEl) startEl.value=''; if(endEl) endEl.value=''; window._newTaskAttachments=[]; var list=document.getElementById('newTaskAttachmentList'); if(list) list.innerHTML=''; loadTasks().then(function(){ alert('已创建'); }); });
};
var btnMyTasks = document.getElementById('btnMyTasks');
if(btnMyTasks) btnMyTasks.onclick=function(){ window._showOnlyMine=true; renderTasks(window._allTasks||[]); document.getElementById('btnMyTasks').classList.add('bg-indigo-100','text-indigo-700'); document.getElementById('btnMyTasks').classList.remove('border'); document.getElementById('btnAllTasks').classList.remove('bg-indigo-100','text-indigo-700'); document.getElementById('btnAllTasks').classList.add('border'); };
var btnAllTasks = document.getElementById('btnAllTasks');
if(btnAllTasks) btnAllTasks.onclick=function(){ window._showOnlyMine=false; renderTasks(window._allTasks||[]); document.getElementById('btnAllTasks').classList.add('bg-indigo-100','text-indigo-700'); document.getElementById('btnAllTasks').classList.remove('border'); document.getElementById('btnMyTasks').classList.remove('bg-indigo-100','text-indigo-700'); document.getElementById('btnMyTasks').classList.add('border'); };
var btnBatchDelete = document.getElementById('btnBatchDelete');
if(btnBatchDelete) btnBatchDelete.onclick=function(){ var ids=[]; document.querySelectorAll('.task-check:checked').forEach(function(c){ ids.push(c.getAttribute('data-task-id')); }); if(!ids.length){ alert('请勾选要删除的任务'); return; } if(!confirm('确定删除 '+ids.length+' 个任务？')) return; fetch('/admin/projects/'+PROJECT_ID+'/tasks/batch-delete', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({task_ids: ids}), credentials:'same-origin' }).then(r=>r.json()).then(function(d){ alert(d.error||'已删除'); if(!d.error) loadTasks(); }); };
['taskFilter','taskFilterStatus','taskFilterUrgency','taskFilterOverdue','taskSortBy'].forEach(function(id){ var el=document.getElementById(id); if(el) el.oninput=el.onchange=function(){ renderTasks(window._allTasks||[]); }; });
var btnViewList = document.getElementById('btnViewList');
if(btnViewList) btnViewList.onclick=function(){ window._taskViewMode='list'; document.getElementById('btnViewList').classList.add('bg-indigo-100','text-indigo-700'); document.getElementById('btnViewList').classList.remove('border'); document.getElementById('btnViewThumb').classList.remove('bg-indigo-100','text-indigo-700'); document.getElementById('btnViewThumb').classList.add('border'); renderTasks(window._allTasks||[]); };
var btnViewThumb = document.getElementById('btnViewThumb');
if(btnViewThumb) btnViewThumb.onclick=function(){ window._taskViewMode='thumb'; document.getElementById('btnViewThumb').classList.add('bg-indigo-100','text-indigo-700'); document.getElementById('btnViewThumb').classList.remove('border'); document.getElementById('btnViewList').classList.remove('bg-indigo-100','text-indigo-700'); document.getElementById('btnViewList').classList.add('border'); renderTasks(window._allTasks||[]); };
function setUrgencyStars(contentEl, starSelector, value, hiddenId){ if(!contentEl) return; var h=document.getElementById(hiddenId); if(h) h.value=String(value); var v=Math.max(1, Math.min(5, value)); contentEl.querySelectorAll(starSelector).forEach(function(s){ var su=parseInt(s.getAttribute('data-urgency'),10)||1; s.classList.remove('text-amber-400','text-gray-300'); s.classList.add(su<=v ? 'text-amber-400' : 'text-gray-300'); }); }
function bindUrgencyStarsCapture(overlayId, contentSelector, starSelector, hiddenId){ var overlay=document.getElementById(overlayId); if(!overlay) return; overlay.addEventListener('click', function(e){ var star=e.target.closest(starSelector); if(!star) return; var content=document.querySelector(contentSelector); if(!content||!content.contains(star)) return; var u=parseInt(star.getAttribute('data-urgency'),10)||1; setUrgencyStars(content, starSelector, u, hiddenId); }, true); }
bindUrgencyStarsCapture('createTaskModal','#createTaskModalContent','.urgency-star','newTaskUrgencyVal');
bindUrgencyStarsCapture('editTaskModal','#editTaskModalContent','.edit-urgency-star','editTaskUrgencyVal');
function showFlowLog(taskId){ var t=(window._allTasks||[]).find(function(x){ return x.id===taskId; }); if(!t) return; var log = t.flow_log||[]; var labels = window.STATUS_LABELS||{}; document.getElementById('flowLogContent').innerHTML = log.length ? log.map(function(e){ var st = e.status ? (labels[e.status]||e.status) : ''; return '<div class="py-1 border-b border-gray-100">'+(e.at?e.at.slice(0,19):'')+' · '+e.from_user+' → '+e.to_user+(st ? ' ['+st+']' : '')+'</div>'; }).join('') : '<div class="text-gray-500">暂无流转记录</div>'; document.getElementById('flowLogModal').classList.remove('hidden'); }
function showComments(taskId){ window._commentTaskId=taskId; var t=(window._allTasks||[]).find(function(x){ return x.id===taskId; }); if(!t) return; var c = t.comments||[]; document.getElementById('commentList').innerHTML = c.length ? c.map(function(e){ return '<div class="py-1"><span class="font-medium">'+e.user+'</span> <span class="text-gray-400 text-xs">'+e.at+'</span><br>'+e.content+'</div>'; }).join('') : '<div class="text-gray-500">暂无评论</div>'; document.getElementById('newCommentContent').value=''; document.getElementById('commentModal').classList.remove('hidden'); }
var btnAddComment = document.getElementById('btnAddComment');
if(btnAddComment) btnAddComment.onclick=function(){ var content=(document.getElementById('newCommentContent')||{}).value.trim(); if(!content){ alert('请输入评论'); return; } var tid=window._commentTaskId; if(!tid) return; fetch('/admin/projects/'+PROJECT_ID+'/tasks/'+tid+'/comment', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content: content}), credentials:'same-origin' }).then(r=>r.json()).then(function(d){ alert(d.error||'已添加'); if(!d.error){ var t=(window._allTasks||[]).find(function(x){ return x.id===tid; }); if(t){ t.comments=t.comments||[]; t.comments.push({user: d.user||'', content: content, at: d.at||''}); } showComments(tid); loadTasks(); } }); };
function openStatusModal(id){ var t=(window._allTasks||[]).find(function(x){ return x.id===id; }); if(!t||t.current_assignee!==window._myUsername) return; window._statusModalTaskId=id; var sel=document.getElementById('statusModalSelect'); sel.innerHTML=''; for(var k in STATUS_LABELS){ var opt=document.createElement('option'); opt.value=k; opt.textContent=STATUS_LABELS[k]; if(t.status===k) opt.selected=true; sel.appendChild(opt); } document.getElementById('statusModal').classList.remove('hidden'); }
function confirmStatusChange(){ var id=window._statusModalTaskId; var v=(document.getElementById('statusModalSelect')||{}).value; if(!id||!v) return; fetch('/admin/projects/'+PROJECT_ID+'/tasks/'+id+'/update-status', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({status: v}), credentials:'same-origin' }).then(r=>r.json()).then(function(d){ alert(d.error||'已更新'); if(!d.error){ loadTasks(); document.getElementById('statusModal').classList.add('hidden'); } }); }
function openHandoffModal(id){ var t=(window._allTasks||[]).find(function(x){ return x.id===id; }); if(!t||t.current_assignee!==window._myUsername) return; window._handoffModalTaskId=id; var sel=document.getElementById('handoffModalSelect'); sel.innerHTML='<option value="">选择参与人</option>'; (window._participants||[]).filter(function(p){ return p.user!==window._myUsername; }).forEach(function(p){ var opt=document.createElement('option'); opt.value=p.user; opt.textContent=p.user+' ('+p.role+')'; sel.appendChild(opt); }); document.getElementById('handoffModal').classList.remove('hidden'); }
function confirmHandoff(){ var id=window._handoffModalTaskId; var to=(document.getElementById('handoffModalSelect')||{}).value.trim(); if(!id||!to){ alert('请选择流转对象'); return; } fetch('/admin/projects/'+PROJECT_ID+'/tasks/'+id+'/handoff', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({passed_to_user: to}), credentials:'same-origin' }).then(r=>r.json()).then(function(d){ alert(d.error||'已流转'); if(!d.error){ loadTasks(); document.getElementById('handoffModal').classList.add('hidden'); } }); }
function deleteTask(id){ if(!confirm('确定删除该任务？')) return; fetch('/admin/projects/'+PROJECT_ID+'/tasks/'+id, { method:'DELETE', credentials:'same-origin' }).then(r=>r.json()).then(function(d){ alert(d.error||'已删除'); if(!d.error) loadTasks(); }); }
window._newTaskAttachments = [];
function uploadTaskFile(file, taskId, isNew, callback){ var fd=new FormData(); fd.append('file', file); var url='/admin/projects/'+PROJECT_ID+'/tasks/upload'; if(taskId) fd.append('task_id', taskId); fetch(url, { method:'POST', body: fd, credentials:'same-origin' }).then(r=>r.json()).then(function(d){ if(d.url){ if(callback) callback(d.url, d.name||file.name); } else alert(d.error||'上传失败'); }).catch(function(){ alert('上传失败'); }); }
var newFileEl = document.getElementById('newTaskFileInput');
if(newFileEl) newFileEl.onchange=function(){
  var files=this.files; if(!files||!files.length) return;
  for(var i=0;i<files.length;i++){ (function(f){
    uploadTaskFile(f, null, true, function(url, name){
      window._newTaskAttachments = window._newTaskAttachments||[];
      window._newTaskAttachments.push({name:name, url:url});
      var list=document.getElementById('newTaskAttachmentList');
      if(list){ var span=document.createElement('span'); span.className='block';
        span.innerHTML=name+' <a href="#" class="text-red-500">移除</a>';
        span.querySelector('a').onclick=function(){ window._newTaskAttachments=window._newTaskAttachments.filter(function(x){return x.url!==url;}); span.remove(); return false; };
        list.appendChild(span);
      }
    });
  })(files[i]); }
  this.value='';
};
function renderEditTaskComments(comments){
  var el=document.getElementById('editTaskCommentsList'); if(!el) return;
  var c=comments||[];
  el.innerHTML= c.length ? c.map(function(e){ return '<div class="py-0.5"><span class="font-medium">'+escAttr(e.user||'')+'</span> <span class="text-gray-400">'+(e.at?e.at.slice(0,16):'')+'</span><br>'+escAttr(e.content||'')+'</div>'; }).join('') : '<div class="text-gray-500">暂无评论</div>';
}
function openEditTask(id){
  var t=(window._allTasks||[]).find(function(x){ return x.id===id; });
  if(!t||!t.can_edit) return;
  window._editTaskId=id;
  document.getElementById('editTaskTitle').value=t.title||'';
  document.getElementById('editTaskContent').value=t.content||'';
  document.getElementById('editTaskStart').value=(t.start_time||'').slice(0,10);
  document.getElementById('editTaskEnd').value=(t.end_time||'').slice(0,10);
  var raw=t.urgency; var u=Math.max(1, Math.min(5, (typeof raw==='number'&&!isNaN(raw)) ? raw : (parseInt(raw,10)||Number(raw)||1)));
  var contentEl=document.getElementById('editTaskModalContent')||document.querySelector('#editTaskModalContent');
  setUrgencyStars(contentEl, '.edit-urgency-star', u, 'editTaskUrgencyVal');
  renderEditTaskComments(t.comments||[]);
  var newC=document.getElementById('editTaskNewComment'); if(newC) newC.value='';
  var wrap=document.getElementById('editTaskStatusAssigneeWrap');
  var canSA=t.can_edit_status_assignee;
  wrap.classList.toggle('hidden',!canSA);
  if(canSA){
    var selS=document.getElementById('editTaskStatus'); selS.innerHTML='';
    for(var k in STATUS_LABELS){ var o=document.createElement('option'); o.value=k; o.textContent=STATUS_LABELS[k]; if(t.status===k) o.selected=true; selS.appendChild(o); }
    var selA=document.getElementById('editTaskAssignee'); selA.innerHTML='';
    (window._participants||[]).forEach(function(p){ var o=document.createElement('option'); o.value=p.user; o.textContent=p.user+' ('+p.role+')'; if(t.current_assignee===p.user) o.selected=true; selA.appendChild(o); });
  }
  window._editTaskAttachments = (t.attachments||[]).slice();
  var listEl=document.getElementById('editTaskAttachmentList');
  listEl.innerHTML='';
  (window._editTaskAttachments||[]).forEach(function(a){
    var span=document.createElement('span'); span.className='block';
    span.setAttribute('data-url', a.url);
    span.innerHTML='<a href="'+escAttr(a.url)+'" target="_blank" class="text-blue-600">'+escAttr(a.name)+'</a> <a href="#" class="text-red-500 text-xs">移除</a>';
    var link=span.querySelector('a[href="#"]');
    if(link){ link.onclick=function(){ window._editTaskAttachments=window._editTaskAttachments.filter(function(x){return x.url!==a.url;}); span.remove(); return false; }; }
    listEl.appendChild(span);
  });
  document.getElementById('editTaskModal').classList.remove('hidden');
  setTimeout(function(){ setUrgencyStars(contentEl, '.edit-urgency-star', u, 'editTaskUrgencyVal'); }, 0);
}
var editTaskBtnComment=document.getElementById('editTaskBtnComment');
if(editTaskBtnComment) editTaskBtnComment.onclick=function(){ var content=(document.getElementById('editTaskNewComment')||{}).value.trim(); if(!content){ alert('请输入评论'); return; } var tid=window._editTaskId; if(!tid) return; fetch('/admin/projects/'+PROJECT_ID+'/tasks/'+tid+'/comment', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({content: content}), credentials:'same-origin' }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); return; } var t=(window._allTasks||[]).find(function(x){ return x.id===tid; }); if(t){ t.comments=t.comments||[]; t.comments.push({user: d.user||'', content: content, at: d.at||''}); } renderEditTaskComments(t.comments); document.getElementById('editTaskNewComment').value=''; }); };
var editFileEl=document.getElementById('editTaskFileInput');
if(editFileEl) editFileEl.onchange=function(){
  var files=this.files; if(!files||!files.length) return;
  for(var i=0;i<files.length;i++){ (function(f){
    uploadTaskFile(f, window._editTaskId, false, function(url, name){
      window._editTaskAttachments=window._editTaskAttachments||[];
      window._editTaskAttachments.push({name:name, url:url});
      var list=document.getElementById('editTaskAttachmentList');
      var span=document.createElement('span'); span.className='block';
      span.innerHTML=escAttr(name)+' <a href="#" class="text-red-500 text-xs" data-url="'+escAttr(url)+'">移除</a>';
      var a=span.querySelector('a');
      if(a){ a.onclick=function(){ window._editTaskAttachments=window._editTaskAttachments.filter(function(x){return x.url!==url;}); span.remove(); return false; }; }
      list.appendChild(span);
    });
  })(files[i]); }
  this.value='';
};
function saveEditTask(){
  var id=window._editTaskId; if(!id) return;
  var task=(window._allTasks||[]).find(function(t){return t.id===id;});
  var urgencyEl=document.getElementById('editTaskUrgencyVal'); var urgency=urgencyEl ? Math.max(1, Math.min(5, parseInt(urgencyEl.value,10)||1)) : 1;
  var payload={ title: document.getElementById('editTaskTitle').value.trim(), content: document.getElementById('editTaskContent').value.trim(), start_time: document.getElementById('editTaskStart').value, end_time: document.getElementById('editTaskEnd').value, urgency: urgency, attachments: window._editTaskAttachments||[] };
  if(task&&task.can_edit_status_assignee){ payload.status=document.getElementById('editTaskStatus').value; payload.current_assignee=document.getElementById('editTaskAssignee').value; }
  fetch('/admin/projects/'+PROJECT_ID+'/tasks/'+id, { method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload), credentials:'same-origin' }).then(r=>r.json()).then(function(d){ if(d.error){ alert(d.error); return; } var task=(window._allTasks||[]).find(function(x){ return x.id===id; }); if(task){ task.urgency=urgency; task.title=payload.title; task.content=payload.content; task.start_time=payload.start_time; task.end_time=payload.end_time; if(payload.status!==undefined) task.status=payload.status; if(payload.current_assignee!==undefined) task.current_assignee=payload.current_assignee; task.attachments=payload.attachments||[]; } document.getElementById('editTaskModal').classList.add('hidden'); loadTasks(); alert('已保存'); });
}
loadTasks();
</script>
'''


def role_to_first_assignee(project_id, role):
    """兼容：旧任务按角色，返回第一个该角色的参与人作为 current_assignee。"""
    proj = projects_db.get(project_id) or {}
    mr = proj.get('member_roles') or {}
    for u, r in mr.items():
        if r == role:
            return u
    return list(mr.keys())[0] if mr else ''


def render_project_tasks_page(project_id, username):
    if project_id not in projects_db or not can_view_project(project_id, username):
        return None, "无权限或项目不存在", 403
    proj = projects_db[project_id]
    editors = proj.get("editors") or []
    member_roles = proj.get("member_roles") or {}
    participants = [{"user": u, "role": member_roles.get(u, "其他")} for u in editors]
    if can_edit_project(project_id, username) and username and not any(p["user"] == username for p in participants):
        participants.insert(0, {"user": username, "role": member_roles.get(username, "其他")})
    status_opts = "".join('<option value="%s">%s</option>' % (k, v) for k, v in TASK_STATUSES)
    participants_opts = "".join(
        '<option value="%s">%s (%s)</option>' % (p["user"], p["user"], p["role"]) for p in participants
    )
    content = _project_tasks_html(project_id, proj.get("name", project_id), status_opts, participants_opts)
    title = "项目任务 - %s" % proj.get("name", project_id)
    return content, title, None


def render_project_tasks_stats_page(project_id, username):
    if project_id not in projects_db or not can_view_project(project_id, username):
        return None, "无权限或项目不存在", 403
    proj = projects_db[project_id]
    content = _project_tasks_stats_html(project_id, proj.get("name", project_id))
    title = "任务统计 - %s" % proj.get("name", project_id)
    return content, title, None

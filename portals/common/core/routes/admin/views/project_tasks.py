# -*- coding: utf-8 -*-
"""Admin project tasks pages."""

import json

from models.data import can_edit_project, can_view_project, projects_db
from routes.admin.views.my_tasks import TASK_STATUSES

def _project_tasks_stats_html(project_id, project_name):
    status_list = json.dumps([{'id': k, 'label': v} for k, v in TASK_STATUSES])
    return '''
<header class="pm-page-head">
  <div class="pm-page-head-copy"><div>
    <h1>任务统计</h1>
    <p>''' + project_name + ''' · 按状态、负责人和超时风险汇总。</p>
  </div></div>
  <div class="pm-page-head-actions">
    <a class="pm-btn pm-btn--primary" href="/admin/projects/''' + project_id + '''/tasks">返回任务列表</a>
  </div>
</header>
<div id="statsLoading" class="studio-empty">加载中…</div>
<div id="statsContent" class="is-hidden studio-section">
  <div class="pm-kpi-row" style="grid-template-columns:repeat(4,minmax(0,1fr))">
    <div class="pm-kpi-card"><div class="pm-kpi-body"><span>总任务数</span><div class="pm-kpi-value-row"><strong id="statTotal">0</strong></div></div></div>
    <div class="pm-kpi-card"><div class="pm-kpi-body"><span>已超时</span><div class="pm-kpi-value-row"><strong id="statOverdue">0</strong></div></div></div>
    <div class="pm-kpi-card"><div class="pm-kpi-body"><span>即将超时</span><div class="pm-kpi-value-row"><strong id="statSoonOverdue">0</strong></div></div></div>
    <div class="pm-kpi-card"><div class="pm-kpi-body"><span>已完成</span><div class="pm-kpi-value-row"><strong id="statDone">0</strong></div></div></div>
  </div>
  <section class="studio-config-panel">
    <h3>按状态分布</h3>
    <div id="statusBars" class="studio-bar-list"></div>
  </section>
  <section class="studio-config-panel">
    <h3>超时风险</h3>
    <div id="overdueBars" class="studio-bar-list"></div>
  </section>
  <section class="studio-config-panel">
    <h3>各负责人任务数</h3>
    <div class="pm-table-panel overflow-x-auto">
      <table class="pm-table">
        <thead><tr><th>负责人</th><th>合计</th><th>进行中</th><th>待验收</th><th>已完成</th><th>其他</th></tr></thead>
        <tbody id="assigneeTable"><tr><td colspan="6">暂无数据</td></tr></tbody>
      </table>
    </div>
  </section>
</div>
<script>
var PROJECT_ID_STATS = ''' + json.dumps(project_id).replace('<', '\\u003c') + ''';
var STATUS_LIST = ''' + status_list + ''';
function renderBars(el, items, maxVal){
  var max = Math.max(1, maxVal || 0);
  el.innerHTML = items.map(function(it){
    var pct = Math.round((it.value || 0) * 100 / max);
    return '<div class="studio-bar-row"><span>'+it.label+'</span><div class="studio-bar-track"><div class="studio-bar-fill" style="width:'+pct+'%"></div></div><strong>'+it.value+'</strong></div>';
  }).join('') || '<p class="studio-empty">暂无数据</p>';
}
fetch("/admin/projects/"+PROJECT_ID_STATS+"/tasks/list", { credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){
  if(d.error){ document.getElementById("statsLoading").textContent=d.error; return; }
  document.getElementById("statsLoading").classList.add("is-hidden");
  document.getElementById("statsContent").classList.remove("is-hidden");
  var tasks=d.tasks||[]; var now=new Date(); now.setHours(0,0,0,0); var in3=new Date(now); in3.setDate(in3.getDate()+3);
  var byStatus={}; var byAssignee={}; var overdue=0, soonOverdue=0, done=0;
  STATUS_LIST.forEach(function(s){ byStatus[s.id]=0; });
  tasks.forEach(function(t){
    var s=t.status||"not_started"; if(s in byStatus) byStatus[s]++; else byStatus[s]=1;
    var u=t.current_assignee||"未分配";
    if(!byAssignee[u]) byAssignee[u]={total:0,in_progress:0,pending_review:0,done:0,other:0};
    byAssignee[u].total++;
    if(s==="in_progress") byAssignee[u].in_progress++;
    else if(s==="pending_review") byAssignee[u].pending_review++;
    else if(s==="done") byAssignee[u].done++;
    else byAssignee[u].other++;
    if(["done","abandoned"].indexOf(s)>=0) done++;
    else if(t.end_time){ var et=new Date(t.end_time.slice(0,10)); et.setHours(0,0,0,0); if(et<now) overdue++; else if(et<=in3) soonOverdue++; }
  });
  document.getElementById("statTotal").textContent=tasks.length;
  document.getElementById("statOverdue").textContent=overdue;
  document.getElementById("statSoonOverdue").textContent=soonOverdue;
  document.getElementById("statDone").textContent=done;
  var statusItems = STATUS_LIST.map(function(s){ return { label:s.label, value:byStatus[s.id]||0 }; });
  var statusMax = Math.max.apply(null, statusItems.map(function(x){ return x.value; }).concat([0]));
  renderBars(document.getElementById("statusBars"), statusItems, statusMax);
  renderBars(document.getElementById("overdueBars"), [
    { label:"已超时", value:overdue },
    { label:"即将超时", value:soonOverdue }
  ], Math.max(overdue, soonOverdue, 1));
  var assignees = Object.keys(byAssignee);
  document.getElementById("assigneeTable").innerHTML = assignees.length ? assignees.map(function(u){
    var row=byAssignee[u];
    return "<tr><td>"+u+"</td><td>"+row.total+"</td><td>"+row.in_progress+"</td><td>"+row.pending_review+"</td><td>"+row.done+"</td><td>"+row.other+"</td></tr>";
  }).join("") : '<tr><td colspan="6"><div class="pm-placeholder-page"><h2>暂无任务</h2><p>创建任务后这里会显示负责人分布。</p><a class="pm-btn pm-btn--primary" href="/admin/projects/'+PROJECT_ID_STATS+'/tasks">去任务列表</a></div></td></tr>';
});
</script>
'''


def _project_tasks_html(project_id, project_name, status_opts, participants_opts):
    return '''
<div class="studio-page">
    <header class="pm-page-head">
        <div class="pm-page-head-copy"><div>
            <h1>项目任务</h1>
            <p>''' + project_name + ''' · 需求、Bug 与协作事项在此流转。</p>
        </div></div>
        <div class="pm-page-head-actions">
            <a class="pm-btn" href="/admin/projects/''' + project_id + '''/tasks/stats">任务统计</a>
            <button type="button" id="btnOpenCreateTask" class="pm-btn pm-btn--primary">创建任务</button>
        </div>
    </header>
    <div class="pm-filter-bar">
        <div class="pm-filter-search"><input type="text" id="taskFilter" placeholder="筛选任务名称、内容…"></div>
        <select id="taskFilterStatus"><option value="">全部状态</option>''' + status_opts + '''</select>
        <button type="button" id="btnMyTasks" class="pm-btn pm-btn--primary pm-btn--compact">仅我的任务</button>
        <button type="button" id="btnAllTasks" class="pm-btn pm-btn--compact">全部任务</button>
        <button type="button" id="btnViewList" class="pm-btn pm-btn--compact">列表</button>
        <button type="button" id="btnViewThumb" class="pm-btn pm-btn--compact">卡片</button>
        <details class="task-filter-more">
          <summary>更多筛选</summary>
          <div class="task-filter-more-body">
            <select id="taskFilterUrgency"><option value="">全部紧急程度</option><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option><option value="5">5</option></select>
            <select id="taskFilterOverdue"><option value="">是否超时</option><option value="normal">正常</option><option value="soon">即将超时</option><option value="overdue">超时</option></select>
            <select id="taskSortBy">
                <option value="default">默认排序</option>
                <option value="status">状态</option>
                <option value="urgency">紧急程度</option>
                <option value="start_time">开始时间</option>
                <option value="remaining">剩余时间</option>
                <option value="role">当前负责人</option>
            </select>
            <button type="button" id="btnBatchDelete" class="pm-btn pm-btn--danger pm-btn--compact hidden">批量删除</button>
          </div>
        </details>
    </div>
    <style>
    .task-filter-more{border:1px solid #dce4f2;border-radius:6px;background:#fff;padding:4px 8px}
    .task-filter-more>summary{cursor:pointer;list-style:none;font-size:12px;font-weight:600;color:#475467}
    .task-filter-more>summary::-webkit-details-marker{display:none}
    .task-filter-more-body{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;align-items:center}
    </style>
    <div id="taskStats" class="studio-section-head"><span class="text-sm text-gray-500"></span></div>
    <div id="createTaskModal" class="pm-modal-root is-hidden" onclick="if(event.target===this) this.classList.add('is-hidden')">
        <div class="pm-modal-mask"></div>
        <div id="createTaskModalContent" class="pm-modal pm-modal--720" onclick="event.stopPropagation()">
            <div class="pm-modal-head"><div><h2>创建任务</h2><p>填写名称、负责人与时间后即可流转。</p></div></div>
            <div class="pm-modal-body">
                <div class="studio-form-grid">
                    <div class="studio-form-field studio-form-field--full"><label>任务名称</label><input type="text" id="newTaskTitle" placeholder="任务名称"></div>
                    <div class="studio-form-field studio-form-field--full"><label>流转给</label><select id="newTaskAssignUser"><option value="">请选择</option>''' + participants_opts + '''</select></div>
                    <div class="studio-form-field"><label>开始时间</label><input type="date" id="newTaskStart"></div>
                    <div class="studio-form-field"><label>完成时间</label><input type="date" id="newTaskEnd"></div>
                    <div class="studio-form-field studio-form-field--full"><label>紧急程度</label>
                        <div id="newTaskUrgency" class="studio-urgency">
                            <button type="button" class="urgency-star is-on" data-urgency="1">1</button>
                            <button type="button" class="urgency-star" data-urgency="2">2</button>
                            <button type="button" class="urgency-star" data-urgency="3">3</button>
                            <button type="button" class="urgency-star" data-urgency="4">4</button>
                            <button type="button" class="urgency-star" data-urgency="5">5</button>
                        </div>
                        <input type="hidden" id="newTaskUrgencyVal" value="1">
                    </div>
                    <div class="studio-form-field studio-form-field--full"><label>具体内容</label><textarea id="newTaskContent" placeholder="具体内容、需要对接角色" rows="3"></textarea></div>
                    <div class="studio-form-field studio-form-field--full"><label>附件</label><div id="newTaskAttachmentList" class="text-xs text-gray-500"></div><input type="file" id="newTaskFileInput" multiple></div>
                </div>
            </div>
            <div class="pm-modal-foot">
                <button type="button" class="pm-btn" onclick="document.getElementById('createTaskModal').classList.add('is-hidden')">取消</button>
                <button type="button" id="btnCreateTask" class="pm-btn pm-btn--primary">创建</button>
            </div>
        </div>
    </div>
    <ul id="taskList" class="studio-todo-list"></ul>
</div>
<div id="flowLogModal" class="pm-modal-root hidden" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="pm-modal-mask"></div>
    <div class="pm-modal pm-modal--480" onclick="event.stopPropagation()">
        <div class="pm-modal-head"><div><h2>任务流转日志</h2></div></div>
        <div class="pm-modal-body"><div id="flowLogContent" class="text-sm"></div></div>
        <div class="pm-modal-foot"><button type="button" class="pm-btn" onclick="document.getElementById('flowLogModal').classList.add('hidden')">关闭</button></div>
    </div>
</div>
<div id="commentModal" class="pm-modal-root hidden" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="pm-modal-mask"></div>
    <div class="pm-modal pm-modal--480" onclick="event.stopPropagation()">
        <div class="pm-modal-head"><div><h2>任务评论</h2></div></div>
        <div class="pm-modal-body"><div id="commentList" class="text-sm" style="max-height:240px;overflow:auto"></div>
            <div class="studio-form-field mt-3"><label>追加评论</label>
            <div class="flex gap-2"><input type="text" id="newCommentContent" class="studio-field" placeholder="输入评论…">
            <button type="button" id="btnAddComment" class="pm-btn pm-btn--primary">发送</button></div></div>
        </div>
    </div>
</div>
<div id="statusModal" class="pm-modal-root hidden" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="pm-modal-mask"></div>
    <div class="pm-modal pm-modal--480" onclick="event.stopPropagation()">
        <div class="pm-modal-head"><div><h2>标记状态</h2></div></div>
        <div class="pm-modal-body"><div class="studio-form-field"><label>状态</label><select id="statusModalSelect" class="studio-field"></select></div></div>
        <div class="pm-modal-foot"><button type="button" class="pm-btn" onclick="document.getElementById('statusModal').classList.add('hidden')">取消</button><button type="button" class="pm-btn pm-btn--primary" onclick="confirmStatusChange()">确认</button></div>
    </div>
</div>
<div id="handoffModal" class="pm-modal-root hidden" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="pm-modal-mask"></div>
    <div class="pm-modal pm-modal--480" onclick="event.stopPropagation()">
        <div class="pm-modal-head"><div><h2>流转给</h2></div></div>
        <div class="pm-modal-body"><div class="studio-form-field"><label>负责人</label><select id="handoffModalSelect" class="studio-field"></select></div></div>
        <div class="pm-modal-foot"><button type="button" class="pm-btn" onclick="document.getElementById('handoffModal').classList.add('hidden')">取消</button><button type="button" class="pm-btn pm-btn--primary" onclick="confirmHandoff()">确认</button></div>
    </div>
</div>
<div id="editTaskModal" class="pm-modal-root hidden" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="pm-modal-mask"></div>
    <div id="editTaskModalContent" class="pm-modal pm-modal--720" onclick="event.stopPropagation()">
        <div class="pm-modal-head"><div><h2>编辑任务</h2></div></div>
        <div class="pm-modal-body">
            <div class="studio-form-grid">
                <div class="studio-form-field studio-form-field--full"><label>任务名称</label><input type="text" id="editTaskTitle" class="studio-field"></div>
                <div class="studio-form-field studio-form-field--full"><label>具体内容</label><textarea id="editTaskContent" rows="3" class="studio-field"></textarea></div>
                <div class="studio-form-field"><label>开始时间</label><input type="date" id="editTaskStart" class="studio-field"></div>
                <div class="studio-form-field"><label>完成时间</label><input type="date" id="editTaskEnd" class="studio-field"></div>
                <div class="studio-form-field studio-form-field--full"><label>紧急程度</label><div id="editTaskUrgency" class="studio-urgency"><button type="button" class="edit-urgency-star is-on" data-urgency="1">1</button><button type="button" class="edit-urgency-star" data-urgency="2">2</button><button type="button" class="edit-urgency-star" data-urgency="3">3</button><button type="button" class="edit-urgency-star" data-urgency="4">4</button><button type="button" class="edit-urgency-star" data-urgency="5">5</button></div><input type="hidden" id="editTaskUrgencyVal" value="1"></div>
                <div id="editTaskStatusAssigneeWrap" class="studio-form-field studio-form-field--full hidden"><div class="studio-form-grid"><div class="studio-form-field"><label>状态</label><select id="editTaskStatus" class="studio-field"></select></div><div class="studio-form-field"><label>当前负责人</label><select id="editTaskAssignee" class="studio-field"></select></div></div></div>
                <div class="studio-form-field studio-form-field--full"><label>附件</label><div id="editTaskAttachmentList" class="studio-hint"></div><input type="file" id="editTaskFileInput" multiple><span class="studio-hint">可传图片或文件</span></div>
                <div class="studio-form-field studio-form-field--full"><label>评论</label><div id="editTaskCommentsList" class="studio-subpanel" style="max-height:8rem;overflow:auto"></div><div class="flex gap-2"><input type="text" id="editTaskNewComment" placeholder="追加评论…" class="studio-field"><button type="button" id="editTaskBtnComment" class="pm-btn pm-btn--primary">发送</button></div></div>
            </div>
        </div>
        <div class="pm-modal-foot"><button type="button" class="pm-btn" onclick="document.getElementById('editTaskModal').classList.add('hidden')">取消</button><button type="button" class="pm-btn pm-btn--primary" onclick="saveEditTask()">保存</button></div>
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
        var s = d.stats||{}; document.getElementById('taskStats').innerHTML = '<span class="text-sm text-gray-500">共 '+s.total+' 个任务 · 进行中 '+(s.in_progress||0)+' · 待验收 '+(s.pending_review||0)+' · 已超时 '+(s.overdue||0)+' · 即将超时 '+(s.soon_overdue||0)+'</span>';
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
    var cardCls = viewMode==='thumb' ? 'is-card' : '';
    list.className = viewMode==='thumb' ? 'studio-project-grid' : 'studio-todo-list';
    list.innerHTML = arr.map(function(t){
        var overdue = t.end_time && new Date(t.end_time) < new Date() && t.status!=='done' && t.status!=='abandoned';
        var rowStyle = taskRowBgAndProgress(t);
        var statusLabel = STATUS_LABELS[t.status] || t.status;
        var overdueBadge = '';
        if(rowStyle.progress==='超时'||rowStyle.progress==='严重超时') overdueBadge = '<span class="pm-tag pm-tag--danger">'+(rowStyle.progress==='严重超时'?'严重超时':'已超时')+'</span>';
        else if(rowStyle.progress==='即将超时') overdueBadge = '<span class="pm-tag pm-tag--warning">即将超时</span>';
        else if(rowStyle.progress==='正常'&&t.status==='in_progress') overdueBadge = '<span class="pm-tag pm-tag--success">正常</span>';
        var isAssignee = t.current_assignee === myUser;
        var urgencyVal = Math.max(1, Math.min(5, parseInt(t.urgency,10)||1));
        var urgencyCls = urgencyVal >= 5 ? 'pm-tag--danger' : (urgencyVal >= 4 ? 'pm-tag--warning' : (urgencyVal >= 3 ? 'pm-tag--official' : 'pm-tag--muted'));
        var actions = [];
        if(t.can_edit){ actions.push('<button type="button" onclick="openEditTask(\\''+escJs(t.id)+'\\')" class="pm-btn pm-btn--compact">编辑</button>'); }
        if(isAssignee){ actions.push('<button type="button" onclick="openStatusModal(\\''+escJs(t.id)+'\\')" class="pm-btn pm-btn--compact">标记状态</button>'); actions.push('<button type="button" onclick="openHandoffModal(\\''+escJs(t.id)+'\\')" class="pm-btn pm-btn--compact">流转</button>'); }
        if(t.can_delete){ actions.push('<button type="button" onclick="deleteTask(\\''+escJs(t.id)+'\\')" class="pm-btn pm-btn--compact pm-btn--danger">删除</button>'); }
        actions.push('<button type="button" onclick="showFlowLog(\\''+escJs(t.id)+'\\')" class="pm-btn pm-btn--compact">流转日志</button>');
        actions.push('<button type="button" onclick="showComments(\\''+escJs(t.id)+'\\')" class="pm-btn pm-btn--compact">评论 ('+((t.comments||[]).length||0)+')</button>');
        var assigneeRole = ''; for(var i=0;i<(window._participants||[]).length;i++){ var p=window._participants[i]; if(p.user===t.current_assignee){ assigneeRole=p.role; break; } }
        var assigneeText = t.current_assignee ? (t.current_assignee+(assigneeRole?' ('+assigneeRole+')':'')) : '暂无';
        var attHtml = (t.attachments||[]).length ? '<div class="text-xs mt-1">附件: '+ (t.attachments||[]).map(function(a){ return '<a href="'+escAttr(a.url)+'" target="_blank">'+escAttr(a.name)+'</a>'; }).join(' ') +'</div>' : '';
        var contentPreview = viewMode==='thumb' ? (t.content||'').slice(0,60)+(t.content&&t.content.length>60?'…':'') : (t.content||'');
        var riskCls = (rowStyle.progress==='超时'||rowStyle.progress==='严重超时') ? ' is-overdue' : (rowStyle.progress==='即将超时' ? ' is-soon' : '');
        return '<li class="studio-task-card'+riskCls+' '+cardCls+'"><label class="studio-task-card-inner"><input type="checkbox" class="task-check" data-task-id="'+escAttr(t.id)+'" '+(t.can_delete?'':'disabled')+' style="display:'+(t.can_delete?'inline-block':'none')+'"><div class="studio-task-card-body"><div class="studio-task-card-head"><strong>'+escAttr(t.title||'')+'</strong><span class="pm-tag pm-tag--muted">'+escAttr(statusLabel)+(overdue?' · 超时':'')+'</span>'+overdueBadge+'</div><div class="studio-task-card-meta"><span class="pm-tag '+urgencyCls+'">紧急 '+urgencyVal+'</span><span>'+escAttr(assigneeText)+'</span></div><div class="studio-task-card-content">'+escAttr(contentPreview||'暂无描述')+'</div>'+attHtml+'<div class="studio-task-card-time">'+(t.start_time||'暂无')+' ~ '+(t.end_time||'暂无')+'</div><div class="pm-table-actions">'+actions.join('')+'</div></div></label></li>';
    }).join('') || '<li class="studio-empty"><strong>暂无任务</strong><span>点击右上角「创建任务」开始。</span></li>';
}
var btnOpenCreate = document.getElementById('btnOpenCreateTask');
if(btnOpenCreate) btnOpenCreate.onclick=function(){ document.getElementById('newTaskTitle').value=''; document.getElementById('newTaskContent').value=''; var s=document.getElementById('newTaskStart'); var e=document.getElementById('newTaskEnd'); if(s)s.value=''; if(e)e.value=''; var createContent=document.getElementById('createTaskModalContent')||document.querySelector('#createTaskModalContent'); setUrgencyStars(createContent, '.urgency-star', 1, 'newTaskUrgencyVal'); window._newTaskAttachments=[]; var list=document.getElementById('newTaskAttachmentList'); if(list) list.innerHTML=''; document.getElementById('createTaskModal').classList.remove('is-hidden'); };
var btnCreateTask = document.getElementById('btnCreateTask');
if(btnCreateTask) btnCreateTask.onclick=function(){
    var title = document.getElementById('newTaskTitle').value.trim();
    var assignUser = (document.getElementById('newTaskAssignUser')||{}).value.trim();
    if(!title){ alert('请输入任务名称'); return; }
    if(!assignUser){ alert('请选择流转给的参与人'); return; }
    var startEl = document.getElementById('newTaskStart'); var endEl = document.getElementById('newTaskEnd');
    var urgencyEl = document.getElementById('newTaskUrgencyVal'); var urgency = urgencyEl ? Math.max(1, Math.min(5, parseInt(urgencyEl.value,10)||1)) : 1;
    var payload = { title: title, content: document.getElementById('newTaskContent').value.trim(), assign_to_user: assignUser, start_time: startEl ? startEl.value : '', end_time: endEl ? endEl.value : '', urgency: urgency, attachments: window._newTaskAttachments || [] };
    fetch('/admin/projects/'+PROJECT_ID+'/tasks/create', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload), credentials:'same-origin' }).then(function(r){ return r.json().then(function(d){ return { ok: r.ok, data: d }; }).catch(function(){ return { ok: false, data: {} }; }); }).then(function(res){ var d=res.data; if(d.error){ alert(d.error); return; } document.getElementById('createTaskModal').classList.add('is-hidden'); document.getElementById('newTaskTitle').value=''; document.getElementById('newTaskContent').value=''; if(startEl) startEl.value=''; if(endEl) endEl.value=''; window._newTaskAttachments=[]; var list=document.getElementById('newTaskAttachmentList'); if(list) list.innerHTML=''; loadTasks().then(function(){ alert('已创建'); }); });
};
var btnMyTasks = document.getElementById('btnMyTasks');
if(btnMyTasks) btnMyTasks.onclick=function(){ window._showOnlyMine=true; renderTasks(window._allTasks||[]); document.getElementById('btnMyTasks').classList.add('pm-btn--primary'); document.getElementById('btnAllTasks').classList.remove('pm-btn--primary'); };
var btnAllTasks = document.getElementById('btnAllTasks');
if(btnAllTasks) btnAllTasks.onclick=function(){ window._showOnlyMine=false; renderTasks(window._allTasks||[]); document.getElementById('btnAllTasks').classList.add('pm-btn--primary'); document.getElementById('btnMyTasks').classList.remove('pm-btn--primary'); };
var btnBatchDelete = document.getElementById('btnBatchDelete');
if(btnBatchDelete) btnBatchDelete.onclick=function(){ var ids=[]; document.querySelectorAll('.task-check:checked').forEach(function(c){ ids.push(c.getAttribute('data-task-id')); }); if(!ids.length){ alert('请勾选要删除的任务'); return; } if(!confirm('确定删除 '+ids.length+' 个任务？')) return; fetch('/admin/projects/'+PROJECT_ID+'/tasks/batch-delete', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({task_ids: ids}), credentials:'same-origin' }).then(r=>r.json()).then(function(d){ alert(d.error||'已删除'); if(!d.error) loadTasks(); }); };
['taskFilter','taskFilterStatus','taskFilterUrgency','taskFilterOverdue','taskSortBy'].forEach(function(id){ var el=document.getElementById(id); if(el) el.oninput=el.onchange=function(){ renderTasks(window._allTasks||[]); }; });
var btnViewList = document.getElementById('btnViewList');
if(btnViewList) btnViewList.onclick=function(){ window._taskViewMode='list'; document.getElementById('btnViewList').classList.add('pm-btn--primary'); document.getElementById('btnViewThumb').classList.remove('pm-btn--primary'); renderTasks(window._allTasks||[]); };
var btnViewThumb = document.getElementById('btnViewThumb');
if(btnViewThumb) btnViewThumb.onclick=function(){ window._taskViewMode='thumb'; document.getElementById('btnViewThumb').classList.add('pm-btn--primary'); document.getElementById('btnViewList').classList.remove('pm-btn--primary'); renderTasks(window._allTasks||[]); };
function setUrgencyStars(contentEl, starSelector, value, hiddenId){ if(!contentEl) return; var h=document.getElementById(hiddenId); if(h) h.value=String(value); var v=Math.max(1, Math.min(5, value)); contentEl.querySelectorAll(starSelector).forEach(function(s){ var su=parseInt(s.getAttribute('data-urgency'),10)||1; s.classList.toggle('is-on', su<=v); }); }
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

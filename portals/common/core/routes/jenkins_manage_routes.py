# -*- coding: utf-8 -*-
"""管理中心 - Jenkins 管理：环境检查、一键部署、多实例启动/停止/删除"""

import os
import json
from flask import Blueprint, request, jsonify, render_template_string
from services.authz import admin_required, admin_required_any, has_scope
from models.data import log_audit
from services import jenkins_manager as jm
from services.unity_version_service import detect_local_unity_installations
from routes.admin_routes import _admin_layout

try:
    from flask_wtf.csrf import generate_csrf
except ImportError:
    generate_csrf = lambda: ''

bp = Blueprint('jenkins_manage_routes', __name__, url_prefix='')


@bp.route('/admin/jenkins')
@admin_required('jenkins')
def jenkins_manage_page():
    """Jenkins 管理页：环境检查、部署、实例列表、启动表单。"""
    env = jm.env_check()
    script_mac = jm.deploy_env_script('mac')
    script_win = jm.deploy_env_script('windows')
    content = _jenkins_manage_html(env, script_mac, script_win)
    return _admin_layout(content, 'Jenkins 管理', back_href='/admin')


@bp.route('/admin/unity-versions')
@admin_required('jenkins')
def unity_versions_manage_page():
    """兼容旧链接：跳转到 Jenkins 管理内的 Unity 版本库模块。"""
    from flask import redirect
    return redirect('/admin/jenkins#unity-catalog', code=302)


def _unity_catalog_module_html():
    return '''
    <div id="unity-catalog" class="bg-white rounded-lg shadow p-6 scroll-mt-4">
        <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
            <h2 class="text-lg font-semibold">Unity 版本库</h2>
            <div class="flex flex-wrap gap-2">
                <button type="button" id="uvBtnReload" class="px-3 py-1.5 border border-gray-200 rounded text-xs hover:bg-gray-50">刷新列表</button>
                <button type="button" id="uvBtnImportDetect" class="px-3 py-1.5 bg-gray-200 rounded hover:bg-gray-300 text-xs">从本机检测导入</button>
                <button type="button" id="uvBtnAdd" class="px-3 py-1.5 bg-indigo-600 text-white rounded hover:bg-indigo-700 text-xs">新增版本</button>
            </div>
        </div>
        <p class="text-xs text-gray-500 mb-3">在此维护全局 Unity 版本（有效/失效、分类、备注）。Jenkins 构建参数、项目版本编辑、构建管理页的下拉仅展示<strong>有效</strong>项。</p>
        <div class="flex flex-wrap gap-2 mb-3 text-sm">
            <label class="text-gray-600">状态</label>
            <select id="uvFilterStatus" class="border rounded px-2 py-1 text-xs">
                <option value="all">全部</option>
                <option value="active">仅有效</option>
                <option value="inactive">仅失效</option>
            </select>
            <label class="text-gray-600 ml-2">分类</label>
            <select id="uvFilterCategory" class="border rounded px-2 py-1 text-xs min-w-[120px]"><option value="">全部分类</option></select>
        </div>
        <div id="uvCatalogListStatus" class="text-sm text-gray-500">加载中…</div>
        <div class="overflow-x-auto border border-gray-200 rounded-lg mt-2">
            <table class="min-w-full text-sm">
                <thead class="bg-gray-50 text-gray-600">
                    <tr>
                        <th class="text-left px-2 py-2">版本号</th>
                        <th class="text-left px-2 py-2">分类</th>
                        <th class="text-left px-2 py-2">状态</th>
                        <th class="text-left px-2 py-2">备注</th>
                        <th class="text-left px-2 py-2">安装路径</th>
                        <th class="text-left px-2 py-2">操作</th>
                    </tr>
                </thead>
                <tbody id="uvCatalogTableBody"><tr><td colspan="6" class="px-3 py-4 text-gray-400">加载中…</td></tr></tbody>
            </table>
        </div>
        <div id="uvFormPanel" class="hidden mt-4 border border-indigo-200 rounded-lg p-4 bg-indigo-50/40">
            <h3 id="uvFormTitle" class="text-sm font-semibold text-gray-800 mb-3">新增 Unity 版本</h3>
            <input type="hidden" id="uvFormEntryId">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <div><label class="block text-gray-600 mb-1">版本号</label><input id="uvFormVersion" class="border rounded px-2 py-1.5 w-full font-mono text-xs" placeholder="6000.3.15f1"></div>
                <div><label class="block text-gray-600 mb-1">分类</label><input id="uvFormCategory" list="uvCategoryDatalist" class="border rounded px-2 py-1.5 w-full text-xs" placeholder="如 Unity6、Unity2022"><datalist id="uvCategoryDatalist"></datalist></div>
                <div><label class="block text-gray-600 mb-1">状态</label><select id="uvFormStatus" class="border rounded px-2 py-1.5 w-full text-xs"><option value="active">有效</option><option value="inactive">失效</option></select></div>
                <div class="md:col-span-2"><label class="block text-gray-600 mb-1">安装路径（可选）</label><input id="uvFormPath" class="border rounded px-2 py-1.5 w-full text-xs" placeholder="留空则构建时自动探测"></div>
                <div class="md:col-span-2"><label class="block text-gray-600 mb-1">备注说明</label><textarea id="uvFormNote" rows="2" class="border rounded px-2 py-1.5 w-full text-xs" placeholder="用途、项目、注意事项等"></textarea></div>
            </div>
            <div id="uvFormStatusMsg" class="text-sm mt-2 text-gray-500"></div>
            <div class="mt-3 flex gap-2">
                <button type="button" id="uvFormSave" class="px-4 py-1.5 bg-indigo-600 text-white rounded text-xs hover:bg-indigo-700">保存</button>
                <button type="button" id="uvFormCancel" class="px-4 py-1.5 border border-gray-300 rounded text-xs hover:bg-gray-50">取消</button>
            </div>
        </div>
    </div>
    <script src="/static/admin/jenkins_unity_catalog.js"></script>
    '''


def _jenkins_manage_html(env, script_mac, script_win):
    return '''<!-- apk-site-page: jenkins-manage-unity-catalog-v2 -->
<div class="space-y-6">
<nav id="jmQuickNav" class="sticky top-0 z-10 flex flex-wrap gap-2 p-3 rounded-lg border border-violet-200 bg-violet-50 shadow-sm">
    <a href="#unity-catalog" class="inline-flex items-center px-4 py-2 rounded-md bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700">Unity 版本库</a>
    <a href="#jm-env" class="inline-flex items-center px-3 py-2 rounded-md bg-white border border-gray-200 text-sm text-gray-700 hover:bg-gray-50">环境检查</a>
    <a href="#jm-start" class="inline-flex items-center px-3 py-2 rounded-md bg-white border border-gray-200 text-sm text-gray-700 hover:bg-gray-50">启动新实例</a>
    <a href="#jm-list" class="inline-flex items-center px-3 py-2 rounded-md bg-white border border-gray-200 text-sm text-gray-700 hover:bg-gray-50">实例列表</a>
</nav>
''' + _unity_catalog_module_html() + '''
    <meta name="csrf-token" content="''' + generate_csrf() + '''">
    <meta name="csrf-token" content="''' + generate_csrf() + '''">
    <div id="jm-env" class="bg-white rounded-lg shadow p-6 scroll-mt-20">
        <h2 class="text-lg font-semibold mb-4">环境检查</h2>
        <ul class="space-y-2 text-sm">
            <li>Java: ''' + ('<span class="text-green-600">已安装</span> ' + (env.get('java', {}).get('version') or '') if env.get('java', {}).get('ok') else '<span class="text-red-600">未安装或不可用</span>') + '''</li>
            <li>Git: ''' + ('<span class="text-green-600">已安装</span> ' + (env.get('git', {}).get('version') or '') if env.get('git', {}).get('ok') else '<span class="text-gray-500">可选</span>') + '''</li>
            <li>Jenkins war: ''' + ('<span class="text-green-600">已配置</span> ' + (env.get('war', {}).get('path') or '') if env.get('war', {}).get('ok') else '<span class="text-red-600">未配置。</span> 可选：① .env 中设置 JENKINS_WAR_PATH ② 将 jenkins.war 放到 <code>data/jenkins_instances/jenkins.war</code> ③ 迁入 jenkins-clone 后放到 <code>jenkins-clone/jenkins.war</code>（见文档 docs/JENKINS_MIGRATION.md）') + '''</li>
        </ul>
        <div class="mt-4">
            <p class="text-sm text-gray-600 mb-2">一键部署（Mac 会尝试 brew install openjdk@17；Windows 请按下方说明手动安装）：</p>
            <button type="button" id="btnDeployEnv" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm">执行部署并查看日志</button>
            <pre id="deployLog" class="mt-2 p-3 bg-gray-900 text-green-400 text-xs rounded overflow-auto max-h-48 hidden"></pre>
        </div>
        <details class="mt-4"><summary class="cursor-pointer text-sm text-gray-600">Mac / Windows 手动部署说明</summary>
        <pre class="mt-2 p-3 bg-gray-100 text-sm rounded overflow-auto">''' + script_mac.replace('<', '&lt;').replace('>', '&gt;') + '''</pre>
        <pre class="mt-2 p-3 bg-gray-100 text-sm rounded overflow-auto">''' + script_win.replace('<', '&lt;').replace('>', '&gt;') + '''</pre>
        </details>
    </div>
    <div id="jm-start" class="bg-white rounded-lg shadow p-6 scroll-mt-20">
        <h2 class="text-lg font-semibold mb-4">启动新 Jenkins 实例</h2>
        <div class="mb-3">
            <label class="block text-sm text-gray-600 mb-1">实例类型</label>
            <div class="inline-flex rounded border border-gray-200 bg-gray-50 p-1">
                <button type="button" id="instanceTypeGeneral" class="px-3 py-1 rounded text-xs font-medium bg-white shadow-sm">通用 APK 构建</button>
                <button type="button" id="instanceTypeCommercial" class="px-3 py-1 rounded text-xs font-medium text-violet-700">商业级热更新发布</button>
            </div>
            <input type="hidden" id="newInstanceType" value="general">
        </div>
        <div class="flex flex-wrap items-end gap-4">
            <div>
                <label class="block text-sm text-gray-600 mb-1">端口</label>
                <input type="number" id="newPort" value="8080" min="1" max="65535" class="border rounded px-3 py-2 w-24">
            </div>
            <div>
                <label class="block text-sm text-gray-600 mb-1">任务名（可选）</label>
                <input type="text" id="newTaskName" placeholder="如 GomeKu、RecycleTycoon" class="border rounded px-3 py-2 w-48" title="用于区分实例，且作为 Builds 下输出子目录名">
            </div>
            <div>
                <label class="block text-sm text-gray-600 mb-1">飞书 Webhook（可选）</label>
                <input type="text" id="newFeishuWebhook" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx" class="border rounded px-3 py-2 w-72" title="该实例构建完成后通知的飞书机器人 Webhook，不同实例可填不同">
            </div>
            <button type="button" id="btnCheckPort" class="px-4 py-2 bg-gray-200 rounded hover:bg-gray-300 text-sm">检测端口</button>
            <span id="portCheckResult" class="text-sm"></span>
            <button type="button" id="btnStartJenkins" class="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 text-sm">启动 Jenkins</button>
        </div>
        <p class="text-xs text-gray-500 mt-1">Git、APP_NAME 等构建参数请在「项目管理」中配置，构建时按所选项目自动注入。</p>
        <p class="text-xs text-gray-500 mt-1">任务名用于构建页区分不同 Jenkins，且该实例的构建输出目录为：扫描目录/任务名（未填则用 jenkins_端口）</p>
        <p id="startResult" class="mt-2 text-sm"></p>
    </div>
    <div id="jm-list" class="bg-white rounded-lg shadow p-6 scroll-mt-20">
        <h2 class="text-lg font-semibold mb-4">已添加的 Jenkins 实例</h2>
        <p class="text-sm text-gray-500 mb-2">在「构建管理」页可选择使用哪个 Jenkins 进行构建，支持多实例并行。</p>
        <div id="listFilterTabs" class="mb-2 inline-flex rounded border border-gray-200 bg-gray-50 p-1">
            <button type="button" data-filter="all" class="px-3 py-1 rounded text-xs font-medium bg-white shadow-sm" onclick="filterList('all')">全部</button>
            <button type="button" data-filter="general" class="px-3 py-1 rounded text-xs font-medium text-slate-600" onclick="filterList('general')">通用</button>
            <button type="button" data-filter="commercial" class="px-3 py-1 rounded text-xs font-medium text-violet-700" onclick="filterList('commercial')">商业</button>
        </div>
        <div class="overflow-x-auto">
            <table class="min-w-full text-sm">
                <thead><tr class="border-b"><th class="text-left py-2">端口</th><th class="text-left py-2">任务名</th><th class="text-left py-2">状态</th><th class="text-left py-2">添加时间</th><th class="text-left py-2">添加人</th><th class="text-left py-2">启动时间</th><th class="text-left py-2">启动人</th><th class="text-left py-2">操作</th></tr></thead>
                <tbody id="jenkinsInstanceList"></tbody>
            </table>
        </div>
        <p id="instanceListMsg" class="text-gray-500 text-sm mt-2">加载中…</p>
    </div>
</div>
<script>
function _jmHeaders(isJson){
    var t=document.querySelector('meta[name="csrf-token"]');
    var h={};
    if(isJson) h['Content-Type']='application/json';
    if(t&&t.content) h['X-CSRFToken']=t.content;
    return h;
}
var _listFilter = 'all';
var _allInstances = [];
function filterList(type){
    _listFilter = type;
    document.querySelectorAll('#listFilterTabs [data-filter]').forEach(function(btn){
        var on = btn.getAttribute('data-filter') === type;
        btn.className = 'px-3 py-1 rounded text-xs font-medium ' + (on ? 'bg-white shadow-sm' : (btn.getAttribute('data-filter')==='commercial' ? 'text-violet-700' : 'text-slate-600'));
    });
    renderList();
}
function _typeBadge(t){
    return t==='commercial'
        ? '<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-violet-100 text-violet-700">商业</span>'
        : '<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-orange-100 text-orange-700">通用</span>';
}
function renderList(){
    var tbody=document.getElementById('jenkinsInstanceList');
    var msg=document.getElementById('instanceListMsg');
    var filtered = _listFilter==='all' ? _allInstances : _allInstances.filter(function(i){ return (i.instance_type||'general')===_listFilter; });
    if(!filtered.length){ tbody.innerHTML=''; msg.textContent='暂无实例'; return; }
    var rows=filtered.map(function(i){
        var t=(i.instance_type||'general');
        var status=i.status==='running' ? '<span class="text-green-600">运行中</span>' : '<span class="text-gray-500">已停止</span>';
        var stopBtn=i.status==='running' ? `<button type="button" onclick="stopInstance('${i.id}')" class="text-red-600 hover:underline">停止</button>` : '';
        var startBtn=i.status!=='running' ? `<button type="button" onclick="startInstance('${i.id}')" class="text-green-600 hover:underline">启动</button>` : '';
        var delBtn=`<button type="button" onclick="deleteInstance('${i.id}')" class="text-gray-600 hover:underline ml-2">删除</button>`;
        var consoleUrl='http://' + window.location.hostname + ':' + i.port + '/';
        var consoleBtn = i.status==='running' ? '<a href="'+consoleUrl+'" target="_blank" class="text-blue-600 hover:underline">控制台</a>' : '<span class="text-gray-400">控制台</span>';
        var logBtn='<a href="/admin/jenkins/instance-log?instance_id='+encodeURIComponent(i.id)+'" target="_blank" class="text-blue-600 hover:underline">日志</a>';
        var editBtn='<a href="/admin/jenkins/edit?instance_id='+encodeURIComponent(i.id)+'" class="text-blue-600 hover:underline ml-1">编辑</a>';
        var taskName=(i.task_name||'').trim()||'-';
        return '<tr class="border-b"><td class="py-2">'+_typeBadge(t)+'</td><td class="py-2">'+i.port+'</td><td>'+taskName+'</td><td>'+status+'</td><td>'+ (i.added_at||'') +'</td><td>'+ (i.added_by||'') +'</td><td>'+ (i.started_at||'') +'</td><td>'+ (i.started_by||'') +'</td><td>'+consoleBtn+' '+logBtn+' '+editBtn+' '+startBtn+stopBtn+delBtn+'</td></tr>';
    }).join('');
    tbody.innerHTML=rows;
    msg.textContent='共 '+filtered.length+' 个实例';
}
function loadList(){
    fetch('/api/jenkins-manage/list', {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
        _allInstances = (d && d.instances) ? d.instances : [];
        renderList();
    }).catch(function(){ document.getElementById('instanceListMsg').textContent='加载失败'; });
}
document.getElementById('instanceTypeGeneral').onclick=function(){
    document.getElementById('newInstanceType').value='general';
    this.className='px-3 py-1 rounded text-xs font-medium bg-white shadow-sm';
    var c=document.getElementById('instanceTypeCommercial');
    c.className='px-3 py-1 rounded text-xs font-medium text-violet-700';
};
document.getElementById('instanceTypeCommercial').onclick=function(){
    document.getElementById('newInstanceType').value='commercial';
    this.className='px-3 py-1 rounded text-xs font-medium bg-violet-600 text-white';
    var g=document.getElementById('instanceTypeGeneral');
    g.className='px-3 py-1 rounded text-xs font-medium text-slate-600';
};
document.getElementById('btnCheckPort').onclick=function(){
    var port=document.getElementById('newPort').value.trim();
    document.getElementById('portCheckResult').textContent='检测中…';
    fetch('/api/jenkins-manage/check-port?port='+encodeURIComponent(port), {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
        document.getElementById('portCheckResult').textContent=d.ok ? d.message : d.message;
        document.getElementById('portCheckResult').className='text-sm ' + (d.ok ? 'text-green-600' : 'text-red-600');
    });
};
document.getElementById('btnValidateGit').onclick=function(){
    var gitUrl=document.getElementById('newGitUrl')&&document.getElementById('newGitUrl').value?document.getElementById('newGitUrl').value.trim():'';
    var gitWorkspace=document.getElementById('newGitWorkspace')&&document.getElementById('newGitWorkspace').value?document.getElementById('newGitWorkspace').value.trim():'';
    var gitSshKeyPath=document.getElementById('newGitSshKeyPath')&&document.getElementById('newGitSshKeyPath').value?document.getElementById('newGitSshKeyPath').value.trim():'';
    var el=document.getElementById('gitValidateResult');
    el.textContent='验证中…'; el.className='text-sm text-gray-500';
    fetch('/api/jenkins-manage/validate-git', {method:'POST', headers:_jmHeaders(true), credentials:'same-origin', body: JSON.stringify({git_url:gitUrl, git_workspace:gitWorkspace, git_ssh_key_path:gitSshKeyPath})})
    .then(r=>r.json()).then(d=>{
        if(d.ok){ el.textContent='Git 配置有效'; el.className='text-sm text-green-600'; }
        else{ el.textContent=(d.errors&&d.errors.length)?d.errors.join('；'):'配置有误'; el.className='text-sm text-red-600'; }
    }).catch(function(){ el.textContent='验证请求失败'; el.className='text-sm text-red-600'; });
};
function collectBuildDefaults(){
    var appName=document.getElementById('newAppName')&&document.getElementById('newAppName').value?document.getElementById('newAppName').value.trim():'';
    var versionName=document.getElementById('newVersionName')&&document.getElementById('newVersionName').value?document.getElementById('newVersionName').value.trim():'';
    var versionCode=document.getElementById('newVersionCode')&&document.getElementById('newVersionCode').value?document.getElementById('newVersionCode').value.trim():'';
    var outputBaseDir=document.getElementById('newOutputBaseDir')&&document.getElementById('newOutputBaseDir').value?document.getElementById('newOutputBaseDir').value.trim():'';
    var gitUrl=document.getElementById('newGitUrl')&&document.getElementById('newGitUrl').value?document.getElementById('newGitUrl').value.trim():'';
    var gitWorkspace=document.getElementById('newGitWorkspace')&&document.getElementById('newGitWorkspace').value?document.getElementById('newGitWorkspace').value.trim():'';
    var gitSshKeyPath=document.getElementById('newGitSshKeyPath')&&document.getElementById('newGitSshKeyPath').value?document.getElementById('newGitSshKeyPath').value.trim():'';
    var defaultGitBranch=document.getElementById('newDefaultGitBranch')&&document.getElementById('newDefaultGitBranch').value?document.getElementById('newDefaultGitBranch').value.trim():'';
    var branchesText=document.getElementById('newGitBranches')&&document.getElementById('newGitBranches').value?document.getElementById('newGitBranches').value.trim():'';
    var gitBranches=branchesText?branchesText.split(/\\n/).map(function(s){ return s.trim(); }).filter(Boolean):[];
    var o={};
    if(appName) o.app_name=appName;
    if(versionName) o.version_name=versionName;
    if(versionCode) o.version_code=versionCode;
    if(outputBaseDir) o.output_base_dir=outputBaseDir;
    if(gitUrl) o.git_url=gitUrl;
    if(gitWorkspace) o.git_workspace=gitWorkspace;
    if(gitSshKeyPath) o.git_ssh_key_path=gitSshKeyPath;
    if(defaultGitBranch) o.default_git_branch=defaultGitBranch;
    if(gitBranches.length) o.git_branches=gitBranches;
    return Object.keys(o).length?o:null;
}
document.getElementById('btnStartJenkins').onclick=function(){
    var port=document.getElementById('newPort').value.trim();
    var taskName=(document.getElementById('newTaskName')&&document.getElementById('newTaskName').value) ? document.getElementById('newTaskName').value.trim() : '';
    var feishuWebhook=(document.getElementById('newFeishuWebhook')&&document.getElementById('newFeishuWebhook').value) ? document.getElementById('newFeishuWebhook').value.trim() : '';
    var el=document.getElementById('startResult');
    el.textContent='启动中…';
    var body={port: parseInt(port,10)};
    var instanceType=(document.getElementById('newInstanceType')&&document.getElementById('newInstanceType').value)||'general';
    body.instance_type = instanceType;
    if(taskName) body.task_name=taskName;
    if(feishuWebhook) body.feishu_webhook=feishuWebhook;
    fetch('/api/jenkins-manage/start', {method:'POST', headers:_jmHeaders(true), credentials:'same-origin', body: JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{
        if(d.success){ el.textContent='已启动，实例 ID: '+d.instance_id; el.className='mt-2 text-sm text-green-600'; loadList(); }
        else{ el.textContent=d.error||'启动失败'; el.className='mt-2 text-sm text-red-600'; }
    }).catch(function(){ document.getElementById('startResult').textContent='请求失败'; });
};
function startInstance(id){
    fetch('/api/jenkins-manage/start-instance', {method:'POST', headers:_jmHeaders(true), credentials:'same-origin', body: JSON.stringify({instance_id: id})})
    .then(r=>r.json()).then(d=>{ if(d.success){ loadList(); } else{ alert(d.error||'启动失败'); } });
}
function stopInstance(id){
    if(!confirm('确定停止该 Jenkins？')) return;
    fetch('/api/jenkins-manage/stop', {method:'POST', headers:_jmHeaders(true), credentials:'same-origin', body: JSON.stringify({instance_id: id})})
    .then(r=>r.json()).then(d=>{ if(d.success) loadList(); else alert(d.error||'停止失败'); });
}
function deleteInstance(id){
    if(!confirm('确定从列表删除该实例？（不会删除 JENKINS_HOME 数据）')) return;
    fetch('/api/jenkins-manage/delete', {method:'POST', headers:_jmHeaders(true), credentials:'same-origin', body: JSON.stringify({instance_id: id})})
    .then(r=>r.json()).then(d=>{ if(d.success) loadList(); else alert(d.error||'删除失败'); });
}
document.getElementById('btnDeployEnv').onclick=function(){
    var logEl=document.getElementById('deployLog');
    logEl.classList.remove('hidden');
    logEl.textContent='部署已开始，请稍候…';
    fetch('/api/jenkins-manage/deploy-env', {method:'POST', headers:_jmHeaders(false), credentials:'same-origin'}).then(r=>r.json()).then(d=>{
        if(d.log_path) fetch('/api/jenkins-manage/deploy-log?path='+encodeURIComponent(d.log_path), {credentials:'same-origin'}).then(r=>r.text()).then(t=>{ logEl.textContent=t||'无输出'; setInterval(function(){ fetch('/api/jenkins-manage/deploy-log?path='+encodeURIComponent(d.log_path), {credentials:'same-origin'}).then(r=>r.text()).then(t=>{ logEl.textContent=t||'无输出'; logEl.scrollTop=logEl.scrollHeight; }); }, 2000); });
        else logEl.textContent=d.error||'执行失败';
    }).catch(function(){ logEl.textContent='请求失败'; });
};
loadList();
</script>
'''


@bp.route('/api/jenkins-manage/check-port')
@admin_required('jenkins')
def api_check_port():
    port = request.args.get('port', '').strip()
    ok, msg = jm.check_port(port)
    return jsonify({'ok': ok, 'message': msg})


def _normalize_build_defaults(data):
    """从请求体解析 build_defaults，统一为实例存储格式。"""
    bd = data.get('build_defaults')
    if not bd or not isinstance(bd, dict):
        return None
    out = {}
    for k in ('app_name', 'version_name', 'version_code', 'output_base_dir', 'git_url', 'git_ssh_key_path', 'git_workspace', 'default_git_branch'):
        v = bd.get(k)
        if v is not None and str(v).strip():
            out[k] = str(v).strip()
    uv = bd.get('unity_versions')
    if isinstance(uv, list) and uv:
        out['unity_versions'] = []
        for u in uv:
            if isinstance(u, dict) and u.get('version'):
                out['unity_versions'].append({'version': str(u.get('version', '')).strip(), 'path': str(u.get('path') or '').strip()})
            elif isinstance(u, str) and u.strip():
                parts = u.split(',', 1)
                out['unity_versions'].append({'version': parts[0].strip(), 'path': (parts[1].strip() if len(parts) > 1 else '')})
    gb = bd.get('git_branches')
    if isinstance(gb, list) and gb:
        out['git_branches'] = [str(b).strip() for b in gb if str(b).strip()]
    elif isinstance(gb, str) and gb.strip():
        out['git_branches'] = [s.strip() for s in gb.splitlines() if s.strip()]
    return out if out else None


def _validate_build_defaults_git(bd):
    """若 build_defaults 含 Git 相关项则校验，返回 (None) 或 (error_message)。"""
    if not bd:
        return None
    git_url = (bd.get('git_url') or '').strip()
    git_workspace = (bd.get('git_workspace') or '').strip()
    git_ssh_key_path = (bd.get('git_ssh_key_path') or '').strip()
    if not git_url and not git_workspace and not git_ssh_key_path:
        return None
    ok, errors = jm.validate_git_config(git_url, git_workspace, git_ssh_key_path)
    if ok:
        return None
    return '；'.join(errors) if errors else 'Git 配置校验未通过'


@bp.route('/api/jenkins-manage/validate-git', methods=['GET', 'POST'])
@admin_required_any('jenkins', 'projects')
def api_validate_git():
    """校验 Git 工作目录、仓库 URL、SSH 密钥路径，用于保存前检测。"""
    if request.method == 'POST':
        data = request.get_json() or {}
    else:
        data = request.args
    git_url = (data.get('git_url') or '').strip()
    git_workspace = (data.get('git_workspace') or '').strip()
    git_ssh_key_path = (data.get('git_ssh_key_path') or '').strip()
    ok, errors = jm.validate_git_config(git_url, git_workspace, git_ssh_key_path)
    return jsonify({'ok': ok, 'errors': errors})




@bp.route('/api/jenkins-manage/detect-unity')
@admin_required('jenkins')
def api_detect_unity():
    versions = detect_local_unity_installations()
    return jsonify({'success': True, 'versions': versions})


@bp.route('/api/jenkins-manage/unity-catalog')
@admin_required_any('jenkins', 'build', 'projects')
def api_unity_catalog_list():
    from services.unity_version_catalog_service import list_entries
    active_only = request.args.get('active_only', '').strip() in ('1', 'true', 'yes')
    category = (request.args.get('category') or '').strip() or None
    entries, categories = list_entries(active_only=active_only, category=category)
    return jsonify({'success': True, 'entries': entries, 'categories': categories})


@bp.route('/api/jenkins-manage/unity-catalog', methods=['POST'])
@admin_required('jenkins')
def api_unity_catalog_create():
    if not has_scope('jenkins.manage'):
        return jsonify({'success': False, 'error': '无权限管理 Unity 版本库'}), 403
    from services.unity_version_catalog_service import create_entry, STATUS_ACTIVE, STATUS_INACTIVE
    data = request.get_json() or {}
    status = (data.get('status') or STATUS_ACTIVE).strip()
    if status not in (STATUS_ACTIVE, STATUS_INACTIVE):
        status = STATUS_ACTIVE
    entry, err = create_entry(
        data.get('version'),
        path=data.get('path'),
        category=data.get('category'),
        status=status,
        note=data.get('note'),
    )
    if err:
        return jsonify({'success': False, 'error': err}), 400
    log_audit('unity_catalog_create', '新增 Unity 版本 %s' % entry.get('version'))
    return jsonify({'success': True, 'entry': entry})


@bp.route('/api/jenkins-manage/unity-catalog/<entry_id>', methods=['PUT'])
@admin_required('jenkins')
def api_unity_catalog_update(entry_id):
    if not has_scope('jenkins.manage'):
        return jsonify({'success': False, 'error': '无权限管理 Unity 版本库'}), 403
    from services.unity_version_catalog_service import update_entry
    data = request.get_json() or {}
    fields = {}
    for key in ('version', 'path', 'category', 'status', 'note'):
        if key in data:
            fields[key] = data.get(key)
    entry, err = update_entry(entry_id, fields)
    if err:
        return jsonify({'success': False, 'error': err}), 400
    log_audit('unity_catalog_update', '更新 Unity 版本 %s' % entry.get('version'))
    return jsonify({'success': True, 'entry': entry})


@bp.route('/api/jenkins-manage/unity-catalog/import-detected', methods=['POST'])
@admin_required('jenkins')
def api_unity_catalog_import_detected():
    if not has_scope('jenkins.manage'):
        return jsonify({'success': False, 'error': '无权限管理 Unity 版本库'}), 403
    from services.unity_version_catalog_service import import_detected_entries
    data = request.get_json() or {}
    as_active = str(data.get('as_active', True)).lower() not in ('0', 'false', 'no')
    added, detected = import_detected_entries(as_active=as_active)
    log_audit('unity_catalog_import', '从本机检测导入 Unity 版本 %d 条' % len(added))
    return jsonify({
        'success': True,
        'added_count': len(added),
        'detected_count': len(detected),
        'entries': added,
    })

@bp.route('/api/jenkins-manage/start', methods=['POST'])
@admin_required('jenkins')
def api_start_jenkins():
    data = request.get_json() or {}
    if not has_scope('jenkins.manage'):
        return jsonify({'success': False, 'error': '无权限启动 Jenkins 实例'}), 403
    port = data.get('port')
    if port is None:
        return jsonify({'success': False, 'error': '缺少 port'})
    from flask import session
    started_by = session.get('user') or request.remote_addr or ''
    task_name = (data.get('task_name') or '').strip()
    feishu_webhook = (data.get('feishu_webhook') or '').strip()
    instance_type = (data.get('instance_type') or 'general').strip()
    success, instance_id, err = jm.start_jenkins(
        int(port), started_by, task_name=task_name, feishu_webhook=feishu_webhook, instance_type=instance_type
    )
    if success:
        log_audit('jenkins_start', '启动 Jenkins 实例 %s 端口 %s' % (instance_id, port))
        return jsonify({'success': True, 'instance_id': instance_id})
    return jsonify({'success': False, 'error': err or '启动失败'})


@bp.route('/api/jenkins-manage/start-instance', methods=['POST'])
@admin_required('jenkins')
def api_start_instance():
    """启动已存在且已停止的 Jenkins 实例。"""
    data = request.get_json() or {}
    if not has_scope('jenkins.manage'):
        return jsonify({'success': False, 'error': '无权限启动 Jenkins 实例'}), 403
    instance_id = (data.get('instance_id') or '').strip()
    if not instance_id:
        return jsonify({'success': False, 'error': '缺少 instance_id'})
    from flask import session
    started_by = session.get('user') or request.remote_addr or ''
    success, err = jm.start_existing_jenkins(instance_id, started_by=started_by)
    if success:
        log_audit('jenkins_start_instance', '启动已有 Jenkins 实例 %s' % instance_id)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': err or '启动失败'})


@bp.route('/api/jenkins-manage/stop', methods=['POST'])
@admin_required('jenkins')
def api_stop_jenkins():
    data = request.get_json() or {}
    if not has_scope('jenkins.manage'):
        return jsonify({'success': False, 'error': '无权限停止 Jenkins 实例'}), 403
    success, err = jm.stop_jenkins(instance_id=data.get('instance_id'), port=data.get('port'))
    if success:
        log_audit('jenkins_stop', '停止 Jenkins 实例 %s' % (data.get('instance_id') or data.get('port')))
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': err})


@bp.route('/api/jenkins-manage/delete', methods=['POST'])
@admin_required('jenkins')
def api_delete_jenkins():
    from models.data import get_system_config, get_approved_approval
    data = request.get_json() or {}
    if not has_scope('jenkins.manage'):
        return jsonify({'success': False, 'error': '无权限删除 Jenkins 实例'}), 403
    instance_id = (data.get('instance_id') or '').strip()
    port = data.get('port')
    target_id = instance_id if instance_id else ('port:%s' % (port or ''))
    if str(get_system_config('REQUIRE_APPROVAL_FOR_DELETE') or '').lower() in ('true', '1', 'yes'):
        if not get_approved_approval('delete_jenkins', target_id):
            return jsonify({'success': False, 'error': '删除 Jenkins 实例需先提交审批并通过。请至 审批管理 发起「删除 Jenkins 实例」申请，目标 ID 填写：' + target_id}), 403
    success, err = jm.delete_jenkins_instance(instance_id=instance_id or None, port=port)
    if success:
        log_audit('jenkins_delete', '删除 Jenkins 实例 %s' % (data.get('instance_id') or data.get('port')))
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': err})


@bp.route('/api/jenkins-manage/instance')
@admin_required_any('jenkins', 'build')
def api_get_instance():
    """获取单个实例详情，供编辑页与构建页选择实例后使用；仅开构建管理也可调用。"""
    instance_id = request.args.get('instance_id', '').strip()
    if not instance_id:
        return jsonify({'success': False, 'error': '缺少 instance_id'}), 400
    inst = jm.get_instance_by_id(instance_id)
    if not inst:
        return jsonify({'success': False, 'error': '未找到该实例'}), 404
    instances = jm.list_instances()
    for i in instances:
        if i.get('id') == instance_id:
            return jsonify({'success': True, 'instance': i})
    return jsonify({'success': False, 'error': '未找到该实例'}), 404


@bp.route('/api/jenkins-manage/update', methods=['POST'])
@admin_required('jenkins')
def api_update_instance():
    """更新实例的 task_name、feishu_webhook。"""
    data = request.get_json() or {}
    instance_id = (data.get('instance_id') or '').strip()
    if not instance_id:
        return jsonify({'success': False, 'error': '缺少 instance_id'})
    task_name = data.get('task_name')
    feishu_webhook = data.get('feishu_webhook')
    success, err = jm.update_instance(instance_id, task_name=task_name, feishu_webhook=feishu_webhook)
    if success:
        log_audit('jenkins_update', '更新 Jenkins 实例 %s' % instance_id)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': err or '更新失败'})


@bp.route('/api/jenkins-manage/sync-job', methods=['POST'])
@admin_required('jenkins')
def api_sync_job():
    """按项目 build_config（可选 project_id）同步 Jenkins 任务 config.xml。"""
    data = request.get_json() or {}
    instance_id = (data.get('instance_id') or '').strip()
    project_id = (data.get('project_id') or '').strip()
    if not instance_id:
        return jsonify({'success': False, 'error': '缺少 instance_id'})
    if jm.sync_instance_job_config(instance_id, project_id=project_id):
        jm.refresh_instance_env_and_scripts(instance_id)
        return jsonify({'success': True})
    return jsonify({'success': False, 'error': '同步失败（实例不存在或目录不可写）'})


@bp.route('/admin/jenkins/edit')
@admin_required('jenkins')
def jenkins_edit_page():
    """编辑实例：任务名、飞书 Webhook（构建参数已归属项目）。"""
    instance_id = request.args.get('instance_id', '').strip()
    if not instance_id:
        return _admin_layout('<p class="text-red-600">缺少 instance_id</p>', '编辑实例', back_href='/admin/jenkins')
    inst = jm.get_instance_by_id(instance_id)
    if not inst:
        return _admin_layout('<p class="text-red-600">未找到该实例</p>', '编辑实例', back_href='/admin/jenkins')
    content = _jenkins_edit_html(instance_id, inst)
    return _admin_layout(content, '编辑 Jenkins 实例', back_href='/admin/jenkins')


def _jenkins_edit_html(instance_id, inst):
    return '''<div class="space-y-6">
    <p class="text-sm text-gray-600">实例 ID: ''' + instance_id + ''' · 端口: ''' + str(inst.get('port', '')) + '''</p>
    <div class="bg-white rounded-lg shadow p-6">
        <h2 class="text-lg font-semibold mb-4">实例属性</h2>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            <div>
                <label class="block text-gray-600 mb-1">任务名</label>
                <input type="text" id="editTaskName" value="''' + (inst.get('task_name') or '').replace('"', '&quot;') + '''" class="border rounded px-2 py-1.5 w-full">
            </div>
            <div class="md:col-span-2">
                <label class="block text-gray-600 mb-1">飞书 Webhook</label>
                <input type="text" id="editFeishuWebhook" value="''' + (inst.get('feishu_webhook') or '').replace('"', '&quot;') + '''" placeholder="https://open.feishu.cn/..." class="border rounded px-2 py-1.5 w-full">
            </div>
        </div>
        <p class="text-xs text-gray-500 mt-4">Git、APP_NAME、Unity 路径等构建参数请在「项目管理」中配置，构建时按所选项目自动注入。</p>
        <div class="mt-4 flex gap-2">
            <button type="button" id="btnSaveEdit" class="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 text-sm">保存</button>
        </div>
        <div id="editResult" class="mt-3 px-4 py-3 rounded text-sm font-medium min-h-[3rem] border-2 border-gray-200 bg-gray-50 text-gray-600" role="status" aria-live="polite">点击「保存」后，结果将显示在此处。</div>
    </div>
</div>
<script>
(function(){
var instanceId = ''' + json.dumps(instance_id) + ''';
function _jmHeaders(isJson){
    var t=document.querySelector('meta[name="csrf-token"]');
    var h={};
    if(isJson) h['Content-Type']='application/json';
    if(t&&t.content) h['X-CSRFToken']=t.content;
    return h;
}
function setEditResult(msg, isError){
    var el = document.getElementById('editResult');
    if(el){ el.textContent = msg; el.className = 'mt-3 px-3 py-2 rounded text-sm font-medium min-h-[2.5rem] border ' + (isError ? 'bg-red-100 text-red-700 border-red-300' : 'bg-green-100 text-green-700 border-green-300'); el.setAttribute('role', 'status'); try{ el.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }catch(e){} }
    else{ alert(msg); }
}
function doSave(){
    try{
        setEditResult('保存中…', false);
        var payload = { instance_id: instanceId, task_name: document.getElementById('editTaskName').value.trim(), feishu_webhook: document.getElementById('editFeishuWebhook').value.trim() };
        fetch('/api/jenkins-manage/update', { method: 'POST', headers: _jmHeaders(true), credentials: 'same-origin', body: JSON.stringify(payload) })
        .then(function(r){ return r.json().then(function(d){ return { ok: r.ok, data: d }; }).catch(function(){ return { ok: false, data: { error: '响应格式错误' } }; }); })
        .then(function(x){ if(x.data && x.data.success) setEditResult('已保存', false); else setEditResult(x.data && x.data.error ? x.data.error : '保存失败', true); })
        .catch(function(e){ setEditResult('请求失败: ' + (e && e.message ? e.message : '请检查网络'), true); });
    }catch(e){ setEditResult('操作异常: ' + (e.message || ''), true); }
}
var btnSave = document.getElementById('btnSaveEdit');
if(btnSave) btnSave.onclick = doSave;
})();
</script>
'''


@bp.route('/admin/jenkins/instance-log')
@admin_required('jenkins')
def instance_log_page():
    """查看指定 Jenkins 实例的运行日志（stdout/stderr），便于出问题时定位。"""
    from flask import Response
    instance_id = request.args.get('instance_id', '').strip()
    if not instance_id:
        return '<p>缺少 instance_id</p>', 400
    inst = jm.get_instance_by_id(instance_id)
    if not inst:
        return '<p>未找到该实例</p>', 404
    jenkins_home = inst.get('jenkins_home') or ''
    if not jenkins_home or not os.path.isdir(jenkins_home):
        return '<p>实例目录不存在</p>', 404
    # 顺带刷新该实例的 .apk-site-env（含当前局域网 APKSITE_BASE_URL）与通知脚本，并修复可执行权限
    jm.refresh_instance_env_and_scripts(instance_id)
    scripts_dir = os.path.join(jenkins_home, 'scripts')
    if os.path.isdir(scripts_dir):
        for name in ('jenkins_send_notify.sh',):
            p = os.path.join(scripts_dir, name)
            if os.path.isfile(p):
                try:
                    os.chmod(p, 0o755)
                except Exception:
                    pass
    log_path = os.path.join(jenkins_home, 'logs', 'jenkins.log')
    if not os.path.isfile(log_path):
        return _admin_layout('<pre class="p-4 text-sm text-gray-600">暂无运行日志（可能尚未启动或日志未生成）</pre>', 'Jenkins 运行日志', back_href='/admin/jenkins')
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        return _admin_layout('<p class="text-red-600">读取失败: %s</p>' % str(e), 'Jenkins 运行日志', back_href='/admin/jenkins')
    # 限制展示尾部，避免过大
    max_chars = 512 * 1024
    if len(content) > max_chars:
        content = '...(仅显示最后 %d 字符)\n\n' % max_chars + content[-max_chars:]
    html = '<div class="bg-white rounded-lg shadow p-4"><p class="text-sm text-gray-500 mb-2">实例 %s 端口 %s · <a href="/admin/jenkins" class="text-blue-600">返回 Jenkins 管理</a></p><pre class="bg-gray-900 text-green-400 text-xs p-4 rounded overflow-auto max-h-[80vh] whitespace-pre-wrap">%s</pre></div>' % (
        instance_id, inst.get('port', ''), content.replace('<', '&lt;').replace('>', '&gt;').replace('&', '&amp;'))
    return _admin_layout(html, 'Jenkins 运行日志', back_href='/admin/jenkins')


@bp.route('/api/jenkins-manage/list')
@admin_required_any('jenkins', 'build')
def api_list_instances():
    """实例列表：Jenkins 管理页与构建页共用；仅开构建管理权限也可拉取已启动的实例以选择打包。"""
    instances = jm.list_instances()
    return jsonify({'instances': instances})


@bp.route('/api/jenkins-manage/list-available')
@admin_required_any('jenkins', 'build')
def api_list_available_instances():
    """返回运行中的 Jenkins 实例；默认排除正在构建的实例，include_instance_id 可强制包含（用于构建中回页）。"""
    from services import jenkins as jenkins_svc
    include_ids = set()
    for raw in request.args.getlist('include_instance_id'):
        for part in str(raw or '').split(','):
            part = part.strip()
            if part:
                include_ids.add(part)
    instances = jm.list_instances()
    available = []
    seen = set()
    for inst in instances:
        if inst.get('status') != 'running':
            continue
        iid = inst.get('id') or ''
        url = jm.get_jenkins_url_for_instance(instance_id=iid)
        bdir = jm.get_builds_dir_for_instance(instance_id=iid)
        if not url or not bdir:
            continue
        try:
            st = jenkins_svc.fetch_jenkins_status(base_url=url, builds_dir=bdir, instance_id=iid)
            if not st.get('ok'):
                continue
            if st.get('building') and iid not in include_ids:
                continue
            available.append(inst)
            seen.add(iid)
        except Exception:
            pass
    for inst in instances:
        iid = inst.get('id') or ''
        if iid in include_ids and iid not in seen and inst.get('status') == 'running':
            available.append(inst)
            seen.add(iid)
    return jsonify({'instances': available})


@bp.route('/api/jenkins-manage/env-check')
@admin_required('jenkins')
def api_env_check():
    return jsonify(jm.env_check())


@bp.route('/api/jenkins-manage/deploy-env', methods=['POST'])
@admin_required('jenkins')
def api_deploy_env():
    if not has_scope('jenkins.manage'):
        return jsonify({'success': False, 'error': '无权限执行环境部署'}), 403
    from config import Config
    from datetime import datetime
    log_dir = Config.LOG_DIR
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'jenkins_deploy_%s.log' % datetime.now().strftime('%Y%m%d_%H%M%S'))
    jm.run_deploy_env(log_path)
    return jsonify({'log_path': os.path.basename(log_path)})


@bp.route('/api/jenkins-manage/deploy-log')
@admin_required('jenkins')
def api_deploy_log():
    from config import Config
    name = request.args.get('path', '').strip()
    if not name or '..' in name or not name.startswith('jenkins_deploy'):
        return '', 400
    log_dir = Config.LOG_DIR
    path = os.path.join(log_dir, os.path.basename(name))
    if not os.path.abspath(path).startswith(os.path.abspath(log_dir)):
        return '', 403
    if not os.path.isfile(path):
        return '日志文件尚未生成', 200
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

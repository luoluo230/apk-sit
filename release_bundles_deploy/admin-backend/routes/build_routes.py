# -*- coding: utf-8 -*-
"""构建管理：Jenkins 触发、状态、日志、停止；支持多实例选择"""

import os
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, render_template_string
from services.authz import admin_required_any, has_scope
from config import Config
from models.data import log_audit, get_channel_by_id
from services import jenkins as jenkins_svc
from services import jenkins_manager as jm

# 阶段 ID -> 输出子目录（dev/test/release）
STAGE_OUTPUT_DIR = {'dev': 'dev', 'test': 'test', 'production': 'release'}


def _compute_stage_output_base(apk_root, channel_id, stage_id):
    """计算某渠道+阶段的 APK 输出目录：apk_root/渠道APK子目录/阶段目录"""
    channel = get_channel_by_id(channel_id) if channel_id else None
    apk_subdir = ((channel or {}).get('apk_subdir') or '').strip()
    stage_dir = STAGE_OUTPUT_DIR.get((stage_id or 'dev').strip(), 'dev')
    parts = [apk_root.rstrip('/')]
    if apk_subdir:
        parts.append(apk_subdir)
    parts.append(stage_dir)
    return os.path.join(*parts)

bp = Blueprint('build_routes', __name__, url_prefix='')

BUILDS_DIR = Config.JENKINS_BUILDS_DIR


def _get_csrf_token():
    try:
        from flask_wtf.csrf import generate_csrf

        return generate_csrf()
    except ImportError:
        return ''


def _jenkins_context():
    """从请求中取 instance_id（body 或 query），返回 (base_url, builds_dir, instance_id)。"""
    instance_id = None
    if request.is_json and request.get_json(silent=True):
        instance_id = (request.get_json() or {}).get('instance_id')
    if instance_id is None:
        instance_id = request.args.get('instance_id', '').strip() or None
    if not instance_id:
        return (None, None, None)
    url = jm.get_jenkins_url_for_instance(instance_id=instance_id)
    bdir = jm.get_builds_dir_for_instance(instance_id=instance_id)
    return (url, bdir, instance_id)


def _build_page_html(project_context=False, version_lock_params=False):
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>构建管理 - APK 下载中心</title>
    <link rel="stylesheet" href="/static/tailwind.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body class="bg-gray-50 min-h-screen">
    <div class="container mx-auto px-4 py-6 max-w-6xl">
        <div class="flex justify-between items-center mb-6">
            <h1 class="text-2xl font-bold text-gray-800 flex items-center gap-2">
                <i class="fas fa-cogs text-orange-500"></i> 构建管理
            </h1>
            <a href="{{ back_href|default('/admin') }}" class="text-blue-600 hover:text-blue-800 hover:underline flex items-center gap-1">
                <i class="fas fa-arrow-left"></i> 返回
            </a>
        </div>
        {% if version_info %}
        <div class="mb-4 bg-white rounded-xl border border-amber-100 p-4 text-sm text-gray-700 flex flex-wrap items-center gap-3">
            <span class="px-2 py-0.5 rounded bg-amber-50 text-amber-700 font-medium">
                项目：{{ version_info.project_id }}{% if version_info.version_name or version_info.version_code %} / 版本：{{ version_info.version_name or version_info.version_code }}{% endif %}
            </span>
            <span class="text-gray-500">渠道：{{ version_info.channel_name or version_info.channel or '-' }}</span>
            {% if version_info.stage_name %}<span class="text-gray-500">阶段：{{ version_info.stage_name }}</span>{% endif %}
        </div>
        {% endif %}
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div class="lg:col-span-2 bg-white rounded-xl shadow-md border border-gray-100 p-6">
                <h2 class="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
                    <i class="fas fa-edit text-blue-500"></i> 构建参数
                </h2>
                <form id="buildForm" class="space-y-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">使用 Jenkins 实例</label>
                        <select id="jenkinsInstance" class="w-full max-w-xs border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500">
                            <option value="">默认（当前配置）</option>
                        </select>
                        <p class="text-xs text-gray-500 mt-1">在「Jenkins 管理」中可启动多个实例，此处选择用于本次构建的 Jenkins。通过本系统新建的实例使用固定账号（默认 admin/admin123），无需在 .env 配置</p>
                    </div>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div><label class="block text-sm font-medium text-gray-700 mb-1">APP_NAME</label><input type="text" name="APP_NAME" id="APP_NAME" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500" value="{{ default_app_name|default('RecycleTycoon') }}" placeholder="应用名"></div>
                        <div><label class="block text-sm font-medium text-gray-700 mb-1">VERSION_NAME</label><input type="text" name="VERSION_NAME" id="VERSION_NAME" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" value="{{ default_version_name|default('1.0.15') }}" placeholder="如 1.0.15"></div>
                        <div><label class="block text-sm font-medium text-gray-700 mb-1">VERSION_CODE</label><input type="text" name="VERSION_CODE" id="VERSION_CODE" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" value="{{ default_version_code|default('1015') }}" placeholder="整数"></div>
                        <div><label class="block text-sm font-medium text-gray-700 mb-1">UNITY_VERSION</label><div id="UNITY_VERSION_container"><input type="text" name="UNITY_VERSION" id="UNITY_VERSION" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" value="6000.3.8f1"></div></div>
                    </div>
                    <div><label class="block text-sm font-medium text-gray-700 mb-1">OUTPUT_BASE_DIR</label><input type="text" name="OUTPUT_BASE_DIR" id="OUTPUT_BASE_DIR" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm" value="{{ apk_dir }}" placeholder="APK 输出目录"><p class="text-xs text-amber-600 mt-1">建议与 APK 目录一致或为其子目录，构建产物将自动出现在版本列表与下载中心</p></div>
                    <div><label class="block text-sm font-medium text-gray-700 mb-1">GIT_BRANCH</label><div id="GIT_BRANCH_container"><input type="text" name="GIT_BRANCH" id="GIT_BRANCH" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" value="{{ default_git_branch|default('main') }}" placeholder="分支名"></div></div>
                    {% if channel_options %}
                    <div><label class="block text-sm font-medium text-gray-700 mb-1">CHANNEL</label><select name="CHANNEL" id="CHANNEL" class="w-full max-w-xs border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500"><option value="">不指定</option>{% for k,v in channel_options %}<option value="{{ k }}" {{ 'selected' if default_channel==k else '' }}>{{ v }}</option>{% endfor %}</select><p class="text-xs text-gray-500 mt-1">用于多渠道构建，会传给 Jenkins 任务参数</p></div>
                    {% endif %}
                    <div class="flex gap-3 pt-2">
                        <button type="submit" id="btnTrigger" class="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:ring-2 focus:ring-blue-300 font-medium flex items-center gap-2">
                            <i class="fas fa-play"></i> <span id="btnTriggerText">开始构建</span>
                        </button>
                        <button type="button" id="btnStop" class="px-5 py-2.5 bg-red-600 text-white rounded-lg hover:bg-red-700 focus:ring-2 focus:ring-red-300 font-medium hidden flex items-center gap-2">
                            <i class="fas fa-stop"></i> 停止构建
                        </button>
                    </div>
                </form>
                <p id="buildStatus" class="mt-3 text-sm text-gray-500 min-h-[1.5rem]"></p>
                <div id="buildSuccessLinks" class="mt-2 flex flex-wrap gap-3 text-sm"></div>
            </div>
            <div class="bg-white rounded-xl shadow-md border border-gray-100 p-6">
                <h2 class="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
                    <i class="fas fa-history text-green-500"></i> 构建历史
                </h2>
                <ul id="buildHistory" class="space-y-2 text-sm text-gray-700"></ul>
            </div>
        </div>
        <div class="mt-6 bg-white rounded-xl shadow-md border border-gray-100 p-6">
            <h2 class="text-lg font-semibold text-gray-800 mb-3 flex items-center gap-2">
                <i class="fas fa-terminal text-gray-500"></i> 构建日志
            </h2>
            <pre id="buildLog" class="bg-gray-900 text-green-400 p-4 rounded-lg overflow-auto text-xs font-mono min-h-[320px] max-h-[420px] border border-gray-700" style="white-space: pre-wrap; word-break: break-all;">点击左侧「构建历史」中的某次构建可查看日志；开始构建后此处将自动刷新。</pre>
        </div>
        {% if version_downloads %}
        <div class="mt-6 bg-white rounded-xl shadow-md border border-gray-100 p-6">
            <h2 class="text-lg font-semibold text-gray-800 mb-3 flex items-center gap-2">
                <i class="fas fa-download text-emerald-500"></i> 本版本下载列表
            </h2>
            <div class="overflow-x-auto">
                <table class="min-w-full text-sm">
                    <thead class="bg-gray-50 border-b border-gray-200">
                        <tr>
                            <th class="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">文件名</th>
                            <th class="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">大小</th>
                            <th class="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">下载次数</th>
                            <th class="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">操作</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100">
                        {% for f in version_downloads %}
                        <tr>
                            <td class="px-4 py-2 text-gray-800">{{ f.name }}</td>
                            <td class="px-4 py-2 text-gray-600">{{ f.size_mb }} MB</td>
                            <td class="px-4 py-2 text-gray-600">{{ f.downloads }}</td>
                            <td class="px-4 py-2">
                                <a href="{{ f.url }}" class="px-3 py-1.5 text-xs rounded bg-indigo-600 text-white hover:bg-indigo-700">下载</a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% endif %}
    </div>
    <script>
    var PROJECT_ID = "{{ project_id or '' }}";
    var VERSION_ID = "{{ version_id or '' }}";
    var CHANNEL_ID = "{{ channel_id or '' }}";
    var STAGE_ID = "{{ stage_id or '' }}";
    function selectedInstanceId(){ var s=document.getElementById('jenkinsInstance'); return (s&&s.value)||''; }
    function apiQuery(){ var id=selectedInstanceId(); return id ? '?instance_id='+encodeURIComponent(id) : ''; }
    function apiBody(obj){
        var id=selectedInstanceId();
        if(id) obj.instance_id=id;
        if(PROJECT_ID){ obj._project_id = PROJECT_ID; }
        if(VERSION_ID){ obj._version_id = VERSION_ID; }
        if(CHANNEL_ID){ obj._channel_id = CHANNEL_ID; }
        if(STAGE_ID){ obj._stage_id = STAGE_ID; }
        return obj;
    }
    function loadJenkinsOptions(){
        return fetch('/api/jenkins-manage/list', {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
            var sel=document.getElementById('jenkinsInstance');
            if(!sel) return;
            while(sel.options.length>1) sel.remove(1);
            (d.instances||[]).forEach(function(i){
                var opt=document.createElement('option');
                opt.value=i.id;
                var label=i.port + ((i.task_name&&i.task_name.trim()) ? ' '+i.task_name.trim() : '') + ' - ' + (i.status==='running'?'运行中':'已停止');
                opt.textContent=label;
                sel.appendChild(opt);
            });
        });
    }
    function loadLastParams(){
        return fetch('/api/build/last-successful-params'+apiQuery(), {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
            if(d && typeof d==='object'){ for(var k in d){ var el=document.getElementById(k); if(el) el.value=d[k]||''; } }
        });
    }
    function setBuilding(yes){
        var startBtn=document.getElementById('btnTrigger');
        var stopBtn=document.getElementById('btnStop');
        if(yes){ startBtn.classList.add('hidden'); stopBtn.classList.remove('hidden'); }
        else{ startBtn.classList.remove('hidden'); stopBtn.classList.add('hidden'); startBtn.disabled=false; var t=document.getElementById('btnTriggerText'); if(t) t.textContent='开始构建'; }
    }
    function statusClass(r){
        if(!r) return 'bg-gray-200 text-gray-700';
        r=r.toUpperCase();
        if(r==='SUCCESS') return 'bg-green-100 text-green-800';
        if(r==='FAILURE'||r==='ABORTED') return 'bg-red-100 text-red-800';
        if(r==='UNSTABLE') return 'bg-yellow-100 text-yellow-800';
        return 'bg-gray-100 text-gray-700';
    }
    function loadHistory(){
        fetch('/api/jenkins/status'+apiQuery(), {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
            var list=document.getElementById('buildHistory');
            if(!d.ok||!d.recent){ list.innerHTML='<li class="text-gray-500 text-sm">暂无构建记录</li>'; return; }
            list.innerHTML=(d.recent||[]).slice(0,12).map(function(b){
                var result=b.result||'';
                var badge='<span class="inline-block px-2 py-0.5 rounded text-xs font-medium '+statusClass(result)+'">'+result+'</span>';
                return '<li class="py-1.5 border-b border-gray-100 last:border-0"><a href="#" onclick="loadLog('+b.number+');return false" class="text-blue-600 hover:underline font-medium">#'+b.number+'</a> '+badge+'</li>';
            }).join('');
        });
    }
    function loadLog(num){
        var el=document.getElementById('buildLog');
        el.textContent='加载中...';
        fetch('/api/build/log/'+num+apiQuery(), {credentials:'same-origin'}).then(r=>r.text()).then(t=>{ el.textContent=t||'（无日志）'; el.scrollTop=el.scrollHeight; });
    }
    function pollLogAndStatus(buildNum){
        var el=document.getElementById('buildLog');
        function tick(){
            fetch('/api/jenkins/status'+apiQuery(), {credentials:'same-origin'}).then(r=>r.json()).then(function(st){
                var done=false;
                if(st.ok&&st.recent){ for(var i=0;i<st.recent.length;i++){ var b=st.recent[i]; if(b.number===buildNum&&b.result){ done=true; break; } } }
                if(done){ stopPoll(); loadHistory(); setBuilding(false); return; }
                fetch('/api/build/log/'+buildNum+apiQuery(), {credentials:'same-origin'}).then(r=>r.text()).then(t=>{ el.textContent=t||'（无日志）'; el.scrollTop=el.scrollHeight; });
            });
        }
        tick();
        window._logTimer=setInterval(tick, 3000);
    }
    function stopPoll(){ if(window._logTimer){ clearInterval(window._logTimer); window._logTimer=null; } }
    function setUnityVersionControl(choices){
        var c=document.getElementById('UNITY_VERSION_container');
        if(!c) return;
        if(choices&&choices.length>0){
            var sel=document.createElement('select');
            sel.id=sel.name='UNITY_VERSION';
            sel.className='w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500';
            choices.forEach(function(v){ var o=document.createElement('option'); o.value=v; o.textContent=v; sel.appendChild(o); });
            c.innerHTML=''; c.appendChild(sel);
        } else {
            c.innerHTML='<input type="text" name="UNITY_VERSION" id="UNITY_VERSION" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" value="6000.3.8f1">';
        }
    }
    function setGitBranchControl(choices){
        var c=document.getElementById('GIT_BRANCH_container');
        if(!c) return;
        if(choices&&choices.length>0){
            var sel=document.createElement('select');
            sel.id=sel.name='GIT_BRANCH';
            sel.className='w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500';
            choices.forEach(function(v){ var o=document.createElement('option'); o.value=v; o.textContent=v; sel.appendChild(o); });
            c.innerHTML=''; c.appendChild(sel);
        } else {
            c.innerHTML='<input type="text" name="GIT_BRANCH" id="GIT_BRANCH" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" value="main" placeholder="分支名">';
        }
    }
    function applyInstanceDefaults(inst){
        var bd=inst&&inst.build_defaults;
        if(!bd) return;
        var uv=bd.unity_versions;
        if(Array.isArray(uv)&&uv.length){ var vs=uv.map(function(u){ return (u&&u.version)!==undefined ? u.version : String(u); }); setUnityVersionControl(vs); }
        else setUnityVersionControl(null);
        var gb=bd.git_branches;
        if(Array.isArray(gb)&&gb.length) setGitBranchControl(gb);
        else setGitBranchControl(null);
        if(bd.app_name){ var e=document.getElementById('APP_NAME'); if(e) e.value=bd.app_name; }
        if(bd.output_base_dir){ var e=document.getElementById('OUTPUT_BASE_DIR'); if(e) e.value=bd.output_base_dir; }
        // VERSION_NAME、VERSION_CODE 不覆盖，保留「上次成功构建」拉取的值
    }
    function refreshForInstance(){
        var sel=document.getElementById('jenkinsInstance');
        var listEl=document.getElementById('buildHistory');
        var logEl=document.getElementById('buildLog');
        if(!sel||!listEl||!logEl) return;
        stopPoll();
        if(!selectedInstanceId()){
            listEl.innerHTML='<li class="text-gray-500 text-sm">请选择上方 Jenkins 实例</li>';
            setBuilding(false);
            logEl.textContent='选择 Jenkins 实例后可查看该实例的构建历史与日志';
            return;
        }
        loadHistory();
        var id=selectedInstanceId();
        fetch('/api/jenkins-manage/instance?instance_id='+encodeURIComponent(id), {credentials:'same-origin'}).then(function(r){ return r.json(); }).then(function(d){
            if(d.success&&d.instance){
                loadLastParams().then(function(){ applyInstanceDefaults(d.instance); });
            } else { loadLastParams(); }
        }).catch(function(){ loadLastParams(); });
        fetch('/api/jenkins/status'+apiQuery(), {credentials:'same-origin'}).then(r=>r.json()).then(function(d){
            if(!d.ok){ setBuilding(false); logEl.textContent='无法获取该实例状态，请检查实例是否运行'; return; }
            setBuilding(d.building);
            if(d.building&&d.recent&&d.recent.length){
                var buildingItem=d.recent.find(function(b){ return !b.result||b.result===''; });
                if(buildingItem){ document.getElementById('btnStop').setAttribute('data-build', buildingItem.number); pollLogAndStatus(buildingItem.number); return; }
            }
            logEl.textContent='点击左侧「构建历史」中的某次构建可查看日志；开始构建后此处将自动刷新。';
        }).catch(function(){ setBuilding(false); logEl.textContent='获取状态失败'; });
    }
    document.getElementById('buildForm').onsubmit=function(e){
        e.preventDefault();
        var btn=document.getElementById('btnTrigger');
        var btnText=document.getElementById('btnTriggerText');
        btn.disabled=true; if(btnText) btnText.textContent='提交中...';
        var params={};
        ['APP_NAME','VERSION_NAME','VERSION_CODE','UNITY_VERSION','OUTPUT_BASE_DIR','GIT_BRANCH','CHANNEL'].forEach(function(k){ var el=document.getElementById(k); if(el) params[k]=el.value.trim(); });
        fetch('/admin/build/trigger', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(apiBody(params)), credentials:'same-origin' })
        .then(r=>r.json())
        .then(d=>{
            if(d.success){
                document.getElementById('buildStatus').textContent='已触发构建 #'+d.build_number;
                document.getElementById('buildStatus').className='mt-3 text-sm text-green-600 min-h-[1.5rem]';
                document.getElementById('btnStop').setAttribute('data-build', d.build_number);
                setBuilding(true);
                pollLogAndStatus(d.build_number);
                loadHistory();
                var el=document.getElementById('buildSuccessLinks');
                if(el&&PROJECT_ID){
                    el.innerHTML='<a href="/admin/projects/'+PROJECT_ID+'" class="text-blue-600 hover:underline">返回项目中心</a>'+
                        '<a href="/admin/projects/'+PROJECT_ID+'#tab=channels" class="text-blue-600 hover:underline">渠道与版本</a>'+
                        '<a href="/download-center?project='+encodeURIComponent(PROJECT_ID)+'" class="text-blue-600 hover:underline">下载中心</a>';
                } else { el.innerHTML=''; }
            } else {
                document.getElementById('buildStatus').textContent='失败: '+(d.error||'');
                document.getElementById('buildStatus').className='mt-3 text-sm text-red-600 min-h-[1.5rem]';
                var el=document.getElementById('buildSuccessLinks'); if(el) el.innerHTML='';
                btn.disabled=false; if(btnText) btnText.textContent='开始构建';
            }
        }).catch(function(){ btn.disabled=false; if(btnText) btnText.textContent='开始构建'; });
        return false;
    };
    document.getElementById('btnStop').onclick=function(){
        var num=this.getAttribute('data-build'); if(!num) return;
        fetch('/api/build/'+num+'/stop', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(apiBody({})), credentials:'same-origin'}).then(r=>r.json()).then(function(x){ document.getElementById('buildStatus').textContent=x.success?'已请求停止':(x.error||''); document.getElementById('buildStatus').className='mt-3 text-sm text-gray-500 min-h-[1.5rem]'; });
    };
    loadJenkinsOptions().then(function(){ refreshForInstance(); });
    var sel=document.getElementById('jenkinsInstance');
    if(sel) sel.addEventListener('change', function(){ refreshForInstance(); });
    </script>
</body>
</html>
'''


def _version_workflow_page_html():
    """版本构建页：独立于构建管理，参数由版本回填且除 Jenkins/GIT_BRANCH 外不可编辑。"""
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>版本构建 - APK 下载中心</title>
    <link rel="stylesheet" href="/static/tailwind.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body class="bg-gray-50 min-h-screen">
    <div class="container mx-auto px-4 py-6 max-w-6xl">
        <div class="flex justify-between items-center mb-6">
            <h1 class="text-2xl font-bold text-gray-800 flex items-center gap-2">
                <i class="fas fa-hammer text-emerald-600"></i> 版本构建
            </h1>
            <a href="{{ back_href|default('/admin') }}" class="text-blue-600 hover:text-blue-800 hover:underline flex items-center gap-1">
                <i class="fas fa-arrow-left"></i> 返回
            </a>
        </div>
        {% if version_info %}
        <div class="mb-4 bg-white rounded-xl border border-emerald-100 p-4 text-sm text-gray-700 flex flex-wrap items-center gap-3">
            <span class="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 font-medium">
                项目：{{ version_info.project_id }}{% if version_info.version_name or version_info.version_code %} / 版本：{{ version_info.version_name or version_info.version_code }}{% endif %}
            </span>
            <span class="text-gray-500">渠道：{{ version_info.channel_name or version_info.channel or '-' }}</span>
            {% if version_info.stage_name %}<span class="text-gray-500">阶段：{{ version_info.stage_name }}</span>{% endif %}
        </div>
        {% endif %}
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div class="lg:col-span-2 bg-white rounded-xl shadow-md border border-gray-100 p-6">
                <h2 class="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
                    <i class="fas fa-cogs text-emerald-500"></i> 构建参数
                </h2>
                <p class="text-xs text-gray-500 mb-4">以下参数由版本锁定，仅 Jenkins 实例与 Git 分支可修改</p>
                <form id="buildForm" class="space-y-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">使用 Jenkins 实例</label>
                        <select id="jenkinsInstance" class="w-full max-w-xs border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-emerald-500">
                            <option value="">请选择（仅显示运行中且无构建任务的实例）</option>
                        </select>
                        <p class="text-xs text-gray-500 mt-1">仅列出可用实例，切换实例不会改变下方版本参数</p>
                    </div>
                    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div><label class="block text-sm font-medium text-gray-600 mb-1">APP_NAME</label><input type="text" id="APP_NAME" readonly class="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-50 text-gray-700" value="{{ default_app_name|default('') }}" placeholder="-"></div>
                        <div><label class="block text-sm font-medium text-gray-600 mb-1">VERSION_NAME</label><input type="text" id="VERSION_NAME" readonly class="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-50 text-gray-700" value="{{ default_version_name|default('') }}" placeholder="-"></div>
                        <div><label class="block text-sm font-medium text-gray-600 mb-1">VERSION_CODE</label><input type="text" id="VERSION_CODE" readonly class="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-50 text-gray-700" value="{{ default_version_code|default('') }}" placeholder="-"></div>
                        <div><label class="block text-sm font-medium text-gray-600 mb-1">UNITY_VERSION</label><input type="text" id="UNITY_VERSION" readonly class="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-50 text-gray-700" value="{{ default_unity_version|default('6000.3.8f1') }}" placeholder="-"></div>
                    </div>
                    <div><label class="block text-sm font-medium text-gray-600 mb-1">OUTPUT_BASE_DIR</label><input type="text" id="OUTPUT_BASE_DIR" readonly class="w-full px-3 py-2 border border-gray-200 rounded-lg bg-gray-50 text-gray-700 text-sm" value="{{ apk_dir }}" placeholder="-"></div>
                    <div><label class="block text-sm font-medium text-gray-700 mb-1">GIT_BRANCH <span class="text-gray-400 font-normal">（可编辑）</span></label><div id="GIT_BRANCH_container"><input type="text" name="GIT_BRANCH" id="GIT_BRANCH" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500" value="{{ default_git_branch|default('main') }}" placeholder="分支名"></div></div>
                    {% if channel_options %}
                    <div><label class="block text-sm font-medium text-gray-600 mb-1">CHANNEL</label><input type="text" id="CHANNEL_display" readonly class="w-full max-w-xs px-3 py-2 border border-gray-200 rounded-lg bg-gray-50 text-gray-700" value="{{ default_channel_display|default('-') }}"><input type="hidden" id="CHANNEL" value="{{ default_channel|default('') }}"></div>
                    {% endif %}
                    <div class="flex gap-3 pt-2">
                        <button type="submit" id="btnTrigger" class="px-5 py-2.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 focus:ring-2 focus:ring-emerald-300 font-medium flex items-center gap-2">
                            <i class="fas fa-play"></i> <span id="btnTriggerText">开始构建</span>
                        </button>
                        <button type="button" id="btnStop" class="px-5 py-2.5 bg-red-600 text-white rounded-lg hover:bg-red-700 focus:ring-2 focus:ring-red-300 font-medium hidden flex items-center gap-2">
                            <i class="fas fa-stop"></i> 停止构建
                        </button>
                    </div>
                </form>
                <p id="buildStatus" class="mt-3 text-sm text-gray-500 min-h-[1.5rem]"></p>
                <div id="buildSuccessLinks" class="mt-2 flex flex-wrap gap-3 text-sm"></div>
            </div>
            <div class="bg-white rounded-xl shadow-md border border-gray-100 p-6">
                <h2 class="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
                    <i class="fas fa-history text-emerald-500"></i> 本版本构建历史
                </h2>
                <ul id="buildHistory" class="space-y-2 text-sm text-gray-700"></ul>
            </div>
        </div>
        <div class="mt-6 bg-white rounded-xl shadow-md border border-gray-100 p-6">
            <h2 class="text-lg font-semibold text-gray-800 mb-3 flex items-center gap-2">
                <i class="fas fa-terminal text-gray-500"></i> 构建日志
            </h2>
            <pre id="buildLog" class="bg-gray-900 text-green-400 p-4 rounded-lg overflow-auto text-xs font-mono min-h-[320px] max-h-[420px] border border-gray-700" style="white-space: pre-wrap; word-break: break-all;">选择 Jenkins 实例后，可从构建历史查看日志；开始构建后此处将自动刷新。</pre>
        </div>
        {% if version_downloads %}
        <div class="mt-6 bg-white rounded-xl shadow-md border border-gray-100 p-6">
            <h2 class="text-lg font-semibold text-gray-800 mb-3 flex items-center gap-2">
                <i class="fas fa-download text-emerald-500"></i> 本版本下载列表
            </h2>
            <div class="overflow-x-auto">
                <table class="min-w-full text-sm">
                    <thead class="bg-gray-50 border-b border-gray-200">
                        <tr>
                            <th class="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">文件名</th>
                            <th class="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">大小</th>
                            <th class="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">下载次数</th>
                            <th class="px-4 py-2 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">操作</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100">
                        {% for f in version_downloads %}
                        <tr>
                            <td class="px-4 py-2 text-gray-800">{{ f.name }}</td>
                            <td class="px-4 py-2 text-gray-600">{{ f.size_mb }} MB</td>
                            <td class="px-4 py-2 text-gray-600">{{ f.downloads }}</td>
                            <td class="px-4 py-2">
                                <a href="{{ f.url }}" class="px-3 py-1.5 text-xs rounded bg-indigo-600 text-white hover:bg-indigo-700">下载</a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% endif %}
    </div>
    <script>
    var PROJECT_ID = "{{ project_id or '' }}";
    var VERSION_ID = "{{ version_id or '' }}";
    function selectedInstanceId(){ var s=document.getElementById('jenkinsInstance'); return (s&&s.value)||''; }
    function apiQuery(){ var id=selectedInstanceId(); return id ? '?instance_id='+encodeURIComponent(id) : ''; }
    function apiBody(obj){
        var id=selectedInstanceId();
        if(id) obj.instance_id=id;
        if(PROJECT_ID) obj._project_id = PROJECT_ID;
        if(VERSION_ID) obj._version_id = VERSION_ID;
        return obj;
    }
    function loadJenkinsOptions(){
        return fetch('/api/jenkins-manage/list-available', {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
            var sel=document.getElementById('jenkinsInstance');
            if(!sel) return;
            while(sel.options.length>1) sel.remove(1);
            (d.instances||[]).forEach(function(i){
                var opt=document.createElement('option');
                opt.value=i.id;
                opt.textContent=(i.port||'') + ((i.task_name&&i.task_name.trim()) ? ' '+i.task_name.trim() : '') + ' - 运行中';
                sel.appendChild(opt);
            });
        });
    }
    function setBuilding(yes){
        var startBtn=document.getElementById('btnTrigger');
        var stopBtn=document.getElementById('btnStop');
        if(yes){ startBtn.classList.add('hidden'); stopBtn.classList.remove('hidden'); }
        else{ startBtn.classList.remove('hidden'); stopBtn.classList.add('hidden'); startBtn.disabled=false; var t=document.getElementById('btnTriggerText'); if(t) t.textContent='开始构建'; }
    }
    function statusClass(r){
        if(!r) return 'bg-gray-200 text-gray-700';
        r=r.toUpperCase();
        if(r==='SUCCESS') return 'bg-green-100 text-green-800';
        if(r==='FAILURE'||r==='ABORTED') return 'bg-red-100 text-red-800';
        if(r==='UNSTABLE') return 'bg-yellow-100 text-yellow-800';
        return 'bg-gray-100 text-gray-700';
    }
    function loadHistory(){
        if(!VERSION_ID){ document.getElementById('buildHistory').innerHTML='<li class="text-gray-500 text-sm">无法加载</li>'; return; }
        var q='version_id='+encodeURIComponent(VERSION_ID);
        if(selectedInstanceId()) q+='&instance_id='+encodeURIComponent(selectedInstanceId());
        fetch('/api/build/history-by-version?'+q, {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
            var list=document.getElementById('buildHistory');
            if(!d.builds||!d.builds.length){ list.innerHTML='<li class="text-gray-500 text-sm">本版本暂无构建记录</li>'; return; }
            list.innerHTML=d.builds.slice(0,12).map(function(b){
                var result=b.result||'';
                var badge='<span class="inline-block px-2 py-0.5 rounded text-xs font-medium '+statusClass(result)+'">'+result+'</span>';
                return '<li class="py-1.5 border-b border-gray-100 last:border-0"><a href="#" onclick="loadLog('+b.number+');return false" class="text-blue-600 hover:underline font-medium">#'+b.number+'</a> '+badge+'</li>';
            }).join('');
        });
    }
    function loadLog(num){
        var el=document.getElementById('buildLog');
        el.textContent='加载中...';
        fetch('/api/build/log/'+num+apiQuery(), {credentials:'same-origin'}).then(r=>r.text()).then(t=>{ el.textContent=t||'（无日志）'; el.scrollTop=el.scrollHeight; });
    }
    function pollLogAndStatus(buildNum){
        var el=document.getElementById('buildLog');
        function tick(){
            fetch('/api/jenkins/status'+apiQuery(), {credentials:'same-origin'}).then(r=>r.json()).then(function(st){
                var done=false;
                if(st.ok&&st.recent){ for(var i=0;i<st.recent.length;i++){ var b=st.recent[i]; if(b.number===buildNum&&b.result){ done=true; break; } } }
                if(done){ stopPoll(); loadHistory(); setBuilding(false); return; }
                fetch('/api/build/log/'+buildNum+apiQuery(), {credentials:'same-origin'}).then(r=>r.text()).then(t=>{ el.textContent=t||'（无日志）'; el.scrollTop=el.scrollHeight; });
            });
        }
        tick();
        window._logTimer=setInterval(tick, 3000);
    }
    function stopPoll(){ if(window._logTimer){ clearInterval(window._logTimer); window._logTimer=null; } }
    function setGitBranchControl(choices){
        var c=document.getElementById('GIT_BRANCH_container');
        if(!c) return;
        if(choices&&choices.length>0){
            var sel=document.createElement('select');
            sel.id=sel.name='GIT_BRANCH';
            sel.className='w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500';
            var currentVal=document.getElementById('GIT_BRANCH')? (document.getElementById('GIT_BRANCH').value||''):'';
            choices.forEach(function(v){ var o=document.createElement('option'); o.value=v; o.textContent=v; if(v===currentVal) o.selected=true; sel.appendChild(o); });
            c.innerHTML=''; c.appendChild(sel);
        }
    }
    function refreshForInstance(){
        var listEl=document.getElementById('buildHistory');
        var logEl=document.getElementById('buildLog');
        if(!listEl||!logEl) return;
        stopPoll();
        if(!selectedInstanceId()){
            listEl.innerHTML='<li class="text-gray-500 text-sm">请选择上方 Jenkins 实例</li>';
            setBuilding(false);
            logEl.textContent='选择 Jenkins 实例后可查看本版本的构建历史与日志';
            return;
        }
        loadHistory();
        fetch('/api/jenkins-manage/instance?instance_id='+encodeURIComponent(selectedInstanceId()), {credentials:'same-origin'}).then(function(r){ return r.json(); }).then(function(d){
            if(d.success&&d.instance&&d.instance.build_defaults&&Array.isArray(d.instance.build_defaults.git_branches)&&d.instance.build_defaults.git_branches.length){
                setGitBranchControl(d.instance.build_defaults.git_branches.map(function(u){ return (u&&u.branch)!==undefined ? u.branch : String(u); }));
            }
        });
        fetch('/api/jenkins/status'+apiQuery(), {credentials:'same-origin'}).then(r=>r.json()).then(function(d){
            if(!d.ok){ setBuilding(false); logEl.textContent='无法获取该实例状态'; return; }
            setBuilding(d.building);
            if(d.building&&d.recent&&d.recent.length){
                var buildingItem=d.recent.find(function(b){ return !b.result||b.result===''; });
                if(buildingItem){ document.getElementById('btnStop').setAttribute('data-build', buildingItem.number); pollLogAndStatus(buildingItem.number); return; }
            }
            logEl.textContent='点击左侧「本版本构建历史」中的某次构建可查看日志；开始构建后此处将自动刷新。';
        }).catch(function(){ setBuilding(false); logEl.textContent='获取状态失败'; });
    }
    document.getElementById('buildForm').onsubmit=function(e){
        e.preventDefault();
        var btn=document.getElementById('btnTrigger');
        var btnText=document.getElementById('btnTriggerText');
        btn.disabled=true; if(btnText) btnText.textContent='提交中...';
        var params={ APP_NAME: (document.getElementById('APP_NAME')||{}).value, VERSION_NAME: (document.getElementById('VERSION_NAME')||{}).value, VERSION_CODE: (document.getElementById('VERSION_CODE')||{}).value, UNITY_VERSION: (document.getElementById('UNITY_VERSION')||{}).value, OUTPUT_BASE_DIR: (document.getElementById('OUTPUT_BASE_DIR')||{}).value, GIT_BRANCH: (document.getElementById('GIT_BRANCH')||{}).value||'main', CHANNEL: (document.getElementById('CHANNEL')||{}).value||'' };
        fetch('/admin/build/trigger', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(apiBody(params)), credentials:'same-origin' })
        .then(r=>r.json())
        .then(d=>{
            if(d.success){
                document.getElementById('buildStatus').textContent='已触发构建 #'+d.build_number;
                document.getElementById('buildStatus').className='mt-3 text-sm text-green-600 min-h-[1.5rem]';
                document.getElementById('btnStop').setAttribute('data-build', d.build_number);
                setBuilding(true);
                pollLogAndStatus(d.build_number);
                loadHistory();
                var el=document.getElementById('buildSuccessLinks');
                if(el&&PROJECT_ID){ el.innerHTML='<a href="/admin/projects/'+PROJECT_ID+'" class="text-blue-600 hover:underline">返回项目中心</a> <a href="/admin/projects/'+PROJECT_ID+'/versions/'+VERSION_ID+'/workflow" class="text-blue-600 hover:underline">刷新本页</a>'; }
            } else {
                document.getElementById('buildStatus').textContent='失败: '+(d.error||'');
                document.getElementById('buildStatus').className='mt-3 text-sm text-red-600 min-h-[1.5rem]';
                btn.disabled=false; if(btnText) btnText.textContent='开始构建';
            }
        }).catch(function(){ btn.disabled=false; if(btnText) btnText.textContent='开始构建'; });
        return false;
    };
    document.getElementById('btnStop').onclick=function(){
        var num=this.getAttribute('data-build'); if(!num) return;
        fetch('/api/build/'+num+'/stop', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(apiBody({})), credentials:'same-origin'}).then(r=>r.json()).then(function(x){ document.getElementById('buildStatus').textContent=x.success?'已请求停止':(x.error||''); });
    };
    loadJenkinsOptions().then(function(){ refreshForInstance(); });
    document.getElementById('jenkinsInstance').addEventListener('change', function(){ refreshForInstance(); });
    </script>
</body>
</html>
'''


@bp.route('/admin/build')
@admin_required_any('projects', 'build')
def build_page():
    """构建管理（通用入口；?project=xxx 时重定向至项目构建页）"""
    from flask import request, redirect
    project_id = (request.args.get('project') or '').strip()
    if project_id:
        from models.data import projects_db, can_view_project
        from flask import session
        if project_id in projects_db and can_view_project(project_id, session.get('user') or ''):
            return redirect('/admin/projects/%s/build' % project_id)
    return render_template('admin_build.html', apk_dir=Config.APK_DIR, default_app_name='RecycleTycoon', default_version_name='1.0.15', default_version_code='1015', csrf_token_value=_get_csrf_token())


@bp.route('/admin/projects/<project_id>/build')
@admin_required_any('projects', 'build')
def project_build_page(project_id):
    """项目内构建页：带项目默认值（兼容入口，推荐从版本工作流进入）"""
    from models.data import projects_db, can_view_project
    from flask import session
    if project_id not in projects_db:
        from flask import abort
        abort(404)
    if not can_view_project(project_id, session.get('user') or ''):
        from flask import abort
        abort(403)
    # 兼容：若存在版本，跳转到最新版本的工作流；否则仍提供通用构建页
    from models.data import project_versions_db
    versions = (project_versions_db.get(project_id) or [])
    if isinstance(versions, list) and versions:
        v = versions[-1]
        vid = (v.get('id') or '').strip()
        if vid:
            from flask import redirect
            return redirect(f'/admin/projects/{project_id}/versions/{vid}/workflow')
    # 从最新版本或 jenkins_params 取默认值
    default_ver_name, default_ver_code, default_branch = '1.0.0', '100', 'main'
    if versions:
        v = versions[-1]
        params = v.get('jenkins_params') or {}
        default_ver_name = params.get('VERSION_NAME') or v.get('version_name') or default_ver_name
        default_ver_code = params.get('VERSION_CODE') or v.get('version_code') or default_ver_code
        default_branch = params.get('GIT_BRANCH') or default_branch
    return render_template(
        'admin_build.html',
        apk_dir=Config.APK_DIR,
        default_app_name=project_id,
        default_version_name=default_ver_name,
        default_version_code=default_ver_code,
        default_git_branch=default_branch,
        project_id=project_id,
        back_href='/admin/projects/%s' % project_id,
        csrf_token_value=_get_csrf_token(),
    )


def _get_version_downloads(project_id, version, scan_dir=None):
    """根据约定规则获取某版本的 APK 下载列表。scan_dir 指定扫描目录（渠道+阶段子目录），否则扫描 APK 根目录。"""
    from models.data import download_stats
    files = []
    root = (scan_dir or Config.APK_DIR).rstrip(os.sep)
    if not os.path.isdir(root):
        return files
    rel_prefix = (scan_dir[len(Config.APK_DIR):].lstrip(os.sep) + '/') if scan_dir and scan_dir != Config.APK_DIR else ''
    names_hint = set(version.get('downloads') or [])
    ver_name = (version.get('version_name') or '').lower()
    proj_id = (project_id or '').lower()
    for fname in os.listdir(root):
        if not fname.lower().endswith(('.apk', '.ipa')):
            continue
        match = False
        if names_hint and fname in names_hint:
            match = True
        else:
            fn_lower = fname.lower()
            if proj_id and proj_id in fn_lower and ver_name and ver_name in fn_lower:
                match = True
        if not match:
            continue
        path = os.path.join(root, fname)
        if not os.path.isfile(path):
            continue
        try:
            size_mb = round(os.path.getsize(path) / (1024 * 1024), 1)
        except OSError:
            size_mb = '-'
        dl_key = (rel_prefix + fname) if rel_prefix else fname
        dl = download_stats.get(dl_key, download_stats.get(fname, 0))
        url_path = (rel_prefix + fname).replace('\\', '/') if rel_prefix else fname
        files.append({
            'name': fname,
            'size_mb': size_mb,
            'downloads': dl,
            'url': f"/pub/download/{url_path}",
        })
    files.sort(key=lambda x: x['name'])
    return files


def _get_stage_downloads(project_id, channel_id, stage_id):
    """获取某渠道+阶段的 APK 下载列表（扫描该阶段输出目录下所有 APK）。"""
    from models.data import download_stats
    files = []
    scan_dir = _compute_stage_output_base(Config.APK_DIR, channel_id, stage_id)
    if not os.path.isdir(scan_dir):
        return files
    rel_prefix = (os.path.relpath(scan_dir, Config.APK_DIR) + os.sep).replace('\\', '/')
    if rel_prefix.startswith('..'):
        rel_prefix = ''
    for fname in os.listdir(scan_dir):
        if not fname.lower().endswith(('.apk', '.ipa')):
            continue
        path = os.path.join(scan_dir, fname)
        if not os.path.isfile(path):
            continue
        try:
            size_mb = round(os.path.getsize(path) / (1024 * 1024), 1)
        except OSError:
            size_mb = '-'
        dl_key = (rel_prefix + fname) if rel_prefix else fname
        dl = download_stats.get(dl_key, download_stats.get(fname, 0))
        url_path = (rel_prefix + fname) if rel_prefix else fname
        files.append({'name': fname, 'size_mb': size_mb, 'downloads': dl, 'url': f"/pub/download/{url_path}"})
    files.sort(key=lambda x: x['name'])
    return files


@bp.route('/admin/projects/<project_id>/versions/<version_id>/workflow')
@admin_required_any('projects', 'build')
def project_version_workflow(project_id, version_id):
    """单个版本的构建工作流页：独立参数与下载列表，OUTPUT_BASE_DIR 含渠道子目录/阶段目录。"""
    from models.data import projects_db, project_versions_db, can_view_project
    from flask import session, abort
    if project_id not in projects_db:
        abort(404)
    if not can_view_project(project_id, session.get('user') or ''):
        abort(403)
    versions = (project_versions_db.get(project_id) or [])
    if not isinstance(versions, list):
        versions = []
    v = next((x for x in versions if (x.get('id') or '') == version_id), None)
    if not v:
        abort(404)
    channel_id = (v.get('channel') or '').strip()
    stage_id = (v.get('stage') or 'dev').strip()
    output_base = _compute_stage_output_base(Config.APK_DIR, channel_id, stage_id)
    downloads = _get_version_downloads(project_id, v, scan_dir=output_base)
    params_saved = v.get('jenkins_params') or {}
    default_output = params_saved.get('OUTPUT_BASE_DIR') or output_base
    from models.data import get_channels_for_project, get_channel_by_id
    ch_obj = get_channel_by_id(channel_id)
    default_channel_display = (ch_obj.get('name') or ch_obj.get('id', '') or channel_id or '-') if ch_obj else (channel_id or '-')
    stage_labels = {'dev': '开发', 'test': '测试', 'production': '线上'}
    version_info = {
        'project_id': project_id,
        'version_name': v.get('version_name'),
        'version_code': v.get('version_code'),
        'channel': channel_id,
        'channel_name': default_channel_display,
        'stage': stage_id,
        'stage_name': stage_labels.get(stage_id, '开发'),
    }
    default_app = params_saved.get('APP_NAME') or project_id
    default_ver_name = params_saved.get('VERSION_NAME') or v.get('version_name') or '1.0.0'
    default_ver_code = params_saved.get('VERSION_CODE') or v.get('version_code') or '100'
    default_unity = params_saved.get('UNITY_VERSION') or '6000.3.8f1'
    default_git_branch = params_saved.get('GIT_BRANCH') or 'main'
    channel_opts = get_channels_for_project(project_id)
    channel_options = [(c.get('id', '').strip(), (c.get('name') or c.get('id', '')).strip()) for c in channel_opts if (c.get('id') or '').strip()]
    default_channel = channel_id or ''
    return render_template_string(
        _version_workflow_page_html(),
        apk_dir=default_output,
        default_app_name=default_app,
        default_version_name=default_ver_name,
        default_version_code=default_ver_code,
        default_unity_version=default_unity,
        default_git_branch=default_git_branch,
        project_id=project_id,
        version_id=version_id,
        version_info=version_info,
        version_downloads=downloads,
        back_href='/admin/projects/%s' % project_id,
        channel_options=channel_options,
        default_channel=default_channel,
        default_channel_display=default_channel_display,
        csrf_token_value=_get_csrf_token(),
    )


@bp.route('/admin/projects/<project_id>/channels/<channel_id>/stages/<stage_id>/build')
@admin_required_any('projects', 'build')
def project_stage_build(project_id, channel_id, stage_id):
    """某渠道+阶段的独立构建页：独立构建参数、独立下载列表，OUTPUT_BASE_DIR 自动含渠道/阶段路径。"""
    from models.data import projects_db, project_versions_db, can_view_project
    from flask import session, abort
    if project_id not in projects_db:
        abort(404)
    if not can_view_project(project_id, session.get('user') or ''):
        abort(403)
    from models.data import projects_db
    output_base = _compute_stage_output_base(Config.APK_DIR, channel_id, stage_id)
    downloads = _get_stage_downloads(project_id, channel_id, stage_id)
    versions = (project_versions_db.get(project_id) or [])
    if not isinstance(versions, list):
        versions = []
    vers_in_stage = [x for x in versions if ((x.get('channel') or '').strip().lower() == (channel_id or '').lower()) and ((x.get('stage') or 'dev') == (stage_id or 'dev'))]
    v = vers_in_stage[-1] if vers_in_stage else {}
    params_saved = v.get('jenkins_params') or {}
    sbp = (projects_db.get(project_id) or {}).get('stage_build_params') or {}
    stage_key = '%s:%s' % (channel_id, stage_id)
    if stage_key in sbp:
        params_saved = dict(params_saved, **sbp[stage_key])
    default_app = params_saved.get('APP_NAME') or project_id
    default_ver_name = params_saved.get('VERSION_NAME') or v.get('version_name') or '1.0.0'
    default_ver_code = params_saved.get('VERSION_CODE') or v.get('version_code') or '100'
    default_git_branch = params_saved.get('GIT_BRANCH') or 'main'
    from models.data import get_channels_for_project, get_channel_by_id
    channel_obj = get_channel_by_id(channel_id)
    channel_name = (channel_obj.get('name') or channel_id) if channel_obj else channel_id
    stage_labels = {'dev': '开发', 'test': '测试', 'production': '线上'}
    stage_name = stage_labels.get((stage_id or 'dev').strip(), '开发')
    version_info = {
        'project_id': project_id,
        'version_name': None,
        'version_code': None,
        'channel': channel_id,
        'channel_name': channel_name,
        'stage': stage_id,
        'stage_name': stage_name,
    }
    channel_opts = get_channels_for_project(project_id)
    channel_options = [(c.get('id', '').strip(), (c.get('name') or c.get('id', '')).strip()) for c in channel_opts if (c.get('id') or '').strip()]
    return render_template(
        'admin_build.html',
        apk_dir=output_base,
        default_app_name=default_app,
        default_version_name=default_ver_name,
        default_version_code=default_ver_code,
        default_git_branch=default_git_branch,
        project_id=project_id,
        version_id='',
        channel_id=channel_id,
        stage_id=stage_id,
        version_info=version_info,
        version_downloads=downloads,
        back_href='/admin/projects/%s#tab=channels' % project_id,
        channel_options=channel_options,
        default_channel=channel_id or '',
        csrf_token_value=_get_csrf_token(),
    )


@bp.route('/admin/build/trigger', methods=['POST'])
@admin_required_any('projects', 'build')
def trigger_build():
    data = request.get_json() or {}
    base_url, builds_dir, instance_id = _jenkins_context()
    unity_version = (data.get('UNITY_VERSION') or '6000.3.8f1').strip()
    version_name = (data.get('VERSION_NAME') or '1.0.15').strip()
    version_code_raw = (data.get('VERSION_CODE') or '1015').strip()
    app_name = (data.get('APP_NAME') or 'RecycleTycoon').strip()
    output_base_dir = (data.get('OUTPUT_BASE_DIR') or Config.APK_DIR).strip()
    git_branch = (data.get('GIT_BRANCH') or 'main').strip()
    channel = (data.get('CHANNEL') or '').strip()
    project_id = (data.get('_project_id') or '').strip()
    version_id = (data.get('_version_id') or '').strip()
    ctx_channel_id = (data.get('_channel_id') or '').strip()
    ctx_stage_id = (data.get('_stage_id') or '').strip()
    try:
        version_code = str(int(version_code_raw))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'VERSION_CODE 须为整数'})
    # 操作级权限：触发/停止构建
    if not has_scope('build.trigger'):
        return jsonify({'success': False, 'error': '无权限触发构建'}), 403
    params = {
        'UNITY_VERSION': unity_version,
        'VERSION_NAME': version_name,
        'VERSION_CODE': version_code,
        'APP_NAME': app_name,
        'OUTPUT_BASE_DIR': output_base_dir,
    }
    if git_branch:
        params['GIT_BRANCH'] = git_branch
    if channel:
        params['CHANNEL'] = channel
    success, build_number, err = jenkins_svc.trigger_build(params, base_url=base_url, builds_dir=builds_dir, instance_id=instance_id)
    if success:
        log_audit('trigger_build', f'Jenkins 构建 #{build_number} - {app_name} {version_name}')
        if project_id and version_id and instance_id:
            try:
                from models.data import record_build_version
                record_build_version(instance_id, build_number, version_id, project_id)
            except Exception:
                pass
        if project_id and version_id:
            try:
                from models.data import project_versions_db, save_project_versions, projects_db, save_projects
                versions = (project_versions_db.get(project_id) or [])
                if isinstance(versions, list):
                    for ver in versions:
                        if (ver.get('id') or '') == version_id:
                            ver['jenkins_params'] = params
                            if instance_id:
                                ver['jenkins_instance_id'] = instance_id
                            ver['updated_at'] = datetime.now().isoformat()
                            break
                    project_versions_db[project_id] = versions
                    save_project_versions()
            except Exception:
                pass
        elif project_id and ctx_channel_id and ctx_stage_id:
            try:
                from models.data import projects_db, save_projects
                proj = projects_db.get(project_id) or {}
                sbp = proj.get('stage_build_params') or {}
                key = '%s:%s' % (ctx_channel_id, ctx_stage_id)
                sbp[key] = params
                if instance_id:
                    proj['stage_build_instance'] = proj.get('stage_build_instance') or {}
                    proj['stage_build_instance'][key] = instance_id
                proj['stage_build_params'] = sbp
                projects_db[project_id] = proj
                save_projects()
            except Exception:
                pass
        try:
            from services.webhook import fire_webhook
            fire_webhook('build_triggered', {'app_name': app_name, 'version_name': version_name, 'build_number': build_number})
        except Exception:
            pass
        return jsonify({'success': True, 'build_number': build_number})
    return jsonify({'success': False, 'error': err or '触发失败'})


@bp.route('/api/build/history-by-version')
@admin_required_any('projects', 'build')
def build_history_by_version():
    """按版本获取构建历史，仅返回本系统记录的、与该版本关联的构建。"""
    version_id = (request.args.get('version_id') or '').strip()
    instance_id = (request.args.get('instance_id') or '').strip()
    if not version_id:
        return jsonify({'builds': []})
    from models.data import get_build_records_for_version
    records = get_build_records_for_version(version_id, instance_id=instance_id if instance_id else None)
    # 若指定了 instance_id，从 Jenkins 拉取 recent 以填充 result
    if instance_id and records:
        base_url, builds_dir, _ = _jenkins_context()
        # 需要为指定 instance 构造 context
        url = jm.get_jenkins_url_for_instance(instance_id=instance_id)
        bdir = jm.get_builds_dir_for_instance(instance_id=instance_id)
        if url and bdir:
            st = jenkins_svc.fetch_jenkins_status(base_url=url, builds_dir=bdir, instance_id=instance_id)
            recent_map = {b.get('number'): b for b in (st.get('recent') or []) if b.get('number')}
            for r in records:
                b = recent_map.get(r.get('build_number'))
                r['result'] = (b.get('result') or '') if b else ''
                r['building'] = b.get('building', False) if b else False
    # 构造与 loadHistory 一致的格式
    builds = [{'number': r.get('build_number'), 'result': r.get('result', ''), 'building': r.get('building', False)} for r in records]
    return jsonify({'ok': True, 'builds': builds, 'recent': builds})


@bp.route('/api/build/recent')
@admin_required_any('projects', 'build')
def build_recent():
    """最近 N 次构建（从第一个可用 Jenkins 实例），用于项目构建 Tab 摘要"""
    limit = min(int(request.args.get('limit', 3)), 10)
    instances = jm.list_instances()
    for inst in instances:
        if inst.get('status') != 'running':
            continue
        url = jm.get_jenkins_url_for_instance(instance_id=inst.get('id'))
        bdir = jm.get_builds_dir_for_instance(instance_id=inst.get('id'))
        if url and bdir:
            data = jenkins_svc.fetch_jenkins_status(base_url=url, builds_dir=bdir, instance_id=inst.get('id'))
            builds = (data.get('recent') or data.get('builds') or [])[:limit]
            return jsonify({'builds': builds, 'instance_id': inst.get('id')})
    return jsonify({'builds': [], 'instance_id': None})


@bp.route('/api/jenkins/status')
@admin_required_any('projects', 'build')
def jenkins_status():
    base_url, builds_dir, instance_id = _jenkins_context()
    if not (has_scope('build.view') or has_scope('build.trigger')):
        return jsonify({'error': '无权限查看构建状态'}), 403
    return jsonify(jenkins_svc.fetch_jenkins_status(base_url=base_url, builds_dir=builds_dir, instance_id=instance_id))


@bp.route('/api/build/last-successful-params')
@admin_required_any('projects', 'build')
def last_successful_params():
    base_url, builds_dir, instance_id = _jenkins_context()
    if not (has_scope('build.view') or has_scope('build.trigger')):
        return jsonify({}), 403
    params = jenkins_svc.get_last_successful_params(base_url=base_url, builds_dir=builds_dir)
    # 该实例无历史成功构建时，返回该实例的默认输出目录，便于表单默认值隔离
    if not params and instance_id:
        inst = jm.get_instance_by_id(instance_id)
        if inst:
            params = {'OUTPUT_BASE_DIR': jm.get_instance_output_base(inst)}
    return jsonify(params or {})


@bp.route('/api/build/<int:build_number>/status')
@admin_required_any('projects', 'build')
def build_status(build_number):
    base_url, builds_dir, instance_id = _jenkins_context()
    if not (has_scope('build.view') or has_scope('build.trigger')):
        return jsonify({'error': '无权限查看构建状态'}), 403
    return jsonify(jenkins_svc.get_build_status(build_number, base_url=base_url, builds_dir=builds_dir))


@bp.route('/api/build/log/<int:build_number>')
@admin_required_any('projects', 'build')
def build_log(build_number):
    from flask import make_response
    base_url, builds_dir, instance_id = _jenkins_context()
    if not (has_scope('build.view') or has_scope('build.trigger')):
        return make_response('无权限查看构建日志', 403)
    content = jenkins_svc.get_build_log_content(build_number, base_url=base_url, builds_dir=builds_dir)
    resp = make_response(content)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@bp.route('/api/build/<int:build_number>/detail')
@admin_required_any('projects', 'build')
def build_detail(build_number):
    base_url, builds_dir, instance_id = _jenkins_context()
    if not (has_scope('build.view') or has_scope('build.trigger')):
        return jsonify({'error': '无权限查看构建详情'}), 403
    info = jenkins_svc.get_build_detail(build_number, base_url=base_url, builds_dir=builds_dir)
    if info is None:
        return jsonify({'error': '构建不存在'}), 404
    return jsonify(info)


@bp.route('/api/build/<int:build_number>/stop', methods=['POST'])
@admin_required_any('projects', 'build')
def stop_build(build_number):
    base_url, builds_dir, instance_id = _jenkins_context()
    if not has_scope('build.trigger'):
        return jsonify({'success': False, 'error': '无权限停止构建'}), 403
    success, err = jenkins_svc.stop_build(build_number, base_url=base_url, builds_dir=builds_dir, instance_id=instance_id)
    if success:
        log_audit('stop_build', f'已请求停止构建 #{build_number}')
        return jsonify({'success': True, 'message': '已请求停止构建'})
    return jsonify({'success': False, 'error': err or '停止失败'})

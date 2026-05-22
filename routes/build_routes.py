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


def _canonical_version_name_code(version_obj: dict | None) -> tuple[str, str]:
    """版本记录上的 version_name / version_code 为权威来源（优先于 jenkins_params 历史残留）。"""
    if not isinstance(version_obj, dict):
        return "", ""
    name = str(version_obj.get("version_name") or "").strip()
    code = str(version_obj.get("version_code") or "").strip()
    if not name:
        saved = version_obj.get("jenkins_params") if isinstance(version_obj.get("jenkins_params"), dict) else {}
        name = str((saved or {}).get("VERSION_NAME") or "").strip()
    if not code:
        saved = version_obj.get("jenkins_params") if isinstance(version_obj.get("jenkins_params"), dict) else {}
        code = str((saved or {}).get("VERSION_CODE") or "").strip()
    return name, code


def _resolve_version_git_branch(version_obj: dict) -> str:
    """从版本记录解析 Git 分支：发布配置 ppApkBranch → pipeline.apk_build.git_branch。"""
    if not isinstance(version_obj, dict):
        return "main"
    pipeline = version_obj.get("pipeline") if isinstance(version_obj.get("pipeline"), dict) else {}
    apk_build = pipeline.get("apk_build") if isinstance(pipeline.get("apk_build"), dict) else {}
    for candidate in (
        apk_build.get("git_branch"),
        pipeline.get("git_branch"),
        (version_obj.get("commercial_release") or {}).get("git_branch")
        if isinstance(version_obj.get("commercial_release"), dict)
        else None,
        (version_obj.get("jenkins_params") or {}).get("GIT_BRANCH")
        if isinstance(version_obj.get("jenkins_params"), dict)
        else None,
    ):
        branch = str(candidate or "").strip()
        if branch:
            return branch
    return "main"


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
    <meta name="csrf-token" content="{{ csrf_token_value|default('') }}">
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
                        <div><label class="block text-sm font-medium text-gray-700 mb-1">VERSION_NAME{% if version_lock_params %} <span class="text-xs text-gray-400 font-normal">（与版本记录 version_name 一致）</span>{% endif %}</label><input type="text" name="VERSION_NAME" id="VERSION_NAME" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" value="{{ default_version_name|default('1.0.15') }}" placeholder="如 1.0.15"></div>
                        <div><label class="block text-sm font-medium text-gray-700 mb-1">VERSION_CODE</label><input type="text" name="VERSION_CODE" id="VERSION_CODE" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" value="{{ default_version_code|default('1015') }}" placeholder="整数"></div>
                        <div><label class="block text-sm font-medium text-gray-700 mb-1">UNITY_VERSION</label><div id="UNITY_VERSION_container"><input type="text" name="UNITY_VERSION" id="UNITY_VERSION" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500" value="{{ default_unity_version|default('6000.3.8f1') }}"></div></div>
                    </div>
                    <div><label class="block text-sm font-medium text-gray-700 mb-1">OUTPUT_BASE_DIR</label><input type="text" name="OUTPUT_BASE_DIR" id="OUTPUT_BASE_DIR" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm" value="{{ apk_dir }}" placeholder="APK 输出目录"><p class="text-xs text-amber-600 mt-1">建议与 APK 目录一致或为其子目录，构建产物将自动出现在版本列表与下载中心</p></div>
                    <div><label class="block text-sm font-medium text-gray-700 mb-1">GIT_BRANCH{% if version_lock_params %} <span class="text-xs text-gray-400 font-normal">（来自版本发布配置，不可修改）</span>{% endif %}</label><div id="GIT_BRANCH_container"><input type="text" name="GIT_BRANCH" id="GIT_BRANCH" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500{% if version_lock_params %} bg-slate-100{% endif %}" value="{{ default_git_branch|default('main') }}" placeholder="分支名"{% if version_lock_params %} readonly{% endif %}></div></div>
                    {% if channel_options %}
                    <div><label class="block text-sm font-medium text-gray-700 mb-1">CHANNEL</label><select name="CHANNEL" id="CHANNEL" class="w-full max-w-xs border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500"><option value="">不指定</option>{% for k,v in channel_options %}<option value="{{ k }}" {{ 'selected' if default_channel==k else '' }}>{{ v }}</option>{% endfor %}</select><p class="text-xs text-gray-500 mt-1">用于多渠道构建，会传给 Jenkins 任务参数</p></div>
                    {% endif %}
                    {% if version_mode == 'commercial' %}
                    <div id="commercialParamsPanel" class="rounded-xl border border-violet-200 bg-gradient-to-br from-violet-50/80 to-white p-4">
                        <div class="w-full flex items-center justify-between gap-2">
                            <button type="button" id="commercialParamsToggle" class="flex-1 flex items-center justify-between gap-2 text-left">
                                <span class="text-sm font-semibold text-violet-800 flex items-center gap-2">
                                    <i class="fas fa-rocket text-violet-500"></i> 商业级构建参数
                                    <span class="text-xs font-normal text-violet-500">（只读，来自版本流水线配置）</span>
                                    <span class="text-[10px] text-violet-400">UIv2026-05-22-01</span>
                                </span>
                                <i id="commercialParamsChevron" class="fas fa-chevron-down text-violet-400 text-xs transition-transform"></i>
                            </button>
                            <div class="inline-flex items-center rounded-lg border border-violet-200 bg-white p-0.5">
                                <button type="button" id="cpLangZh" class="px-2 py-1 text-[11px] rounded text-violet-700 bg-violet-100">中文</button>
                                <button type="button" id="cpLangEn" class="px-2 py-1 text-[11px] rounded text-slate-500">EN</button>
                            </div>
                        </div>
                        <div id="commercialParamsBody" data-panel-body="1" class="mt-3 text-sm text-slate-700 space-y-2 border-t border-violet-100 pt-3"></div>
                    </div>
                    {% endif %}
                    <div class="flex gap-3 pt-2">
                        <button type="submit" id="btnTrigger" class="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:ring-2 focus:ring-blue-300 font-medium flex items-center gap-2">
                            <i class="fas fa-play"></i> <span id="btnTriggerText">开始构建</span>
                        </button>
                        <button type="button" id="btnStop" class="px-5 py-2.5 bg-red-600 text-white rounded-lg hover:bg-red-700 focus:ring-2 focus:ring-red-300 font-medium hidden flex items-center gap-2">
                            <i class="fas fa-stop"></i> 停止构建
                        </button>
                    </div>
                    <div id="jenkinsConsoleRow" class="hidden mt-2">
                        <a id="jenkinsConsoleLink" href="#" target="_blank" rel="noopener noreferrer" class="text-sm text-indigo-600 hover:underline">
                            进入 Jenkins 控制台
                        </a>
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
    var VERSION_MODE = "{{ version_mode or 'general' }}";
    var PREFERRED_INSTANCE_ID = "{{ preferred_instance_id or '' }}";
    var VERSION_LOCK_PARAMS = {{ 'true' if version_lock_params else 'false' }};
    var CANONICAL_VERSION_NAME = {{ (canonical_version_name|default('')|tojson) }};
    var CANONICAL_VERSION_CODE = {{ (canonical_version_code|default('')|tojson) }};
    var CANONICAL_GIT_BRANCH = {{ (default_git_branch|default('')|tojson) }};
    var VERSION_PIPELINE = {{ (version_pipeline or {})|tojson }};
    var VERSION_INFO = {{ (version_info or {})|tojson }};
    var INSTANCE_META = {};
    function modeLabel(v){ return normalizedType(v)==='commercial' ? '商业级' : '通用级'; }
    function normalizedType(v){
        var t=String(v||'general').trim().toLowerCase();
        if(t!=='commercial') t='general';
        return t;
    }
    function getCsrfToken(){
        var m=document.querySelector('meta[name="csrf-token"]');
        return m ? (m.getAttribute('content')||'') : '';
    }
    function versionGitBranch(){ return (document.getElementById('GIT_BRANCH')||{}).value || ''; }
    function _buildStorageKey(suffix){ return 'buildwf:'+PROJECT_ID+':'+VERSION_ID+':'+suffix; }
    function persistInstanceChoice(){ try{ localStorage.setItem(_buildStorageKey('instance_id'), selectedInstanceId()||''); }catch(e){} }
    function loadInstanceChoice(){ try{ return localStorage.getItem(_buildStorageKey('instance_id'))||''; }catch(e){ return ''; } }
    function saveActiveBuild(instanceId, buildNumber){ try{ localStorage.setItem(_buildStorageKey('active_build'), JSON.stringify({instance_id:instanceId||'', build_number:buildNumber||''})); }catch(e){} }
    function loadActiveBuild(){ try{ var s=localStorage.getItem(_buildStorageKey('active_build')); return s?JSON.parse(s):null; }catch(e){ return null; } }
    function clearActiveBuild(){ try{ localStorage.removeItem(_buildStorageKey('active_build')); }catch(e){} }
    function bindPanelState(panelId, storageKey, defaultCollapsed){
        var panel=document.getElementById(panelId);
        if(!panel) return;
        var body=panel.querySelector('[data-panel-body]');
        var toggle=document.getElementById('commercialParamsToggle');
        var chevron=document.getElementById('commercialParamsChevron');
        var collapsed=false;
        try{ collapsed=localStorage.getItem(storageKey)==='1'; }catch(e){}
        if(defaultCollapsed && localStorage.getItem(storageKey)===null) collapsed=true;
        function applyState(){
            if(!body) return;
            body.style.display=collapsed?'none':'block';
            if(chevron) chevron.style.transform=collapsed?'rotate(-90deg)':'';
        }
        applyState();
        if(toggle){
            toggle.onclick=function(){
                collapsed=!collapsed;
                try{ localStorage.setItem(storageKey, collapsed?'1':'0'); }catch(e){}
                applyState();
            };
        }
    }
    window._cpLang = window._cpLang || 'zh';
    function _escHtml(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
    function _onOff(v){
        if(window._cpLang==='en'){
            return v ? '<span class="text-emerald-600 font-medium">Enabled</span>' : '<span class="text-slate-400">Disabled</span>';
        }
        return v ? '<span class="text-emerald-600 font-medium">启用</span>' : '<span class="text-slate-400">禁用</span>';
    }
    function _cpLabel(k){
        var map={
            APP_NAME:{zh:'应用名',en:'App Name'},
            VERSION_NAME:{zh:'版本名',en:'Version Name'},
            VERSION_CODE:{zh:'版本号',en:'Version Code'},
            UNITY_VERSION:{zh:'Unity 版本',en:'Unity Version'},
            OUTPUT_BASE_DIR:{zh:'输出目录',en:'Output Base Dir'},
            GIT_BRANCH:{zh:'Git 分支',en:'Git Branch'},
            RELEASE_ENVIRONMENT:{zh:'发布环境',en:'Release Environment'},
            RELEASE_CHANNEL:{zh:'发布渠道',en:'Release Channel'},
            RELEASE_PLATFORM:{zh:'发布平台',en:'Release Platform'},
            RELEASE_MODE:{zh:'发布模式',en:'Release Mode'},
            RELEASE_TARGETS:{zh:'发布对象',en:'Release Targets'},
            RELEASE_UPLOAD_MODE:{zh:'上传模式',en:'Upload Mode'},
            CONFIG_REMOTE_PREFIX:{zh:'配置远端前缀',en:'Config Remote Prefix'},
            RESOURCE_PROVIDER:{zh:'资源引擎',en:'Resource Provider'},
            RESOURCE_SCENARIO:{zh:'资源场景',en:'Resource Scenario'},
            CODE_UNITS:{zh:'代码单元',en:'Code Units'},
            RESOURCE_UNITS:{zh:'资源单元',en:'Resource Units'}
        };
        var n=map[k]||{zh:k,en:k};
        return window._cpLang==='en' ? (n.en+' / '+k) : (n.zh+' / '+k);
    }
    function _inputVal(id){
        var el=document.getElementById(id);
        return (el && el.value!=null) ? String(el.value).trim() : '';
    }
    function renderCommercialSummary(){
        var panel=document.getElementById('commercialParamsPanel');
        var body=document.getElementById('commercialParamsBody');
        if(!panel||!body) return;
        if(normalizedType(VERSION_MODE)!=='commercial'){
            panel.classList.add('hidden');
            return;
        }
        panel.classList.remove('hidden');
        var pp=VERSION_PIPELINE||{};
        var rows=[];
        var ce=pp.config_export||{};
        var rb=pp.resource_build||{};
        var hr=pp.hot_release||{};
        var ab=pp.apk_build||{};
        var isEn=(window._cpLang==='en');
        rows.push('<div class="grid grid-cols-1 md:grid-cols-2 gap-2">');
        rows.push('<div class="rounded-lg border border-violet-100 bg-white p-2"><div class="text-xs font-semibold text-violet-700 mb-1">Step1 '+(isEn?'Config Export':'配置导出')+'</div><div class="text-xs text-slate-600">'+_onOff(ce.enabled)+' · '+(isEn?'Env':'环境')+': '+_escHtml(ce.environment||'-')+' · '+(isEn?'Platform':'平台')+': '+_escHtml(ce.platform||'-')+' · '+(isEn?'Version':'版本')+': '+_escHtml(ce.client_version||CANONICAL_VERSION_NAME||'-')+'</div><div class="text-xs text-slate-600 mt-1">OSS Prefix: '+_escHtml(ce.remote_prefix||'-')+(ce.include_code?(isEn?' · Include code':' · 含代码'):'')+'</div></div>');
        rows.push('<div class="rounded-lg border border-violet-100 bg-white p-2"><div class="text-xs font-semibold text-violet-700 mb-1">Step2 '+(isEn?'Resource Build':'资源打包')+'</div><div class="text-xs text-slate-600">'+_onOff(rb.enabled)+' · '+(isEn?'Provider':'引擎')+': '+_escHtml(rb.provider||'-')+' · '+(isEn?'Scenario':'场景')+': '+_escHtml(rb.scenario||'-')+'</div></div>');
        rows.push('<div class="rounded-lg border border-violet-100 bg-white p-2"><div class="text-xs font-semibold text-violet-700 mb-1">Step3 '+(isEn?'Hot Release':'热更发布')+'</div><div class="text-xs text-slate-600">'+_onOff(hr.enabled)+' · '+(isEn?'Targets':'对象')+': '+_escHtml(hr.release_targets||'-')+' · '+(isEn?'Mode':'模式')+': '+_escHtml(hr.release_mode||'-')+' · '+(isEn?'Upload':'上传')+': '+_escHtml(hr.release_upload_mode||'-')+'</div>');
        if(hr.release_hot_labels) rows.push('<div class="pl-2 text-xs text-slate-600">热更标签: '+_escHtml(hr.release_hot_labels)+'</div>');
        if(hr.code_enabled) rows.push('<div class="pl-2 text-xs text-slate-600"><span class="text-blue-600">代码包</span> 压缩 '+_escHtml(hr.code_compression||'-')+' · 加密 '+_escHtml(hr.code_encryption||'-')+' · 签名 '+_escHtml(hr.code_signature||'-')+'</div>');
        if(hr.resource_enabled) rows.push('<div class="pl-2 text-xs text-slate-600"><span class="text-emerald-600">资源包</span> 压缩 '+_escHtml(hr.resource_compression||'-')+' · 加密 '+_escHtml(hr.resource_encryption||'-')+' · 签名 '+_escHtml(hr.resource_signature||'-')+'</div>');
        rows.push('</div>');
        rows.push('<div class="rounded-lg border border-violet-100 bg-white p-2"><div class="text-xs font-semibold text-violet-700 mb-1">Step4 APK '+(isEn?'(Optional)':'（可选）')+'</div><div class="text-xs text-slate-600">'+_onOff(ab.enabled)+' · Unity '+_escHtml(ab.unity_version||'-')+' · '+(isEn?'Branch':'分支')+' '+_escHtml(ab.git_branch||CANONICAL_GIT_BRANCH||'-')+'</div></div>');
        rows.push('</div>');
        var missing=[];
        if(!_inputVal('APP_NAME')) missing.push('APP_NAME');
        if(!_inputVal('VERSION_NAME')) missing.push('VERSION_NAME');
        if(!_inputVal('VERSION_CODE')) missing.push('VERSION_CODE');
        if(!_inputVal('UNITY_VERSION') && !String(ab.unity_version||'').trim()) missing.push('UNITY_VERSION');
        if(!_inputVal('OUTPUT_BASE_DIR') && !String(ab.output_base_dir||'').trim()) missing.push('OUTPUT_BASE_DIR');
        if(!_inputVal('GIT_BRANCH') && !String(ab.git_branch||'').trim()) missing.push('GIT_BRANCH');
        if(!String(ce.remote_prefix||'').trim()) missing.push('CONFIG_REMOTE_PREFIX');
        if(!String(hr.release_targets||'').trim()) missing.push('RELEASE_TARGETS');
        if(missing.length){
            rows.push('<div class="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-700">参数缺失预警：'+_escHtml(missing.join(', '))+'（建议先回版本编辑页补齐流水线配置）</div>');
        }
        var coverage=[
            ['APP_NAME', _inputVal('APP_NAME') || ab.app_name],
            ['VERSION_NAME', _inputVal('VERSION_NAME') || CANONICAL_VERSION_NAME],
            ['VERSION_CODE', _inputVal('VERSION_CODE') || CANONICAL_VERSION_CODE],
            ['UNITY_VERSION', _inputVal('UNITY_VERSION') || ab.unity_version],
            ['OUTPUT_BASE_DIR', _inputVal('OUTPUT_BASE_DIR') || ab.output_base_dir],
            ['GIT_BRANCH', _inputVal('GIT_BRANCH') || ab.git_branch || CANONICAL_GIT_BRANCH],
            ['RELEASE_ENVIRONMENT', hr.release_environment || ce.environment],
            ['RELEASE_CHANNEL', hr.release_channel || _inputVal('CHANNEL')],
            ['RELEASE_PLATFORM', ce.platform || (VERSION_INFO.platform||'')],
            ['RELEASE_MODE', hr.release_mode],
            ['RELEASE_TARGETS', hr.release_targets],
            ['RELEASE_UPLOAD_MODE', hr.release_upload_mode],
            ['CONFIG_REMOTE_PREFIX', ce.remote_prefix],
            ['RESOURCE_PROVIDER', rb.provider],
            ['RESOURCE_SCENARIO', rb.scenario],
            ['CODE_UNITS', hr.code_units],
            ['RESOURCE_UNITS', hr.resource_units]
        ];
        rows.push('<details class="mt-2 rounded border border-violet-200 bg-white" open><summary class="cursor-pointer select-none px-2 py-1 text-xs font-semibold text-violet-700">'+(isEn?'Parameter Coverage (Commercial)':'参数覆盖检查（商业级）')+'</summary>');
        rows.push('<div class="rounded border-t border-violet-100 overflow-hidden"><table class="w-full text-[11px]"><thead class="bg-slate-50"><tr><th class="text-left px-2 py-1 text-slate-500">'+(isEn?'Parameter':'参数')+'</th><th class="text-left px-2 py-1 text-slate-500">'+(isEn?'Status':'状态')+'</th><th class="text-left px-2 py-1 text-slate-500">'+(isEn?'Current Value':'当前值')+'</th></tr></thead><tbody>'+
            coverage.map(function(item){
                var ok=!!String(item[1]||'').trim();
                return '<tr class="border-t border-slate-100"><td class="px-2 py-1 text-slate-700">'+_escHtml(_cpLabel(item[0]))+'</td><td class="px-2 py-1">'+(ok?'<span class="text-emerald-600">'+(isEn?'OK':'已覆盖')+'</span>':'<span class="text-rose-600">'+(isEn?'Missing':'缺失')+'</span>')+'</td><td class="px-2 py-1 text-slate-600">'+_escHtml(String(item[1]||'-'))+'</td></tr>';
            }).join('')+
            '</tbody></table></div></details>');
        if(!ce.enabled && !rb.enabled && !hr.enabled && !ab.enabled){
            body.innerHTML='<p class="text-xs text-amber-700">未配置商业流水线步骤。请返回项目「版本管理」编辑该版本的商业级流水线后刷新本页。</p>';
        } else {
            body.innerHTML=rows.join('');
        }
    }
    function applyVersionCanonicalFields(){
        if(CANONICAL_VERSION_NAME){
            var vn=document.getElementById('VERSION_NAME');
            if(vn) vn.value=CANONICAL_VERSION_NAME;
        }
        if(CANONICAL_VERSION_CODE){
            var vc=document.getElementById('VERSION_CODE');
            if(vc) vc.value=String(CANONICAL_VERSION_CODE);
        }
        if(CANONICAL_GIT_BRANCH){
            var gb=document.getElementById('GIT_BRANCH');
            if(gb) gb.value=CANONICAL_GIT_BRANCH;
        }
    }
    function buildCommercialPlanFromVersion(){
        var plan={
            unityProjectPath:'',
            gitBranch: versionGitBranch(),
            appName: _inputVal('APP_NAME'),
            releaseVersion: _inputVal('VERSION_NAME'),
            versionCode: _inputVal('VERSION_CODE'),
            unityVersion: _inputVal('UNITY_VERSION'),
            outputBaseDir: _inputVal('OUTPUT_BASE_DIR'),
            releaseUpload: true,
            releaseActivate: false
        };
        if(CANONICAL_VERSION_NAME){ plan.releaseVersion=CANONICAL_VERSION_NAME; }
        if(CANONICAL_VERSION_CODE){ plan.versionCode=String(CANONICAL_VERSION_CODE); }
        var ch=document.getElementById('CHANNEL');
        if(ch&&ch.value){ plan.releaseChannel=ch.value; }
        var pp=VERSION_PIPELINE||{};
        var ce=pp.config_export||{};
        var rb=pp.resource_build||{};
        var hr=pp.hot_release||{};
        var ab=pp.apk_build||{};
        if(ce.enabled!=null) plan.configEnabled=!!ce.enabled;
        if(ce.remote_prefix) plan.configRemotePrefix=ce.remote_prefix;
        if(ce.include_code!=null) plan.configIncludeCode=!!ce.include_code;
        if(rb.enabled!=null) plan.resourceEnabled=!!rb.enabled;
        if(rb.provider) plan.resourceProvider=rb.provider;
        if(rb.scenario) plan.resourceScenario=rb.scenario;
        if(hr.enabled!=null) plan.hotReleaseEnabled=!!hr.enabled;
        if(hr.release_mode) plan.releaseMode=hr.release_mode;
        if(hr.release_environment) plan.releaseEnvironment=hr.release_environment;
        if(hr.release_channel) plan.releaseChannel=hr.release_channel;
        if(hr.release_targets) plan.releaseTargets=hr.release_targets;
        if(hr.release_hot_labels) plan.releaseHotLabels=hr.release_hot_labels;
        if(hr.release_upload_mode) plan.releaseUploadMode=hr.release_upload_mode;
        if(hr.release_rollback_target) plan.releaseRollbackTarget=hr.release_rollback_target;
        if(hr.release_compression_override) plan.releaseCompressionOverride=hr.release_compression_override;
        if(hr.release_encryption_override) plan.releaseEncryptionOverride=hr.release_encryption_override;
        if(hr.release_signature_override) plan.releaseSignatureOverride=hr.release_signature_override;
        if(hr.code_enabled!=null) plan.codeEnabled=!!hr.code_enabled;
        if(hr.code_compression) plan.codeCompression=hr.code_compression;
        if(hr.code_encryption) plan.codeEncryption=hr.code_encryption;
        if(hr.code_signature) plan.codeSignature=hr.code_signature;
        if(hr.code_units) plan.codeUnits=hr.code_units;
        if(hr.resource_enabled!=null) plan.resourceEnabled=!!hr.resource_enabled;
        if(hr.resource_compression) plan.resourceCompression=hr.resource_compression;
        if(hr.resource_encryption) plan.resourceEncryption=hr.resource_encryption;
        if(hr.resource_signature) plan.resourceSignature=hr.resource_signature;
        if(hr.resource_units) plan.resourceUnits=hr.resource_units;
        if(ab.app_name) plan.appName=ab.app_name;
        if(ab.unity_version) plan.unityVersion=ab.unity_version;
        if(ab.output_base_dir) plan.outputBaseDir=ab.output_base_dir;
        if(ab.unity_project_path) plan.unityProjectPath=ab.unity_project_path;
        var plat=(VERSION_INFO.platform||'android').toString();
        plan.releasePlatform=plat.charAt(0).toUpperCase()+plat.slice(1).toLowerCase();
        if(ce.platform) plan.releasePlatform=ce.platform;
        if(!plan.releaseVersion) plan.releaseVersion=CANONICAL_VERSION_NAME||'0.0.1';
        if(!plan.versionCode) plan.versionCode=String(CANONICAL_VERSION_CODE||'');
        if(!plan.releaseChannel && ch && ch.value) plan.releaseChannel=ch.value;
        return plan;
    }
    function ensureInstanceOption(instanceId){
        var sel=document.getElementById('jenkinsInstance');
        if(!sel||!instanceId) return Promise.resolve(false);
        for(var i=0;i<sel.options.length;i++){ if(sel.options[i].value===instanceId){ sel.value=instanceId; return Promise.resolve(true); } }
        return fetch('/api/jenkins-manage/instance?instance_id='+encodeURIComponent(instanceId), {credentials:'same-origin'})
            .then(function(r){ return r.json(); })
            .then(function(d){
                var inst=((d||{}).instance)||{};
                if(!inst.id) return false;
                INSTANCE_META[inst.id]={port:inst.port,task_name:(inst.task_name||'').trim()};
                var opt=document.createElement('option');
                opt.value=inst.id;
                opt.textContent=(inst.port||'') + ((inst.task_name&&inst.task_name.trim()) ? ' '+inst.task_name.trim() : '') + ' - ' + (inst.status==='running'?'运行中':'已停止');
                sel.appendChild(opt);
                sel.value=inst.id;
                return true;
            }).catch(function(){ return false; });
    }
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
    function listAvailableUrl(){
        var q='instance_type='+encodeURIComponent(normalizedType(VERSION_MODE));
        if(PREFERRED_INSTANCE_ID){ q+='&include_instance_id='+encodeURIComponent(PREFERRED_INSTANCE_ID); }
        return '/api/jenkins-manage/list-available?'+q;
    }
    function loadJenkinsOptions(){
        return fetch(listAvailableUrl(), {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
            var sel=document.getElementById('jenkinsInstance');
            if(!sel) return;
            while(sel.options.length>1) sel.remove(1);
            (d.instances||[]).forEach(function(i){
                INSTANCE_META[i.id]={port:i.port,task_name:(i.task_name||'').trim()};
                var opt=document.createElement('option');
                opt.value=i.id;
                var label=i.port + ((i.task_name&&i.task_name.trim()) ? ' '+i.task_name.trim() : '') + ' - ' + (i.status==='running'?'运行中':'已停止');
                opt.textContent=label;
                sel.appendChild(opt);
            });
            if(PREFERRED_INSTANCE_ID){
                for(var k=0;k<sel.options.length;k++){
                    if(sel.options[k].value===PREFERRED_INSTANCE_ID){ sel.value=PREFERRED_INSTANCE_ID; break; }
                }
            }
            if(!sel.value){
                var remembered=loadInstanceChoice();
                if(remembered){
                    for(var j=0;j<sel.options.length;j++){
                        if(sel.options[j].value===remembered){ sel.value=remembered; break; }
                    }
                }
            }
        });
    }
    function applyVersionLockParams(){
        if(!VERSION_LOCK_PARAMS) return;
        var lockIds=['APP_NAME','VERSION_NAME','VERSION_CODE','UNITY_VERSION','OUTPUT_BASE_DIR','CHANNEL','GIT_BRANCH'];
        lockIds.forEach(function(id){
            var el=document.getElementById(id);
            if(!el) return;
            if(el.tagName==='SELECT'){ el.disabled=true; }
            else { el.readOnly=true; }
            el.classList.add('bg-slate-100');
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
        var sel=document.getElementById('jenkinsInstance');
        if(yes){
            startBtn.classList.add('hidden');
            stopBtn.classList.remove('hidden');
            if(sel) sel.disabled=true;
        } else{
            startBtn.classList.remove('hidden');
            stopBtn.classList.add('hidden');
            startBtn.disabled=false;
            var t=document.getElementById('btnTriggerText');
            if(t) t.textContent='开始构建';
            if(sel) sel.disabled=false;
            updateJenkinsConsoleLink('', '');
        }
    }
    function updateJenkinsConsoleLink(instanceId, buildNum){
        var row=document.getElementById('jenkinsConsoleRow');
        var link=document.getElementById('jenkinsConsoleLink');
        if(!row||!link) return;
        var id=instanceId||selectedInstanceId();
        if(!id){ row.classList.add('hidden'); return; }
        var m=INSTANCE_META[id]||{};
        var port=m.port;
        if(!port){ row.classList.add('hidden'); return; }
        var url='http://127.0.0.1:'+port+'/job/Android/';
        if(buildNum){ url+=String(buildNum)+'/console'; }
        link.href=url;
        link.textContent=buildNum?('进入 Jenkins 控制台（#'+buildNum+'）'):'进入 Jenkins 控制台';
        row.classList.remove('hidden');
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
        if(!VERSION_ID){ document.getElementById('buildHistory').innerHTML='<li class="text-gray-500 text-sm">无法加载</li>'; return Promise.resolve(); }
        var q='version_id='+encodeURIComponent(VERSION_ID);
        return fetch('/api/build/history-by-version?'+q, {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
            var list=document.getElementById('buildHistory');
            if(!d.builds||!d.builds.length){ list.innerHTML='<li class="text-gray-500 text-sm">本版本暂无构建记录</li>'; return d; }
            list.innerHTML=d.builds.slice(0,12).map(function(b){
                var result=b.result||(b.building?'BUILDING':'');
                var badge='<span class="inline-block px-2 py-0.5 rounded text-xs font-medium '+statusClass(result)+'">'+result+'</span>';
                var iid=(b.instance_id||'').replace(/'/g,'');
                return '<li class="py-1.5 border-b border-gray-100 last:border-0"><a href="#" onclick="loadLog('+b.number+',\\\''+iid+'\\\');return false" class="text-blue-600 hover:underline font-medium">#'+b.number+'</a> '+badge+(iid?'<span class="text-[10px] text-gray-400 ml-1">'+iid.slice(0,8)+'</span>':'')+'</li>';
            }).join('');
            return d;
        });
    }
    function resolveEffectiveBuildNumber(triggeredBuildNumber){
        var triggeredNum = parseInt(triggeredBuildNumber, 10);
        if(!triggeredNum || triggeredNum<=0) return Promise.resolve(triggeredBuildNumber);
        if(!VERSION_ID) return Promise.resolve(triggeredNum);
        var q='version_id='+encodeURIComponent(VERSION_ID);
        return fetch('/api/build/history-by-version?'+q, {credentials:'same-origin'})
            .then(function(r){ return r.json(); })
            .then(function(d){
                var builds=(d&&d.builds)||[];
                if(!builds.length) return triggeredNum;
                var top=builds[0]||{};
                var topNum=parseInt(top.number,10)||0;
                var topBuilding=!!top.building || String(top.result||'').toUpperCase()==='BUILDING';
                // 触发后若 Jenkins 已产生更高编号（或最新正在构建），以最新编号为准
                if(topNum>triggeredNum || (topNum>=triggeredNum && topBuilding)){
                    return topNum;
                }
                return triggeredNum;
            })
            .catch(function(){ return triggeredNum; });
    }
    function loadLog(num, optInstanceId){
        var el=document.getElementById('buildLog');
        var instId=optInstanceId||selectedInstanceId();
        if(!instId){ el.textContent='请先选择 Jenkins 实例'; return; }
        el.textContent='加载中...';
        fetch('/api/build/log/'+num+'?instance_id='+encodeURIComponent(instId), {credentials:'same-origin'}).then(r=>r.text()).then(t=>{ el.textContent=t||'（无日志）'; el.scrollTop=el.scrollHeight; });
    }
    function pollLogAndStatus(buildNum, optInstanceId){
        var el=document.getElementById('buildLog');
        var instId=optInstanceId||selectedInstanceId();
        if(!buildNum||!instId) return;
        function logUrl(){ return '/api/build/log/'+buildNum+'?instance_id='+encodeURIComponent(instId); }
        function statusUrl(){ return '/api/build/'+buildNum+'/status?instance_id='+encodeURIComponent(instId); }
        function fetchLogOnce(cb){
            fetch(logUrl(), {credentials:'same-origin'}).then(r=>r.text()).then(function(t){
                el.textContent=t||'（无日志）';
                el.scrollTop=el.scrollHeight;
                if(cb) cb();
            }).catch(function(){ if(cb) cb(); });
        }
        function tick(){
            fetch(statusUrl(), {credentials:'same-origin'}).then(r=>r.json()).then(function(st){
                var status=(st&&st.status)||'';
                var done=st&&!st.building&&status!=='BUILDING'&&status!=='QUEUED';
                if(done){
                    stopPoll();
                    fetchLogOnce(function(){
                        setBuilding(false);
                        clearActiveBuild();
                        var stEl=document.getElementById('buildStatus');
                        if(stEl){
                            stEl.textContent='构建 #'+buildNum+' 已结束: '+status;
                            stEl.className='mt-3 text-sm min-h-[1.5rem] '+(status==='SUCCESS'?'text-green-600':'text-red-600');
                        }
                        loadHistory();
                    });
                    return;
                }
                fetchLogOnce();
            }).catch(function(){ fetchLogOnce(); });
        }
        tick();
        window._logTimer=setInterval(tick, 2500);
    }
    function stopPoll(){ if(window._logTimer){ clearInterval(window._logTimer); window._logTimer=null; } }
    function resumeVersionBuild(){
        var logEl=document.getElementById('buildLog');
        var active=loadActiveBuild();
        loadHistory().then(function(d){
            var builds=(d&&d.builds)||[];
            var target=null;
            if(active&&active.build_number){
                for(var i=0;i<builds.length;i++){ if(builds[i].number===active.build_number){ target=builds[i]; break; } }
                if(!target){ target={number:active.build_number,instance_id:active.instance_id,building:true,result:''}; }
            }
            if(!target&&builds.length) target=builds[0];
            if(!target||!target.number){
                if(logEl) logEl.textContent='点击左侧「本版本构建历史」中的某次构建可查看日志；开始构建后此处将自动刷新。';
                setBuilding(false);
                return;
            }
            var instId=target.instance_id||(active&&active.instance_id)||'';
            function afterInstanceReady(){
                var resolvedId=instId||selectedInstanceId();
                if(target.building){
                    document.getElementById('btnStop').setAttribute('data-build', target.number);
                    setBuilding(true);
                    updateJenkinsConsoleLink(resolvedId, target.number);
                    var stEl=document.getElementById('buildStatus');
                    if(stEl){ stEl.textContent='构建进行中 #'+target.number; stEl.className='mt-3 text-sm text-amber-600 min-h-[1.5rem]'; }
                    saveActiveBuild(resolvedId, target.number);
                    pollLogAndStatus(target.number, resolvedId);
                }else{
                    setBuilding(false);
                    clearActiveBuild();
                    loadLog(target.number, resolvedId);
                    var stEl2=document.getElementById('buildStatus');
                    if(stEl2&&target.result){
                        stEl2.textContent='最近构建 #'+target.number+': '+target.result;
                        stEl2.className='mt-3 text-sm min-h-[1.5rem] '+(target.result==='SUCCESS'?'text-green-600':'text-gray-600');
                    }
                }
            }
            if(instId){ ensureInstanceOption(instId).then(afterInstanceReady); }
            else{ afterInstanceReady(); }
        });
    }
    function refreshForInstance(){
        var listEl=document.getElementById('buildHistory');
        var logEl=document.getElementById('buildLog');
        if(!listEl||!logEl) return;
        stopPoll();
        persistInstanceChoice();
        if(!selectedInstanceId()){
            listEl.innerHTML='<li class="text-gray-500 text-sm">请选择上方 Jenkins 实例</li>';
            setBuilding(false);
            logEl.textContent='选择 Jenkins 实例后可查看本版本的构建历史与日志';
            resumeVersionBuild();
            return;
        }
        fetch('/api/jenkins-manage/instance?instance_id='+encodeURIComponent(selectedInstanceId()), {credentials:'same-origin'}).then(function(r){ return r.json(); }).then(function(d){
            INSTANCE_COMMERCIAL_DEFAULTS = (((d||{}).instance||{}).build_defaults||{}).commercial_release || {};
            renderCommercialSummary();
        });
        resumeVersionBuild();
    }
    document.getElementById('buildForm').onsubmit=function(e){
        e.preventDefault();
        if(!selectedInstanceId()){
            document.getElementById('buildStatus').textContent='请选择可用 Jenkins 实例（'+modeLabel(VERSION_MODE)+'）';
            document.getElementById('buildStatus').className='mt-3 text-sm text-red-600 min-h-[1.5rem]';
            return false;
        }
        var btn=document.getElementById('btnTrigger');
        var btnText=document.getElementById('btnTriggerText');
        btn.disabled=true; if(btnText) btnText.textContent='提交中...';
        var params={ APP_NAME: (document.getElementById('APP_NAME')||{}).value, VERSION_NAME: (document.getElementById('VERSION_NAME')||{}).value, VERSION_CODE: (document.getElementById('VERSION_CODE')||{}).value, UNITY_VERSION: (document.getElementById('UNITY_VERSION')||{}).value, OUTPUT_BASE_DIR: (document.getElementById('OUTPUT_BASE_DIR')||{}).value, GIT_BRANCH: versionGitBranch(), CHANNEL: (document.getElementById('CHANNEL')||{}).value||'' };
        var url='/admin/build/trigger';
        var body=apiBody(params);
        if(normalizedType(VERSION_MODE)==='commercial'){
            url='/admin/build/commercial-release/trigger';
            var cPlan = buildCommercialPlanFromVersion();
            body={
                instance_id: selectedInstanceId(),
                _project_id: PROJECT_ID,
                _version_id: VERSION_ID,
                UNITY_PROJECT_PATH: cPlan.unityProjectPath || '',
                plan: cPlan
            };
        }
        fetch(url, { method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':getCsrfToken()}, body: JSON.stringify(body), credentials:'same-origin' })
        .then(function(r){ return r.json().then(function(d){ return {ok:r.ok, status:r.status, data:d}; }); })
        .then(function(res){
            var d=res.data||{};
            if(res.ok&&d.success){
                persistInstanceChoice();
                resolveEffectiveBuildNumber(d.build_number).then(function(effectiveBuildNumber){
                    saveActiveBuild(selectedInstanceId(), effectiveBuildNumber);
                    var statusText = '已触发构建 #'+effectiveBuildNumber;
                    if(parseInt(effectiveBuildNumber,10)!==parseInt(d.build_number,10)){
                        statusText += '（已自动对齐 Jenkins 实际构建号）';
                    }
                    document.getElementById('buildStatus').textContent=statusText;
                    document.getElementById('buildStatus').className='mt-3 text-sm text-green-600 min-h-[1.5rem]';
                    document.getElementById('btnStop').setAttribute('data-build', effectiveBuildNumber);
                    setBuilding(true);
                    pollLogAndStatus(effectiveBuildNumber, selectedInstanceId());
                    loadHistory();
                    var el=document.getElementById('buildSuccessLinks');
                    if(el&&PROJECT_ID){ el.innerHTML='<a href="/admin/projects/'+PROJECT_ID+'" class="text-blue-600 hover:underline">返回项目中心</a> <a href="/admin/projects/'+PROJECT_ID+'/versions/'+VERSION_ID+'/workflow" class="text-blue-600 hover:underline">刷新本页</a>'; }
                });
            } else {
                var errMsg=d.error||d.message||('HTTP '+res.status);
                if(res.status===400&&!errMsg) errMsg='请求被拒绝（400）：请确认已选 Jenkins 实例、实例已启动，并刷新页面后重试';
                document.getElementById('buildStatus').textContent='失败: '+errMsg;
                document.getElementById('buildStatus').className='mt-3 text-sm text-red-600 min-h-[1.5rem]';
                btn.disabled=false;
                if(btnText) btnText.textContent=normalizedType(VERSION_MODE)==='commercial'?'执行商业发布':'开始构建';
            }
        }).catch(function(){
            btn.disabled=false;
            if(btnText) btnText.textContent=normalizedType(VERSION_MODE)==='commercial'?'执行商业发布':'开始构建';
        });
        return false;
    };
    document.getElementById('btnStop').onclick=function(){
        var num=this.getAttribute('data-build'); if(!num) return;
        fetch('/api/build/'+num+'/stop', {method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':getCsrfToken()}, body: JSON.stringify(apiBody({})), credentials:'same-origin'})
        .then(r=>r.json())
        .then(function(x){
            if(x && x.success){
                stopPoll();
                clearActiveBuild();
                setBuilding(false);
                var st=document.getElementById('buildStatus');
                if(st){
                    st.textContent='已停止构建 #'+num;
                    st.className='mt-3 text-sm text-amber-600 min-h-[1.5rem]';
                }
                loadHistory();
            }else{
                var stErr=document.getElementById('buildStatus');
                if(stErr){
                    stErr.textContent='停止失败: '+((x&&x.error)||'未知错误');
                    stErr.className='mt-3 text-sm text-red-600 min-h-[1.5rem]';
                }
            }
        })
        .catch(function(){
            var stErr=document.getElementById('buildStatus');
            if(stErr){
                stErr.textContent='停止失败: 网络异常';
                stErr.className='mt-3 text-sm text-red-600 min-h-[1.5rem]';
            }
        });
    };
    applyVersionCanonicalFields();
    applyVersionLockParams();
    renderCommercialSummary();
    var cpZh=document.getElementById('cpLangZh');
    var cpEn=document.getElementById('cpLangEn');
    function _applyCpLangBtn(){
        if(cpZh){ cpZh.className='px-2 py-1 text-[11px] rounded '+(window._cpLang==='zh'?'text-violet-700 bg-violet-100':'text-slate-500'); }
        if(cpEn){ cpEn.className='px-2 py-1 text-[11px] rounded '+(window._cpLang==='en'?'text-violet-700 bg-violet-100':'text-slate-500'); }
    }
    if(cpZh){ cpZh.onclick=function(){ window._cpLang='zh'; _applyCpLangBtn(); renderCommercialSummary(); }; }
    if(cpEn){ cpEn.onclick=function(){ window._cpLang='en'; _applyCpLangBtn(); renderCommercialSummary(); }; }
    _applyCpLangBtn();
    bindPanelState('commercialParamsPanel', 'buildwf:'+PROJECT_ID+':'+VERSION_ID+':commercial_panel', false);
    var btnTextInit=document.getElementById('btnTriggerText');
    if(btnTextInit && normalizedType(VERSION_MODE)==='commercial') btnTextInit.textContent='执行商业发布';
    loadJenkinsOptions().then(function(){ refreshForInstance(); });
    document.getElementById('jenkinsInstance').addEventListener('change', function(){
        if(document.getElementById('jenkinsInstance').disabled) return;
        persistInstanceChoice();
        updateJenkinsConsoleLink(selectedInstanceId(), '');
        refreshForInstance();
    });
    </script>
</body>
</html>
'''


def _version_workflow_page_html():
    """版本构建工作流模板。"""
    return _build_page_html(project_context=True, version_lock_params=True)


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
    """项目内统一构建页：?type=general 通用APK构建 / ?type=commercial 商业级热更发布"""
    from models.data import projects_db, can_view_project
    from flask import session, request
    if project_id not in projects_db:
        from flask import abort
        abort(404)
    if not can_view_project(project_id, session.get('user') or ''):
        from flask import abort
        abort(403)
    build_type = (request.args.get('type') or 'general').strip()
    if build_type not in ('general', 'commercial'):
        build_type = 'general'
    from models.data import project_versions_db
    versions = (project_versions_db.get(project_id) or [])
    if not isinstance(versions, list):
        versions = []
    # 从最新版本取默认值
    default_ver_name, default_ver_code, default_branch = '1.0.0', '100', 'main'
    if versions:
        v = versions[-1]
        params = v.get('jenkins_params') or {}
        default_ver_name = params.get('VERSION_NAME') or v.get('version_name') or default_ver_name
        default_ver_code = params.get('VERSION_CODE') or v.get('version_code') or default_ver_code
        default_branch = params.get('GIT_BRANCH') or default_branch
    return _unified_project_build_html(
        project_id=project_id,
        default_app_name=project_id,
        default_version_name=default_ver_name,
        default_version_code=default_ver_code,
        default_git_branch=default_branch,
        build_type=build_type,
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
    version_mode = (v.get('version_mode') or 'general').strip().lower()
    if version_mode not in ('general', 'commercial'):
        version_mode = 'general'
    preferred_instance_id = (v.get('jenkins_instance_id') or '').strip()
    pipeline = v.get('pipeline') or {}
    apk_build_cfg = (pipeline.get('apk_build') or {}) if isinstance(pipeline, dict) else {}
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
        'platform': (v.get('platform') or 'android'),
    }
    default_app = params_saved.get('APP_NAME') or project_id
    default_ver_name, default_ver_code = _canonical_version_name_code(v)
    if not default_ver_name:
        default_ver_name = '1.0.0'
    if not default_ver_code:
        default_ver_code = '100'
    default_unity = params_saved.get('UNITY_VERSION') or '6000.3.8f1'
    default_git_branch = _resolve_version_git_branch(v)
    if version_mode == 'commercial' and isinstance(apk_build_cfg, dict):
        default_app = (apk_build_cfg.get('app_name') or '').strip() or default_app
        default_unity = (apk_build_cfg.get('unity_version') or '').strip() or default_unity
        default_output = (apk_build_cfg.get('output_base_dir') or '').strip() or default_output
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
        version_mode=version_mode,
        preferred_instance_id=preferred_instance_id,
        version_pipeline=pipeline,
        version_lock_params=True,
        canonical_version_name=default_ver_name,
        canonical_version_code=default_ver_code,
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
    unity_project_path = (data.get('UNITY_PROJECT_PATH') or '').strip()
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
    if unity_project_path:
        params['UNITY_PROJECT_PATH'] = unity_project_path
    # 版本构建上下文：强约束版本模式与 Jenkins 实例类型一致（商业/通用不能混用）
    if project_id and version_id:
        if not instance_id:
            return jsonify({'success': False, 'error': '版本构建必须选择 Jenkins 实例'})
        from models.data import project_versions_db
        versions = (project_versions_db.get(project_id) or [])
        if not isinstance(versions, list):
            versions = []
        version_obj = next((x for x in versions if (x.get('id') or '') == version_id), None)
        if not version_obj:
            return jsonify({'success': False, 'error': '未找到对应版本，无法触发构建'})
        canon_name, canon_code = _canonical_version_name_code(version_obj)
        if canon_name:
            version_name = canon_name
        if canon_code:
            version_code = str(canon_code).strip()
            try:
                version_code = str(int(version_code))
            except (ValueError, TypeError):
                return jsonify({'success': False, 'error': '版本记录 version_code 须为整数'})
        version_mode = (version_obj.get('version_mode') or 'general').strip().lower()
        if version_mode not in ('general', 'commercial'):
            version_mode = 'general'
        inst = jm.get_instance_by_id(instance_id)
        if not inst:
            return jsonify({'success': False, 'error': '所选 Jenkins 实例不存在'})
        instance_type = (inst.get('instance_type') or 'general').strip().lower()
        if instance_type not in ('general', 'commercial'):
            instance_type = 'general'
        if version_mode != instance_type:
            if version_mode == 'commercial':
                return jsonify({'success': False, 'error': '商业级版本仅可使用商业级 Jenkins 实例'})
            return jsonify({'success': False, 'error': '通用级版本仅可使用通用级 Jenkins 实例'})
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
                            canon_name, canon_code = _canonical_version_name_code(ver)
                            saved_params = dict(params)
                            if canon_name:
                                saved_params['VERSION_NAME'] = canon_name
                            if canon_code:
                                saved_params['VERSION_CODE'] = str(canon_code)
                            ver['jenkins_params'] = saved_params
                            if instance_id:
                                ver['jenkins_instance_id'] = instance_id
                            if build_number:
                                ver['last_build_number'] = int(build_number)
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
    builds = []
    for r in records:
        bn = r.get('build_number')
        iid = (r.get('instance_id') or '').strip()
        item = {
            'number': bn,
            'result': '',
            'building': False,
            'instance_id': iid,
        }
        if iid and bn:
            bdir = jm.get_builds_dir_for_instance(instance_id=iid)
            if bdir:
                st = jenkins_svc.get_build_status(bn, builds_dir=bdir)
                item['building'] = bool(st.get('building'))
                status = (st.get('status') or '').strip()
                if not item['building'] and status not in ('BUILDING', 'QUEUED', 'UNKNOWN', ''):
                    item['result'] = status
        builds.append(item)
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
    resp.headers['Content-Type'] = 'text/plain; charset=utf-8'
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


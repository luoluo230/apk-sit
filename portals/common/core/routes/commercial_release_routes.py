# -*- coding: utf-8 -*-
"""商业级热更构建与发布工作台 — 独立页面"""

import os
import json as json_module
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template_string, session

from config import Config, DATA_DIR
from models.data import log_audit, projects_db, resolve_project_id
from services.authz import admin_required_any, has_scope
from services import jenkins_manager as jm
from services import jenkins as jenkins_svc
from services.commercial_release_plan import (
    normalize_release_environment,
    normalize_release_channel,
    normalize_step3_targets,
    plan_to_jenkins_params,
)

try:
    from flask_wtf.csrf import generate_csrf
except ImportError:
    generate_csrf = lambda: ''

bp = Blueprint('commercial_release_routes', __name__, url_prefix='')

RELEASE_PLANS_DIR = os.path.join(DATA_DIR, 'release_plans')
os.makedirs(RELEASE_PLANS_DIR, exist_ok=True)


def _admin_layout(content, title, back_href='/admin'):
    """复用 admin 布局"""
    username = session.get("user") or ""
    csrf_token = generate_csrf()
    import html
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{html.escape(csrf_token)}">
    <title>{title} - APK 下载中心</title>
    <link rel="stylesheet" href="/static/tailwind.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        .admin-nav {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 40%, #4f46e5 100%); }}
        .cr-card {{ transition: all 0.2s ease; }}
        .cr-card:hover {{ box-shadow: 0 8px 30px -15px rgba(15,23,42,0.25); }}
        .cr-input:focus {{ outline: none; border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.15); }}
        .cr-select:focus {{ outline: none; border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.15); }}
        .btn-primary {{ background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); }}
        .btn-primary:hover {{ background: linear-gradient(135deg, #4338ca 0%, #6d28d9 100%); }}
        .chip {{ display: inline-flex; align-items: center; padding: 4px 12px; border-radius: 20px; font-size: 13px; cursor: pointer; transition: all 0.15s; user-select: none; }}
        .chip-off {{ background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }}
        .chip-on {{ border: 1px solid transparent; }}
        .chip-code-on {{ background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); color: white; }}
        .chip-config-on {{ background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; }}
        .chip-resource-on {{ background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; }}
        .pulse-dot {{ width: 8px; height: 8px; border-radius: 50%; background: #10b981; animation: pulse 1.5s infinite; }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} }}
    </style>
</head>
<body class="bg-slate-50 min-h-screen text-slate-800 antialiased">
    <div class="min-h-screen flex flex-col">
        <header class="admin-nav shadow-lg">
            <div class="max-w-7xl mx-auto px-4">
                <div class="flex items-center justify-between h-14 md:h-16">
                    <div class="flex items-center gap-3">
                        <span class="flex items-center justify-center w-9 h-9 rounded-xl bg-white/10 text-white">
                            <i class="fas fa-rocket text-lg"></i>
                        </span>
                        <div>
                            <h1 class="text-lg md:text-xl font-semibold text-white tracking-tight">{title}</h1>
                            <p class="hidden md:block text-[11px] text-slate-200/80">商业级热更构建、发布、激活与回滚工作台</p>
                        </div>
                    </div>
                    <div class="flex items-center gap-2">
                        <div class="hidden md:flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-xs text-slate-100">
                            <i class="fas fa-user-circle text-slate-200"></i>
                            <span class="font-semibold">{html.escape(username or '未登录')}</span>
                        </div>
                        <a href="/admin" class="hidden sm:inline-flex items-center gap-1.5 text-xs font-medium text-slate-100 hover:text-white hover:underline">
                            <i class="fas fa-arrow-left"></i><span>返回管理中心</span>
                        </a>
                    </div>
                </div>
            </div>
        </header>
        <main class="flex-1">
            <div class="max-w-7xl mx-auto px-4 py-6">
                {content}
            </div>
        </main>
    </div>
</body>
</html>'''


# ============ 页面主体模板 ============

COMMERCIAL_RELEASE_PAGE = '''<meta name="csrf-token" content="">
<div class="mb-6">
    <div class="flex items-center justify-between flex-wrap gap-3">
        <div>
            <h2 class="text-xl font-bold text-slate-800 flex items-center gap-2">
                <i class="fas fa-rocket text-indigo-600"></i> 商业级热更构建与发布
            </h2>
            <p class="text-sm text-slate-500 mt-1">一个工作台覆盖计划、构建、上传、激活与回滚。参数驱动，无需打开 Unity 编辑器。</p>
        </div>
        <div class="flex items-center gap-2">
            <a href="/admin/build" class="px-3 py-1.5 text-xs rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50">
                <i class="fas fa-cogs mr-1"></i> 传统 APK 构建
            </a>
        </div>
    </div>
</div>

<div class="grid grid-cols-1 xl:grid-cols-3 gap-6">
    <!-- ====== 左栏：构建参数 (2 col space) ====== -->
    <div class="xl:col-span-2 space-y-5">

        <!-- 区域1: Jenkins实例 + 项目 -->
        <div class="bg-white rounded-2xl border border-slate-200 p-5 cr-card">
            <h3 class="text-sm font-semibold text-slate-700 mb-4 flex items-center gap-2">
                <span class="flex items-center justify-center w-6 h-6 rounded-lg bg-indigo-100 text-indigo-600 text-xs font-bold">1</span>
                构建环境
            </h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                    <label class="block text-xs font-medium text-slate-500 mb-1.5">Jenkins 实例</label>
                    <select id="jenkinsInstance" class="cr-select w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm bg-white">
                        <option value="">选择运行中的实例...</option>
                    </select>
                    <p class="text-[11px] text-slate-400 mt-1">在「Jenkins 管理」中创建和维护实例</p>
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-500 mb-1.5">目标项目</label>
                    <select id="targetProject" class="cr-select w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm bg-white">
                        <option value="">选择项目...</option>
                    </select>
                </div>
            </div>
        </div>

        <!-- 区域2: 核心发布参数 -->
        <div class="bg-white rounded-2xl border border-slate-200 p-5 cr-card">
            <h3 class="text-sm font-semibold text-slate-700 mb-4 flex items-center gap-2">
                <span class="flex items-center justify-center w-6 h-6 rounded-lg bg-violet-100 text-violet-600 text-xs font-bold">2</span>
                发布计划
            </h3>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div>
                    <label class="block text-xs font-medium text-slate-500 mb-1.5">
                        <i class="fas fa-tag text-indigo-400 mr-1"></i> 版本号
                    </label>
                    <input type="text" id="releaseVersion" class="cr-input w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm"
                           placeholder="例如 0.0.12" value="0.0.1">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-500 mb-1.5">
                        <i class="fas fa-globe text-violet-400 mr-1"></i> 环境
                    </label>
                    <select id="releaseEnvironment" class="cr-select w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm bg-white">
                        <option value="Development">Development</option>
                        <option value="Testing">Testing</option>
                        <option value="Staging">Staging</option>
                        <option value="Production">Production</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-500 mb-1.5">
                        <i class="fas fa-share-alt text-amber-400 mr-1"></i> 渠道
                    </label>
                    <select id="releaseChannel" class="cr-select w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm bg-white">
                        <option value="wechat">wechat</option>
                        <option value="common">common</option>
                        <option value="official">official</option>
                        <option value="tap">tap</option>
                        <option value="bilibili">bilibili</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-500 mb-1.5">
                        <i class="fas fa-mobile-alt text-emerald-400 mr-1"></i> 平台
                    </label>
                    <select id="releasePlatform" class="cr-select w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm bg-white">
                        <option value="Android">Android</option>
                        <option value="iOS">iOS</option>
                        <option value="Windows">Windows</option>
                    </select>
                </div>
            </div>

            <!-- 发布对象 Chips -->
            <div class="mb-4">
                <label class="block text-xs font-medium text-slate-500 mb-2">发布对象</label>
                <div class="flex flex-wrap gap-2">
                    <span class="chip chip-code-on" id="chipCode" onclick="toggleTarget('code')">
                        <i class="fas fa-code mr-1.5 text-[11px]"></i> 代码包
                    </span>
                    <span class="chip chip-config-on" id="chipConfig" onclick="toggleConfigStep1()">
                        <i class="fas fa-sliders-h mr-1.5 text-[11px]"></i> Step1 配置导表
                    </span>
                    <span class="chip chip-resource-on" id="chipResource" onclick="toggleTarget('resource')">
                        <i class="fas fa-cube mr-1.5 text-[11px]"></i> 资源包
                    </span>
                </div>
                <p class="text-[11px] text-slate-400 mt-1.5">代码包(DLL/AOT/Script)、配置包(逻辑表/灰度/实验)、资源包(ABundle/高清/可选)</p>
            </div>

            <!-- 热更标签 -->
            <div>
                <label class="block text-xs font-medium text-slate-500 mb-1.5">
                    <i class="fas fa-tags text-rose-400 mr-1"></i> 热更标签
                </label>
                <input type="text" id="hotUpdateLabels" class="cr-input w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm"
                       placeholder="多个标签用逗号分隔，例如 hotupdate,aotmeta" value="hotupdate,aotmeta">
            </div>
        </div>

        <!-- 区域3: 构建策略 (折叠) -->
        <details class="bg-white rounded-2xl border border-slate-200 cr-card" id="detailsStrategy" open>
            <summary class="p-5 cursor-pointer text-sm font-semibold text-slate-700 flex items-center gap-2 select-none">
                <span class="flex items-center justify-center w-6 h-6 rounded-lg bg-emerald-100 text-emerald-600 text-xs font-bold">3</span>
                构建策略
                <span class="text-[11px] text-slate-400 font-normal ml-2">压缩 / 加密 / 签名</span>
            </summary>
            <div class="px-5 pb-5 space-y-4 border-t border-slate-100 pt-4">
                <!-- 三个策略tab -->
                <div class="flex gap-1 bg-slate-100 rounded-xl p-1" id="strategyTabs">
                    <button class="flex-1 py-2 px-3 rounded-lg text-sm font-medium transition bg-white text-slate-700 shadow-sm" data-tab="code" onclick="switchStrategyTab('code')">
                        <i class="fas fa-code text-blue-500 mr-1"></i> 代码包
                    </button>
                    <button class="flex-1 py-2 px-3 rounded-lg text-sm font-medium transition text-slate-500" data-tab="config" onclick="switchStrategyTab('config')">
                        <i class="fas fa-sliders-h text-amber-500 mr-1"></i> 配置包
                    </button>
                    <button class="flex-1 py-2 px-3 rounded-lg text-sm font-medium transition text-slate-500" data-tab="resource" onclick="switchStrategyTab('resource')">
                        <i class="fas fa-cube text-emerald-500 mr-1"></i> 资源包
                    </button>
                </div>

                <!-- 代码包面板 -->
                <div id="panelCode" class="strategy-panel space-y-3">
                    <div class="grid grid-cols-3 gap-3">
                        <div class="col-span-3">
                            <label class="flex items-center gap-2 text-sm">
                                <input type="checkbox" id="codeEnabled" checked class="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500">
                                启用代码包构建
                            </label>
                        </div>
                        <div>
                            <label class="block text-xs text-slate-500 mb-1">压缩方式</label>
                            <select id="codeCompression" class="cr-select w-full border border-slate-200 rounded-lg px-2.5 py-2 text-sm bg-white">
                                <option value="Zip">Zip</option>
                                <option value="None">不压缩</option>
                                <option value="Lz4">LZ4</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs text-slate-500 mb-1">加密方式</label>
                            <select id="codeEncryption" class="cr-select w-full border border-slate-200 rounded-lg px-2.5 py-2 text-sm bg-white">
                                <option value="Aes">AES</option>
                                <option value="None">不加密</option>
                                <option value="Xor">XOR</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs text-slate-500 mb-1">签名</label>
                            <select id="codeSignature" class="cr-select w-full border border-slate-200 rounded-lg px-2.5 py-2 text-sm bg-white">
                                <option value="builtin-signature">启用</option>
                                <option value="">关闭</option>
                            </select>
                        </div>
                    </div>
                    <div>
                        <label class="block text-xs text-slate-500 mb-1">包单元</label>
                        <input type="text" id="codeUnits" class="cr-input w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                               value="aotmeta, hotupdate, scriptpatch, symbols"
                               placeholder="逗号分隔">
                    </div>
                </div>

                <!-- 配置包面板 -->
                <div id="panelConfig" class="strategy-panel space-y-3 hidden">
                    <div class="grid grid-cols-3 gap-3">
                        <div class="col-span-3">
                            <label class="flex items-center gap-2 text-sm">
                                <input type="checkbox" id="configEnabled" checked class="rounded border-slate-300 text-amber-500 focus:ring-amber-500">
                                启用配置包构建
                            </label>
                        </div>
                        <div>
                            <label class="block text-xs text-slate-500 mb-1">压缩方式</label>
                            <select id="configCompression" class="cr-select w-full border border-slate-200 rounded-lg px-2.5 py-2 text-sm bg-white">
                                <option value="Zip">Zip</option>
                                <option value="None">不压缩</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs text-slate-500 mb-1">加密方式</label>
                            <select id="configEncryption" class="cr-select w-full border border-slate-200 rounded-lg px-2.5 py-2 text-sm bg-white">
                                <option value="Aes">AES</option>
                                <option value="None">不加密</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs text-slate-500 mb-1">签名</label>
                            <select id="configSignature" class="cr-select w-full border border-slate-200 rounded-lg px-2.5 py-2 text-sm bg-white">
                                <option value="builtin-signature">启用</option>
                                <option value="">关闭</option>
                            </select>
                        </div>
                    </div>
                    <div>
                        <label class="block text-xs text-slate-500 mb-1">包单元</label>
                        <input type="text" id="configUnits" class="cr-input w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                               value="base, liveops, gray, localization, experiment, logic"
                               placeholder="逗号分隔">
                    </div>
                </div>

                <!-- 资源包面板 -->
                <div id="panelResource" class="strategy-panel space-y-3 hidden">
                    <div class="grid grid-cols-3 gap-3">
                        <div class="col-span-3">
                            <label class="flex items-center gap-2 text-sm">
                                <input type="checkbox" id="resourceEnabled" checked class="rounded border-slate-300 text-emerald-500 focus:ring-emerald-500">
                                启用资源包构建
                            </label>
                        </div>
                        <div>
                            <label class="block text-xs text-slate-500 mb-1">压缩方式</label>
                            <select id="resourceCompression" class="cr-select w-full border border-slate-200 rounded-lg px-2.5 py-2 text-sm bg-white">
                                <option value="None">不压缩</option>
                                <option value="Zip">Zip</option>
                                <option value="Lz4">LZ4</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs text-slate-500 mb-1">加密方式</label>
                            <select id="resourceEncryption" class="cr-select w-full border border-slate-200 rounded-lg px-2.5 py-2 text-sm bg-white">
                                <option value="None">不加密</option>
                                <option value="Aes">AES</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs text-slate-500 mb-1">签名</label>
                            <select id="resourceSignature" class="cr-select w-full border border-slate-200 rounded-lg px-2.5 py-2 text-sm bg-white">
                                <option value="builtin-signature">启用</option>
                                <option value="">关闭</option>
                            </select>
                        </div>
                    </div>
                    <div>
                        <label class="block text-xs text-slate-500 mb-1">包单元</label>
                        <input type="text" id="resourceUnits" class="cr-input w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                               value="addressable, hotupdate, optional, platform, hd, streaming"
                               placeholder="逗号分隔">
                    </div>
                </div>
            </div>
        </details>

        <!-- 区域4: 发布操作 -->
        <div class="bg-white rounded-2xl border border-slate-200 p-5 cr-card">
            <h3 class="text-sm font-semibold text-slate-700 mb-4 flex items-center gap-2">
                <span class="flex items-center justify-center w-6 h-6 rounded-lg bg-rose-100 text-rose-600 text-xs font-bold">4</span>
                发布操作
            </h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                    <label class="block text-xs font-medium text-slate-500 mb-1.5">发布模式</label>
                    <select id="releaseMode" class="cr-select w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm bg-white">
                        <option value="build-upload">构建并上传</option>
                        <option value="build">仅构建</option>
                        <option value="upload">仅上传</option>
                        <option value="activate">激活版本</option>
                        <option value="rollback">回滚版本</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-500 mb-1.5">上传模式</label>
                    <select id="uploadMode" class="cr-select w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm bg-white">
                        <option value="incremental">增量上传</option>
                        <option value="full">全量上传</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-500 mb-1.5">激活后自动发布</label>
                    <select id="activateAfterUpload" class="cr-select w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm bg-white">
                        <option value="true">是</option>
                        <option value="false">否</option>
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-500 mb-1.5">回滚目标版本</label>
                    <input type="text" id="rollbackTarget" class="cr-input w-full border border-slate-200 rounded-xl px-3 py-2.5 text-sm"
                           placeholder="仅回滚模式需要" disabled>
                </div>
            </div>

            <!-- 高级选项 -->
            <details class="mt-3">
                <summary class="cursor-pointer text-xs text-slate-500 hover:text-slate-700">高级选项</summary>
                <div class="mt-3 grid grid-cols-3 gap-3 bg-slate-50 rounded-xl p-3">
                    <div>
                        <label class="block text-xs text-slate-500 mb-1">压缩覆盖</label>
                        <select id="compressionOverride" class="cr-select w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm bg-white">
                            <option value="">默认</option>
                            <option value="Zip">Zip</option>
                            <option value="Lz4">LZ4</option>
                            <option value="None">无</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs text-slate-500 mb-1">加密覆盖</label>
                        <select id="encryptionOverride" class="cr-select w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm bg-white">
                            <option value="">默认</option>
                            <option value="Aes">AES</option>
                            <option value="Xor">XOR</option>
                            <option value="None">无</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs text-slate-500 mb-1">签名覆盖</label>
                        <select id="signatureOverride" class="cr-select w-full border border-slate-200 rounded-lg px-2 py-1.5 text-sm bg-white">
                            <option value="">默认</option>
                            <option value="builtin-signature">启用</option>
                        </select>
                    </div>
                </div>
            </details>

            <!-- 执行按钮 -->
            <div class="mt-5 flex items-center gap-3">
                <button type="button" id="btnExecute" onclick="executeRelease()"
                        class="btn-primary px-6 py-3 rounded-xl text-white font-semibold text-sm flex items-center gap-2 shadow-lg shadow-indigo-200 transition disabled:opacity-50 disabled:cursor-not-allowed">
                    <i class="fas fa-rocket"></i>
                    <span id="btnExecuteText">执行发布</span>
                </button>
                <button type="button" id="btnStop" onclick="stopRelease()"
                        class="px-5 py-3 rounded-xl border border-red-200 bg-red-50 text-red-600 font-semibold text-sm hidden items-center gap-2 hover:bg-red-100">
                    <i class="fas fa-stop-circle"></i> 停止
                </button>
                <span id="releaseStatus" class="text-sm text-slate-500"></span>
            </div>
        </div>
    </div>

    <!-- ====== 右栏：状态与历史 ====== -->
    <div class="space-y-5">
        <!-- 实例信息卡片 -->
        <div class="bg-white rounded-2xl border border-slate-200 p-5 cr-card">
            <h3 class="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                <i class="fas fa-server text-slate-400"></i> 实例状态
            </h3>
            <div id="instanceInfo" class="text-sm text-slate-500">
                <p class="text-[13px]"><i class="fas fa-info-circle mr-1"></i> 请先选择 Jenkins 实例</p>
            </div>
        </div>

        <!-- 计划预览卡片 -->
        <div class="bg-white rounded-2xl border border-slate-200 p-5 cr-card">
            <h3 class="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                <i class="fas fa-file-code text-slate-400"></i> 发布计划预览
                <button onclick="previewPlan()" class="ml-auto text-[11px] text-indigo-500 hover:text-indigo-700 font-normal">
                    <i class="fas fa-sync-alt mr-1"></i> 刷新
                </button>
            </h3>
            <pre id="planPreview" class="bg-slate-900 text-green-400 text-xs p-3 rounded-xl overflow-auto max-h-64 font-mono">点击刷新生成计划预览...</pre>
        </div>

        <!-- 构建历史 -->
        <div class="bg-white rounded-2xl border border-slate-200 p-5 cr-card">
            <h3 class="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
                <i class="fas fa-history text-slate-400"></i> 最近发布
            </h3>
            <ul id="releaseHistory" class="space-y-2 text-sm text-slate-600">
                <li class="text-[13px] text-slate-400">选择 Jenkins 实例后加载...</li>
            </ul>
        </div>
    </div>
</div>

<!-- 构建日志 (全宽) -->
<div class="mt-6 bg-white rounded-2xl border border-slate-200 p-5 cr-card">
    <h3 class="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
        <i class="fas fa-terminal text-slate-400"></i> 构建日志
        <span id="buildNumberBadge" class="hidden px-2 py-0.5 rounded-full text-[11px] bg-indigo-100 text-indigo-600 font-medium">#-</span>
    </h3>
    <pre id="buildLog" class="bg-slate-900 text-green-400 p-4 rounded-xl overflow-auto text-xs font-mono h-[360px] border border-slate-700"
         style="white-space: pre-wrap; word-break: break-all;">选择 Jenkins 实例后，可从构建历史查看日志。开始构建后此处将自动刷新。</pre>
</div>

<script>
// ======= 状态管理 =======
var _selectedTargets = { code: true, resource: true };
var _configStep1Enabled = true;
var _currentStrategyTab = 'code';
var _buildNumber = null;
var _pollTimer = null;

// ======= 初始化 =======
function init() {
    loadJenkinsInstances();
    loadProjects();
    document.getElementById('releaseMode').addEventListener('change', onModeChange);
    previewPlan();
}
setTimeout(init, 50);

// ======= 加载 Jenkins 实例 =======
function loadJenkinsInstances() {
    fetch('/api/jenkins-manage/list', {credentials:'same-origin'})
        .then(r => r.json())
        .then(d => {
            var sel = document.getElementById('jenkinsInstance');
            while(sel.options.length > 1) sel.remove(1);
            (d.instances || []).forEach(function(i) {
                var opt = document.createElement('option');
                opt.value = i.id;
                var label = i.port + ((i.task_name && i.task_name.trim()) ? ' ' + i.task_name : '');
                opt.textContent = label + ' — ' + (i.status === 'running' ? '运行中' : '已停止');
                opt.disabled = i.status !== 'running';
                sel.appendChild(opt);
            });
            updateInstanceInfo();
            loadReleaseHistory();
        });
}

// ======= 加载项目列表 =======
function loadProjects() {
    fetch('/api/projects', {credentials:'same-origin'})
        .then(r => r.json())
        .then(d => {
            var sel = document.getElementById('targetProject');
            (d.projects || []).forEach(function(p) {
                var o = document.createElement('option');
                o.value = p.id || p.name;
                o.textContent = p.name || p.id;
                sel.appendChild(o);
            });
        }).catch(function(){});
}

// ======= 实例信息更新 =======
function updateInstanceInfo() {
    var id = selectedInstanceId();
    if (!id) return;
    fetch('/api/jenkins-manage/instance?instance_id=' + id, {credentials:'same-origin'})
        .then(r => r.json())
        .then(d => {
            if (!d.success || !d.instance) return;
            var inst = d.instance;
            var html = '';
            html += '<div class="space-y-2 text-[13px]">';
            html += '<div class="flex justify-between"><span class="text-slate-400">端口</span><span class="font-medium">' + inst.port + '</span></div>';
            html += '<div class="flex justify-between"><span class="text-slate-400">任务名</span><span class="font-medium">' + (inst.task_name || '-') + '</span></div>';
            html += '<div class="flex justify-between"><span class="text-slate-400">状态</span><span class="flex items-center gap-1.5">' + (inst.status === 'running' ? '<span class="pulse-dot"></span>运行中' : '已停止') + '</span></div>';
            html += '</div>';
            document.getElementById('instanceInfo').innerHTML = html;
        });
}
document.getElementById('jenkinsInstance').addEventListener('change', function() {
    updateInstanceInfo();
    loadReleaseHistory();
});

// ======= 发布目标 Chip 切换（Step3: code/resource；config 仅 Step1） =======
function toggleTarget(kind) {
    _selectedTargets[kind] = !_selectedTargets[kind];
    updateChipUI(kind);
    previewPlan();
}

function toggleConfigStep1() {
    _configStep1Enabled = !_configStep1Enabled;
    var cb = document.getElementById('configEnabled');
    if (cb) cb.checked = _configStep1Enabled;
    updateChipUI('config');
    previewPlan();
}

function updateChipUI(kind) {
    var el = document.getElementById('chip' + kind.charAt(0).toUpperCase() + kind.slice(1));
    if (!el) return;
    var on = (kind === 'config') ? _configStep1Enabled : !!_selectedTargets[kind];
    el.className = 'chip ' + (on ? 'chip-' + kind + '-on' : 'chip-off');
}

// ======= 策略Tab切换 =======
function switchStrategyTab(tab) {
    _currentStrategyTab = tab;
    // 更新 tab 样式
    document.querySelectorAll('#strategyTabs button').forEach(function(btn) {
        var isActive = btn.getAttribute('data-tab') === tab;
        btn.className = 'flex-1 py-2 px-3 rounded-lg text-sm font-medium transition ' + (isActive ? 'bg-white text-slate-700 shadow-sm' : 'text-slate-500');
    });
    // 显示/隐藏面板
    document.querySelectorAll('.strategy-panel').forEach(function(p) { p.classList.add('hidden'); });
    var panel = document.getElementById('panel' + tab.charAt(0).toUpperCase() + tab.slice(1));
    if (panel) panel.classList.remove('hidden');
}

// ======= 模式切换 =======
function onModeChange() {
    var m = document.getElementById('releaseMode').value;
    var rb = document.getElementById('rollbackTarget');
    var um = document.getElementById('uploadMode');
    var aa = document.getElementById('activateAfterUpload');
    if (m === 'rollback') {
        rb.disabled = false;
        um.disabled = true;
        aa.disabled = true;
    } else if (m === 'activate') {
        rb.disabled = true;
        um.disabled = true;
        aa.disabled = true;
    } else {
        rb.disabled = true;
        um.disabled = false;
        aa.disabled = false;
    }
}

// ======= 收集所有参数 =======
function collectParams() {
    var plan = {
        releaseMode: document.getElementById('releaseMode').value,
        releaseVersion: document.getElementById('releaseVersion').value.trim(),
        releaseEnvironment: document.getElementById('releaseEnvironment').value,
        releaseChannel: document.getElementById('releaseChannel').value,
        releasePlatform: document.getElementById('releasePlatform').value,
        releaseHotLabels: document.getElementById('hotUpdateLabels').value.trim(),
        releaseUpload: document.getElementById('releaseMode').value !== 'build',
        releaseActivate: document.getElementById('activateAfterUpload').value === 'true',
        releaseUploadMode: document.getElementById('uploadMode').value,
        releaseRollbackTarget: document.getElementById('rollbackTarget').value.trim(),
        releaseTargets: Object.keys(_selectedTargets).filter(function(k) { return _selectedTargets[k]; }).join(','),
        configEnabled: _configStep1Enabled,
        hotReleaseEnabled: document.getElementById('resourceEnabled').checked || _selectedTargets.code || _selectedTargets.resource,
        targetProject: document.getElementById('targetProject').value,
        // 高级选项
        releaseCompressionOverride: document.getElementById('compressionOverride').value,
        releaseEncryptionOverride: document.getElementById('encryptionOverride').value,
        releaseSignatureOverride: document.getElementById('signatureOverride').value,
        // 三类包策略
        codeEnabled: document.getElementById('codeEnabled').checked,
        codeCompression: document.getElementById('codeCompression').value,
        codeEncryption: document.getElementById('codeEncryption').value,
        codeSignature: document.getElementById('codeSignature').value,
        codeUnits: document.getElementById('codeUnits').value.trim(),
        configCompression: document.getElementById('configCompression').value,
        configEncryption: document.getElementById('configEncryption').value,
        configSignature: document.getElementById('configSignature').value,
        configUnits: document.getElementById('configUnits').value.trim(),
        resourceEnabled: document.getElementById('resourceEnabled').checked,
        resourceCompression: document.getElementById('resourceCompression').value,
        resourceEncryption: document.getElementById('resourceEncryption').value,
        resourceSignature: document.getElementById('resourceSignature').value,
        resourceUnits: document.getElementById('resourceUnits').value.trim()
    };
    return plan;
}

// ======= 计划预览 =======
function previewPlan() {
    var plan = collectParams();
    var el = document.getElementById('planPreview');
    el.textContent = JSON.stringify(plan, null, 2);
}

// ======= 执行发布 =======
function executeRelease() {
    var id = selectedInstanceId();
    if (!id) { alert('请先选择运行中的 Jenkins 实例'); return; }

    var plan = collectParams();
    if (!plan.releaseVersion) { alert('请输入版本号'); return; }
    var mode = plan.releaseMode || 'build-upload';
    if (mode !== 'activate' && mode !== 'rollback') {
        if (!plan.releaseTargets) { alert('请至少选择代码包或资源包（Step3）'); return; }
    }

    var btn = document.getElementById('btnExecute');
    var btnText = document.getElementById('btnExecuteText');
    btn.disabled = true;
    btnText.textContent = '提交中...';
    document.getElementById('releaseStatus').textContent = '正在提交发布计划...';
    document.getElementById('releaseStatus').className = 'text-sm text-indigo-600';

    var body = { instance_id: id, plan: plan };
    fetch('/admin/build/commercial-release/trigger', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken()},
        body: JSON.stringify(body),
        credentials: 'same-origin'
    })
    .then(r => r.json())
    .then(d => {
        if (d.success) {
            document.getElementById('releaseStatus').textContent = '已触发构建 #' + d.build_number;
            document.getElementById('releaseStatus').className = 'text-sm text-green-600';
            _buildNumber = d.build_number;
            var badge = document.getElementById('buildNumberBadge');
            badge.textContent = '#' + d.build_number;
            badge.classList.remove('hidden');
            setBuilding(true);
            pollLogAndStatus();
            loadReleaseHistory();
        } else {
            document.getElementById('releaseStatus').textContent = '失败: ' + (d.error || '未知错误');
            document.getElementById('releaseStatus').className = 'text-sm text-red-600';
            btn.disabled = false;
            btnText.textContent = '执行发布';
        }
    }).catch(function() {
        document.getElementById('releaseStatus').textContent = '网络错误';
        document.getElementById('releaseStatus').className = 'text-sm text-red-600';
        btn.disabled = false;
        btnText.textContent = '执行发布';
    });
}

// ======= 停止发布 =======
function stopRelease() {
    if (!_buildNumber) return;
    var id = selectedInstanceId();
    fetch('/api/build/' + _buildNumber + '/stop', {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken()},
        body: JSON.stringify({instance_id: id}),
        credentials: 'same-origin'
    }).then(r => r.json())
    .then(function(x) {
        document.getElementById('releaseStatus').textContent = x.success ? '已请求停止' : (x.error || '');
        document.getElementById('releaseStatus').className = 'text-sm text-gray-500';
    });
}

// ======= 构建状态轮询 =======
function pollLogAndStatus() {
    if (_pollTimer) clearInterval(_pollTimer);
    var missCount = 0;
    function tick() {
        var id = selectedInstanceId();
        fetch('/api/jenkins/status?instance_id=' + id, {credentials:'same-origin'})
        .then(r => r.json())
        .then(function(st) {
            var done = false;
            var matched = false;
            if (st.ok && st.recent) {
                for (var i = 0; i < st.recent.length; i++) {
                    if (st.recent[i].number === _buildNumber) {
                        matched = true;
                        if (st.recent[i].result) {
                            done = true;
                        }
                        break;
                    }
                }
            }
            missCount = matched ? 0 : (missCount + 1);
            if (done) {
                stopPoll();
                setBuilding(false);
                loadReleaseHistory();
                updateBuildLog();
                document.getElementById('releaseStatus').textContent = '构建完成';
                document.getElementById('releaseStatus').className = 'text-sm text-green-600';
                return;
            }
            // 连续多次在 Jenkins 最近构建中找不到该构建号，判定为旧状态串号并自动清理。
            if (missCount >= 4) {
                stopPoll();
                _buildNumber = null;
                setBuilding(false);
                var badge = document.getElementById('buildNumberBadge');
                if (badge) badge.classList.add('hidden');
                document.getElementById('releaseStatus').textContent = '未检测到对应构建号，已清理旧状态';
                document.getElementById('releaseStatus').className = 'text-sm text-slate-500';
                return;
            }
            updateBuildLog();
        });
    }
    tick();
    _pollTimer = setInterval(tick, 3000);
}

function updateBuildLog() {
    if (!_buildNumber) return;
    var id = selectedInstanceId();
    fetch('/api/build/log/' + _buildNumber + '?instance_id=' + id, {credentials:'same-origin'})
        .then(r => r.text())
        .then(function(t) {
            var el = document.getElementById('buildLog');
            if (t && t.trim()) {
                el.textContent = t;
                el.scrollTop = el.scrollHeight;
            }
        });
}

function stopPoll() {
    if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}

// ======= 构建状态UI =======
function setBuilding(yes) {
    var startBtn = document.getElementById('btnExecute');
    var stopBtn = document.getElementById('btnStop');
    if (yes) {
        startBtn.classList.add('hidden');
        stopBtn.classList.remove('hidden');
        stopBtn.style.display = 'flex';
    } else {
        startBtn.classList.remove('hidden');
        stopBtn.classList.add('hidden');
        stopBtn.style.display = 'none';
        startBtn.disabled = false;
        document.getElementById('btnExecuteText').textContent = '执行发布';
    }
}

// ======= 发布历史 =======
function loadReleaseHistory() {
    var id = selectedInstanceId();
    if (!id) { document.getElementById('releaseHistory').innerHTML = '<li class="text-[13px] text-slate-400">请先选择运行中的 Jenkins 实例</li>'; return; }
    var el = document.getElementById('releaseHistory');
    el.innerHTML = '<li class="text-[13px] text-slate-400"><i class="fas fa-spinner fa-spin mr-1"></i>加载中...</li>';
    
    fetch('/api/jenkins/status?instance_id=' + id, {credentials:'same-origin'})
    .then(r => r.json())
    .then(d => {
        if (!d.ok || !d.recent || !d.recent.length) {
            el.innerHTML = '<li class="text-[13px] text-slate-400">暂无构建记录</li>';
            if (_buildNumber) {
                _buildNumber = null;
                stopPoll();
                setBuilding(false);
                var badge0 = document.getElementById('buildNumberBadge');
                if (badge0) badge0.classList.add('hidden');
            }
            return;
        }
        if (_buildNumber) {
            var exists = false;
            for (var j = 0; j < d.recent.length; j++) {
                if (d.recent[j].number === _buildNumber) { exists = true; break; }
            }
            if (!exists) {
                _buildNumber = null;
                stopPoll();
                setBuilding(false);
                var badge1 = document.getElementById('buildNumberBadge');
                if (badge1) badge1.classList.add('hidden');
                document.getElementById('releaseStatus').textContent = '未检测到对应构建号，已清理旧状态';
                document.getElementById('releaseStatus').className = 'text-sm text-slate-500';
            }
        }
        el.innerHTML = d.recent.slice(0, 8).map(function(b) {
            var r = b.result || '进行中';
            var color = r === 'SUCCESS' ? 'text-green-600' : r === 'FAILURE' ? 'text-red-600' : r === 'ABORTED' ? 'text-yellow-600' : 'text-slate-400';
            var isBuilding = !b.result;
            var icon = isBuilding ? '<i class="fas fa-spinner fa-pulse mr-1 text-indigo-400"></i>' : '';
            return '<li class="py-1.5 border-b border-slate-50 last:border-0 flex justify-between items-center">' +
                '<a href="#" onclick="viewBuildLog(' + b.number + ');return false" class="text-indigo-600 hover:underline text-[13px]">' + icon + '#' + b.number + '</a>' +
                '<span class="text-[12px] ' + color + '">' + r + '</span></li>';
        }).join('');
    }).catch(function() {
        el.innerHTML = '<li class="text-[13px] text-slate-400">加载失败</li>';
    });
}

function viewBuildLog(num) {
    _buildNumber = num;
    stopPoll();
    setBuilding(false);
    var badge = document.getElementById('buildNumberBadge');
    badge.textContent = '#' + num;
    badge.classList.remove('hidden');
    updateBuildLog();
}

// ======= 辅助方法 =======
function selectedInstanceId() {
    var s = document.getElementById('jenkinsInstance');
    return (s && s.value) || '';
}

function getCsrfToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return (m && m.content) || '';
}
</script>'''


# ============ 路由定义 ============

@bp.route('/admin/build/commercial-release')
@admin_required_any('projects', 'build')
def commercial_release_page():
    """商业级发布独立页面"""
    csrf_token = generate_csrf()
    # 注入 CSRF token 到 meta 标签
    page = COMMERCIAL_RELEASE_PAGE.replace(
        '<meta name="csrf-token" content="">',
        '<meta name="csrf-token" content="' + csrf_token + '">'
    )
    return _admin_layout(page, '商业级发布', back_href='/admin')


@bp.route('/admin/build/commercial-release/trigger', methods=['POST'])
@bp.route('/api/admin/build/commercial-release/trigger', methods=['POST'])
@admin_required_any('projects', 'build')
def trigger_commercial_release():
    """触发商业级发布"""
    if not has_scope('build.trigger'):
        return jsonify({'success': False, 'error': '无权限触发构建'}), 403

    data = request.get_json(silent=True) or {}
    if not data and request.get_data():
        return jsonify({'success': False, 'error': '请求体不是合法 JSON'}), 400
    instance_id = (data.get('instance_id') or '').strip()
    if not instance_id:
        return jsonify({'success': False, 'error': '请选择 Jenkins 实例（缺少 instance_id）'}), 400
    project_id = (data.get('_project_id') or '').strip()
    version_id = (data.get('_version_id') or '').strip()
    version_obj = None
    if project_id and version_id:
        try:
            from models.data import project_versions_db
            versions = (project_versions_db.get(project_id) or [])
            if isinstance(versions, list):
                version_obj = next((v for v in versions if (v.get('id') or '') == version_id), None)
        except Exception:
            version_obj = None
    # Jenkins context
    base_url, builds_dir, instance_id = _jenkins_context(data)

    if not base_url or not builds_dir:
        return jsonify({
            'success': False,
            'error': 'Jenkins 实例未找到或未运行，请在 Jenkins 管理中启动对应实例',
        }), 400

    plan = data.get('plan') or {}
    if not isinstance(plan, dict):
        plan = {}
    # 兼容“从版本点构建”：若前端未完整传入商业流水线计划，则从版本保存的 pipeline 补齐。
    pipeline = (version_obj or {}).get('pipeline') if isinstance(version_obj, dict) else {}
    if not isinstance(pipeline, dict):
        pipeline = {}
    config_export = pipeline.get('config_export') or {}
    resource_build = pipeline.get('resource_build') or {}
    hot_release = pipeline.get('hot_release') or {}
    apk_build = pipeline.get('apk_build') or {}
    if not isinstance(config_export, dict):
        config_export = {}
    if not isinstance(resource_build, dict):
        resource_build = {}
    if not isinstance(hot_release, dict):
        hot_release = {}
    if not isinstance(apk_build, dict):
        apk_build = {}
    plan_defaults = {
        'configEnabled': config_export.get('enabled'),
        'configRemotePrefix': config_export.get('remote_prefix'),
        'configIncludeCode': config_export.get('include_code'),
        'resourceEnabled': resource_build.get('enabled'),
        'resourceProvider': resource_build.get('provider'),
        'resourceScenario': resource_build.get('scenario'),
        'hotReleaseEnabled': hot_release.get('enabled'),
        'apkBuildEnabled': apk_build.get('enabled'),
        'releaseMode': hot_release.get('release_mode'),
        'releaseEnvironment': hot_release.get('release_environment'),
        'releaseChannel': hot_release.get('release_channel'),
        'releaseTargets': hot_release.get('release_targets'),
        'releaseHotLabels': hot_release.get('release_hot_labels'),
        'releaseUploadMode': hot_release.get('release_upload_mode'),
        'releaseRollbackTarget': hot_release.get('release_rollback_target'),
        'releaseCompressionOverride': hot_release.get('release_compression_override'),
        'releaseEncryptionOverride': hot_release.get('release_encryption_override'),
        'releaseSignatureOverride': hot_release.get('release_signature_override'),
        'codeEnabled': hot_release.get('code_enabled'),
        'codeCompression': hot_release.get('code_compression'),
        'codeEncryption': hot_release.get('code_encryption'),
        'codeSignature': hot_release.get('code_signature'),
        'codeUnits': hot_release.get('code_units'),
        'resourceCompression': hot_release.get('resource_compression'),
        'resourceEncryption': hot_release.get('resource_encryption'),
        'resourceSignature': hot_release.get('resource_signature'),
        'resourceUnits': hot_release.get('resource_units'),
        'appName': apk_build.get('app_name'),
        'unityVersion': apk_build.get('unity_version'),
        'gitBranch': apk_build.get('git_branch'),
        'outputBaseDir': apk_build.get('output_base_dir'),
        'unityProjectPath': apk_build.get('unity_project_path'),
        'versionCode': (version_obj or {}).get('version_code') if isinstance(version_obj, dict) else None,
        'releaseVersion': (version_obj or {}).get('version_name') if isinstance(version_obj, dict) else None,
    }
    for k, v in plan_defaults.items():
        if k not in plan and v is not None and str(v).strip() != '':
            plan[k] = v
    if project_id:
        try:
            from services.admin.project_build_config_service import get_project_build_config

            pbc = get_project_build_config(project_id)
            if not str(plan.get('appName') or '').strip():
                plan['appName'] = (pbc.get('app_name') or project_id).strip()
            if not str(plan.get('unityProjectPath') or '').strip():
                plan['unityProjectPath'] = (pbc.get('unity_project_path') or '').strip()
            if not str(plan.get('outputBaseDir') or '').strip():
                plan['outputBaseDir'] = (pbc.get('output_base_dir') or '').strip()
            if not str(plan.get('gitBranch') or '').strip() and (pbc.get('default_git_branch') or '').strip():
                plan['gitBranch'] = (pbc.get('default_git_branch') or '').strip()
        except Exception:
            pass

    # 生成 RELEASE_PLAN_FILE JSON
    plan_id = str(uuid.uuid4())[:8]
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    plan_filename = f'release_plan_{plan_id}_{timestamp}.json'
    plan_filepath = os.path.join(RELEASE_PLANS_DIR, plan_filename)

    # 构建完整的自动化计划
    release_mode = plan.get('releaseMode', 'build-upload')
    if isinstance(version_obj, dict) and str(version_obj.get('version_name') or '').strip():
        release_version = str(version_obj.get('version_name') or '').strip()
    else:
        release_version = str(plan.get('releaseVersion') or '0.0.1').strip() or '0.0.1'
    release_env = plan.get('releaseEnvironment', 'Development')
    if str(release_env) not in ('Development', 'Testing', 'Staging', 'Production'):
        stage = ((version_obj or {}).get('stage') or '').strip().lower() if isinstance(version_obj, dict) else ''
        if stage == 'production':
            release_env = 'Production'
        elif stage == 'test':
            release_env = 'Testing'
        else:
            release_env = 'Development'
    release_channel = normalize_release_channel(plan.get('releaseChannel', 'common'))
    release_platform = plan.get('releasePlatform', 'Android')
    release_targets = normalize_step3_targets(plan.get('releaseTargets', 'code,resource'))
    release_hotlabels = plan.get('releaseHotLabels', '')
    release_upload_mode = plan.get('releaseUploadMode', 'incremental')
    release_upload = plan.get('releaseUpload', True)
    release_activate = plan.get('releaseActivate', False)
    release_rollback = plan.get('releaseRollbackTarget', '')

    automation_plan = {
        'releaseMode': release_mode,
        'releaseVersion': release_version,
        'releaseEnvironment': release_env,
        'releaseChannel': release_channel,
        'releasePlatform': release_platform,
        'releaseTargets': release_targets,
        'releaseHotLabels': release_hotlabels,
        'releaseUploadMode': release_upload_mode,
        'releaseUpload': release_upload,
        'releaseActivate': release_activate,
        'releaseRollbackTarget': release_rollback,
        'releaseCompressionOverride': plan.get('releaseCompressionOverride', ''),
        'releaseEncryptionOverride': plan.get('releaseEncryptionOverride', ''),
        'releaseSignatureOverride': plan.get('releaseSignatureOverride', ''),
        # 三类包策略
        'codeEnabled': plan.get('codeEnabled', True),
        'codeCompression': plan.get('codeCompression', 'Zip'),
        'codeEncryption': plan.get('codeEncryption', 'Aes'),
        'codeSignature': plan.get('codeSignature', 'builtin-signature'),
        'codeUnits': plan.get('codeUnits', 'aotmeta, hotupdate, scriptpatch, symbols'),
        'configEnabled': plan.get('configEnabled', True),
        'configCompression': plan.get('configCompression', 'Zip'),
        'configEncryption': plan.get('configEncryption', 'Aes'),
        'configSignature': plan.get('configSignature', 'builtin-signature'),
        'configUnits': plan.get('configUnits', 'base, liveops, gray, localization, experiment, logic'),
        'resourceEnabled': plan.get('resourceEnabled', True),
        'resourceCompression': plan.get('resourceCompression', 'None'),
        'resourceEncryption': plan.get('resourceEncryption', 'None'),
        'resourceSignature': plan.get('resourceSignature', 'builtin-signature'),
        'resourceUnits': plan.get('resourceUnits', 'addressable, hotupdate, optional, platform, hd, streaming'),
        'generatedBy': 'apk-site-admin',
        'generatedAtUtc': datetime.utcnow().isoformat(),
        'targetProject': plan.get('targetProject', ''),
        'versionCode': str(plan.get('versionCode') or (version_obj or {}).get('version_code') or ''),
        'configRemotePrefix': str(plan.get('configRemotePrefix') or ''),
    }

    unity_path_override = (data.get('UNITY_PROJECT_PATH') or plan.get('unityProjectPath') or '').strip()
    if unity_path_override:
        plan['unityProjectPath'] = unity_path_override
    plan['releaseTargets'] = release_targets
    plan['releaseEnvironment'] = normalize_release_environment(
        release_env, (version_obj or {}).get('stage') if isinstance(version_obj, dict) else ''
    )

    params, plan_patch = plan_to_jenkins_params(plan, plan_filepath, version_obj)
    automation_plan.update(plan_patch)

    with open(plan_filepath, 'w', encoding='utf-8') as f:
        json_module.dump(automation_plan, f, ensure_ascii=False, indent=2)

    ok_prep, prep_err = jm.prepare_instance_job_for_plan(instance_id, plan, project_id=project_id)
    if not ok_prep:
        return jsonify({'success': False, 'error': prep_err or '同步 Jenkins Job 参数失败'}), 400

    success, build_number, err = jenkins_svc.trigger_build(params, base_url=base_url, builds_dir=builds_dir, instance_id=instance_id)

    if success:
        log_audit('commercial_release', f'商业发布 #{build_number} - {release_version} {release_env}/{release_channel}/{release_platform}')
        if project_id and version_id and instance_id:
            try:
                from models.data import record_build_version
                record_build_version(instance_id, build_number, version_id, project_id)
            except Exception:
                pass
        if project_id and version_id:
            try:
                from models.data import project_versions_db, save_project_versions
                versions = (project_versions_db.get(project_id) or [])
                if isinstance(versions, list):
                    for ver in versions:
                        if (ver.get('id') or '') == version_id:
                            ver['jenkins_instance_id'] = instance_id
                            ver['last_build_number'] = int(build_number)
                            saved_vn = str(ver.get('version_name') or release_version or '').strip()
                            ver['jenkins_params'] = {
                                'APP_NAME': automation_plan.get('targetProject', 'GameKu'),
                                'VERSION_NAME': saved_vn,
                                'VERSION_CODE': str(ver.get('version_code') or ''),
                                'GIT_BRANCH': str(
                                    params.get('GIT_BRANCH')
                                    or plan.get('gitBranch')
                                    or ((ver.get('pipeline') or {}).get('apk_build') or {}).get('git_branch')
                                    or 'main'
                                ),
                                'CHANNEL': release_channel,
                            }
                            ver['updated_at'] = datetime.now().isoformat()
                            break
                    project_versions_db[project_id] = versions
                    save_project_versions()
            except Exception:
                pass
        return jsonify({
            'success': True,
            'build_number': build_number,
            'plan_file': plan_filepath,
            'mode': release_mode
        })
    else:
        return jsonify({'success': False, 'error': err or '触发失败'})


@bp.route('/admin/build/commercial-release/activate', methods=['POST'])
@admin_required_any('projects', 'build')
def activate_commercial_release():
    """仅 Step4 激活：上传完成后单独触发，不写 release_plan 构建步骤。"""
    if not has_scope('build.trigger'):
        return jsonify({'success': False, 'error': '无权限触发构建'}), 403

    data = request.get_json() or {}
    base_url, builds_dir, instance_id = _jenkins_context(data)
    if not base_url or not builds_dir:
        return jsonify({'success': False, 'error': 'Jenkins 实例未找到或未运行'}), 400

    plan = data.get('plan') or {}
    if not isinstance(plan, dict):
        plan = {}
    plan['releaseMode'] = 'activate'
    plan['releaseActivate'] = True
    plan['releaseUpload'] = False
    plan['configEnabled'] = False
    plan['resourceEnabled'] = False
    plan['hotReleaseEnabled'] = True

    plan_id = str(uuid.uuid4())[:8]
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    plan_filename = f'release_plan_activate_{plan_id}_{timestamp}.json'
    plan_filepath = os.path.join(RELEASE_PLANS_DIR, plan_filename)
    with open(plan_filepath, 'w', encoding='utf-8') as f:
        json_module.dump(plan, f, ensure_ascii=False, indent=2)

    params, _ = plan_to_jenkins_params(plan, plan_filepath, None)
    success, build_number, err = jenkins_svc.trigger_build(
        params, base_url=base_url, builds_dir=builds_dir, instance_id=instance_id
    )
    if success:
        log_audit('commercial_release_activate', f'激活 #{build_number}')
        return jsonify({'success': True, 'build_number': build_number, 'mode': 'activate'})
    return jsonify({'success': False, 'error': err or '触发失败'}), 500


@bp.route('/admin/build/commercial-release/plan-preview', methods=['POST'])
@admin_required_any('projects', 'build')
def preview_commercial_plan():
    """预览发布计划 JSON"""
    data = request.get_json() or {}
    plan = data.get('plan') or {}
    return jsonify({'plan': plan})


def _jenkins_context(data=None):
    """从请求中取 instance_id，返回 (base_url, builds_dir, instance_id)。"""
    if data is None:
        data = request.get_json(silent=True) or {}
    instance_id = (data.get('instance_id') or request.args.get('instance_id', '') or '').strip()
    if not instance_id:
        return (None, None, None)
    url = jm.get_jenkins_url_for_instance(instance_id=instance_id)
    bdir = jm.get_builds_dir_for_instance(instance_id=instance_id)
    return (url, bdir, instance_id)

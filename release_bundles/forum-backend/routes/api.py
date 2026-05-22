# -*- coding: utf-8 -*-
"""API：APK 列表、统计、健康检查、状态、文档"""

import os
from datetime import datetime
from flask import Blueprint, jsonify

from config import Config
from services.authz import login_required
from models.data import (
    extract_package_info, download_stats, projects_db,
    users_db, project_versions_db, iter_package_files, detect_platform,
)

bp = Blueprint('api', __name__, url_prefix='/api')

__version__ = '1.0'


@bp.route('/status')
def status():
    """扩展健康检查：含基础统计与性能指标，供监控/负载均衡使用。无需登录。"""
    from services.monitor import get_stats
    package_counts = {'android': 0, 'ios': 0}
    for filename, _ in iter_package_files():
        package_counts[detect_platform(filename)] = package_counts.get(detect_platform(filename), 0) + 1
    package_count = sum(package_counts.values())
    version_count = sum(len(v) if isinstance(v, list) else 0 for v in (project_versions_db or {}).values())
    perf = get_stats()
    out = {
        'status': 'ok',
        'service': 'apk-site',
        'version': __version__,
        'stats': {
            'users': len(users_db) if isinstance(users_db, dict) else 0,
            'projects': len(projects_db) if isinstance(projects_db, dict) else 0,
            'apk_count': package_count,
            'package_count': package_count,
            'platforms': package_counts,
            'version_count': version_count,
        },
    }
    if perf.get('count'):
        out['perf'] = perf
    return jsonify(out)


@bp.route('/openapi.json')
def openapi_spec():
    """OpenAPI 3.0 规范，供 Swagger UI 等加载"""
    import json
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'openapi.json')
    if os.path.isfile(p):
        with open(p, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    return jsonify({'openapi': '3.0.2', 'info': {'title': 'APK 下载中心 API', 'version': '1.0'}, 'paths': {}})


@bp.route('/docs')
def docs():
    """API 文档页：列出主要接口说明。无需登录。"""
    html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>API 文档 - APK 下载中心</title>
    <link rel="stylesheet" href="/static/tailwind.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body class="bg-gray-50 min-h-screen">
    <div class="max-w-3xl mx-auto px-4 py-8">
        <h1 class="text-2xl font-bold text-gray-800 mb-2"><i class="fas fa-book text-indigo-500 mr-2"></i>API 文档</h1>
        <p class="text-gray-600 mb-6">APK 下载中心主要接口说明，供集成与监控使用。</p>
        <div class="space-y-4">
            <div class="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
                <div class="flex items-center gap-2"><span class="px-2 py-0.5 rounded bg-green-100 text-green-800 text-sm font-mono">GET</span><code class="text-indigo-600">/health</code></div>
                <p class="text-sm text-gray-600 mt-2">健康检查，返回 status、service。负载均衡探测用，无需认证。</p>
            </div>
            <div class="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
                <div class="flex items-center gap-2"><span class="px-2 py-0.5 rounded bg-green-100 text-green-800 text-sm font-mono">GET</span><code class="text-indigo-600">/api/status</code></div>
                <p class="text-sm text-gray-600 mt-2">扩展状态，含用户数、项目数、APK 数等统计。无需认证。</p>
            </div>
            <div class="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
                <div class="flex items-center gap-2"><span class="px-2 py-0.5 rounded bg-green-100 text-green-800 text-sm font-mono">GET</span><code class="text-indigo-600">/api/apks</code></div>
                <p class="text-sm text-gray-600 mt-2">APK 列表，需登录。</p>
            </div>
            <div class="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
                <div class="flex items-center gap-2"><span class="px-2 py-0.5 rounded bg-green-100 text-green-800 text-sm font-mono">GET</span><code class="text-indigo-600">/api/stats</code></div>
                <p class="text-sm text-gray-600 mt-2">统计汇总，需登录。</p>
            </div>
            <div class="bg-white rounded-lg border border-gray-200 p-4 shadow-sm">
                <p class="text-sm text-gray-500">管理接口（构建、版本、Jenkins 等）需管理员权限，见管理中心各模块。</p>
            </div>
        </div>
        <p class="mt-6 text-sm text-gray-500"><a href="/" class="text-indigo-600 hover:underline">← 返回首页</a></p>
    </div>
</body>
</html>'''
    return html


@bp.route('/apks')
@login_required
def list_apks():
    files = []
    for filename, filepath in iter_package_files():
        files.append(extract_package_info(filename, filepath))
    return jsonify({'success': True, 'data': files})


@bp.route('/stats')
@login_required
def stats():
    package_counts = {'android': 0, 'ios': 0}
    for filename, _ in iter_package_files():
        package_counts[detect_platform(filename)] = package_counts.get(detect_platform(filename), 0) + 1
    total_apks = sum(package_counts.values())
    return jsonify({
        'success': True,
        'data': {
            'total_apks': total_apks,
            'package_count': total_apks,
            'platforms': package_counts,
            'total_downloads': sum(download_stats.values()),
            'projects': len(projects_db)
        }
    })

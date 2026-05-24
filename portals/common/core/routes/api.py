# -*- coding: utf-8 -*-
"""API：APK 列表、统计、健康检查、状态、文档、运行时版本解析"""

import os
from datetime import datetime
from flask import Blueprint, jsonify, request

from config import Config
from services.authz import login_required
from services.admin.version_domain import normalize_version_status
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


def _normalize_version_status(raw_status):
    return normalize_version_status(raw_status)


def _parse_version_code_weight(raw_code):
    code = str(raw_code or "").strip()
    if not code:
        return -1, ""
    if code.isdigit():
        return int(code), code
    digits = "".join(ch for ch in code if ch.isdigit())
    return (int(digits) if digits else -1), code


def _channel_matches(query_channel: str, row_channel: str) -> bool:
    """Match channel id (1001) with runtime key (wechat) via channels.json build_param."""
    query = (query_channel or "").strip().lower()
    row = (row_channel or "").strip().lower()
    if not query or not row:
        return True
    if query == row:
        return True
    from services.commercial_release_plan import normalize_release_channel

    return normalize_release_channel(query) == normalize_release_channel(row)


@bp.route('/runtime/version-resolve')
def resolve_runtime_version():
    """按项目版本管理数据解析运行时版本：同 VersionName 下返回最大可用 VersionCode。"""
    project_id = (request.args.get('project_id') or '').strip()
    version_name = (request.args.get('version_name') or request.args.get('client_version') or '').strip()
    channel = (request.args.get('channel') or '').strip().lower()
    platform = (request.args.get('platform') or '').strip().lower()
    status = _normalize_version_status(request.args.get('status') or request.args.get('state') or 'active')
    include_status_raw = (request.args.get('include_status') or '').strip()
    version_code_exact = (request.args.get('version_code') or '').strip()
    device_id = (request.args.get('device_id') or '').strip()
    stage_param = (request.args.get('stage') or '').strip().lower()
    environment = (request.args.get('environment') or '').strip().lower()
    effective_stage = ''
    if device_id:
        from services.test_device_service import resolve_stage_for_device
        effective_stage = resolve_stage_for_device(project_id, device_id) or ''
    elif stage_param in ('dev', 'test', 'production'):
        effective_stage = stage_param
    elif environment in ('development', 'dev'):
        effective_stage = 'dev'
    elif environment in ('testing', 'test'):
        effective_stage = 'test'
    elif environment in ('production', 'prod', 'online'):
        effective_stage = 'production'
    include_statuses = set()
    if include_status_raw:
        for item in include_status_raw.split(','):
            norm = _normalize_version_status(item.strip())
            if norm:
                include_statuses.add(norm)

    if not project_id or not version_name:
        return jsonify({
            'ok': False,
            'error': 'missing project_id or version_name',
            'data': None,
        }), 400

    rows = project_versions_db.get(project_id) or []
    if not isinstance(rows, list):
        rows = []

    candidates = []
    for row in rows:
        if str(row.get('version_name') or '').strip() != version_name:
            continue
        row_status = _normalize_version_status(row.get('version_status') or 'active')
        if version_code_exact and str(row.get('version_code') or '').strip() != version_code_exact:
            continue
        if include_statuses:
            if row_status not in include_statuses:
                continue
        elif row_status != status:
            continue
        row_channel = str(row.get('channel') or '').strip().lower()
        row_platform = str(row.get('platform') or '').strip().lower()
        if channel and row_channel and not _channel_matches(channel, row_channel):
            continue
        if platform and row_platform and row_platform != platform:
            continue
        if effective_stage and str(row.get('stage') or 'dev').strip() != effective_stage:
            continue
        candidates.append(row)

    if not candidates:
        return jsonify({
            'ok': False,
            'error': f'no matched version for {project_id}/{version_name}',
            'data': None,
        }), 404

    candidates.sort(
        key=lambda x: (
            str(x.get('updated_at') or ''),
            _parse_version_code_weight(x.get('version_code') or '')[0],
            _parse_version_code_weight(x.get('version_code') or '')[1],
        ),
        reverse=True,
    )
    selected = candidates[0]

    from services.commercial_release_plan import (
        build_runtime_resolve_paths,
        normalize_release_environment,
        normalize_release_channel,
        DEFAULT_RESOURCE_SERVER,
    )

    row_channel = normalize_release_channel(str(selected.get('channel') or channel or 'common'))
    row_platform_raw = str(selected.get('platform') or platform or 'android')
    row_platform = 'ios' if row_platform_raw.lower() == 'ios' else 'android'
    platform_title = row_platform
    release_env = normalize_release_environment(
        str(selected.get('release_environment') or ''),
        str(selected.get('stage') or ''),
    )
    version_code = str(selected.get('version_code') or '').strip()
    resource_server_url = str(selected.get('resource_server_url') or '').strip()
    runtime_paths = build_runtime_resolve_paths(
        resource_server_url=resource_server_url,
        release_environment=release_env,
        release_channel=row_channel,
        release_platform=platform_title,
        release_version=version_name,
        version_code=version_code,
    )
    resource_relative_path = (
        str(selected.get('resource_path') or '').strip()
        or runtime_paths['resource_relative_path']
    )
    catalog_file_name = (
        str(selected.get('catalog_file_name') or '').strip()
        or runtime_paths['catalog_file_name']
    )
    resource_base = (resource_server_url or DEFAULT_RESOURCE_SERVER).rstrip('/')
    catalog_url = f"{resource_base}/{resource_relative_path.strip('/')}/{catalog_file_name.lstrip('/')}"

    min_client_version = str(
        selected.get('min_client_version') or selected.get('version_name') or version_name
    ).strip()
    max_client_version = str(
        selected.get('max_client_version') or selected.get('version_name') or version_name
    ).strip()
    rollout_percentage = selected.get('rollout_percentage')
    if rollout_percentage is None:
        rollout_percentage = 100
    is_revoked = bool(selected.get('is_revoked') or selected.get('version_status') == 'revoked')

    return jsonify({
        'ok': True,
        'data': {
            'project_id': project_id,
            'version_id': selected.get('id'),
            'version_name': selected.get('version_name') or version_name,
            'version_code': version_code,
            'version_status': _normalize_version_status(selected.get('version_status') or 'active'),
            'channel': row_channel,
            'platform': row_platform,
            'environment': release_env,
            'min_client_version': min_client_version,
            'max_client_version': max_client_version,
            'rollout_percentage': rollout_percentage,
            'is_revoked': is_revoked,
            'resource_path': resource_relative_path,
            'config_path': selected.get('config_path') or runtime_paths['config_relative_path'],
            'resource_relative_path': resource_relative_path,
            'config_relative_path': runtime_paths['config_relative_path'],
            'code_relative_path': runtime_paths['code_relative_path'],
            'config_manifest_path': runtime_paths['config_manifest_path'],
            'code_manifest_path': runtime_paths['code_manifest_path'],
            'catalog_file_name': catalog_file_name,
            'catalog_url': catalog_url,
            'resource_server_url': resource_base,
            'apk_path': selected.get('apk_path') or '',
            'updated_at': selected.get('updated_at') or '',
            'version_record': dict(selected),
        },
        'meta': {
            'matched_count': len(candidates),
            'selected_rule': 'latest_updated_at_then_version_code',
            'query': {
                'status': status,
                'include_status': sorted(list(include_statuses)),
                'version_code': version_code_exact,
                'device_id': device_id,
                'effective_stage': effective_stage,
            },
        },
    })

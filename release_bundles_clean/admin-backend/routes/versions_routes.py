# -*- coding: utf-8 -*-
"""版本管理：安装包按项目/版本列表。"""

import os
from collections import defaultdict

from flask import Blueprint, jsonify, render_template, request, session

from config import Config
from models.data import (
    can_view_project,
    changelog_db,
    extract_package_info,
    iter_package_files,
    log_audit,
    projects_db,
    save_changelog,
)
from services.authz import admin_required

bp = Blueprint('versions_routes', __name__, url_prefix='')


def _get_csrf_token():
    try:
        from flask_wtf.csrf import generate_csrf

        return generate_csrf()
    except ImportError:
        return ''


def _changelog_display(filename):
    raw = changelog_db.get(filename)
    if raw is None:
        return '', False
    if isinstance(raw, dict):
        return (raw.get('text') or '')[:50], bool(raw.get('recommended'))
    return str(raw)[:50], False


@bp.route('/admin/versions')
@admin_required('versions')
def admin_versions_page():
    username = session.get('user') or ''
    project_filter = (request.args.get('project_id') or '').strip()
    grouped = defaultdict(list)
    if os.path.exists(Config.APK_DIR):
        for filename, filepath in iter_package_files():
            info = extract_package_info(filename, filepath)
            if can_view_project(info.get('project', ''), username):
                if project_filter and info.get('project') != project_filter:
                    continue
                ch_text, recommended = _changelog_display(info['name'])
                info['changelog_preview'] = ch_text or '-'
                info['recommended'] = recommended
                grouped[info['project']].append(info)
    for project_id in grouped:
        grouped[project_id].sort(key=lambda item: item.get('timestamp', 0), reverse=True)

    def project_sort_key(project_id):
        return projects_db.get(project_id, {}).get('name', project_id), project_id

    grouped_projects = []
    for project_id in sorted(grouped.keys(), key=project_sort_key):
        grouped_projects.append({
            'project_id': project_id,
            'project_name': projects_db.get(project_id, {}).get('name', project_id),
            'files': grouped[project_id],
        })

    project_options = []
    for project_id, project in sorted(projects_db.items(), key=lambda item: (((item[1] or {}).get('name') or item[0]), item[0])):
        if not can_view_project(project_id, username):
            continue
        project_options.append({'id': project_id, 'name': (project or {}).get('name') or project_id})

    return render_template(
        'admin_versions.html',
        grouped_projects=grouped_projects,
        project_options=project_options,
        project_filter=project_filter,
        csrf_token_value=_get_csrf_token(),
    )


@bp.route('/admin/versions/changelog/<filename>')
@admin_required('versions')
def versions_changelog_get(filename):
    raw = changelog_db.get(filename)
    if raw is None:
        return jsonify({'text': '', 'recommended': False})
    if isinstance(raw, dict):
        return jsonify({'text': raw.get('text', ''), 'recommended': bool(raw.get('recommended'))})
    return jsonify({'text': str(raw), 'recommended': False})


@bp.route('/admin/versions/changelog/<filename>', methods=['POST'])
@admin_required('versions')
def versions_changelog_save(filename):
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    recommended = bool(data.get('recommended'))
    changelog_db[filename] = {'text': text, 'recommended': recommended}
    save_changelog()
    log_audit('changelog_update', filename)
    return jsonify({'success': True})

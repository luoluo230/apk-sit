# -*- coding: utf-8 -*-
"""安装包 changelog / 删除 API。旧全局版本页已并入项目「版本与管线」。"""

import os

from flask import Blueprint, jsonify, redirect, request

from config import Config
from models.data import changelog_db, log_audit, save_changelog
from services.authz import admin_required

bp = Blueprint('versions_routes', __name__, url_prefix='')


@bp.route('/admin/versions')
@admin_required('versions')
def admin_versions_page():
    return redirect('/admin/projects')


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


@bp.route('/admin/versions/delete/<filename>', methods=['POST'])
@admin_required('versions')
def versions_delete_file(filename):
    """删除指定安装包文件。"""
    if not filename:
        return jsonify({'error': '文件名不能为空'}), 400
    filepath = os.path.join(Config.APK_DIR, filename)
    if not os.path.isfile(filepath):
        return jsonify({'error': '文件不存在'}), 404
    try:
        os.remove(filepath)
        # 同时清理 changelog
        if filename in changelog_db:
            del changelog_db[filename]
            save_changelog()
        log_audit('version_delete', filename)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

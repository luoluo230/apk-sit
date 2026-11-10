from __future__ import annotations
# -*- coding: utf-8 -*-
"""构建管理：Jenkins 触发、状态、日志、停止；支持多实例选择"""

import os
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, render_template_string, redirect
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


def _version_group_key(version_obj: dict) -> tuple:
    if not isinstance(version_obj, dict):
        return ("", "", "dev")
    return (
        str(version_obj.get("version_name") or "").strip(),
        str(version_obj.get("channel") or "").strip(),
        str(version_obj.get("stage") or "dev").strip(),
    )


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


def _resolve_version_unity_version(version_obj: dict, all_versions=None, fallback: str = "6000.3.8f1") -> str:
    """从版本发布配置解析 Unity 版本；同版本组内取最近更新的 pipeline.apk_build.unity_version。"""
    if not isinstance(version_obj, dict):
        return fallback
    group_key = _version_group_key(version_obj)
    candidates = [version_obj]
    if all_versions and group_key[0]:
        candidates = [
            row for row in all_versions
            if isinstance(row, dict) and _version_group_key(row) == group_key
        ] or candidates
    best = ""
    best_ts = ""
    for row in candidates:
        pipeline = row.get("pipeline") if isinstance(row.get("pipeline"), dict) else {}
        apk_build = pipeline.get("apk_build") if isinstance(pipeline.get("apk_build"), dict) else {}
        unity = str(apk_build.get("unity_version") or "").strip()
        if not unity:
            continue
        ts = str(row.get("updated_at") or row.get("created_at") or "")
        if ts >= best_ts:
            best_ts = ts
            best = unity
    if best:
        return best
    saved = version_obj.get("jenkins_params") if isinstance(version_obj.get("jenkins_params"), dict) else {}
    legacy = str((saved or {}).get("UNITY_VERSION") or "").strip()
    if legacy:
        return legacy
    return fallback


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
    """Legacy inline build HTML removed; use templates/admin_build.html."""
    from flask import render_template
    return render_template(
        'admin_build.html',
        project_context=project_context,
        version_lock_params=version_lock_params,
        csrf_token_value=_get_csrf_token(),
    )


def _version_workflow_page_html():
    return _build_page_html(project_context=True, version_lock_params=True)


@bp.route('/admin/build')
@admin_required_any('projects', 'build')
def build_page():
    """旧构建入口。进入项目工作区的构建与产物。"""
    from flask import request, redirect
    project_id = (request.args.get('project') or '').strip()
    if project_id:
        from models.data import projects_db, can_view_project
        from flask import session
        if project_id in projects_db and can_view_project(project_id, session.get('user') or ''):
            return redirect('/admin/projects/%s/build-history' % project_id)
    return redirect('/admin/projects')


@bp.route('/admin/projects/<project_id>/build')
@admin_required_any('projects', 'build')
def project_build_page(project_id):
    """旧项目构建页。进入项目工作区的构建与产物。"""
    from models.data import projects_db, can_view_project
    from flask import session, redirect, abort
    if project_id not in projects_db:
        abort(404)
    if not can_view_project(project_id, session.get('user') or ''):
        abort(403)
    return redirect('/admin/projects/%s/build-history' % project_id)


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
    return redirect('/admin/projects/%s/build-history' % project_id)


@bp.route('/admin/build/trigger', methods=['POST'])
@admin_required_any('projects', 'build')
def trigger_build():
    from flask import session

    data = request.get_json() or {}
    project_id_top = (data.get('_project_id') or '').strip()
    version_id_top = (data.get('_version_id') or '').strip()
    if project_id_top and version_id_top and not has_scope('build.trigger'):
        return jsonify({'success': False, 'error': '无权限触发构建'}), 403
    if project_id_top and version_id_top:
        try:
            from services.release.release_order_service import ensure_draft_release_order, request_build as ro_request_build
            actor = session.get('user') or ''
            draft = ensure_draft_release_order(project_id_top, version_id_top, actor)
            updated = ro_request_build(project_id_top, draft.get('release_order_id') or '', actor)
            build_number = ((updated.get('payload') or {}).get('build_job_id')) or ''
            log_audit('trigger_build', f"Jenkins 构建 (release_order) - {draft.get('version_name', '')} #{build_number}")
            return jsonify({'success': True, 'build_number': build_number, 'release_order_id': draft.get('release_order_id')})
        except ValueError as exc:
            return jsonify({'success': False, 'error': str(exc)}), 400
        except Exception as exc:
            return jsonify({'success': False, 'error': f'通过发布单触发构建失败：{exc}'}), 500

    return jsonify({
        'success': False,
        'error': '请通过发布单触发构建，需要提供 _project_id 与 _version_id。',
    }), 400


@bp.route('/api/build/history-by-version')
@admin_required_any('projects', 'build')
def build_history_by_version():
    """按 version_code 获取构建历史（含 Jenkins 实时状态）。"""
    version_id = (request.args.get('version_id') or '').strip()
    instance_id = (request.args.get('instance_id') or '').strip()
    project_id = (request.args.get('project_id') or '').strip()
    if not version_id:
        return jsonify({'ok': True, 'builds': []})
    from services.build_history_service import builds_for_version_enriched, latest_build_for_version

    builds = builds_for_version_enriched(version_id, instance_id=instance_id)
    latest = builds[0] if builds else latest_build_for_version(version_id, project_id, instance_id=instance_id)
    if latest and not builds:
        builds = [latest]
    return jsonify({'ok': True, 'builds': builds, 'recent': builds, 'latest': latest or {}})


@bp.route('/api/build/history-by-project')
@admin_required_any('projects', 'build')
def build_history_by_project():
    """按项目获取构建历史，按 version_name -> version_code 分组。"""
    project_id = (request.args.get('project_id') or '').strip()
    if not project_id:
        return jsonify({'ok': False, 'error': '缺少 project_id'}), 400
    from services.build_history_service import builds_grouped_by_project

    return jsonify(builds_grouped_by_project(project_id))


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


@bp.route('/api/build/<int:build_number>/finalize-apk', methods=['POST'])
@admin_required_any('projects', 'build')
def finalize_apk_after_build(build_number):
    """Jenkins SUCCESS 后补做 APK 本地落盘（防止流水线未执行 Step 4c）。"""
    if not has_scope('build.trigger'):
        return jsonify({'ok': False, 'error': '无权限'}), 403
    data = request.get_json(silent=True) or {}
    _, _, instance_id = _jenkins_context()
    instance_id = (data.get('instance_id') or instance_id or '').strip()
    if not instance_id:
        return jsonify({'ok': False, 'error': '缺少 instance_id'}), 400
    try:
        from services.apk_artifact_service import finalize_apk_from_jenkins_build

        result = finalize_apk_from_jenkins_build(instance_id, build_number)
        status = 200 if result.get('ok') else 400
        return jsonify(result), status
    except Exception as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500


@bp.route('/api/build/<int:build_number>/status')
@admin_required_any('projects', 'build')
def build_status(build_number):
    base_url, builds_dir, instance_id = _jenkins_context()
    if not (has_scope('build.view') or has_scope('build.trigger')):
        return jsonify({'error': '无权限查看构建状态'}), 403
    return jsonify(jenkins_svc.get_build_status(build_number, base_url=base_url, builds_dir=builds_dir, instance_id=instance_id))


@bp.route('/api/build/log/<int:build_number>')
@admin_required_any('projects', 'build')
def build_log(build_number):
    from flask import make_response
    base_url, builds_dir, instance_id = _jenkins_context()
    if not (has_scope('build.view') or has_scope('build.trigger')):
        return make_response('无权限查看构建日志', 403)
    content = jenkins_svc.get_build_log_content(
        build_number,
        base_url=base_url,
        builds_dir=builds_dir,
        instance_id=instance_id,
    )
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
    if not instance_id:
        return jsonify({'error': '缺少 instance_id'}), 400
    version_id = (request.args.get('version_id') or '').strip()
    project_id = (request.args.get('project_id') or '').strip()
    from services.build_history_service import build_detail_enriched

    info = build_detail_enriched(instance_id, build_number, version_id=version_id, project_id=project_id)
    if info is None:
        return jsonify({'error': '构建不存在'}), 404
    return jsonify({'ok': True, 'build': info})


@bp.route('/api/build/<int:build_number>', methods=['DELETE'])
@admin_required_any('projects', 'build')
def delete_build_record_route(build_number):
    base_url, builds_dir, instance_id = _jenkins_context()
    if not has_scope('build.trigger'):
        return jsonify({'success': False, 'error': '无权限删除构建记录'}), 403
    if not instance_id:
        return jsonify({'success': False, 'error': '缺少 instance_id'}), 400
    version_id = (request.args.get('version_id') or '').strip()
    project_id = (request.args.get('project_id') or '').strip()
    from services.build_history_service import delete_build

    ok, err = delete_build(instance_id, build_number, version_id=version_id, project_id=project_id)
    if not ok:
        return jsonify({'success': False, 'error': err or '删除失败'}), 400
    return jsonify({'success': True})


@bp.route('/api/build/<int:build_number>/stop', methods=['POST'])
@admin_required_any('projects', 'build')
def stop_build(build_number):
    base_url, builds_dir, instance_id = _jenkins_context()
    if not has_scope('build.trigger'):
        return jsonify({'success': False, 'error': '无权限停止构建'}), 403
    success, err = jenkins_svc.stop_build(build_number, base_url=base_url, builds_dir=builds_dir, instance_id=instance_id)
    if success:
        try:
            from flask import session
            from services.build_history_service import mark_build_stopped

            mark_build_stopped(instance_id or '', build_number, session.get('user') or '')
        except Exception:
            pass
        log_audit('stop_build', f'已请求停止构建 #{build_number}')
        return jsonify({'success': True, 'message': '已请求停止构建'})
    return jsonify({'success': False, 'error': err or '停止失败'})


@bp.route('/api/build/records/batch-delete', methods=['POST'])
@admin_required_any('projects', 'build')
def batch_delete_build_records_api():
    if not has_scope('build.trigger'):
        return jsonify({'success': False, 'error': '无权限删除构建记录'}), 403
    data = request.get_json(silent=True) or {}
    project_id = (data.get('project_id') or '').strip()
    items = data.get('items') or []
    if not project_id:
        return jsonify({'success': False, 'error': '缺少 project_id'}), 400
    if not isinstance(items, list) or not items:
        return jsonify({'success': False, 'error': '请选择要删除的构建'}), 400
    from services.build_history_service import batch_delete_builds

    deleted, err = batch_delete_builds(project_id, items)
    if err and deleted == 0:
        return jsonify({'success': False, 'error': err, 'deleted': deleted}), 400
    return jsonify({'success': True, 'deleted': deleted, 'error': err or ''})


@bp.route('/api/build/record/delete', methods=['POST'])
@admin_required_any('projects', 'build')
def delete_build_record_api():
    data = request.get_json(silent=True) or {}
    project_id = (data.get('project_id') or '').strip()
    instance_id = (data.get('instance_id') or '').strip()
    build_number = data.get('build_number')
    try:
        build_number = int(build_number)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': '无效的 build_number'}), 400
    from services.build_history_service import delete_build_record

    err = delete_build_record(project_id, instance_id, build_number)
    if err:
        return jsonify({'success': False, 'error': err}), 400
    return jsonify({'success': True})

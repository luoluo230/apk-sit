# -*- coding: utf-8 -*-
"""管理中心 - Jenkins 管理：环境检查、一键部署、多实例启动/停止/删除"""

import os
import json
import html
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

_JM_CSS = '<link rel="stylesheet" href="/static/admin/jenkins_manage.css?v=20261030-jm4">'


def _jm_layout(content: str, title: str):
    return _admin_layout(
        f'<div class="jm-page">{content}</div>',
        title,
        back_href='/admin/jenkins' if title != 'Jenkins 管理' else '/admin',
        extra_css=_JM_CSS,
    )


@bp.route('/admin/jenkins')
@admin_required('jenkins')
def jenkins_manage_page():
    """Jenkins 管理页：环境检查、部署、实例列表、启动表单。"""
    env = jm.env_check()
    script_mac = jm.deploy_env_script('mac')
    script_win = jm.deploy_env_script('windows')
    content = _jenkins_manage_html(env, script_mac, script_win)
    return _jm_layout(content, 'Jenkins 管理')


@bp.route('/admin/unity-versions')
@admin_required('jenkins')
def unity_versions_manage_page():
    """兼容旧链接：跳转到 Jenkins 管理内的 Unity 版本库模块。"""
    from flask import redirect
    return redirect('/admin/jenkins#unity-catalog', code=302)


def _unity_catalog_module_html():
    return '''
    <div id="unity-catalog" class="studio-config-panel scroll-mt-4">
        <div class="studio-section-head">
            <h3>Unity 版本库</h3>
            <div class="flex flex-wrap gap-2">
                <button type="button" id="uvBtnReload" class="pm-btn pm-btn--compact">刷新列表</button>
                <button type="button" id="uvBtnImportDetect" class="pm-btn pm-btn--compact">从本机检测导入</button>
                <button type="button" id="uvBtnAdd" class="pm-btn pm-btn--compact pm-btn--primary">新增版本</button>
            </div>
        </div>
        <p class="text-xs text-gray-500">维护全局 Unity 版本。构建参数与版本编辑下拉仅展示<strong>有效</strong>项。</p>
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
        <div class="pm-table-panel overflow-x-auto">
            <table class="pm-table">
                <thead>
                    <tr>
                        <th>版本号</th><th>分类</th><th>状态</th><th>备注</th><th>安装路径</th><th>操作</th>
                    </tr>
                </thead>
                <tbody id="uvCatalogTableBody"><tr><td colspan="6">加载中…</td></tr></tbody>
            </table>
        </div>
        <div id="uvFormPanel" class="is-hidden studio-config-panel">
            <h3 id="uvFormTitle">新增 Unity 版本</h3>
            <input type="hidden" id="uvFormEntryId">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <div><label class="block text-gray-600 mb-1">版本号</label><input id="uvFormVersion" class="border rounded px-2 py-1.5 w-full font-mono text-xs" placeholder="6000.3.15f1"></div>
                <div><label class="block text-gray-600 mb-1">分类</label><input id="uvFormCategory" list="uvCategoryDatalist" class="border rounded px-2 py-1.5 w-full text-xs" placeholder="如 Unity6、Unity2022"><datalist id="uvCategoryDatalist"></datalist></div>
                <div><label class="block text-gray-600 mb-1">状态</label><select id="uvFormStatus" class="border rounded px-2 py-1.5 w-full text-xs"><option value="active">有效</option><option value="inactive">失效</option></select></div>
                <div class="md:col-span-2"><label class="block text-gray-600 mb-1">安装路径（可选）</label><input id="uvFormPath" class="border rounded px-2 py-1.5 w-full text-xs" placeholder="留空则构建时自动探测"></div>
                <div class="md:col-span-2"><label class="block text-gray-600 mb-1">备注说明</label><textarea id="uvFormNote" rows="2" class="border rounded px-2 py-1.5 w-full text-xs" placeholder="用途、项目、注意事项等"></textarea></div>
            </div>
            <div id="uvFormStatusMsg" class="text-sm mt-2 text-gray-500"></div>
            <div class="flex gap-2">
                <button type="button" id="uvFormSave" class="pm-btn pm-btn--primary">保存</button>
                <button type="button" id="uvFormCancel" class="pm-btn">取消</button>
            </div>
        </div>
    </div>
    <script src="/static/admin/jenkins_unity_catalog.js?v=20260609"></script>
    '''


def _jenkins_manage_html(env, script_mac, script_win):
    java_ok = bool(env.get('java', {}).get('ok'))
    git_ok = bool(env.get('git', {}).get('ok'))
    war_ok = bool(env.get('war', {}).get('ok'))
    java_line = (
        '<span class="jm-status-ok">已安装</span> ' + (env.get('java', {}).get('version') or '')
        if java_ok else '<span class="jm-status-off">未安装或不可用</span>'
    )
    git_line = (
        '<span class="jm-status-ok">已安装</span> ' + (env.get('git', {}).get('version') or '')
        if git_ok else '<span class="jm-status-off">可选</span>'
    )
    war_line = (
        '<span class="jm-status-ok">已配置</span> ' + (env.get('war', {}).get('path') or '')
        if war_ok else
        '<span class="jm-link--danger">未配置</span>。可在 .env 设置 JENKINS_WAR_PATH，或放入 data/jenkins_instances/jenkins.war / jenkins-clone/jenkins.war'
    )
    return f'''<!-- apk-site-page: jenkins-manage-v20261030 -->
<section class="jm-page" data-jm-page>
<header class="pm-page-head">
  <div class="pm-page-head-copy"><div>
    <h1>打包机</h1>
    <p>日常管理 Jenkins 实例；环境与 Unity 版本按需切换。</p>
  </div></div>
  <div class="pm-page-head-actions">
    <button type="button" class="pm-btn pm-btn--primary" data-jm-goto="start">启动新实例</button>
  </div>
</header>
<nav id="jmQuickNav" class="jm-tabs" role="tablist" aria-label="打包机分区">
  <button type="button" class="jm-tab is-active" role="tab" aria-selected="true" data-jm-tab="list">实例列表</button>
  <button type="button" class="jm-tab" role="tab" aria-selected="false" data-jm-tab="start">启动新实例</button>
  <button type="button" class="jm-tab" role="tab" aria-selected="false" data-jm-tab="unity">Unity 版本库</button>
  <button type="button" class="jm-tab" role="tab" aria-selected="false" data-jm-tab="env">环境检查</button>
</nav>
<div class="jm-panel is-active" data-jm-panel="list" id="jm-list">
  <div class="studio-config-panel">
    <div class="studio-section-head">
      <h3>Jenkins 实例</h3>
      <p class="jm-hint">构建时选择实例执行打包，支持多实例并行。</p>
    </div>
    <div id="listFilterTabs" class="jm-filter-tabs">
      <button type="button" data-filter="all" class="pm-btn pm-btn--compact pm-btn--primary is-active" onclick="filterList('all')">全部</button>
      <button type="button" data-filter="general" class="pm-btn pm-btn--compact" onclick="filterList('general')">通用</button>
      <button type="button" data-filter="commercial" class="pm-btn pm-btn--compact" onclick="filterList('commercial')">商业</button>
    </div>
    <div class="pm-table-panel">
      <table class="pm-table">
        <thead><tr><th>类型</th><th>端口</th><th>任务名</th><th>状态</th><th>添加时间</th><th>添加人</th><th>启动时间</th><th>启动人</th><th>操作</th></tr></thead>
        <tbody id="jenkinsInstanceList"></tbody>
      </table>
    </div>
    <p id="instanceListMsg" class="jm-hint">加载中…</p>
  </div>
</div>
<div class="jm-panel" data-jm-panel="start" id="jm-start" hidden>
  <div class="studio-config-panel">
    <h3>启动新实例</h3>
    <div class="jm-start-core">
      <label class="jm-label">实例用途</label>
      <div class="jm-type-toggle" role="group" aria-label="实例用途">
        <button type="button" id="instanceTypeGeneral" class="is-active">通用 APK 打包</button>
        <button type="button" id="instanceTypeCommercial">商业热更发布</button>
      </div>
      <input type="hidden" id="newInstanceType" value="general">
      <p class="jm-hint">通用侧重安装包；商业侧重热更 Bundle。版本页「版本模式」需与用途一致。</p>
      <div class="jm-field-row">
        <div class="jm-field" style="flex:0 0 120px;min-width:120px">
          <label class="jm-label" for="newPort">端口</label>
          <input type="number" id="newPort" value="8080" min="1" max="65535">
        </div>
        <div class="jm-field">
          <label class="jm-label" for="newTaskName">任务名（可选）</label>
          <input type="text" id="newTaskName" placeholder="如 GomeKu" title="区分实例，并作为产物子目录名">
        </div>
        <div class="jm-field" style="flex:0 0 auto;display:flex;gap:8px;align-items:flex-end">
          <button type="button" id="btnCheckPort" class="pm-btn">检测端口</button>
          <button type="button" id="btnStartJenkins" class="pm-btn pm-btn--primary">启动 Jenkins</button>
        </div>
      </div>
      <p id="portCheckResult" class="jm-hint"></p>
      <p id="startResult" class="jm-hint"></p>
    </div>
    <details class="jm-advanced">
      <summary>构建完成通知（可选）</summary>
      <div class="jm-notify-grid">
        <div class="jm-notify-card">
          <h4>飞书</h4>
          <label class="jm-label" for="newFeishuWebhook">Webhook URL</label>
          <input type="url" id="newFeishuWebhook" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx">
        </div>
        <div class="jm-notify-card">
          <h4>钉钉</h4>
          <label class="jm-label" for="newDingtalkWebhook">Webhook URL</label>
          <input type="url" id="newDingtalkWebhook" placeholder="https://oapi.dingtalk.com/robot/send?access_token=xxx">
        </div>
        <div class="jm-notify-card">
          <h4>企业微信</h4>
          <label class="jm-label" for="newWecomWebhook">Webhook URL</label>
          <input type="url" id="newWecomWebhook" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx">
        </div>
      </div>
    </details>
  </div>
</div>
<div class="jm-panel" data-jm-panel="unity" id="unity-catalog-wrap" hidden>
{_unity_catalog_module_html()}
</div>
<div class="jm-panel" data-jm-panel="env" id="jm-env" hidden>
  <div class="studio-config-panel">
    <h3>环境检查</h3>
    <ul class="jm-env-list">
      <li><strong>Java</strong>：{java_line}</li>
      <li><strong>Git</strong>：{git_line}</li>
      <li><strong>Jenkins war</strong>：{war_line}</li>
    </ul>
    <div class="jm-env-actions">
      <p class="jm-hint">一键部署（Mac 尝试 brew install openjdk@17；Windows 请按说明手动安装）。</p>
      <button type="button" id="btnDeployEnv" class="pm-btn pm-btn--primary">执行部署并查看日志</button>
      <pre id="deployLog" class="jm-deploy-log is-hidden"></pre>
    </div>
    <details class="jm-advanced">
      <summary>Mac / Windows 手动部署说明</summary>
      <pre class="jm-script-pre">{script_mac.replace('<', '&lt;').replace('>', '&gt;')}</pre>
      <pre class="jm-script-pre">{script_win.replace('<', '&lt;').replace('>', '&gt;')}</pre>
    </details>
  </div>
</div>
</section>
<script src="/static/admin/jenkins_manage.js?v=20261030-jm4"></script>
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
    dingtalk_webhook = (data.get('dingtalk_webhook') or '').strip()
    wecom_webhook = (data.get('wecom_webhook') or '').strip()
    instance_type = (data.get('instance_type') or 'general').strip()
    success, instance_id, err = jm.start_jenkins(
        int(port),
        started_by,
        task_name=task_name,
        feishu_webhook=feishu_webhook,
        dingtalk_webhook=dingtalk_webhook,
        wecom_webhook=wecom_webhook,
        instance_type=instance_type,
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
    """更新实例的 task_name 与通知 Webhook。"""
    data = request.get_json() or {}
    instance_id = (data.get('instance_id') or '').strip()
    if not instance_id:
        return jsonify({'success': False, 'error': '缺少 instance_id'})
    success, err = jm.update_instance(
        instance_id,
        task_name=data.get('task_name'),
        feishu_webhook=data.get('feishu_webhook'),
        dingtalk_webhook=data.get('dingtalk_webhook'),
        wecom_webhook=data.get('wecom_webhook'),
    )
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
    """编辑实例：任务名与多渠道通知 Webhook。"""
    instance_id = request.args.get('instance_id', '').strip()
    if not instance_id:
        return _jm_layout('<p class="jm-hint" style="color:#cf1322">缺少 instance_id</p>', '编辑实例')
    inst = jm.get_instance_by_id(instance_id)
    if not inst:
        return _jm_layout('<p class="jm-hint" style="color:#cf1322">未找到该实例</p>', '编辑实例')
    content = _jenkins_edit_html(instance_id, inst)
    return _jm_layout(content, '编辑 Jenkins 实例')


def _jenkins_edit_html(instance_id, inst):
    def _esc(v):
        return html.escape(str(v or ''), quote=True)

    itype = (inst.get('instance_type') or 'general').strip().lower()
    type_label = '商业热更发布' if itype == 'commercial' else '通用 APK 打包'
    return '''
<header class="pm-page-head">
  <div class="pm-page-head-copy"><div>
    <h1>编辑打包机实例</h1>
    <p>实例 ID: ''' + _esc(instance_id) + ''' · 端口 ''' + _esc(inst.get('port', '')) + ''' · ''' + type_label + '''</p>
  </div></div>
  <div class="pm-page-head-actions">
    <a class="pm-btn" href="/admin/jenkins">返回列表</a>
    <a class="pm-btn" href="/admin/jenkins/instance-log?instance_id=''' + _esc(instance_id) + '''">查看日志</a>
  </div>
</header>
<section class="studio-config-panel">
  <h3>实例属性</h3>
  <div class="jm-field-row">
    <div class="jm-field">
      <label class="jm-label" for="editTaskName">任务名</label>
      <input type="text" id="editTaskName" value="''' + _esc(inst.get('task_name')) + '''" placeholder="如 Gomoku">
      <p class="jm-hint">用于区分实例，并作为构建产物输出子目录名。</p>
    </div>
  </div>
  <h3 style="margin-top:20px">构建通知（可选）</h3>
  <p class="jm-hint">配置后，构建成功会向对应群机器人推送版本与下载链接。可只填其中一个或多个。</p>
  <div class="jm-notify-grid">
    <div class="jm-notify-card">
      <h4>飞书机器人</h4>
      <label class="jm-label" for="editFeishuWebhook">Webhook URL</label>
      <input type="url" id="editFeishuWebhook" value="''' + _esc(inst.get('feishu_webhook')) + '''" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx">
    </div>
    <div class="jm-notify-card">
      <h4>钉钉机器人</h4>
      <label class="jm-label" for="editDingtalkWebhook">Webhook URL</label>
      <input type="url" id="editDingtalkWebhook" value="''' + _esc(inst.get('dingtalk_webhook')) + '''" placeholder="https://oapi.dingtalk.com/robot/send?access_token=xxx">
    </div>
    <div class="jm-notify-card">
      <h4>企业微信机器人</h4>
      <label class="jm-label" for="editWecomWebhook">Webhook URL</label>
      <input type="url" id="editWecomWebhook" value="''' + _esc(inst.get('wecom_webhook')) + '''" placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx">
    </div>
  </div>
  <p class="jm-hint">Git、APP_NAME、Unity 运行时参数请在「项目管理」中配置，构建时自动注入。</p>
  <div style="margin-top:16px;display:flex;gap:8px;align-items:center">
    <button type="button" id="btnSaveEdit" class="pm-btn pm-btn--primary">保存</button>
    <span id="editResult" class="jm-hint" role="status">点击「保存」后结果将显示在此处。</span>
  </div>
</section>
<script>
(function(){
var instanceId = ''' + json.dumps(instance_id) + ''';
function _jmHeaders(isJson){
  var t=document.querySelector('meta[name="csrf-token"]');
  var h={}; if(isJson) h['Content-Type']='application/json';
  if(t&&t.content) h['X-CSRFToken']=t.content; return h;
}
function setEditResult(msg, isError){
  var el=document.getElementById('editResult');
  if(!el) return;
  el.textContent=msg;
  el.style.color=isError?'#cf1322':'#389e0d';
}
function doSave(){
  setEditResult('保存中…', false);
  var payload={
    instance_id: instanceId,
    task_name: (document.getElementById('editTaskName').value||'').trim(),
    feishu_webhook: (document.getElementById('editFeishuWebhook').value||'').trim(),
    dingtalk_webhook: (document.getElementById('editDingtalkWebhook').value||'').trim(),
    wecom_webhook: (document.getElementById('editWecomWebhook').value||'').trim()
  };
  fetch('/api/jenkins-manage/update',{method:'POST',headers:_jmHeaders(true),credentials:'same-origin',body:JSON.stringify(payload)})
  .then(function(r){return r.json();})
  .then(function(d){ if(d&&d.success) setEditResult('已保存',false); else setEditResult((d&&d.error)||'保存失败',true); })
  .catch(function(){ setEditResult('请求失败',true); });
}
var btn=document.getElementById('btnSaveEdit');
if(btn) btn.onclick=doSave;
})();
</script>
'''


def _colorize_jenkins_log(raw: str) -> str:
    """按行着色：ERROR/Exception 红、WARNING 黄、INFO 蓝、成功绿。"""
    import re

    lines_out = []
    for line in (raw or '').splitlines():
        esc = html.escape(line)
        low = line.lower()
        cls = ''
        if re.search(r'\b(error|exception|fatal|severe)\b', low) or 'traceback' in low or 'caused by:' in low:
            cls = 'jm-log-line--error'
        elif re.search(r'\b(warn(ing)?)\b', low):
            cls = 'jm-log-line--warn'
        elif re.search(r'\b(info|informational)\b', low):
            cls = 'jm-log-line--info'
        elif re.search(r'\b(success|started successfully|listening)\b', low):
            cls = 'jm-log-line--ok'
        if cls:
            lines_out.append('<span class="%s">%s</span>' % (cls, esc))
        else:
            lines_out.append(esc)
    return '\n'.join(lines_out)


@bp.route('/admin/jenkins/instance-log')
@admin_required('jenkins')
def instance_log_page():
    """查看指定 Jenkins 实例的运行日志（stdout/stderr），便于出问题时定位。"""
    instance_id = request.args.get('instance_id', '').strip()
    if not instance_id:
        return _jm_layout('<p class="jm-hint" style="color:#cf1322">缺少 instance_id</p>', 'Jenkins 运行日志')
    inst = jm.get_instance_by_id(instance_id)
    if not inst:
        return _jm_layout('<p class="jm-hint" style="color:#cf1322">未找到该实例</p>', 'Jenkins 运行日志')
    jenkins_home = jm.resolve_jenkins_home(inst)
    if not jenkins_home or not os.path.isdir(jenkins_home):
        return _jm_layout(
            '<p class="jm-hint" style="color:#cf1322">实例目录不存在：%s</p>' % html.escape(jenkins_home or '(空)'),
            'Jenkins 运行日志',
        )
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
        return _jm_layout(
            '<div class="jm-log-shell"><div class="jm-log-meta"><span>实例 %s · 端口 %s</span>'
            '<a href="/admin/jenkins">返回 Jenkins 管理</a></div>'
            '<pre class="jm-log-body">暂无运行日志（可能尚未启动或日志未生成）</pre></div>'
            % (html.escape(instance_id), html.escape(str(inst.get('port', '')))),
            'Jenkins 运行日志',
        )
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        return _jm_layout(
            '<p class="jm-hint" style="color:#cf1322">读取失败: %s</p>' % html.escape(str(e)),
            'Jenkins 运行日志',
        )
    max_chars = 512 * 1024
    truncated = False
    if len(content) > max_chars:
        content = content[-max_chars:]
        truncated = True
    colored = _colorize_jenkins_log(content)
    note = '（仅显示最后 %d 字节）' % max_chars if truncated else ''
    page = (
        '<header class="pm-page-head"><div class="pm-page-head-copy"><div>'
        '<h1>Jenkins 运行日志</h1>'
        '<p>实例 %s · 端口 %s %s</p></div></div>'
        '<div class="pm-page-head-actions">'
        '<a class="pm-btn" href="/admin/jenkins">返回列表</a>'
        '<a class="pm-btn" href="/admin/jenkins/edit?instance_id=%s">编辑实例</a>'
        '<a class="pm-btn pm-btn--primary" href="/admin/jenkins/instance-log?instance_id=%s">刷新</a>'
        '</div></header>'
        '<div class="jm-log-shell"><div class="jm-log-meta">'
        '<span>深色终端视图 · ERROR 红 / WARN 黄 / INFO 蓝</span>'
        '<a href="/admin/jenkins">返回 Jenkins 管理</a></div>'
        '<pre class="jm-log-body">%s</pre></div>'
    ) % (
        html.escape(instance_id),
        html.escape(str(inst.get('port', ''))),
        note,
        html.escape(instance_id),
        html.escape(instance_id),
        colored,
    )
    return _jm_layout(page, 'Jenkins 运行日志')


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
    instance_type_filter = (request.args.get('instance_type') or '').strip().lower()
    if instance_type_filter not in ('general', 'commercial'):
        instance_type_filter = ''
    instances = jm.list_instances()
    available = []
    seen = set()
    for inst in instances:
        iid = inst.get('id') or ''
        itype = (inst.get('instance_type') or 'general').strip().lower()
        if instance_type_filter and itype != instance_type_filter:
            continue
        url = jm.get_jenkins_url_for_instance(instance_id=iid)
        bdir = jm.get_builds_dir_for_instance(instance_id=iid)
        if not url or not bdir:
            continue
        status = (inst.get('status') or 'stopped').strip().lower()
        reachable = False
        health_message = ''
        building = False
        if status == 'running':
            try:
                st = jenkins_svc.fetch_jenkins_status(base_url=url, builds_dir=bdir, instance_id=iid)
                reachable = bool(st.get('ok'))
                health_message = st.get('message') or ''
                building = bool(st.get('building'))
                if reachable and building and iid not in include_ids:
                    continue
            except Exception as exc:
                health_message = str(exc)
        else:
            health_message = '实例已停止，选择后触发构建将尝试自动启动'
        row = dict(inst)
        row['reachable'] = reachable
        row['health_message'] = health_message
        available.append(row)
        seen.add(iid)
    for inst in instances:
        iid = inst.get('id') or ''
        if iid in include_ids and iid not in seen:
            itype = (inst.get('instance_type') or 'general').strip().lower()
            if instance_type_filter and itype != instance_type_filter:
                continue
            row = dict(inst)
            row['reachable'] = False
            row['health_message'] = '强制包含（健康检查未通过）'
            available.append(row)
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

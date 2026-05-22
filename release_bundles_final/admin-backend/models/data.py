# -*- coding: utf-8 -*-
"""APK 下载中心 - 数据层：加载/保存、业务辅助函数"""

import os
import re
import uuid
from datetime import datetime, timedelta
from collections import defaultdict
from difflib import SequenceMatcher

from flask import request, session
from config import Config, DATA_DIR
from utils import load_json, save_json

# 文件路径
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
PROJECTS_FILE = os.path.join(DATA_DIR, 'projects.json')
STATS_FILE = os.path.join(DATA_DIR, 'download_stats.json')
DOWNLOAD_EVENTS_FILE = os.path.join(DATA_DIR, 'download_events.json')
LOGIN_ATTEMPTS_FILE = os.path.join(DATA_DIR, 'login_attempts.json')
VERSIONS_FILE = os.path.join(DATA_DIR, 'versions.json')
CHANGELOG_FILE = os.path.join(DATA_DIR, 'changelog.json')
AUDIT_LOG_FILE = os.path.join(DATA_DIR, 'audit_log.json')
JENKINS_INSTANCES_FILE = os.path.join(DATA_DIR, 'jenkins_instances.json')
PROJECT_TASKS_FILE = os.path.join(DATA_DIR, 'project_tasks.json')
NOTIFICATIONS_FILE = os.path.join(DATA_DIR, 'notifications.json')
APPROVALS_FILE = os.path.join(DATA_DIR, 'approvals.json')
APPROVAL_RECORDS_FILE = os.path.join(DATA_DIR, 'approval_records.json')
SYSTEM_CONFIG_FILE = os.path.join(DATA_DIR, 'system_config.json')
REPORT_TEMPLATES_FILE = os.path.join(DATA_DIR, 'report_templates.json')
EXPORT_RECORDS_FILE = os.path.join(DATA_DIR, 'export_records.json')
USER_TASK_PLANS_FILE = os.path.join(DATA_DIR, 'user_task_plans.json')
PRODUCTS_FILE = os.path.join(DATA_DIR, 'products.json')
PRODUCT_MEDIA_DIR = os.path.join(DATA_DIR, 'product_media')
PROJECT_VERSIONS_FILE = os.path.join(DATA_DIR, 'project_versions.json')
CHANNELS_FILE = os.path.join(DATA_DIR, 'channels.json')

DOWNLOAD_EVENTS_MAX_DAYS = 365
NOTIFICATIONS_RETENTION_DAYS = 90
SUPPORTED_PACKAGE_EXTENSIONS = ('.apk', '.ipa')
PLATFORM_LABELS = {
    'android': 'Android',
    'ios': 'iOS',
}

# 内存数据（单进程内有效）
users_db = load_json(USERS_FILE, {
    'admin': {
        'password': __import__('hashlib').sha256('admin123'.encode()).hexdigest(),
        'role': 'super_admin',
        'created_at': datetime.now().isoformat(),
        'email': 'admin@example.com',
        'last_login': None
    }
})
projects_db = load_json(PROJECTS_FILE, {
    'RecycleTycoon': {
        'name': '垃圾回收站',
        'description': '垃圾回收站游戏',
        'created_at': datetime.now().isoformat(),
        'order': 1,
        'status': 'active'
    }
})
download_stats = load_json(STATS_FILE, {})
login_attempts = load_json(LOGIN_ATTEMPTS_FILE, {})
versions_db = load_json(VERSIONS_FILE, {})
changelog_db = load_json(CHANGELOG_FILE, {})
audit_log_db = load_json(AUDIT_LOG_FILE, [])
# project_tasks: { project_id: [ { id, title, content, assign_to_user, start_time, end_time, created_by, created_at, current_assignee, status, urgency (1-5), flow_log, comments, attachments } ] }
# flow_log: [ { type, from_user, to_user, from_role, to_role, status?, at, by } ]
# comments: [ { user, content, at } ]
project_tasks_db = load_json(PROJECT_TASKS_FILE, {})

# 通知：列表 [ { id, user, type, title, body, link, read_at, created_at, related_id, related_type } ]
notifications_db = load_json(NOTIFICATIONS_FILE, [])
# 审批单：列表 [ { id, type, status, applicant, target_type, target_id, reason, created_at, updated_at, approvers } ]
approvals_db = load_json(APPROVALS_FILE, [])
# 审批记录：{ approval_id: [ { approver, action, comment, at } ] }
approval_records_db = load_json(APPROVAL_RECORDS_FILE, {})
# 系统配置：{ key: { value, type, description, updated_at, updated_by } }
system_config_db = load_json(SYSTEM_CONFIG_FILE, {})
# 报表模板： [ { id, name, description, config, created_by, created_at } ]
report_templates_db = load_json(REPORT_TEMPLATES_FILE, [])
# 导出记录： [ { user, template_id, template_name, params, exported_at, format } ]
export_records_db = load_json(EXPORT_RECORDS_FILE, [])
# 用户任务规划：{ username: { "project_id:task_id": "today_todo"|"today_done"|"tomorrow_plan"|"backlog" } }
user_task_plans_db = load_json(USER_TASK_PLANS_FILE, {})
# 官网产品展示： [ { id, name, slug, intro, description, cover_image, gallery: [], video_url, project_id, order, created_at, updated_at } ]
products_db = load_json(PRODUCTS_FILE, [])
# 项目版本管理：{ project_id: [ { id, channel, version_name, version_code, apk_path, resource_path, config_path, jenkins_job_id, jenkins_params, notes, created_at, updated_at } ] }
# channel: dev|test|production -> 开发|测试|线上
project_versions_db = load_json(PROJECT_VERSIONS_FILE, {})
# 渠道配置： [ { id, name, description, order, apk_subdir, build_param } ] —— 用于版本渠道、下载中心筛选、构建参数等
_default_channels = [
    {'id': 'dev', 'name': '开发版', 'description': '内部开发、自测使用', 'order': 10, 'apk_subdir': 'dev', 'build_param': 'CHANNEL=dev'},
    {'id': 'test', 'name': '测试版', 'description': '功能联调、提测与回归测试使用', 'order': 20, 'apk_subdir': 'test', 'build_param': 'CHANNEL=test'},
    {'id': 'production', 'name': '线上版', 'description': '正式对外发布给用户的版本', 'order': 30, 'apk_subdir': '', 'build_param': 'CHANNEL=production'},
]
channels_db = load_json(CHANNELS_FILE, _default_channels)


def _normalize_version_platforms():
    changed = False
    if not isinstance(project_versions_db, dict):
        return changed
    for project_id, versions in list(project_versions_db.items()):
        if not isinstance(versions, list):
            continue
        for version in versions:
            if not isinstance(version, dict):
                continue
            platform = (version.get('platform') or '').strip().lower()
            if platform not in ('android', 'ios'):
                apk_path = version.get('apk_path') or ''
                ext = os.path.splitext(apk_path or '')[1].lower()
                version['platform'] = 'ios' if ext == '.ipa' else 'android'
                changed = True
    return changed


if _normalize_version_platforms():
    save_json(PROJECT_VERSIONS_FILE, project_versions_db)


def get_channels_for_project(project_id):
    """返回项目可用渠道列表。若项目配置了 channels 则只返回这些；否则返回全部。"""
    raw = channels_db if isinstance(channels_db, list) else []
    out = [c for c in raw if (c.get('id') or '').strip()]
    proj = projects_db.get(project_id) or {}
    allowed = proj.get('channels')
    if isinstance(allowed, list) and allowed:
        allowed_set = {str(a).strip() for a in allowed if str(a).strip()}
        out = [c for c in out if (c.get('id') or '').strip() in allowed_set]
    out.sort(key=lambda x: (int(x.get('order') or 0), x.get('id', '')))
    return out


def get_channel_by_id(channel_id):
    """根据 ID 获取渠道完整信息（含 apk_subdir、build_param）。"""
    raw = channels_db if isinstance(channels_db, list) else []
    for c in raw:
        if (c.get('id') or '').strip() == (channel_id or '').strip():
            return c
    return None


def save_products():
    save_json(PRODUCTS_FILE, products_db)


def save_project_tasks():
    save_json(PROJECT_TASKS_FILE, project_tasks_db)


def save_project_versions():
    save_json(PROJECT_VERSIONS_FILE, project_versions_db)


def load_jenkins_instances():
    """返回 Jenkins 实例列表 [{id, port, status, pid, jenkins_home, added_at, added_by, started_at, started_by}, ...]"""
    raw = load_json(JENKINS_INSTANCES_FILE, [])
    return raw if isinstance(raw, list) else []


def save_jenkins_instances(instances):
    save_json(JENKINS_INSTANCES_FILE, instances)


BUILD_VERSION_RECORDS_FILE = os.path.join(DATA_DIR, 'build_version_records.json')


def record_build_version(instance_id, build_number, version_id, project_id):
    """记录构建号与版本的关联，用于版本构建历史展示。"""
    records = load_json(BUILD_VERSION_RECORDS_FILE, [])
    if not isinstance(records, list):
        records = []
    records.append({
        'instance_id': instance_id or '',
        'build_number': int(build_number),
        'version_id': version_id or '',
        'project_id': project_id or '',
        'created_at': datetime.now().isoformat(),
    })
    # 只保留最近 500 条
    if len(records) > 500:
        records = records[-500:]
    save_json(BUILD_VERSION_RECORDS_FILE, records)


def get_build_records_for_version(version_id, instance_id=None):
    """获取某版本关联的构建记录，可选按实例筛选。返回按 build_number 降序。"""
    records = load_json(BUILD_VERSION_RECORDS_FILE, [])
    if not isinstance(records, list):
        return []
    vid = (version_id or '').strip()
    out = [r for r in records if (r.get('version_id') or '') == vid]
    if instance_id:
        iid = (instance_id or '').strip()
        out = [r for r in out if (r.get('instance_id') or '') == iid]
    out.sort(key=lambda x: x.get('build_number', 0), reverse=True)
    return out[:20]


def load_download_events():
    raw = load_json(DOWNLOAD_EVENTS_FILE, [])
    if not isinstance(raw, list):
        return []
    cutoff = (datetime.now() - timedelta(days=DOWNLOAD_EVENTS_MAX_DAYS)).strftime('%Y-%m-%d')
    return [e for e in raw if isinstance(e, dict) and e.get('date', '') >= cutoff]


def save_download_events(events):
    cutoff = (datetime.now() - timedelta(days=DOWNLOAD_EVENTS_MAX_DAYS)).strftime('%Y-%m-%d')
    trimmed = [e for e in events if isinstance(e, dict) and e.get('date', '') >= cutoff]
    save_json(DOWNLOAD_EVENTS_FILE, trimmed)


def record_download_event(filename, source=None, ip=None):
    try:
        events = load_download_events()
        e = {'filename': filename, 'date': datetime.now().strftime('%Y-%m-%d')}
        if source:
            e['source'] = source
        if ip:
            e['ip'] = ip
        events.append(e)
        save_download_events(events)
    except Exception as ex:
        get_logger().warning("记录下载事件失败: %s", ex)


def get_logger():
    return __import__('logging').getLogger(__name__)


def is_supported_package(filename):
    return os.path.splitext(filename or '')[1].lower() in SUPPORTED_PACKAGE_EXTENSIONS


def detect_platform(filename):
    ext = os.path.splitext(filename or '')[1].lower()
    if ext == '.ipa':
        return 'ios'
    return 'android'


def get_platform_label(platform):
    return PLATFORM_LABELS.get((platform or '').lower(), 'Unknown')


def iter_package_files(root_dir=None):
    root = os.path.normpath(root_dir or Config.APK_DIR)
    if not os.path.isdir(root):
        return
    for current_root, _, filenames in os.walk(root):
        for filename in filenames:
            if not is_supported_package(filename):
                continue
            full_path = os.path.join(current_root, filename)
            if not os.path.isfile(full_path):
                continue
            rel_path = os.path.relpath(full_path, root).replace('\\', '/')
            yield rel_path, full_path


def save_users():
    save_json(USERS_FILE, users_db)


def save_projects():
    save_json(PROJECTS_FILE, projects_db)


def save_stats():
    save_json(STATS_FILE, download_stats)


def save_login_attempts():
    save_json(LOGIN_ATTEMPTS_FILE, login_attempts)


def save_versions():
    save_json(VERSIONS_FILE, versions_db)


def save_channels():
    """保存渠道配置列表到 channels.json。"""
    save_json(CHANNELS_FILE, channels_db)


def save_changelog():
    save_json(CHANGELOG_FILE, changelog_db)


def save_audit_log():
    save_json(AUDIT_LOG_FILE, audit_log_db)


def get_current_tenant_id():
    """多租户：当前租户 ID，默认 'default'"""
    return session.get('tenant_id') or 'default'


def log_audit(action, details=""):
    entry = {
        'timestamp': datetime.now().isoformat(),
        'user': session.get('user', 'unknown'),
        'action': action,
        'details': details,
        'ip': request.remote_addr or '127.0.0.1'
    }
    audit_log_db.append(entry)
    save_audit_log()
    # SQLite 双写（商业级持久化）
    try:
        from config import Config
        from models.data import get_system_config
        use_sqlite = get_system_config('USE_SQLITE') or ''
        if str(use_sqlite).lower() in ('true', '1', 'yes') or getattr(Config, 'USE_SQLITE', False):
            from models.db import log_audit_db
            tenant = get_current_tenant_id()
            log_audit_db(tenant, entry['user'], action, details, entry['ip'])
    except Exception:
        pass


def save_notifications():
    save_json(NOTIFICATIONS_FILE, notifications_db)


def save_approvals():
    save_json(APPROVALS_FILE, approvals_db)


def save_approval_records():
    save_json(APPROVAL_RECORDS_FILE, approval_records_db)


def save_system_config():
    save_json(SYSTEM_CONFIG_FILE, system_config_db)


def save_report_templates():
    save_json(REPORT_TEMPLATES_FILE, report_templates_db)


def save_export_records():
    save_json(EXPORT_RECORDS_FILE, export_records_db)


def save_user_task_plans():
    save_json(USER_TASK_PLANS_FILE, user_task_plans_db)


def get_task_plan_key(project_id, task_id):
    return '%s:%s' % (project_id or '', task_id or '')


def set_task_plan(username, project_id, task_id, plan_type):
    """设置任务规划类型：today_todo, today_done, tomorrow_plan, backlog"""
    if not username:
        return
    plans = user_task_plans_db.get(username) or {}
    key = get_task_plan_key(project_id, task_id)
    if plan_type:
        plans[key] = plan_type
    else:
        plans.pop(key, None)
    user_task_plans_db[username] = plans
    save_user_task_plans()


def get_task_plan(username, project_id, task_id):
    """获取任务规划类型"""
    plans = user_task_plans_db.get(username) or {}
    return plans.get(get_task_plan_key(project_id, task_id), '')


def add_notification(user, ntype, title, body='', link='', related_id='', related_type=''):
    """添加一条通知，返回 id。"""
    nid = uuid.uuid4().hex[:16]
    notifications_db.append({
        'id': nid, 'user': user, 'type': ntype, 'title': title, 'body': body or title,
        'link': link, 'read_at': None, 'created_at': datetime.now().isoformat(),
        'related_id': related_id, 'related_type': related_type,
    })
    save_notifications()
    return nid


def get_notifications_for_user(username, type_filter=None, limit=100):
    """获取用户通知，未读优先，时间倒序。"""
    cutoff = (datetime.now() - timedelta(days=NOTIFICATIONS_RETENTION_DAYS)).strftime('%Y-%m-%d')
    out = [n for n in notifications_db if n.get('user') == username and (n.get('created_at') or '')[:10] >= cutoff]
    if type_filter:
        out = [n for n in out if n.get('type') == type_filter]
    out.sort(key=lambda x: (x.get('read_at') or '0', x.get('created_at') or ''), reverse=True)
    return out[:limit]


def get_system_config(key, default=None):
    """读取系统配置项。"""
    item = system_config_db.get(key)
    if not item or not isinstance(item, dict):
        return default
    return item.get('value', default)


def set_system_config(key, value, value_type='string', description='', username=''):
    """写入系统配置项。"""
    system_config_db[key] = {
        'value': value,
        'type': value_type,
        'description': description,
        'updated_at': datetime.now().isoformat(),
        'updated_by': username or session.get('user', ''),
    }
    save_system_config()


# 审批类型与默认审批人（管理员）
APPROVAL_TYPES = [
    ('version_publish', '版本发布'),
    ('delete_project', '删除项目'),
    ('delete_version', '删除版本'),
    ('delete_jenkins', '删除 Jenkins 实例'),
    ('batch_delete_tasks', '批量删除任务'),
    ('news_publish', '新闻发布'),
    ('welfare_publish', '福利发布'),
    ('forum_post_publish', '官方帖子发布'),
]


def get_approved_approval(atype, target_id):
    """获取已通过的审批单（用于高危操作前置校验）。target_id 需与创建时一致。"""
    tid = (target_id or '').strip()
    for a in approvals_db:
        if a.get('type') == atype and (a.get('target_id') or '').strip() == tid and a.get('status') == 'approved':
            return a
    return None


def create_approval(atype, applicant, target_type, target_id, reason='', project_id=''):
    """创建审批单，返回 id。"""
    aid = uuid.uuid4().hex[:16]
    resolved_project_id = resolve_project_id(project_id) or str(project_id or '').strip()
    approvals_db.append({
        'id': aid, 'type': atype, 'status': 'pending', 'applicant': applicant,
        'target_type': target_type, 'target_id': target_id, 'reason': reason or '',
        'project_id': resolved_project_id,
        'created_at': datetime.now().isoformat(), 'updated_at': datetime.now().isoformat(),
        'approvers': [],  # 可扩展为配置的审批人列表
    })
    save_approvals()
    return aid


def get_pending_approvals_for_user(username):
    """待当前用户审批的列表（管理员或配置的审批人）。"""
    role = (users_db.get(username) or {}).get('role', 'user')
    is_admin_user = role in ('super_admin', 'admin')
    out = []
    for a in approvals_db:
        if a.get('status') != 'pending':
            continue
        if is_admin_user:
            out.append(a)
        else:
            approvers = a.get('approvers') or []
            if username in approvers:
                out.append(a)
    out.sort(key=lambda x: x.get('created_at') or '', reverse=True)
    return out


def approve_or_reject(approval_id, username, action, comment=''):
    """审批通过或驳回。返回 (True, None) 或 (False, error_msg)。"""
    for a in approvals_db:
        if a.get('id') == approval_id:
            if a.get('status') != 'pending':
                return False, '该申请已处理'
            a['status'] = 'approved' if action == 'approve' else 'rejected'
            a['updated_at'] = datetime.now().isoformat()
            rec = {'approver': username, 'action': action, 'comment': comment or '', 'at': datetime.now().isoformat()}
            approval_records_db[approval_id] = approval_records_db.get(approval_id, []) + [rec]
            save_approvals()
            save_approval_records()
            return True, None
    return False, '审批单不存在'


def is_inner_network(ip):
    if not ip:
        return False
    for prefix in Config.INNER_NET:
        prefix = prefix.strip()
        if prefix and ip.startswith(prefix):
            return True
    return False


def check_login_attempts(ip):
    now = datetime.now().timestamp()
    if ip not in login_attempts:
        return True, 0
    attempts = login_attempts[ip]
    locked_until = attempts.get('locked_until', 0)
    if locked_until > now:
        return False, attempts.get('attempts', 0)
    if locked_until > 0 and locked_until <= now:
        login_attempts[ip] = {'attempts': 0, 'locked_until': 0}
        save_login_attempts()
    return True, attempts.get('attempts', 0)


def record_login_attempt(ip, success):
    now = datetime.now().timestamp()
    if ip not in login_attempts:
        login_attempts[ip] = {'attempts': 0, 'locked_until': 0}
    if success:
        login_attempts[ip] = {'attempts': 0, 'locked_until': 0}
        username = session.get('user')
        if username and username in users_db:
            users_db[username]['last_login'] = datetime.now().isoformat()
            save_users()
    else:
        login_attempts[ip]['attempts'] = login_attempts[ip].get('attempts', 0) + 1
        limit_val = get_system_config('LOGIN_ATTEMPTS_LIMIT')
        limit = int(limit_val) if limit_val is not None and str(limit_val).strip().isdigit() else Config.LOGIN_ATTEMPTS_LIMIT
        lockout_val = get_system_config('LOGIN_LOCKOUT_MINUTES')
        lockout = int(lockout_val) if lockout_val is not None and str(lockout_val).strip().isdigit() else Config.LOGIN_LOCKOUT_MINUTES
        if login_attempts[ip]['attempts'] >= limit:
            login_attempts[ip]['locked_until'] = now + (lockout * 60)
            get_logger().warning("IP %s 登录失败次数过多，已锁定 %s 分钟", ip, Config.LOGIN_LOCKOUT_MINUTES)
    save_login_attempts()


# ---------- 业务辅助 ----------
def extract_project_name(filename):
    base = os.path.splitext(os.path.basename(filename or ''))[0]
    project_token = base
    if '_' in base:
        project_token = base.split('_')[0]
    resolved = resolve_project_id(project_token)
    return resolved or project_token


def extract_version_from_filename(filename):
    base = os.path.splitext(os.path.basename(filename or ''))[0]
    parts = base.split('_')
    for p in reversed(parts):
        if re.match(r'^\d+\.\d+\.\d+', p):
            return p
    return base if parts else ''


def parse_apk_metadata(apk_path):
    try:
        filename = os.path.basename(apk_path)
        base_name = os.path.splitext(filename)[0].replace('_', ' ')
        version_match = re.search(r'(\d+\.\d+\.\d+)', filename)
        version = version_match.group(1) if version_match else '1.0'
        app_name = base_name.title()
        return {
            'package': f'com.example.{base_name.replace(" ", "").lower()}',
            'version': version,
            'app_name': app_name
        }
    except Exception as e:
        get_logger().warning("解析 APK 失败 %s: %s", apk_path, e)
        return None


def extract_package_info(filename, filepath):
    stat = os.stat(filepath)
    project_name = extract_project_name(filename)
    platform = detect_platform(filename)
    file_info = {
        'name': filename,
        'basename': os.path.basename(filename),
        'extension': os.path.splitext(filename)[1].lower(),
        'platform': platform,
        'platform_label': get_platform_label(platform),
        'size': stat.st_size,
        'size_mb': round(stat.st_size / 1024 / 1024, 1),
        'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
        'timestamp': stat.st_mtime,
        'download_count': download_stats.get(filename, download_stats.get(os.path.basename(filename), 0)),
        'project': project_name
    }
    metadata = parse_apk_metadata(filepath)
    if metadata:
        file_info.update(metadata)
    else:
        file_info['app_name'] = os.path.splitext(os.path.basename(filename))[0].replace('_', ' ').title()
        file_info['package'] = 'unknown'
        file_info['version'] = '1.0'
    return file_info


def extract_apk_info(filename, filepath):
    return extract_package_info(filename, filepath)


def get_project_apk_count(project_id):
    count = 0
    for filename, _ in iter_package_files():
        if extract_project_name(filename) == project_id:
            count += 1
    return count


def get_project_download_count(project_id):
    """本项目下所有包件的下载次数总和"""
    total = 0
    for filename, _ in iter_package_files():
        if extract_project_name(filename) == project_id:
            total += download_stats.get(filename, download_stats.get(os.path.basename(filename), 0))
    return total


def get_version_download_count(project_id, version):
    """某版本对应 APK 的下载次数。仅基于 apk_path 对应的文件，无则返回 0。"""
    if not project_id:
        return 0
    apk_path = (version.get('apk_path') or '').strip()
    if not apk_path:
        return 0
    if apk_path.startswith('/'):
        if not os.path.isfile(apk_path):
            return 0
        key = os.path.basename(apk_path)
    else:
        full = os.path.join(Config.APK_DIR, apk_path.replace('/', os.path.sep))
        if not os.path.isfile(full):
            return 0
        key = apk_path
    return download_stats.get(key, download_stats.get(os.path.basename(apk_path), 0))


def get_channel_for_apk(project_id, filename, project_versions=None):
    """根据 project_versions 匹配 filename，返回渠道标签；无匹配返回空"""
    versions = project_versions if project_versions is not None else (project_versions_db.get(project_id) or [])
    if not isinstance(versions, list):
        return ''
    ver_from_file = extract_version_from_filename(filename)
    fn_lower = filename.lower()
    proj_lower = (project_id or '').lower()
    for v in versions:
        platform = (v.get('platform') or '').strip().lower()
        if platform in ('android', 'ios') and platform != detect_platform(filename):
            continue
        vn = (v.get('version_name') or '').lower()
        vc = (v.get('version_code') or '').lower()
        apk_path = (v.get('apk_path') or '').strip().lower()
        if apk_path and apk_path in fn_lower:
            return v.get('channel', '') or ''
        if vn and vn in fn_lower:
            return v.get('channel', '') or ''
        if vc and vc in fn_lower:
            return v.get('channel', '') or ''
        if ver_from_file and (vn == ver_from_file.lower() or vc == ver_from_file.lower()):
            return v.get('channel', '') or ''
    return ''


def version_is_recommended(project_id, version):
    """版本是否被标记为推荐：版本级 changelog 或任一匹配 APK 的 changelog"""
    if not project_id:
        return False
    vid = version.get('id') or ''
    vkey = 'version:' + project_id + ':' + vid
    vch = changelog_db.get(vkey)
    if isinstance(vch, dict) and vch.get('recommended'):
        return True
    apk_path = (version.get('apk_path') or '').strip()
    if apk_path and os.path.sep not in apk_path and not apk_path.startswith('/'):
        ch = changelog_db.get(apk_path)
        if isinstance(ch, dict) and ch.get('recommended'):
            return True
    if not os.path.isdir(Config.APK_DIR):
        return False
    ver_name = (version.get('version_name') or '').lower()
    ver_code = (version.get('version_code') or '').lower()
    for fname, _ in iter_package_files():
        if extract_project_name(fname) != project_id:
            continue
        fn_lower = fname.lower()
        match = (ver_name and ver_name in fn_lower) or (ver_code and ver_code in fn_lower) or (not ver_name and not ver_code)
        if match:
            ch = changelog_db.get(fname)
            if isinstance(ch, dict) and ch.get('recommended'):
                return True
    return False


def get_changelog_for_file(filename):
    """获取文件对应的 Changelog：优先按文件名，其次按匹配的版本配置（version:project:vid）"""
    raw = changelog_db.get(filename)
    if raw is not None:
        if isinstance(raw, dict):
            return raw.get('text', ''), bool(raw.get('recommended'))
        return (str(raw)[:500], False)
    project_id = extract_project_name(filename)
    versions = project_versions_db.get(project_id) or []
    if not isinstance(versions, list):
        return '', False
    ver_name = ''
    ver_code = ''
    for v in versions:
        vkey = 'version:' + project_id + ':' + (v.get('id') or '')
        vch = changelog_db.get(vkey)
        if not vch or not isinstance(vch, dict):
            continue
        vn = (v.get('version_name') or '').lower()
        vc = (v.get('version_code') or '').lower()
        apk_path = (v.get('apk_path') or '').strip().lower()
        fn_lower = filename.lower()
        if apk_path and apk_path in fn_lower:
            return vch.get('text', ''), bool(vch.get('recommended'))
        if vn and vn in fn_lower:
            return vch.get('text', ''), bool(vch.get('recommended'))
        if vc and vc in fn_lower:
            return vch.get('text', ''), bool(vch.get('recommended'))
    return '', False


def version_has_apk(project_id, version):
    """判断版本是否有对应 APK 已落盘。仅基于 apk_path 检查，避免误匹配其他已存在的同名 APK。"""
    if not project_id:
        return False
    apk_path = (version.get('apk_path') or '').strip()
    if not apk_path:
        return False
    if apk_path.startswith('/'):
        return os.path.isfile(apk_path)
    full = os.path.join(Config.APK_DIR, apk_path.replace('/', os.path.sep))
    return os.path.isfile(full)


def get_version_platform(version):
    platform = (version.get('platform') or '').strip().lower()
    if platform in ('android', 'ios'):
        return platform
    return detect_platform(version.get('apk_path') or '')


def _normalize_project_token(value):
    text = str(value or '').strip().lower()
    if not text:
        return ''
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', text)


def resolve_project_id(project_ref):
    """Resolve a project reference to the canonical project id."""
    project_ref = str(project_ref or '').strip()
    if not project_ref or not isinstance(projects_db, dict):
        return ''
    if project_ref in projects_db:
        return project_ref
    lowered = project_ref.lower()
    normalized_ref = _normalize_project_token(project_ref)
    best_match = ('', 0.0)
    for project_id, project in projects_db.items():
        payload = project if isinstance(project, dict) else {}
        aliases_raw = payload.get('aliases') or payload.get('alias') or []
        if isinstance(aliases_raw, str):
            aliases_raw = [part.strip() for part in aliases_raw.split(',') if part.strip()]
        elif not isinstance(aliases_raw, (list, tuple, set)):
            aliases_raw = []
        aliases = [
            str(project_id or '').strip(),
            str(payload.get('name') or '').strip(),
            str(payload.get('name_en') or '').strip(),
        ] + [str(alias or '').strip() for alias in aliases_raw]
        for alias in aliases:
            if alias and (alias == project_ref or alias.lower() == lowered):
                return str(project_id)
            normalized_alias = _normalize_project_token(alias)
            if normalized_ref and normalized_alias and normalized_ref == normalized_alias:
                return str(project_id)
            if normalized_ref and normalized_alias:
                ratio = SequenceMatcher(None, normalized_ref, normalized_alias).ratio()
                if ratio > best_match[1]:
                    best_match = (str(project_id), ratio)
    # Fuzzy fallback for legacy typo / transliteration drift (e.g. GameKu vs GomeKu).
    if best_match[0] and best_match[1] >= 0.82:
        return best_match[0]
    return ''


def get_project_record(project_ref):
    project_id = resolve_project_id(project_ref)
    if not project_id:
        return None, None
    payload = projects_db.get(project_id)
    if not isinstance(payload, dict):
        payload = {}
    return project_id, payload


def normalize_public_url(value):
    """Normalize external portal URL input for cross-server routing."""
    text = str(value or '').strip()
    if not text:
        return ''
    text = text.replace('\\', '/')
    if text.startswith('//'):
        text = 'https:' + text
    if not re.match(r'^https?://', text, re.IGNORECASE):
        text = 'https://' + text
    return text.rstrip('/')


def get_project_portal_urls(project_ref=''):
    """Resolve project-level portal domains with global config fallback."""
    project_id, project = get_project_record(project_ref)
    project = project or {}
    player_public_url = normalize_public_url(project.get('player_public_url'))
    forum_public_url = normalize_public_url(project.get('forum_public_url'))
    admin_public_url = normalize_public_url(project.get('admin_public_url'))
    if not player_public_url:
        player_public_url = normalize_public_url(getattr(Config, 'PLAYER_PUBLIC_URL', ''))
    if not forum_public_url:
        forum_public_url = normalize_public_url(getattr(Config, 'FORUM_PUBLIC_URL', ''))
    if not admin_public_url:
        admin_public_url = normalize_public_url(getattr(Config, 'ADMIN_PUBLIC_URL', ''))
    return {
        'project_id': project_id or '',
        'player_public_url': player_public_url,
        'forum_public_url': forum_public_url,
        'admin_public_url': admin_public_url,
    }


def resolve_project_id_for_product(product):
    if not isinstance(product, dict):
        return ''
    raw_project = product.get('project_id')
    raw_resolved = resolve_project_id(raw_project)
    if raw_resolved:
        return raw_resolved
    candidates = [
        product.get('name'),
        product.get('title'),
        product.get('name_en'),
        product.get('slug'),
        product.get('intro'),
    ]
    for candidate in candidates:
        project_id = resolve_project_id(candidate)
        if project_id:
            return project_id
    # Last-resort compatibility for old datasets with a single project.
    if isinstance(projects_db, dict) and len(projects_db) == 1:
        return next(iter(projects_db.keys()))
    return ''


def can_view_project(project_id, username):
    """用户是否可查看该项目（管理员、创建者、编辑者、查看者均可）。旧项目无 created_by/viewers/editors 时视为全员可查看。"""
    if not username:
        return False
    role = (users_db.get(username) or {}).get('role', 'user')
    if role in ('super_admin', 'admin'):
        return True
    if project_id not in projects_db:
        return False
    p = projects_db[project_id]
    created_by = p.get('created_by')
    editors = p.get('editors') or []
    viewers = p.get('viewers') or []
    # 旧项目：无创建者且未配置查看/编辑名单，视为所有有模块权限的用户可查看
    if not created_by and not editors and not viewers:
        return True
    if created_by == username:
        return True
    if username in editors or username in viewers:
        return True
    return False


def can_edit_project(project_id, username):
    """用户是否可编辑该项目（管理员、创建者、编辑者）。旧项目仅管理员可编辑。"""
    if not username:
        return False
    role = (users_db.get(username) or {}).get('role', 'user')
    if role in ('super_admin', 'admin'):
        return True
    if project_id not in projects_db:
        return False
    p = projects_db[project_id]
    created_by = p.get('created_by')
    editors = p.get('editors') or []
    if not created_by and not editors:
        return False  # 旧项目仅管理员可编辑
    if created_by == username:
        return True
    if username in editors:
        return True
    return False


def get_total_downloads():
    return sum(download_stats.values())


def get_active_projects_count():
    active = set()
    for filename, _ in iter_package_files():
        active.add(extract_project_name(filename))
    return len(active)

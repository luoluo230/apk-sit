# -*- coding: utf-8 -*-
"""统一权限与鉴权能力。"""

from functools import wraps

from flask import abort, redirect, session, url_for

from models.data import users_db

ADMIN_MODULES = [
    ('user_management', '用户与权限', True),
    ('projects', '项目与工作流', False),
    ('community', '玩家生态与内容运营', False),
    ('build', '构建管理', False),
    ('dashboard', '数据总览仪表盘', False),
    ('versions', '版本与发布管理', False),
    ('docs', '文档与知识库', False),
    ('jenkins', 'Jenkins 实例管理', False),
    ('audit_log', '审计与安全日志', False),
    ('notifications', '通知与消息中心', False),
    ('approval', '审批与发布管控', False),
    ('gm_ops', 'GM运营中心', False),
    ('reports', '报表中心', False),
    ('system_settings', '系统与安全设置', True),
]

ALL_MODULES_EXCEPT_USER_MANAGEMENT = [m[0] for m in ADMIN_MODULES if m[0] != 'user_management']


def current_user_info():
    username = session.get('user')
    if not username or username not in users_db:
        return None
    return users_db[username]


def is_super_admin_or_admin():
    info = current_user_info()
    return bool(info and info.get('role') in ('super_admin', 'admin'))


def has_scope(scope):
    info = current_user_info()
    if not info:
        return False
    if info.get('role') in ('super_admin', 'admin'):
        return True
    scopes = info.get('allowed_scopes') or []
    if isinstance(scopes, list):
        return scope in scopes or '*' in scopes
    try:
        parts = [s.strip() for s in str(scopes).split(',') if s.strip()]
        return scope in parts
    except Exception:
        return False


def can_access_module(module_id):
    info = current_user_info()
    if not info:
        return False
    role = info.get('role', 'user')
    if role in ('super_admin', 'admin'):
        return True
    if module_id in ('user_management', 'system_settings'):
        return False
    allowed = info.get('allowed_modules') or []
    if '*' in allowed or (isinstance(allowed, list) and '*' in allowed):
        return True
    return module_id in (allowed or [])


def get_visible_modules():
    info = current_user_info()
    if not info:
        return []
    role = info.get('role', 'user')
    if role in ('super_admin', 'admin'):
        return list(ADMIN_MODULES)
    allowed = info.get('allowed_modules') or []
    if '*' in allowed or (isinstance(allowed, list) and '*' in allowed):
        return [m for m in ADMIN_MODULES if not m[2]]
    return [m for m in ADMIN_MODULES if not m[2] and m[0] in allowed]


def _ensure_logged_in():
    if 'user' not in session:
        return False
    info = users_db.get(session['user'])
    if not info:
        return False
    if info.get('disabled'):
        session.pop('user', None)
        abort(403)
    return True


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not _ensure_logged_in():
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(module_id=None):
    if callable(module_id):
        return admin_required()(module_id)

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not _ensure_logged_in():
                return redirect(url_for('auth.login'))
            info = users_db.get(session['user']) or {}
            if info.get('role') in ('super_admin', 'admin'):
                return f(*args, **kwargs)
            if module_id == 'user_management':
                abort(403)
            if module_id is None:
                if not get_visible_modules():
                    abort(403)
                return f(*args, **kwargs)
            if not can_access_module(module_id):
                abort(403)
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def admin_required_any(*module_ids):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not _ensure_logged_in():
                return redirect(url_for('auth.login'))
            info = users_db.get(session['user']) or {}
            if info.get('role') in ('super_admin', 'admin'):
                return f(*args, **kwargs)
            for module_id in module_ids:
                if can_access_module(module_id):
                    return f(*args, **kwargs)
            abort(403)

        return decorated_function

    return decorator


def is_admin():
    if not session.get('user') or session['user'] not in users_db:
        return False
    return len(get_visible_modules()) > 0

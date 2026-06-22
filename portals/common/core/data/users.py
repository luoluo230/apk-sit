# -*- coding: utf-8 -*-
"""User accounts and login attempt tracking."""

from datetime import datetime

from flask import session

from config import Config
from data._store import LOGIN_ATTEMPTS_FILE, USERS_FILE, get_logger, load_document, save_document

users_db = load_document(USERS_FILE, {
    'admin': {
        'password': __import__('hashlib').sha256('admin123'.encode()).hexdigest(),
        'role': 'super_admin',
        'created_at': datetime.now().isoformat(),
        'email': 'admin@example.com',
        'last_login': None
    }
})
login_attempts = load_document(LOGIN_ATTEMPTS_FILE, {})


def save_users():
    save_document(USERS_FILE, users_db)


def save_login_attempts():
    save_document(LOGIN_ATTEMPTS_FILE, login_attempts)


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
    from data.settings import get_system_config

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

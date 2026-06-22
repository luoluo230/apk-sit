# -*- coding: utf-8 -*-
"""Audit log persistence."""

from datetime import datetime

from flask import request, session

from data._store import AUDIT_LOG_FILE, load_document, save_document

audit_log_db = load_document(AUDIT_LOG_FILE, [])


def save_audit_log():
    save_document(AUDIT_LOG_FILE, audit_log_db)


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
        from data.settings import get_system_config

        use_sqlite = get_system_config('USE_SQLITE') or ''
        if str(use_sqlite).lower() in ('true', '1', 'yes') or getattr(Config, 'USE_SQLITE', False):
            from models.db import log_audit_db

            tenant = get_current_tenant_id()
            log_audit_db(tenant, entry['user'], action, details, entry['ip'])
    except Exception:
        pass

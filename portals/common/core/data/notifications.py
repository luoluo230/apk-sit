# -*- coding: utf-8 -*-
"""Notifications."""

import uuid
from datetime import datetime, timedelta

from data._store import NOTIFICATIONS_FILE, NOTIFICATIONS_RETENTION_DAYS, load_document, save_document

notifications_db = load_document(NOTIFICATIONS_FILE, [])


def save_notifications():
    save_document(NOTIFICATIONS_FILE, notifications_db)


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

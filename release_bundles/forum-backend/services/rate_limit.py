# -*- coding: utf-8 -*-
"""API 限流（防暴力破解、商业级）"""

import time
from collections import defaultdict
from threading import Lock

# key -> [(timestamp, count), ...]
_store = defaultdict(list)
_lock = Lock()
# 配置：每窗口最多请求数、窗口秒数
LOGIN_LIMIT = 10
LOGIN_WINDOW = 60
API_LIMIT = 100
API_WINDOW = 60
FORUM_POST_LIMIT = 8
FORUM_POST_WINDOW = 300
FORUM_COMMENT_LIMIT = 20
FORUM_COMMENT_WINDOW = 300


def _clean_old(entries, window):
    now = time.time()
    return [(t, c) for t, c in entries if now - t < window]


def check_rate_limit(key, limit, window):
    """
    检查是否超限。返回 (allowed, retry_after_seconds)。
    key 通常为 ip 或 ip:username
    """
    with _lock:
        entries = _store[key]
        entries = _clean_old(entries, window)
        now = time.time()
        total = sum(c for _, c in entries)
        if total >= limit:
            oldest = min(t for t, _ in entries) if entries else now
            retry_after = int(window - (now - oldest))
            retry_after = max(1, min(retry_after, window))
            return False, retry_after
        entries.append((now, 1))
        _store[key] = entries[-500:]  # 保留最近 500 条
        return True, 0


def rate_limit_login():
    """登录接口限流：每 IP 10 次/分钟"""
    from flask import request
    ip = request.remote_addr or '0.0.0.0'
    return check_rate_limit('login:' + ip, LOGIN_LIMIT, LOGIN_WINDOW)


def rate_limit_api(key_suffix=''):
    """通用 API 限流"""
    from flask import request
    ip = request.remote_addr or '0.0.0.0'
    return check_rate_limit('api:' + ip + (':' + key_suffix if key_suffix else ''), API_LIMIT, API_WINDOW)


def rate_limit_forum_post():
    from flask import request
    ip = request.remote_addr or '0.0.0.0'
    return check_rate_limit('forum_post:' + ip, FORUM_POST_LIMIT, FORUM_POST_WINDOW)


def rate_limit_forum_comment():
    from flask import request
    ip = request.remote_addr or '0.0.0.0'
    return check_rate_limit('forum_comment:' + ip, FORUM_COMMENT_LIMIT, FORUM_COMMENT_WINDOW)

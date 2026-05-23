# -*- coding: utf-8 -*-
"""Webhook 通知（构建完成、版本发布等事件）"""

import json
import threading
import urllib.request
import urllib.error
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_webhook_url():
    from models.data import get_system_config
    return (get_system_config('webhook_url') or '').strip()


def fire_webhook(event_type, payload):
    """异步发送 Webhook，不阻塞主流程"""
    url = _get_webhook_url()
    if not url or not url.startswith('http'):
        return
    data = {
        'event': event_type,
        'payload': payload,
        'timestamp': datetime.now().isoformat(),
    }
    def _send():
        try:
            req = urllib.request.Request(
                url, data=json.dumps(data).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                logger.info('Webhook %s ok: %s', event_type, r.status)
        except Exception as e:
            logger.warning('Webhook %s failed: %s', event_type, e)
    threading.Thread(target=_send, daemon=True).start()

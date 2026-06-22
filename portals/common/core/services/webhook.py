# -*- coding: utf-8 -*-
"""Webhook 通知（构建完成、版本发布等事件）"""

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime

logger = logging.getLogger(__name__)


def _get_webhook_url():
    from models.data import get_system_config
    return (get_system_config('webhook_url') or '').strip()


def _get_feishu_webhook_url():
    from models.data import get_system_config
    url = (get_system_config('webhook_feishu_url') or os.getenv('WEBHOOK_FEISHU_URL') or '').strip()
    return url


def _get_dingtalk_webhook_url():
    from models.data import get_system_config
    url = (get_system_config('webhook_dingtalk_url') or os.getenv('WEBHOOK_DINGTALK_URL') or '').strip()
    return url


def _post_json(url, payload, timeout=10):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json; charset=utf-8'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status


def send_feishu(title, content, url=None):
    """Send Feishu interactive card webhook (async when called from fire_*)."""
    target = (url or _get_feishu_webhook_url() or '').strip()
    if not target.startswith('http'):
        return False
    payload = {
        'msg_type': 'interactive',
        'card': {
            'header': {'title': {'tag': 'plain_text', 'content': str(title or '通知')}},
            'elements': [{'tag': 'div', 'text': {'tag': 'plain_text', 'content': str(content or '')}}],
        },
    }
    try:
        status = _post_json(target, payload)
        logger.info('Feishu webhook ok: %s', status)
        return True
    except Exception as exc:
        logger.warning('Feishu webhook failed: %s', exc)
        return False


def send_dingtalk(title, content, url=None):
    """Send DingTalk markdown robot message."""
    target = (url or _get_dingtalk_webhook_url() or '').strip()
    if not target.startswith('http'):
        return False
    text = f"### {title}\n\n{content}"
    payload = {'msgtype': 'markdown', 'markdown': {'title': str(title or '通知'), 'text': text}}
    try:
        status = _post_json(target, payload)
        logger.info('DingTalk webhook ok: %s', status)
        return True
    except Exception as exc:
        logger.warning('DingTalk webhook failed: %s', exc)
        return False


def fire_feishu(title, content, url=None):
    threading.Thread(target=lambda: send_feishu(title, content, url=url), daemon=True).start()


def fire_dingtalk(title, content, url=None):
    threading.Thread(target=lambda: send_dingtalk(title, content, url=url), daemon=True).start()


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

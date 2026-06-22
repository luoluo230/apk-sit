# -*- coding: utf-8 -*-
"""Distribution channel configuration."""

from data._store import CHANNELS_FILE, load_document, save_document

_default_channels = [
    {'id': 'dev', 'name': '开发版', 'description': '内部开发、自测使用', 'order': 10, 'apk_subdir': 'dev', 'build_param': 'CHANNEL=dev'},
    {'id': 'test', 'name': '测试版', 'description': '功能联调、提测与回归测试使用', 'order': 20, 'apk_subdir': 'test', 'build_param': 'CHANNEL=test'},
    {'id': 'production', 'name': '线上版', 'description': '正式对外发布给用户的版本', 'order': 30, 'apk_subdir': '', 'build_param': 'CHANNEL=production'},
]
channels_db = load_document(CHANNELS_FILE, _default_channels)


def save_channels():
    """保存渠道配置列表到 channels.json。"""
    save_document(CHANNELS_FILE, channels_db)


def get_channels_for_project(project_id):
    """返回项目可用渠道列表。若项目配置了 channels 则只返回这些；否则返回全部。"""
    from data.projects import projects_db

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

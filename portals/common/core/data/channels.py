# -*- coding: utf-8 -*-
"""Distribution channel configuration."""

from data._store import CHANNELS_FILE, load_document, save_document
from repositories.registry._proxies import ChannelsDbProxy
from repositories.registry.channel_repo import get_channel_repository

_default_channels = [
    {'id': 'dev', 'name': '开发版', 'description': '内部开发、自测使用', 'order': 10, 'apk_subdir': 'dev', 'build_param': 'CHANNEL=dev'},
    {'id': 'test', 'name': '测试版', 'description': '功能联调、提测与回归测试使用', 'order': 20, 'apk_subdir': 'test', 'build_param': 'CHANNEL=test'},
    {'id': 'production', 'name': '线上版', 'description': '正式对外发布给用户的版本', 'order': 30, 'apk_subdir': '', 'build_param': 'CHANNEL=production'},
]
channels_db = ChannelsDbProxy()


def _ensure_default_channels():
    if get_channel_repository().list():
        return
    get_channel_repository().replace_all(list(_default_channels))


_ensure_default_channels()


def save_channels():
    """Persist channel list via registry repository."""
    get_channel_repository()._mirror_all()


def get_project_assigned_channel_ids(project_id: str) -> list:
    """返回项目白名单渠道 ID；未配置白名单时视为全局渠道库全部可用。"""
    from data.projects import projects_db

    proj = projects_db.get(project_id) or {}
    raw = proj.get('channels')
    if isinstance(raw, list) and raw:
        return [str(x).strip() for x in raw if str(x).strip()]
    return [
        str(c.get('id') or '').strip()
        for c in (channels_db if isinstance(channels_db, list) else [])
        if str(c.get('id') or '').strip()
    ]


def get_disabled_channel_ids(project_id: str) -> list:
    """返回项目内已禁用的渠道 ID（仍在白名单，不参与交付线/发布）。"""
    from data.projects import projects_db

    proj = projects_db.get(project_id) or {}
    raw = proj.get('disabled_channels')
    if not isinstance(raw, list):
        return []
    assigned = set(get_project_assigned_channel_ids(project_id))
    return [str(x).strip() for x in raw if str(x).strip() and str(x).strip() in assigned]


def is_channel_enabled_for_project(project_id: str, channel_id: str) -> bool:
    cid = str(channel_id or '').strip()
    if not cid:
        return False
    return cid not in set(get_disabled_channel_ids(project_id))


def get_channels_for_project(project_id, enabled_only=True):
    """返回项目可用渠道列表。若项目配置了 channels 则只返回这些；否则返回全部。
    enabled_only=True 时排除项目内已禁用的渠道。"""
    out = []
    allowed_ids = set(get_project_assigned_channel_ids(project_id))
    disabled_ids = set(get_disabled_channel_ids(project_id)) if enabled_only else set()
    raw = channels_db if isinstance(channels_db, list) else []
    for c in raw:
        cid = (c.get('id') or '').strip()
        if not cid or cid not in allowed_ids:
            continue
        if enabled_only and cid in disabled_ids:
            continue
        out.append(c)
    out.sort(key=lambda x: (int(x.get('order') or 0), x.get('id', '')))
    return out


def get_channel_by_id(channel_id):
    """根据 ID 获取渠道完整信息（含 apk_subdir、build_param）。"""
    raw = channels_db if isinstance(channels_db, list) else []
    for c in raw:
        if (c.get('id') or '').strip() == (channel_id or '').strip():
            return c
    return None

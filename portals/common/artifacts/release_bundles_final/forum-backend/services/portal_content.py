# -*- coding: utf-8 -*-
"""Portal copy and brand configuration."""

import json
import os

from config import DATA_DIR
from services.media_library import normalize_local_media_url, normalize_local_media_urls
from utils import load_json, save_json

PLAYER_PORTAL_FILE = os.path.join(DATA_DIR, "player_portal_content.json")
DEV_PORTAL_FILE = os.path.join(DATA_DIR, "developer_portal_content.json")

DEFAULT_PLAYER_PORTAL = {
    "site_name": "星云游戏站",
    "site_subtitle": "Nebula Game Studio",
    "logo_icon": "fa-gamepad",
    "layout_mode": "flow",
    "hero_image_url": "",
    "hero_video_url": "",
    "hero_gallery_urls": [],
    "nav_about": "公司简介",
    "nav_games": "游戏产品",
    "hero_badge": "面向玩家的项目官网入口",
    "hero_title": "让每一款游戏，\n都有自己的舞台。",
    "hero_description": "星云游戏站专注于打造高品质、长线运营的游戏产品。玩家可以先认识品牌，再快速进入感兴趣的项目详情、新闻、福利和社区。",
    "hero_button": "浏览游戏产品",
    "games_title": "游戏产品入口",
    "games_description": "点击游戏卡片进入详情页，查看项目介绍、新闻公告、福利活动与下载入口。",
    "featured_product_ids": "",
    "visible_product_ids": "",
    "home_modules": [
        {"type": "hero", "title": "主视觉", "enabled": True, "order": 0, "size": "full"},
        {"type": "products", "title": "产品入口", "enabled": True, "order": 1},
        {"type": "news", "title": "新闻公告", "enabled": True, "order": 2},
        {"type": "welfare", "title": "福利中心", "enabled": True, "order": 3},
        {"type": "forum", "title": "玩家论坛", "enabled": True, "order": 4},
        {"type": "company", "title": "公司简介", "enabled": True, "order": 5},
        {"type": "media", "title": "视觉展示", "enabled": True, "order": 6},
        {"type": "timeline", "title": "公司历程", "enabled": True, "order": 7},
    ],
}

DEFAULT_DEV_PORTAL = {
    "site_name": "星云游戏站",
    "site_subtitle": "高品质游戏品牌工作台",
    "logo_icon": "fa-gamepad",
    "layout_mode": "flow",
    "hero_image_url": "",
    "hero_video_url": "",
    "hero_gallery_urls": [],
    "nav_games": "游戏阵容",
    "nav_showcase": "视觉展示",
    "nav_news": "新闻公告",
    "nav_welfare": "福利中心",
    "nav_forum": "玩家论坛",
    "nav_download": "下载中心",
    "hero_badge": "面向长线运营的游戏官网与发布门户",
    "hero_title": "打造让玩家\n一眼记住的游戏世界",
    "hero_description": "用更成熟的视觉包装、内容运营与发布链路，承接 Android / iOS 游戏产品、版本节奏和玩家社区。",
    "primary_button": "查看游戏",
    "secondary_button": "进入下载中心",
    "workspace_badge": "Studio Workspace",
    "workspace_title": "为项目、运营与发布准备的统一工作台。",
    "workspace_intro": "这里是星云游戏站的内部入口。登录后按角色进入运营、开发、运维与配置分区，不再把后台能力暴露在玩家官网页面里。",
    "featured_product_ids": "",
    "visible_product_ids": "",
    "home_modules": [
        {"type": "hero", "title": "主视觉", "enabled": True, "order": 0, "size": "full"},
        {"type": "products", "title": "产品入口", "enabled": True, "order": 1},
        {"type": "company", "title": "公司简介", "enabled": True, "order": 2},
        {"type": "media", "title": "视觉展示", "enabled": True, "order": 3},
        {"type": "timeline", "title": "公司历程", "enabled": True, "order": 4},
    ],
}


def _clean_text(value, fallback=""):
    text = str(value or "").strip()
    if not text:
        return fallback
    if "�" in text:
        return fallback or ""
    if text.count("?") / max(len(text), 1) >= 0.35:
        return fallback or ""
    return text


def _merge(defaults, current):
    merged = dict(defaults)
    if isinstance(current, dict):
        for key, value in current.items():
            if value not in (None, ""):
                if isinstance(value, (list, dict)):
                    merged[key] = value
                else:
                    merged[key] = _clean_text(value, merged.get(key, ""))
    return merged


def get_player_portal_content():
    merged = _merge(DEFAULT_PLAYER_PORTAL, load_json(PLAYER_PORTAL_FILE, DEFAULT_PLAYER_PORTAL))
    return _sanitize_portal_media_fields(merged)


def get_dev_portal_content():
    merged = _merge(DEFAULT_DEV_PORTAL, load_json(DEV_PORTAL_FILE, DEFAULT_DEV_PORTAL))
    return _sanitize_portal_media_fields(merged)


def _normalize_payload(data, defaults):
    payload = {}
    for key in defaults.keys():
        if key not in data:
            continue
        value = data.get(key)
        if isinstance(defaults[key], list):
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except Exception:
                    value = []
            if not isinstance(value, list):
                value = []
            payload[key] = value
        elif isinstance(defaults[key], dict):
            if isinstance(value, dict):
                payload[key] = value
        else:
            payload[key] = str(value)
    return payload


def _sanitize_portal_media_fields(payload):
    if not isinstance(payload, dict):
        return {}
    if "hero_image_url" in payload:
        payload["hero_image_url"] = normalize_local_media_url(payload.get("hero_image_url"))
    if "hero_video_url" in payload:
        payload["hero_video_url"] = normalize_local_media_url(payload.get("hero_video_url"))
    if "hero_gallery_urls" in payload:
        payload["hero_gallery_urls"] = normalize_local_media_urls(payload.get("hero_gallery_urls"), max_count=12)

    modules = payload.get("home_modules")
    if isinstance(modules, list):
        cleaned_modules = []
        for module in modules:
            if not isinstance(module, dict):
                continue
            row = dict(module)
            row["image_url"] = normalize_local_media_url(row.get("image_url"))
            row["video_url"] = normalize_local_media_url(row.get("video_url"))
            row["media_urls"] = normalize_local_media_urls(row.get("media_urls"), max_count=12)
            cleaned_modules.append(row)
        payload["home_modules"] = cleaned_modules
    return payload


def _merge_module_layouts(incoming_modules, current_modules):
    if not isinstance(incoming_modules, list):
        return incoming_modules
    if not isinstance(current_modules, list):
        current_modules = []

    current_by_id = {}
    current_by_type = {}
    for item in current_modules:
        if not isinstance(item, dict):
            continue
        module_id = str(item.get("id") or "").strip()
        module_type = str(item.get("type") or "").strip()
        if module_id:
            current_by_id[module_id] = item
        if module_type and module_type not in current_by_type:
            current_by_type[module_type] = item

    merged = []
    for item in incoming_modules:
        if not isinstance(item, dict):
            continue
        module_id = str(item.get("id") or "").strip()
        module_type = str(item.get("type") or "").strip()
        current = current_by_id.get(module_id) or current_by_type.get(module_type) or {}
        row = dict(current)
        row.update(item)
        if not isinstance(row.get("layout"), dict) and isinstance(current.get("layout"), dict):
            row["layout"] = current.get("layout")
        merged.append(row)
    return merged


def save_player_portal_content(data):
    current = get_player_portal_content()
    payload = _normalize_payload(data or {}, DEFAULT_PLAYER_PORTAL)
    payload = _sanitize_portal_media_fields(payload)
    if "home_modules" in payload:
        payload["home_modules"] = _merge_module_layouts(payload.get("home_modules"), current.get("home_modules"))
    for key, value in payload.items():
        if isinstance(value, str):
            current[key] = value[:5000]
        else:
            current[key] = value
    save_json(PLAYER_PORTAL_FILE, current)
    return current


def save_dev_portal_content(data):
    current = get_dev_portal_content()
    payload = _normalize_payload(data or {}, DEFAULT_DEV_PORTAL)
    payload = _sanitize_portal_media_fields(payload)
    if "home_modules" in payload:
        payload["home_modules"] = _merge_module_layouts(payload.get("home_modules"), current.get("home_modules"))
    for key, value in payload.items():
        if isinstance(value, str):
            current[key] = value[:5000]
        else:
            current[key] = value
    save_json(DEV_PORTAL_FILE, current)
    return current

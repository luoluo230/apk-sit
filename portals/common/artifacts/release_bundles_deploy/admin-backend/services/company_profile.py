# -*- coding: utf-8 -*-
"""Company profile content for the public-facing brand page."""

import os

from config import DATA_DIR
from utils import load_json, save_json

COMPANY_PROFILE_FILE = os.path.join(DATA_DIR, "company_profile.json")

_LEGACY_BRAND_NAMES = {"星云游戏站", "Nebula Game Studio"}

DEFAULT_COMPANY_PROFILE = {
    "company_name": "星云游戏站",
    "hero_eyebrow": "品牌故事",
    "hero_title": "以品牌叙事、长线运营和玩家社区搭建游戏产品价值",
    "hero_summary": "星云游戏站聚焦于游戏品牌首页、内容运营、社区增长和分发转化，让每个项目拥有对外统一、对内可管理的商业官网体系。",
    "company_intro": "我们以游戏品牌首页、新闻公告、福利活动、玩家论坛与下载转化为主线，为不同游戏项目提供可迭代的官网产品体系。前台承接玩家认知与转化，后台支持按角色分工、按项目隔离、按审批流发布。",
    "mission_title": "我们的价值不只是搭站，而是把官网变成可运营的产品",
    "mission_body": "在视觉上，它需要像商业游戏官网一样有主视觉、节奏和媒体感；在产品上，它需要能承接新闻、福利、论坛、下载、审批、配置与项目隔离。",
    "timeline": [
        {"year": "2024", "title": "官网体系设计", "description": "完成品牌首页、产品页、新闻、福利、论坛的结构规划。"},
        {"year": "2025", "title": "项目隔离与审批升级", "description": "新闻、福利、官方帖子全部接入审批流，并按项目隔离内容。"},
        {"year": "2026", "title": "商业级发布门户", "description": "形成对外品牌站点与对内管理工作台双端闭环。"},
    ],
    "achievements": [
        {"label": "双端体系", "value": "品牌官网 + 管理工作台"},
        {"label": "项目治理", "value": "新闻、福利、论坛按项目隔离"},
        {"label": "发布能力", "value": "草稿、审批、发布、下线闭环"},
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


def get_company_profile():
    current = load_json(COMPANY_PROFILE_FILE, DEFAULT_COMPANY_PROFILE)
    merged = dict(DEFAULT_COMPANY_PROFILE)
    if isinstance(current, dict):
        for key, value in current.items():
            if value in (None, ""):
                continue
            if isinstance(value, str):
                merged[key] = _clean_text(value, merged.get(key, ""))
            else:
                merged[key] = value
    if not isinstance(merged.get("timeline"), list) or not merged.get("timeline"):
        merged["timeline"] = list(DEFAULT_COMPANY_PROFILE["timeline"])
    if not isinstance(merged.get("achievements"), list) or not merged.get("achievements"):
        merged["achievements"] = list(DEFAULT_COMPANY_PROFILE["achievements"])
    cleaned_timeline = []
    for item in merged.get("timeline") or []:
        if not isinstance(item, dict):
            continue
        cleaned_timeline.append({k: _clean_text(v, "") for k, v in item.items()})
    if cleaned_timeline:
        merged["timeline"] = cleaned_timeline
    cleaned_achievements = []
    for item in merged.get("achievements") or []:
        if not isinstance(item, dict):
            continue
        cleaned_achievements.append({k: _clean_text(v, "") for k, v in item.items()})
    if cleaned_achievements:
        merged["achievements"] = cleaned_achievements
    return merged


def _sync_portal_site_names(old_name, new_name):
    old_value = str(old_name or "").strip()
    new_value = str(new_name or "").strip()
    if not new_value:
        return
    try:
        from services.portal_content import (
            DEFAULT_DEV_PORTAL,
            DEFAULT_PLAYER_PORTAL,
            get_dev_portal_content,
            get_player_portal_content,
            save_dev_portal_content,
            save_player_portal_content,
        )
    except Exception:
        return

    def should_sync(site_name, default_name):
        value = str(site_name or "").strip()
        if not value:
            return True
        if old_value and value == old_value:
            return True
        if value == str(default_name or "").strip():
            return True
        return value in _LEGACY_BRAND_NAMES

    player_portal = get_player_portal_content()
    if should_sync(player_portal.get("site_name"), DEFAULT_PLAYER_PORTAL.get("site_name")):
        save_player_portal_content({"site_name": new_value})

    dev_portal = get_dev_portal_content()
    if should_sync(dev_portal.get("site_name"), DEFAULT_DEV_PORTAL.get("site_name")):
        save_dev_portal_content({"site_name": new_value})


def save_company_profile(data):
    current = get_company_profile()
    old_company_name = str(current.get("company_name") or "").strip()
    payload = data or {}
    for key in ("company_name", "hero_eyebrow", "hero_title", "hero_summary", "company_intro", "mission_title", "mission_body"):
        if key in payload:
            current[key] = str(payload.get(key) or "")[:5000]
    for list_key in ("timeline", "achievements"):
        if list_key in payload and isinstance(payload.get(list_key), list):
            rows = []
            for item in payload.get(list_key):
                if not isinstance(item, dict):
                    continue
                clean = {k: str(v or "")[:1000] for k, v in item.items()}
                if any(clean.values()):
                    rows.append(clean)
            if rows:
                current[list_key] = rows[:12]
    save_json(COMPANY_PROFILE_FILE, current)
    new_company_name = str(current.get("company_name") or "").strip()
    if new_company_name and new_company_name != old_company_name:
        _sync_portal_site_names(old_company_name, new_company_name)
    return current

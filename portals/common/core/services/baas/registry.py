# -*- coding: utf-8 -*-
"""BaaS feature catalog and dependency metadata."""

from __future__ import annotations

from typing import Any, Dict, List

FEATURE_CATALOG: List[Dict[str, Any]] = [
    {"key": "login", "label": "登录配置", "phase": 1, "group": "core", "default_enabled": True},
    {"key": "announce", "label": "公告", "phase": 1, "group": "core", "default_enabled": True},
    {"key": "mail", "label": "邮件", "phase": 1, "group": "core", "default_enabled": True},
    {"key": "cloudsave", "label": "云存档", "phase": 1, "group": "core", "default_enabled": True},
    {"key": "leaderboard", "label": "排行榜", "phase": 2, "group": "retention", "default_enabled": False},
    {"key": "economy", "label": "经济系统", "phase": 2, "group": "retention", "default_enabled": False},
    {"key": "achievement", "label": "成就", "phase": 2, "group": "retention", "default_enabled": False},
    {"key": "gift", "label": "礼包", "phase": 2, "group": "retention", "default_enabled": False},
    {"key": "guild", "label": "公会", "phase": 3, "group": "social", "default_enabled": False},
    {"key": "battlepass", "label": "战令", "phase": 3, "group": "social", "default_enabled": False},
    {"key": "periodic_task", "label": "周期任务", "phase": 3, "group": "social", "default_enabled": False},
    {"key": "compliance", "label": "防沉迷", "phase": 4, "group": "compliance", "default_enabled": False},
    {"key": "pvp", "label": "PVP 战斗同步", "phase": 4, "group": "pvp", "default_enabled": False},
]

FEATURE_KEYS = {row["key"] for row in FEATURE_CATALOG}


def default_feature_flags() -> Dict[str, bool]:
    return {row["key"]: bool(row.get("default_enabled")) for row in FEATURE_CATALOG}


def default_feature_configs() -> Dict[str, Dict[str, Any]]:
    return {
        "login": {
            "guest_login_enabled": True,
            "password_login_enabled": True,
            "token_ttl_hours": 168,
        },
        "announce": {"audience": "all"},
        "mail": {"max_inbox": 100, "expire_days": 30},
        "cloudsave": {"max_keys_per_player": 32, "max_value_bytes": 65536},
        "leaderboard": {"boards": [{"id": "default", "name": "默认榜", "sort": "desc", "limit": 100}]},
        "economy": {
            "currencies": [{"id": "gold", "name": "金币", "initial": 1000}],
            "products": [],
        },
        "achievement": {"definitions": []},
        "gift": {"packs": [], "codes": []},
        "guild": {"max_members": 50, "create_cost": 0},
        "battlepass": {"season_id": "s1", "levels": 30, "premium_enabled": False},
        "periodic_task": {"daily_tasks": [], "weekly_tasks": []},
        "compliance": {
            "enabled": False,
            "daily_limit_minutes": 120,
            "curfew_start": "22:00",
            "curfew_end": "08:00",
            "require_real_name": False,
        },
        "pvp": {"mode": "state_sync", "room_ttl_seconds": 600, "max_players": 2},
    }


def public_endpoints_for_features(flags: Dict[str, bool]) -> Dict[str, str]:
    base = "/api/baas/v1/{service_id}"
    mapping = {
        "login": f"{base}/auth",
        "announce": f"{base}/announcements",
        "mail": f"{base}/mail",
        "cloudsave": f"{base}/cloudsave",
        "leaderboard": f"{base}/leaderboards",
        "economy": f"{base}/shop",
        "achievement": f"{base}/achievements",
        "gift": f"{base}/gifts",
        "guild": f"{base}/guilds",
        "battlepass": f"{base}/battlepass",
        "periodic_task": f"{base}/tasks",
        "compliance": f"{base}/compliance",
        "pvp": f"{base}/pvp",
    }
    return {k: v for k, v in mapping.items() if flags.get(k)}


def list_catalog() -> List[Dict[str, Any]]:
    return list(FEATURE_CATALOG)

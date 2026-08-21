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
    {"key": "pve", "label": "PVE 推图战斗", "phase": 1, "group": "battle", "default_enabled": True},
    {"key": "arena", "label": "异步竞技场", "phase": 2, "group": "battle", "default_enabled": True},
    {"key": "hero", "label": "英雄养成", "phase": 1, "group": "battle", "default_enabled": True},
    {"key": "inventory", "label": "背包道具", "phase": 2, "group": "battle", "default_enabled": True},
    {"key": "gacha", "label": "抽卡召唤", "phase": 1, "group": "battle", "default_enabled": True},
    {"key": "idle", "label": "挂机离线收益", "phase": 1, "group": "retention", "default_enabled": True},
    {"key": "tower", "label": "爬塔副本", "phase": 2, "group": "battle", "default_enabled": True},
    {"key": "iap", "label": "应用内购", "phase": 2, "group": "monetization", "default_enabled": False},
    {"key": "pvp", "label": "PVP 实时房间(可选)", "phase": 4, "group": "pvp", "default_enabled": False},
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
        "leaderboard": {
            "boards": [
                {"id": "default", "name": "默认榜", "sort": "desc", "limit": 100},
                {"id": "guild_war:gw_s1", "name": "公会战跨服榜", "sort": "desc", "limit": 100, "scope": "cross_server"},
            ],
        },
        "economy": {
            "currencies": [
                {"id": "gold", "name": "金币", "initial": 1000},
                {"id": "diamond", "name": "钻石", "initial": 200},
            ],
            "products": [],
        },
        "achievement": {"definitions": []},
        "gift": {"packs": [], "codes": []},
        "guild": {
            "max_members": 50,
            "create_cost": 0,
            "active_season": {"season_id": "gw_s1", "name": "公会战 S1", "max_guilds": 64},
        },
        "battlepass": {"season_id": "s1", "levels": 30, "premium_enabled": False},
        "periodic_task": {"daily_tasks": [], "weekly_tasks": []},
        "compliance": {
            "enabled": False,
            "daily_limit_minutes": 120,
            "curfew_start": "22:00",
            "curfew_end": "08:00",
            "require_real_name": False,
        },
        "pve": {
            "stamina_max": 120,
            "stamina_recover_seconds": 360,
            "heroes": [
                {"id": 1, "name": "战士", "base_power": 120, "role": "tank"},
                {"id": 2, "name": "法师", "base_power": 150, "role": "dps"},
                {"id": 3, "name": "射手", "base_power": 140, "role": "dps"},
                {"id": 11, "name": "圣骑士", "base_power": 180, "role": "tank"},
                {"id": 12, "name": "牧师", "base_power": 130, "role": "support"},
                {"id": 21, "name": "刺客", "base_power": 160, "role": "dps"},
                {"id": 22, "name": "游侠", "base_power": 155, "role": "dps"},
            ],
            "anti_cheat": {
                "require_checksum": True,
                "require_replay_hash": True,
                "min_duration_ms": 3000,
                "max_duration_ms": 600000,
                "max_power_delta_ratio": 0.35,
            },
            "stages": [
                {"id": "1-1", "chapter": 1, "stage": 1, "name": "第一章-1", "power_required": 100, "stamina_cost": 6, "rewards": {"gold": 100}},
                {"id": "1-2", "chapter": 1, "stage": 2, "name": "第一章-2", "power_required": 250, "stamina_cost": 6, "rewards": {"gold": 120}},
                {"id": "2-1", "chapter": 2, "stage": 1, "name": "第二章-1", "power_required": 400, "stamina_cost": 8, "rewards": {"gold": 200}},
            ],
        },
        "arena": {
            "season_id": "arena_s1",
            "season_name": "第一赛季",
            "daily_attempts": 5,
            "rating_board_id": "arena",
            "win_rating_delta": 15,
            "lose_rating_delta": -10,
            "opponent_count": 3,
            "win_rewards": {"gold": 80},
            "lose_rewards": {"gold": 20},
        },
        "pvp": {"mode": "state_sync", "room_ttl_seconds": 600, "max_players": 2},
        "hero": {
            "max_level": 100,
            "level_cost_gold": 100,
            "duplicate_shards": 10,
            "equipment_slots": ["weapon", "armor"],
            "hero_defs": [
                {"id": 1, "name": "战士", "base_power": 120, "role": "tank"},
                {"id": 2, "name": "法师", "base_power": 150, "role": "dps"},
                {"id": 3, "name": "射手", "base_power": 140, "role": "dps"},
                {"id": 11, "name": "圣骑士", "base_power": 180, "role": "tank", "rare": True},
                {"id": 12, "name": "牧师", "base_power": 130, "role": "support", "rare": True},
            ],
        },
        "gacha": {
            "pools": [{
                "id": "standard",
                "name": "标准召唤",
                "cost_currency": "diamond",
                "cost_amount": 100,
                "pity_max": 10,
                "items": [
                    {"type": "hero", "hero_id": 1, "weight": 40},
                    {"type": "hero", "hero_id": 2, "weight": 35},
                    {"type": "hero", "hero_id": 3, "weight": 20},
                    {"type": "hero", "hero_id": 11, "weight": 4, "rare": True},
                    {"type": "hero", "hero_id": 12, "weight": 1, "rare": True},
                ],
            }],
        },
        "idle": {
            "max_hours": 12,
            "gold_per_hour": 500,
            "requires_stage_cleared": "1-1",
        },
        "tower": {
            "towers": [{
                "id": "main",
                "name": "试炼之塔",
                "floors": [
                    {"floor": 1, "name": "第1层", "power_required": 80, "rewards": {"gold": 50}},
                    {"floor": 2, "name": "第2层", "power_required": 150, "rewards": {"gold": 80}},
                    {"floor": 3, "name": "第3层", "power_required": 220, "rewards": {"gold": 120, "diamond": 5}},
                ],
            }],
        },
        "iap": {
            "dev_verify_always_ok": True,
            "apple_shared_secret": "",
            "apple_sandbox": True,
            "wechat_app_id": "",
            "wechat_mch_id": "",
            "wechat_api_key": "",
            "products": [
                {"id": "com.game.diamond60", "name": "60钻石", "diamond": 60, "price_display": "¥6"},
                {"id": "com.game.diamond300", "name": "300钻石", "diamond": 300, "price_display": "¥30"},
            ],
        },
        "inventory": {
            "item_defs": [
                {"id": "sword_001", "name": "铁剑", "type": "equipment", "slot": "weapon", "stack_limit": 1},
                {"id": "armor_001", "name": "皮甲", "type": "equipment", "slot": "armor", "stack_limit": 1},
                {"id": "potion_hp", "name": "生命药水", "type": "consumable", "stack_limit": 99},
            ],
        },
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
        "pve": f"{base}/pve",
        "arena": f"{base}/arena",
        "hero": f"{base}/heroes",
        "inventory": f"{base}/inventory",
        "gacha": f"{base}/gacha",
        "idle": f"{base}/idle",
        "tower": f"{base}/tower",
        "iap": f"{base}/iap",
        "pvp": f"{base}/pvp",
    }
    return {k: v for k, v in mapping.items() if flags.get(k)}


def list_catalog() -> List[Dict[str, Any]]:
    return list(FEATURE_CATALOG)

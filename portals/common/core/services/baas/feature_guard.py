# -*- coding: utf-8 -*-
"""
BaaS 业务模块公共守卫与上下文工具。

各 service 模块在入口调用 require_feature / require_player，保证功能门控与登录校验一致。
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from services.baas.errors import baas_error
from services.baas.service_crud import feature_enabled, get_feature_config

# 功能键 → 未启用时的业务错误码（与 packages/baas_shared/error_codes.json 一致）
_FEATURE_DISABLED_CODES: Dict[str, str] = {
    "login": "BAAS_AUTH_LOGIN_DISABLED",
    "announce": "BAAS_VALIDATION_FAILED",
    "mail": "BAAS_MAIL_DISABLED",
    "cloudsave": "BAAS_CLOUDSAVE_DISABLED",
    "leaderboard": "BAAS_LEADERBOARD_DISABLED",
    "economy": "BAAS_ECONOMY_DISABLED",
    "achievement": "BAAS_ACHIEVEMENT_DISABLED",
    "gift": "BAAS_GIFT_DISABLED",
    "guild": "BAAS_GUILD_DISABLED",
    "battlepass": "BAAS_BATTLEPASS_DISABLED",
    "periodic_task": "BAAS_TASK_DISABLED",
    "compliance": "BAAS_COMPLIANCE_DISABLED",
    "pve": "BAAS_PVE_DISABLED",
    "arena": "BAAS_ARENA_DISABLED",
    "hero": "BAAS_VALIDATION_FAILED",
    "inventory": "BAAS_VALIDATION_FAILED",
    "gacha": "BAAS_VALIDATION_FAILED",
    "idle": "BAAS_VALIDATION_FAILED",
    "tower": "BAAS_VALIDATION_FAILED",
    "iap": "BAAS_VALIDATION_FAILED",
    "pvp": "BAAS_FEATURE_ROOM_DISABLED",
}


def require_feature(service_id: str, feature_key: str) -> None:
    """功能未开通时抛出对应 BaasError。"""
    if feature_enabled(service_id, feature_key):
        return
    code = _FEATURE_DISABLED_CODES.get(feature_key, "BAAS_FORBIDDEN")
    raise baas_error(code, details={"feature": feature_key})


def require_player(player_id: str, player_token: str = "") -> str:
    """玩家 ID 为空时抛出 BaasError(BAAS_NOT_LOGGED_IN)。"""
    pid = str(player_id or "").strip()
    if not pid:
        raise baas_error("BAAS_NOT_LOGGED_IN")
    return pid


def load_feature_config(service_id: str, feature_key: str) -> Dict[str, Any]:
    """读取合并后的功能配置（DB 覆盖 + registry 默认值）。"""
    require_feature(service_id, feature_key)
    return dict(get_feature_config(service_id, feature_key) or {})


def player_scope(service_id: str, player_id: str) -> Tuple[str, str]:
    """返回 (service_id, player_id)，二者均非空。"""
    sid = str(service_id or "").strip()
    if not sid:
        raise baas_error("BAAS_AUTH_SERVICE_MISMATCH")
    return sid, require_player(player_id)

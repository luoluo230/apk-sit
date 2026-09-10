# -*- coding: utf-8 -*-
"""Grant AFK reward dicts to wallet + inventory."""

from __future__ import annotations

from typing import Any, Dict, List

from services.baas.service_crud import feature_enabled


def grant_rewards(cur, service_id: str, player_id: str, rewards: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not rewards:
        return []
    from services.baas.wallet_helpers import credit_wallet
    from services.baas import inventory_service

    granted: List[Dict[str, Any]] = []
    for key, val in rewards.items():
        if key in ("gold", "diamond", "arena_coin", "guild_coin", "dungeon_coin") and isinstance(val, (int, float)):
            if feature_enabled(service_id, "economy"):
                credit_wallet(cur, service_id, player_id, str(key), int(val))
            granted.append({"type": "currency", "currency_id": key, "amount": int(val)})
        elif isinstance(val, (int, float)) and int(val) > 0:
            if feature_enabled(service_id, "inventory"):
                inventory_service.grant_item(cur, service_id, player_id, str(key), quantity=int(val))
            granted.append({"type": "item", "item_id": str(key), "quantity": int(val)})
    return granted

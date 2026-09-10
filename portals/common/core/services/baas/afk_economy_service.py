# -*- coding: utf-8 -*-
"""AFK 经济 / 道具 / 副本 / 装备成长 — BaaS 服务。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.baas.afk_config_loader import load_afk_bundle
from services.baas.feature_guard import feature_enabled, get_feature_config


def _economy_cfg(service_id: str) -> Dict[str, Any]:
    bundle = load_afk_bundle() or {}
    eco = bundle.get("economy_system") or {}
    feat = get_feature_config(service_id, "economy") if feature_enabled(service_id, "economy") else {}
    merged = dict(eco)
    if feat.get("items"):
        merged["items"] = feat["items"]
    if feat.get("dungeons"):
        merged["dungeons"] = feat["dungeons"]
    return merged


def list_items(service_id: str) -> List[Dict[str, Any]]:
    return list(_economy_cfg(service_id).get("items") or [])


def list_dungeons(service_id: str, max_cleared: int = 0) -> List[Dict[str, Any]]:
    out = []
    for dg in _economy_cfg(service_id).get("dungeons") or []:
        row = dict(dg)
        row["unlocked"] = max_cleared >= int(dg.get("unlock_stage") or 0)
        out.append(row)
    return out


def equip_growth_config(service_id: str) -> Dict[str, Any]:
    return dict(_economy_cfg(service_id).get("equip_growth") or {})


def skill_rules_config(service_id: str) -> Dict[str, Any]:
    eco = _economy_cfg(service_id)
    return dict(eco.get("skill_rules") or {})


def simulate_dungeon_reward(dungeon_id: str, service_id: str) -> Optional[Dict[str, Any]]:
    for dg in _economy_cfg(service_id).get("dungeons") or []:
        if str(dg.get("id")) == str(dungeon_id):
            return dict(dg.get("rewards") or {})
    return None

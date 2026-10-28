# -*- coding: utf-8 -*-
"""AFK 经济 / 道具 / 副本 / 装备成长 — BaaS 服务。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from services.baas.afk.afk_config_loader import load_afk_bundle
from services.baas.feature_guard import feature_enabled, get_feature_config


def _economy_cfg(service_id: str) -> Dict[str, Any]:
    bundle = load_afk_bundle() or {}
    eco = bundle.get("economy_system") or {}
    feat = get_feature_config(service_id, "economy") if feature_enabled(service_id, "economy") else {}
    merged = dict(eco)
    if feat.get("items"):
        merged["items"] = feat["items"]
    if feat.get("dungeons"):
        merged["dungeons"] = _overlay_exported_dungeons(feat["dungeons"])
    elif eco.get("dungeons"):
        merged["dungeons"] = list(eco["dungeons"])
    return merged


_DUNGEON_EXPORT_KEYS = (
    "daily_limit",
    "weekly_limit",
    "stamina",
    "unlock_stage",
    "entry_item",
    "power_scale",
    "scales_with_tier",
    "rewards",
    "cooldown_seconds",
    "name",
    "name_key",
    "mode",
)


def _overlay_exported_dungeons(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """副本次数、体力、解锁、产出以 Excel 导出的 bundle 为准。"""
    bundle = load_afk_bundle() or {}
    exported = {
        str(row.get("id") or ""): row
        for row in ((bundle.get("economy_system") or {}).get("dungeons") or [])
        if row.get("id")
    }
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in rows or []:
        did = str(row.get("id") or "")
        fresh = exported.get(did)
        if not fresh:
            out.append(dict(row))
            continue
        merged = dict(row)
        for key in _DUNGEON_EXPORT_KEYS:
            if key in fresh:
                merged[key] = fresh[key]
        out.append(merged)
        seen.add(did)
    for did, fresh in exported.items():
        if did not in seen:
            out.append(dict(fresh))
    return out


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

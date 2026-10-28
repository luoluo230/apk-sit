# -*- coding: utf-8 -*-
"""Load shared AFK config bundle (Excel export) for BaaS default feature configs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

_REPO_ROOT = Path(__file__).resolve().parents[5]
_BUNDLE_PATH = _REPO_ROOT / "data" / "afk_shared" / "baas_bundle.json"
_BUNDLE_CACHE: Dict[str, Any] = {"mtime_ns": None, "data": None, "generation": 0}


def bundle_generation() -> int:
    load_afk_bundle()
    return int(_BUNDLE_CACHE.get("generation") or 0)


def balance_number(key: str, default: float) -> float:
    """Excel ServerBalance 导出的标量。缺表时用已验证的默认值。"""
    bundle = load_afk_bundle() or {}
    table = bundle.get("balance_const") if isinstance(bundle, dict) else None
    raw = default if not isinstance(table, dict) else table.get(key, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def load_afk_bundle() -> Optional[Dict[str, Any]]:
    """Excel 导出写入 baas_bundle.json 后，按文件时间重新加载，不必重启进程。"""
    if not _BUNDLE_PATH.is_file():
        return None
    try:
        mtime_ns = _BUNDLE_PATH.stat().st_mtime_ns
    except OSError:
        return None
    if _BUNDLE_CACHE.get("mtime_ns") == mtime_ns and _BUNDLE_CACHE.get("data") is not None:
        return _BUNDLE_CACHE["data"]
    try:
        with _BUNDLE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    _BUNDLE_CACHE["mtime_ns"] = mtime_ns
    _BUNDLE_CACHE["data"] = data
    _BUNDLE_CACHE["generation"] = int(_BUNDLE_CACHE.get("generation") or 0) + 1
    return data


def _inventory_defs_from_economy(bundle: Dict[str, Any]) -> list:
    eco = bundle.get("economy_system") or bundle.get("economy") or {}
    out = []
    for row in eco.get("items") or []:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        itype = str(row.get("type") or "item")
        slot = str(row.get("slot") or "")
        if itype == "currency":
            continue
        out.append({
            "id": key,
            "name": row.get("name", key),
            "type": "equipment" if slot or itype == "equipment" else itype,
            "slot": slot,
            "stack_limit": int(row.get("stack") or row.get("stack_limit") or 9999),
        })
    return out


def _shop_products(bundle: Dict[str, Any]) -> list:
    shop = bundle.get("shop") or {}
    shops = {str(s.get("shop_id") or ""): s for s in (shop.get("shops") or [])}
    out = []
    for g in shop.get("goods") or []:
        sid = str(g.get("shop_id") or "")
        shop_row = shops.get(sid, {})
        currency = str(shop_row.get("currency") or "gold")
        gid = str(g.get("goods_id") or "")
        out.append({
            "id": gid,
            "name": g.get("name_zh") or g.get("item_key") or gid,
            "shop_id": sid,
            "price": int(g.get("price") or 0),
            "currency_id": currency,
            "item_key": str(g.get("item_key") or ""),
            "quantity": int(g.get("count") or 1),
            "limit_per_refresh": int(g.get("limit_per_refresh") or 0),
            "unlock_stage": int(g.get("unlock_stage") or 0),
        })
    return out


def _gacha_runtime_config(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Convert planner-facing AFK pool rows into BaaS executable draw tables."""
    source = bundle.get("gacha") or {}
    heroes = list((bundle.get("hero") or {}).get("hero_defs") or [])
    by_quality: Dict[int, list] = {}
    for hero in heroes:
        try:
            quality = int(hero.get("quality") or 3)
            hero_id = int(hero.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if hero_id > 0:
            by_quality.setdefault(quality, []).append(hero_id)
    pools = []
    for raw in source.get("pools") or []:
        pool = dict(raw)
        pool_id = str(pool.get("pool_id") or pool.get("id") or pool.get("key") or "").strip()
        if not pool_id:
            continue
        rates = dict(pool.get("rates_json") or {})
        items = []
        for quality, ids in sorted(by_quality.items()):
            rate = float(rates.get(f"quality_{quality}") or 0)
            if rate <= 0 or not ids:
                continue
            weight = max(1, int(round(rate * 10000 / len(ids))))
            items.extend({"type": "hero", "hero_id": hero_id, "weight": weight, "rare": quality >= 5} for hero_id in ids)
        if not items:
            continue
        pools.append({
            "id": pool_id,
            "name": pool.get("name_zh") or pool.get("name") or pool_id,
            "cost_currency": pool.get("cost_currency") or "diamond",
            "cost_amount": int(pool.get("cost_amount") or 0),
            "pity_max": int(pool.get("pity_max") or 0),
            "unlock_stage": int(pool.get("unlock_stage") or 0),
            "items": items,
        })
    return {"pools": pools}


def afk_feature_configs() -> Dict[str, Dict[str, Any]]:
    bundle = load_afk_bundle()
    if not bundle:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    if isinstance(bundle.get("pve"), dict):
        out["pve"] = dict(bundle["pve"])
    if isinstance(bundle.get("hero"), dict):
        out["hero"] = dict(bundle["hero"])
    if isinstance(bundle.get("idle"), dict):
        out["idle"] = dict(bundle["idle"])
    if isinstance(bundle.get("gacha"), dict):
        out["gacha"] = _gacha_runtime_config(bundle)
    if isinstance(bundle.get("economy_system"), dict):
        out["economy_system"] = dict(bundle["economy_system"])
    if isinstance(bundle.get("tower"), dict):
        out["tower"] = dict(bundle["tower"])
    if isinstance(bundle.get("formulas"), dict):
        out["_afk_formulas"] = dict(bundle["formulas"])

    eco = dict(bundle.get("economy") or {})
    products = _shop_products(bundle)
    if products:
        eco["products"] = products
    vip_iap = bundle.get("vip_iap") or {}
    if vip_iap.get("iap_products"):
        eco["iap_products"] = list(vip_iap["iap_products"])
    if eco:
        out["economy"] = eco

    bp = bundle.get("battle_pass") or {}
    if bp:
        out["battlepass"] = {
            "season_id": bp.get("season_id", "afk_bp_s1"),
            "levels": int(bp.get("levels") or 30),
            "premium_enabled": bool(bp.get("premium_enabled", True)),
            "level_rewards": bp.get("level_rewards") or [],
        }

    ach = bundle.get("achievements") or {}
    if ach.get("definitions"):
        out["achievement"] = {"definitions": list(ach["definitions"])}

    tasks = bundle.get("periodic_tasks") or {}
    if tasks:
        out["periodic_task"] = {
            "daily_tasks": list(tasks.get("daily_tasks") or []),
            "weekly_tasks": list(tasks.get("weekly_tasks") or []),
        }

    guild = bundle.get("guild") or {}
    if guild:
        out["guild"] = dict(guild)
        if guild.get("active_season"):
            out["guild"]["active_season"] = dict(guild["active_season"])

    arena = bundle.get("arena") or {}
    if arena:
        out["arena"] = dict(arena)

    inv_defs = _inventory_defs_from_economy(bundle)
    if inv_defs:
        out["inventory"] = {"item_defs": inv_defs}

    vip_iap = bundle.get("vip_iap") or {}
    if vip_iap:
        products = []
        for row in vip_iap.get("iap_products") or []:
            pid = str(row.get("id") or "")
            if not pid:
                continue
            rewards = dict(row.get("rewards") or {})
            products.append({
                "id": pid,
                "name": row.get("name_zh") or pid,
                "price_display": f"¥{row.get('price_cny', 0)}",
                "rewards": rewards,
                "diamond": int(rewards.get("diamond") or 0),
                "vip_exp": int(row.get("vip_exp") or 0),
                "once_only": bool(row.get("once_only")),
                "daily_rewards": dict(row.get("daily_rewards") or {}),
            })
        out["iap"] = {
            # Development receipts require BAAS_ALLOW_DEV_IAP=1 at runtime; a shipped
            # feature config must never make fake receipt delivery the default.
            "dev_verify_always_ok": False,
            "products": products,
            "vip_levels": list(vip_iap.get("vip_levels") or []),
        }

    for key in (
        "equip_drops", "dungeon_scaling", "activities", "shop", "mail",
        "progressive_rewards", "tutorial", "reddot", "vip_iap", "friend",
    ):
        if isinstance(bundle.get(key), dict):
            out[f"_afk_{key}"] = dict(bundle[key])
    return out


def afk_formulas() -> Dict[str, str]:
    bundle = load_afk_bundle()
    if not bundle:
        return {}
    raw = bundle.get("formulas") or {}
    return {str(k): str(v) for k, v in raw.items()}


def hero_def_map(cfg: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    hero_cfg = cfg if cfg.get("hero_defs") is not None else {}
    rows = hero_cfg.get("hero_defs") or cfg.get("hero_defs") or []
    for row in rows:
        try:
            hid = int(row.get("id") or row.get("hero_id") or 0)
        except (TypeError, ValueError):
            continue
        if hid > 0:
            out[hid] = dict(row)
    return out

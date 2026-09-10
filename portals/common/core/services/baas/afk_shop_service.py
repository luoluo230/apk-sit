# -*- coding: utf-8 -*-
"""AFK shop catalog + purchase from baas_bundle shop tables."""

from __future__ import annotations

from typing import Any, Dict, List

from models.db import get_cursor, init_db
from services.baas.afk_config_loader import load_afk_bundle
from services.baas.afk_reward_grants import grant_rewards
from services.baas.helpers import _now_iso, new_id
from services.baas.service_crud import feature_enabled, get_feature_config
from services.baas.wallet_helpers import credit_wallet, debit_wallet


def _shop_goods() -> List[Dict[str, Any]]:
    bundle = load_afk_bundle() or {}
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
            "product_id": gid,
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


def shop_catalog(service_id: str) -> List[Dict[str, Any]]:
    goods = _shop_goods()
    if goods:
        return goods
    cfg = get_feature_config(service_id, "economy")
    return list(cfg.get("products") or [])


def purchase(service_id: str, player_id: str, product_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "economy"):
        raise ValueError("经济系统未启用")
    pid = str(product_id or "").strip()
    product = next((p for p in shop_catalog(service_id) if str(p.get("id")) == pid), None)
    if not product:
        raise ValueError("商品不存在")
    price = int(product.get("price") or 0)
    try:
        from services.baas.afk_vip_service import shop_discount_mul
        price = max(1, int(price * shop_discount_mul(service_id, player_id)))
    except Exception:
        pass
    currency = str(product.get("currency_id") or "gold")
    item_key = str(product.get("item_key") or "")
    qty = int(product.get("quantity") or 1)
    init_db()
    with get_cursor() as cur:
        from services.baas.retention_services import _wallet_row

        wallet = _wallet_row(cur, service_id, player_id, currency)
        balance = int(wallet["balance"] or 0) if wallet else 0
        if balance < price:
            raise ValueError("余额不足")
        debit_wallet(cur, service_id, player_id, currency, price)
        rewards = {}
        if item_key:
            rewards[item_key] = qty
        granted = grant_rewards(cur, service_id, player_id, rewards)
        order_id = new_id("ord_")
        cur.execute(
            """
            INSERT INTO baas_shop_orders (order_id, service_id, player_id, product_id, price, currency_id, created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (order_id, service_id, player_id, pid, price, currency, _now_iso()),
        )
    return {"order_id": order_id, "product_id": pid, "spent": price, "currency_id": currency, "grants": granted}

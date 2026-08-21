# -*- coding: utf-8 -*-
"""应用内购 IAP：创建订单、验单（开发模式可跳过）、发放钻石等。"""

from __future__ import annotations

import hashlib
from typing import Any, Dict

from models.db import get_cursor, init_db
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas.iap_verify import verify_platform_receipt
from services.baas.service_crud import feature_enabled, get_feature_config
from services.baas.wallet_helpers import credit_wallet


def _product_cfg(cfg: Dict[str, Any], product_id: str) -> Dict[str, Any]:
    pid = str(product_id or "").strip()
    for row in cfg.get("products") or []:
        if str(row.get("id") or "") == pid:
            return dict(row)
    raise ValueError("IAP 商品不存在")


def list_products(service_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "iap"):
        return {"products": []}
    cfg = get_feature_config(service_id, "iap")
    return {"products": list(cfg.get("products") or [])}


def create_order(service_id: str, player_id: str, product_id: str, *, platform: str = "dev") -> Dict[str, Any]:
    if not feature_enabled(service_id, "iap"):
        raise ValueError("IAP 功能未启用")
    product = _product_cfg(get_feature_config(service_id, "iap"), product_id)
    order_id = new_id("iap_")
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_iap_orders (
                order_id, service_id, player_id, product_id, platform, receipt_hash, status, rewards_json, created_at, verified_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (order_id, service_id, player_id, product_id, str(platform or "dev"), "", "pending", _json_dump(product), now, ""),
        )
    return {"order_id": order_id, "product_id": product_id, "platform": platform, "status": "pending", "product": product}


def verify_and_deliver(
    service_id: str,
    player_id: str,
    order_id: str,
    *,
    receipt: str = "",
    platform: str = "",
    transaction_id: str = "",
) -> Dict[str, Any]:
    if not feature_enabled(service_id, "iap"):
        raise ValueError("IAP 功能未启用")
    cfg = get_feature_config(service_id, "iap")
    oid = str(order_id or "").strip()
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_iap_orders WHERE order_id=? AND service_id=? AND player_id=?",
            (oid, service_id, player_id),
        ).fetchone()
        if not row:
            raise ValueError("订单不存在")
        if str(row["status"] or "") == "delivered":
            return _json_load(row["rewards_json"], {})
        if str(row["status"] or "") != "pending":
            raise ValueError("订单状态不可验单")
        product = _json_load(row["rewards_json"], {})
        plat = str(platform or row["platform"] or "dev").strip().lower()
        receipt_hash = hashlib.sha256(str(receipt or oid).encode()).hexdigest()[:32]
        dup = cur.execute(
            "SELECT 1 FROM baas_iap_orders WHERE service_id=? AND receipt_hash=? AND status='delivered' LIMIT 1",
            (service_id, receipt_hash),
        ).fetchone()
        if dup and receipt_hash:
            raise ValueError("收据已使用")
        dev_ok = bool(cfg.get("dev_verify_always_ok"))
        verify_info: Dict[str, Any]
        if dev_ok and plat in ("dev", "development", "test", ""):
            verify_info = {"platform": "dev", "transaction_id": receipt_hash, "product_id": str(row["product_id"] or "")}
        else:
            verify_info = verify_platform_receipt(
                plat or str(row["platform"] or "dev"),
                str(row["product_id"] or ""),
                str(receipt or ""),
                cfg,
                transaction_id=str(transaction_id or ""),
            )
            receipt_hash = hashlib.sha256(str(verify_info.get("transaction_id") or receipt or oid).encode()).hexdigest()[:32]
            dup2 = cur.execute(
                "SELECT 1 FROM baas_iap_orders WHERE service_id=? AND receipt_hash=? AND status='delivered' LIMIT 1",
                (service_id, receipt_hash),
            ).fetchone()
            if dup2:
                raise ValueError("交易号已使用")
        rewards: Dict[str, Any] = {}
        for key, val in product.items():
            if key.endswith("_grant") or key in ("diamond", "gold"):
                continue
            if key == "diamond_grant":
                credit_wallet(cur, service_id, player_id, "diamond", int(val or 0))
                rewards["diamond"] = int(val or 0)
            elif key == "gold_grant":
                credit_wallet(cur, service_id, player_id, "gold", int(val or 0))
                rewards["gold"] = int(val or 0)
        if "diamond" in product and "diamond" not in rewards:
            amt = int(product.get("diamond") or 0)
            if amt > 0:
                credit_wallet(cur, service_id, player_id, "diamond", amt)
                rewards["diamond"] = amt
        now = _now_iso()
        result = {
            "order_id": oid,
            "status": "delivered",
            "rewards": rewards,
            "verified_at": now,
            "verify": verify_info,
        }
        cur.execute(
            """
            UPDATE baas_iap_orders SET status=?, receipt_hash=?, verified_at=?, rewards_json=?
            WHERE order_id=?
            """,
            ("delivered", receipt_hash, now, _json_dump(result), oid),
        )
    return result

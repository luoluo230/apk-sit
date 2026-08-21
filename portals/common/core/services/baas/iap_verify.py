# -*- coding: utf-8 -*-
"""IAP 平台验单：Apple App Store / 微信小游戏支付。"""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request
from typing import Any, Dict


def _post_json(url: str, payload: Dict[str, Any], *, timeout: int = 15) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def verify_apple_receipt(receipt: str, product_id: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """调用 Apple verifyReceipt；sandbox 失败时自动重试 production。"""
    secret = str(cfg.get("apple_shared_secret") or "").strip()
    if not secret:
        raise ValueError("Apple shared secret 未配置")
    body = str(receipt or "").strip()
    if not body:
        raise ValueError("Apple 收据为空")
    sandbox_url = "https://sandbox.itunes.apple.com/verifyReceipt"
    prod_url = "https://buy.itunes.apple.com/verifyReceipt"
    payload = {"receipt-data": body, "password": secret, "exclude-old-transactions": True}
    prefer_sandbox = bool(cfg.get("apple_sandbox", True))
    first_url = sandbox_url if prefer_sandbox else prod_url
    second_url = prod_url if prefer_sandbox else sandbox_url
    result = _post_json(first_url, payload)
    status = int(result.get("status") or -1)
    # 21007: sandbox receipt sent to production
    # 21008: production receipt sent to sandbox
    if status in (21007, 21008):
        result = _post_json(second_url, payload)
        status = int(result.get("status") or -1)
    if status != 0:
        raise ValueError(f"Apple 验单失败 status={status}")
    receipt_info = result.get("receipt") or {}
    in_app = list(receipt_info.get("in_app") or [])
    if not in_app and result.get("latest_receipt_info"):
        in_app = list(result.get("latest_receipt_info") or [])
    pid = str(product_id or "").strip()
    matched = [row for row in in_app if str(row.get("product_id") or "") == pid]
    if not matched:
        raise ValueError("Apple 收据中未找到对应商品")
    tx = matched[-1]
    tx_id = str(tx.get("transaction_id") or tx.get("original_transaction_id") or "")
    return {"platform": "apple", "transaction_id": tx_id, "product_id": pid, "raw_status": status}


def verify_wechat_order(
    *,
    transaction_id: str,
    product_id: str,
    cfg: Dict[str, Any],
    receipt: str = "",
) -> Dict[str, Any]:
    """微信小游戏 / 微信支付验单（HMAC 签名校验 + 交易号格式）。"""
    app_id = str(cfg.get("wechat_app_id") or "").strip()
    mch_id = str(cfg.get("wechat_mch_id") or "").strip()
    api_key = str(cfg.get("wechat_api_key") or "").strip()
    if not app_id or not mch_id or not api_key:
        raise ValueError("微信支付 app_id / mch_id / api_key 未配置")
    tx_id = str(transaction_id or receipt or "").strip()
    if not tx_id:
        raise ValueError("微信交易号为空")
    if len(tx_id) < 8:
        raise ValueError("微信交易号格式无效")
    sign_src = f"{app_id}|{mch_id}|{tx_id}|{product_id}"
    expected = hmac.new(api_key.encode("utf-8"), sign_src.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    provided = str(cfg.get("_wechat_sign_override") or "").strip()
    if provided and provided != expected:
        raise ValueError("微信验签失败")
    return {"platform": "wechat", "transaction_id": tx_id, "product_id": str(product_id or "")}


def verify_platform_receipt(
    platform: str,
    product_id: str,
    receipt: str,
    cfg: Dict[str, Any],
    *,
    transaction_id: str = "",
) -> Dict[str, Any]:
    plat = str(platform or "dev").strip().lower()
    if plat in ("dev", "development", "test"):
        if not bool(cfg.get("dev_verify_always_ok")):
            raise ValueError("开发环境验单未启用")
        return {"platform": "dev", "transaction_id": transaction_id or receipt or "dev", "product_id": product_id}
    if plat in ("apple", "ios", "appstore"):
        return verify_apple_receipt(receipt, product_id, cfg)
    if plat in ("wechat", "wx", "weixin"):
        return verify_wechat_order(transaction_id=transaction_id, product_id=product_id, cfg=cfg, receipt=receipt)
    raise ValueError(f"不支持的 IAP 平台: {platform}")

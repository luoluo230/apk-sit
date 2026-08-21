# -*- coding: utf-8 -*-
"""BaaS 钱包读写辅助（供抽卡、挂机、IAP 等模块复用）。"""

from __future__ import annotations

from services.baas.helpers import _now_iso
from services.baas.retention_services import _wallet_row


def get_balance(cur, service_id: str, player_id: str, currency_id: str) -> int:
    row = _wallet_row(cur, service_id, player_id, currency_id)
    return int(row["balance"] or 0) if row else 0


def credit_wallet(cur, service_id: str, player_id: str, currency_id: str, amount: int) -> int:
    cid = str(currency_id or "gold").strip() or "gold"
    delta = int(amount or 0)
    if delta <= 0:
        return get_balance(cur, service_id, player_id, cid)
    balance = get_balance(cur, service_id, player_id, cid) + delta
    cur.execute(
        """
        INSERT INTO baas_wallets (service_id, player_id, currency_id, balance, updated_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(service_id, player_id, currency_id) DO UPDATE SET
            balance=excluded.balance, updated_at=excluded.updated_at
        """,
        (service_id, player_id, cid, balance, _now_iso()),
    )
    return balance


def debit_wallet(cur, service_id: str, player_id: str, currency_id: str, amount: int) -> int:
    cid = str(currency_id or "gold").strip() or "gold"
    cost = int(amount or 0)
    if cost <= 0:
        return get_balance(cur, service_id, player_id, cid)
    balance = get_balance(cur, service_id, player_id, cid)
    if balance < cost:
        raise ValueError("余额不足")
    balance -= cost
    cur.execute(
        """
        INSERT INTO baas_wallets (service_id, player_id, currency_id, balance, updated_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(service_id, player_id, currency_id) DO UPDATE SET
            balance=excluded.balance, updated_at=excluded.updated_at
        """,
        (service_id, player_id, cid, balance, _now_iso()),
    )
    return balance

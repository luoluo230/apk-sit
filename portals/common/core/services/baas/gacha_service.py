# -*- coding: utf-8 -*-
"""抽卡 / 召唤：卡池配置、扣费、 pity、发放英雄。"""

from __future__ import annotations

import random
from typing import Any, Dict, List

from models.db import get_cursor, init_db
from services.baas.helpers import _json_dump, _now_iso, new_id
from services.baas.hero_service import grant_hero
from services.baas.service_crud import feature_enabled, get_feature_config
from services.baas.wallet_helpers import debit_wallet


def _pool_cfg(cfg: Dict[str, Any], pool_id: str) -> Dict[str, Any]:
    pid = str(pool_id or "standard").strip()
    for row in cfg.get("pools") or []:
        if str(row.get("id") or "") == pid:
            return dict(row)
    raise ValueError("卡池不存在")


def list_pools(service_id: str) -> List[Dict[str, Any]]:
    if not feature_enabled(service_id, "gacha"):
        return []
    cfg = get_feature_config(service_id, "gacha")
    out = []
    for pool in cfg.get("pools") or []:
        out.append({
            "id": pool.get("id"),
            "name": pool.get("name"),
            "cost_currency": pool.get("cost_currency", "diamond"),
            "cost_amount": int(pool.get("cost_amount") or 0),
            "pity_max": int(pool.get("pity_max") or 0),
        })
    return out


def get_pity_state(service_id: str, player_id: str, pool_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "gacha"):
        raise ValueError("抽卡功能未启用")
    pid = str(pool_id or "standard").strip()
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT pity_counter, total_pulls FROM baas_gacha_state WHERE service_id=? AND player_id=? AND pool_id=?",
            (service_id, player_id, pid),
        ).fetchone()
    return {
        "pool_id": pid,
        "pity_counter": int(row["pity_counter"] or 0) if row else 0,
        "total_pulls": int(row["total_pulls"] or 0) if row else 0,
    }


def _roll_item(pool: Dict[str, Any], *, force_rare: bool = False) -> Dict[str, Any]:
    items = list(pool.get("items") or [])
    if not items:
        raise ValueError("卡池未配置奖品")
    if force_rare:
        rare = [i for i in items if bool(i.get("rare"))]
        if rare:
            items = rare
    weights = [max(1, int(i.get("weight") or 1)) for i in items]
    pick = random.choices(items, weights=weights, k=1)[0]
    return dict(pick)


def pull(service_id: str, player_id: str, pool_id: str, *, count: int = 1) -> Dict[str, Any]:
    if not feature_enabled(service_id, "gacha"):
        raise ValueError("抽卡功能未启用")
    cfg = get_feature_config(service_id, "gacha")
    pool = _pool_cfg(cfg, pool_id)
    pulls = max(1, min(int(count or 1), 10))
    currency = str(pool.get("cost_currency") or "diamond")
    unit_cost = int(pool.get("cost_amount") or 100)
    total_cost = unit_cost * pulls
    pity_max = int(pool.get("pity_max") or 0)
    pid = str(pool.get("id") or "standard")
    results: List[Dict[str, Any]] = []
    init_db()
    with get_cursor() as cur:
        debit_wallet(cur, service_id, player_id, currency, total_cost)
        row = cur.execute(
            "SELECT pity_counter, total_pulls FROM baas_gacha_state WHERE service_id=? AND player_id=? AND pool_id=?",
            (service_id, player_id, pid),
        ).fetchone()
        pity = int(row["pity_counter"] or 0) if row else 0
        total = int(row["total_pulls"] or 0) if row else 0
        for _ in range(pulls):
            pity += 1
            total += 1
            force_rare = pity_max > 0 and pity >= pity_max
            item = _roll_item(pool, force_rare=force_rare)
            if str(item.get("type") or "") == "hero":
                grant_result = grant_hero(cur, service_id, player_id, int(item.get("hero_id") or 0))
                results.append({"type": "hero", **grant_result, "rare": bool(item.get("rare"))})
            else:
                results.append({"type": item.get("type", "unknown"), "payload": item})
            if force_rare or bool(item.get("rare")):
                pity = 0
            pull_id = new_id("gacha_")
            cur.execute(
                """
                INSERT INTO baas_gacha_pulls (pull_id, service_id, player_id, pool_id, result_json, created_at)
                VALUES (?,?,?,?,?,?)
                """,
                (pull_id, service_id, player_id, pid, _json_dump(results[-1]), _now_iso()),
            )
        now = _now_iso()
        cur.execute(
            """
            INSERT INTO baas_gacha_state (service_id, player_id, pool_id, pity_counter, total_pulls, updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(service_id, player_id, pool_id) DO UPDATE SET
                pity_counter=excluded.pity_counter, total_pulls=excluded.total_pulls, updated_at=excluded.updated_at
            """,
            (service_id, player_id, pid, pity, total, now),
        )
    return {
        "pool_id": pid,
        "count": pulls,
        "spent": {"currency_id": currency, "amount": total_cost},
        "pity_counter": pity,
        "total_pulls": total,
        "results": results,
    }

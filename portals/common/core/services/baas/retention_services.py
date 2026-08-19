# -*- coding: utf-8 -*-
"""Phase 2: leaderboard, economy, achievement, gift."""

from __future__ import annotations

from typing import Any, Dict, List

from models.db import get_cursor, init_db
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas.service_crud import feature_enabled, get_feature_config


# --- Leaderboard ---


def submit_score(service_id: str, player_id: str, board_id: str, score: float, *, display_name: str = "") -> Dict[str, Any]:
    if not feature_enabled(service_id, "leaderboard"):
        raise ValueError("排行榜功能未启用")
    bid = str(board_id or "default").strip()
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        existing = cur.execute(
            "SELECT score FROM baas_leaderboard_scores WHERE service_id=? AND board_id=? AND player_id=?",
            (service_id, bid, player_id),
        ).fetchone()
        new_score = max(float(score), float(existing["score"] or 0)) if existing else float(score)
        cur.execute(
            """
            INSERT INTO baas_leaderboard_scores (service_id, board_id, player_id, display_name, score, updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(service_id, board_id, player_id) DO UPDATE SET
                score=excluded.score, display_name=excluded.display_name, updated_at=excluded.updated_at
            """,
            (service_id, bid, player_id, display_name or player_id, new_score, now),
        )
    return {"board_id": bid, "player_id": player_id, "score": new_score}


def top_scores(service_id: str, board_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    if not feature_enabled(service_id, "leaderboard"):
        return []
    bid = str(board_id or "default").strip()
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            """
            SELECT player_id, display_name, score, updated_at FROM baas_leaderboard_scores
            WHERE service_id=? AND board_id=? ORDER BY score DESC LIMIT ?
            """,
            (service_id, bid, min(limit, 200)),
        ).fetchall()
    return [dict(r) for r in rows]


# --- Economy ---


def _wallet_row(cur, service_id: str, player_id: str, currency_id: str):
    return cur.execute(
        "SELECT * FROM baas_wallets WHERE service_id=? AND player_id=? AND currency_id=?",
        (service_id, player_id, currency_id),
    ).fetchone()


def get_wallet(service_id: str, player_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "economy"):
        return {"balances": {}}
    cfg = get_feature_config(service_id, "economy")
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            "SELECT currency_id, balance FROM baas_wallets WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchall()
        balances = {str(r["currency_id"]): int(r["balance"] or 0) for r in rows}
        for cur_def in cfg.get("currencies") or []:
            cid = str(cur_def.get("id") or "")
            if cid and cid not in balances:
                balances[cid] = int(cur_def.get("initial") or 0)
                cur.execute(
                    """
                    INSERT INTO baas_wallets (service_id, player_id, currency_id, balance, updated_at)
                    VALUES (?,?,?,?,?)
                    """,
                    (service_id, player_id, cid, balances[cid], _now_iso()),
                )
    return {"balances": balances}


def shop_catalog(service_id: str) -> List[Dict[str, Any]]:
    cfg = get_feature_config(service_id, "economy")
    return list(cfg.get("products") or [])


def purchase(service_id: str, player_id: str, product_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "economy"):
        raise ValueError("经济系统未启用")
    cfg = get_feature_config(service_id, "economy")
    pid = str(product_id or "").strip()
    product = next((p for p in (cfg.get("products") or []) if str(p.get("id")) == pid), None)
    if not product:
        raise ValueError("商品不存在")
    price = int(product.get("price") or 0)
    currency = str(product.get("currency_id") or "gold")
    init_db()
    with get_cursor() as cur:
        wallet = _wallet_row(cur, service_id, player_id, currency)
        balance = int(wallet["balance"] or 0) if wallet else 0
        if balance < price:
            raise ValueError("余额不足")
        now = _now_iso()
        cur.execute(
            """
            INSERT INTO baas_wallets (service_id, player_id, currency_id, balance, updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(service_id, player_id, currency_id) DO UPDATE SET
                balance=excluded.balance, updated_at=excluded.updated_at
            """,
            (service_id, player_id, currency, balance - price, now),
        )
        order_id = new_id("ord_")
        cur.execute(
            """
            INSERT INTO baas_shop_orders (order_id, service_id, player_id, product_id, price, currency_id, created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (order_id, service_id, player_id, pid, price, currency, now),
        )
    return {"order_id": order_id, "product_id": pid, "spent": price, "currency_id": currency}


# --- Achievement ---


def list_achievements(service_id: str, player_id: str) -> List[Dict[str, Any]]:
    if not feature_enabled(service_id, "achievement"):
        return []
    cfg = get_feature_config(service_id, "achievement")
    defs = {str(d.get("id")): d for d in (cfg.get("definitions") or []) if d.get("id")}
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            "SELECT achievement_id, status, progress, claimed_at FROM baas_player_achievements WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchall()
    progress = {str(r["achievement_id"]): dict(r) for r in rows}
    out = []
    for aid, d in defs.items():
        row = progress.get(aid, {})
        out.append({
            "achievement_id": aid,
            "name": d.get("name"),
            "target": d.get("target"),
            "progress": int(row.get("progress") or 0),
            "status": row.get("status") or "locked",
            "claimed_at": row.get("claimed_at") or "",
        })
    return out


def claim_achievement(service_id: str, player_id: str, achievement_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "achievement"):
        raise ValueError("成就功能未启用")
    aid = str(achievement_id or "").strip()
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_player_achievements WHERE service_id=? AND player_id=? AND achievement_id=?",
            (service_id, player_id, aid),
        ).fetchone()
        if not row or row["status"] != "completed":
            raise ValueError("成就未完成")
        cur.execute(
            "UPDATE baas_player_achievements SET status='claimed', claimed_at=?, updated_at=? WHERE service_id=? AND player_id=? AND achievement_id=?",
            (now, now, service_id, player_id, aid),
        )
    return {"achievement_id": aid, "status": "claimed", "claimed_at": now}


def report_achievement_progress(service_id: str, player_id: str, achievement_id: str, progress: int) -> Dict[str, Any]:
    if not feature_enabled(service_id, "achievement"):
        raise ValueError("成就功能未启用")
    aid = str(achievement_id or "").strip()
    cfg = get_feature_config(service_id, "achievement")
    target = next((int(d.get("target") or 1) for d in (cfg.get("definitions") or []) if str(d.get("id")) == aid), 1)
    status = "completed" if int(progress) >= target else "in_progress"
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_player_achievements (service_id, player_id, achievement_id, status, progress, updated_at, claimed_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(service_id, player_id, achievement_id) DO UPDATE SET
                progress=excluded.progress, status=excluded.status, updated_at=excluded.updated_at
            """,
            (service_id, player_id, aid, status, int(progress), now, ""),
        )
    return {"achievement_id": aid, "progress": int(progress), "status": status}


# --- Gift ---


def redeem_gift(service_id: str, player_id: str, code: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "gift"):
        raise ValueError("礼包功能未启用")
    c = str(code or "").strip().upper()
    if not c:
        raise ValueError("兑换码必填")
    cfg = get_feature_config(service_id, "gift")
    pack = next((p for p in (cfg.get("codes") or []) if str(p.get("code", "")).upper() == c), None)
    rewards = (pack or {}).get("rewards") or []
    init_db()
    with get_cursor() as cur:
        gm_code = cur.execute(
            "SELECT * FROM baas_gift_codes WHERE service_id=? AND code=?",
            (service_id, c),
        ).fetchone()
        if gm_code:
            code_type = str(gm_code["code_type"] or "shared").lower() if "code_type" in gm_code.keys() else "shared"
            assigned = str(gm_code["assigned_player_id"] or "").strip() if "assigned_player_id" in gm_code.keys() else ""
            per_player_limit = int(gm_code["per_player_limit"] or 1) if "per_player_limit" in gm_code.keys() else 1
            if assigned and assigned != player_id:
                raise ValueError("兑换码仅限指定玩家使用")
            if code_type == "personal":
                if assigned and assigned != player_id:
                    raise ValueError("个人兑换码不可使用")
            max_uses = int(gm_code["max_uses"] or 0)
            use_count = int(gm_code["use_count"] or 0)
            if max_uses > 0 and use_count >= max_uses:
                raise ValueError("兑换码已用完")
            exp = str(gm_code["expires_at"] or "").strip()
            if exp and exp < _now_iso():
                raise ValueError("兑换码已过期")
            rewards = _json_load(gm_code["rewards_json"], [])
            if per_player_limit > 0:
                used_count = cur.execute(
                    "SELECT COUNT(*) AS cnt FROM baas_gift_redemptions WHERE service_id=? AND player_id=? AND code=?",
                    (service_id, player_id, c),
                ).fetchone()
                if int(used_count["cnt"] or 0) >= per_player_limit:
                    raise ValueError("已达个人兑换上限")
        elif not pack:
            raise ValueError("兑换码无效")
        elif int(pack.get("redeemed_count") or 0) >= int(pack.get("max_redeems") or 1):
            raise ValueError("兑换码已用完")
        used = cur.execute(
            "SELECT 1 FROM baas_gift_redemptions WHERE service_id=? AND player_id=? AND code=? LIMIT 1",
            (service_id, player_id, c),
        ).fetchone()
        code_type = str(gm_code["code_type"] or "shared").lower() if gm_code and "code_type" in gm_code.keys() else "shared"
        if used and code_type != "compensation":
            raise ValueError("已兑换过该礼包")
        now = _now_iso()
        rid = new_id("gred_")
        cur.execute(
            "INSERT INTO baas_gift_redemptions (redemption_id, service_id, player_id, code, rewards_json, created_at) VALUES (?,?,?,?,?,?)",
            (rid, service_id, player_id, c, _json_dump(rewards), now),
        )
        if gm_code:
            cur.execute(
                "UPDATE baas_gift_codes SET use_count=use_count+1 WHERE service_id=? AND code=?",
                (service_id, c),
            )
    return {"code": c, "rewards": rewards}

# -*- coding: utf-8 -*-
"""赛季段位、结算、奖励发放（竞技/战令/公会战）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db
from services.baas.afk_reward_grants import grant_rewards
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas import mail_service
from services.baas.service_crud import feature_enabled, get_feature_config


def _ensure_season_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS baas_season_claims (
            service_id TEXT NOT NULL,
            player_id TEXT NOT NULL,
            season_key TEXT NOT NULL,
            claim_type TEXT NOT NULL,
            claim_id TEXT NOT NULL,
            claimed_at TEXT NOT NULL,
            PRIMARY KEY (service_id, player_id, season_key, claim_type, claim_id)
        )
        """
    )


def arena_tier_for_rating(cfg: Dict[str, Any], rating: int) -> Optional[Dict[str, Any]]:
    tiers = sorted(cfg.get("tier_rewards") or [], key=lambda t: int(t.get("min_rating") or 0), reverse=True)
    for t in tiers:
        if int(rating) >= int(t.get("min_rating") or 0):
            return dict(t)
    return None


def claim_arena_tier_reward(service_id: str, player_id: str, tier_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "arena"):
        raise ValueError("竞技场未启用")
    cfg = get_feature_config(service_id, "arena")
    season_id = str(cfg.get("season_id") or "arena_s1")
    tid = str(tier_id or "").strip()
    tier = next((t for t in (cfg.get("tier_rewards") or []) if str(t.get("tier")) == tid), None)
    if not tier:
        raise ValueError("段位不存在")
    from services.baas.arena_service import get_state

    state = get_state(service_id, player_id)
    rating = int(state.get("rating") or 0)
    if rating < int(tier.get("min_rating") or 0):
        raise ValueError("积分未达段位要求")
    init_db()
    with get_cursor() as cur:
        _ensure_season_table(cur)
        exists = cur.execute(
            "SELECT 1 FROM baas_season_claims WHERE service_id=? AND player_id=? AND season_key=? AND claim_type=? AND claim_id=?",
            (service_id, player_id, season_id, "arena_tier", tid),
        ).fetchone()
        if exists:
            raise ValueError("已领取")
        rewards = dict(tier.get("rewards") or {})
        granted = grant_rewards(cur, service_id, player_id, rewards) if rewards else []
        now = _now_iso()
        cur.execute(
            "INSERT INTO baas_season_claims (service_id, player_id, season_key, claim_type, claim_id, claimed_at) VALUES (?,?,?,?,?,?)",
            (service_id, player_id, season_id, "arena_tier", tid, now),
        )
    return {"tier": tid, "rewards": granted}


def settle_arena_season(service_id: str, *, actor: str = "system") -> Dict[str, Any]:
    """GM/定时：按排行榜发放赛季排名奖励邮件。"""
    if not feature_enabled(service_id, "arena"):
        raise ValueError("竞技场未启用")
    cfg = get_feature_config(service_id, "arena")
    season_id = str(cfg.get("season_id") or "arena_s1")
    board_id = str(cfg.get("rating_board_id") or "arena")
    rank_rewards = list(cfg.get("rank_rewards") or [])
    from services.baas import retention_services

    top = retention_services.top_scores(service_id, board_id, limit=500)
    sent = 0
    init_db()
    with get_cursor() as cur:
        _ensure_season_table(cur)
        for idx, row in enumerate(top, start=1):
            pid = str(row.get("player_id") or "")
            if not pid:
                continue
            pack = next((r for r in rank_rewards if int(r.get("rank_min") or 0) <= idx <= int(r.get("rank_max") or 9999)), None)
            if not pack:
                continue
            claim_id = f"rank_{idx}"
            exists = cur.execute(
                "SELECT 1 FROM baas_season_claims WHERE service_id=? AND player_id=? AND season_key=? AND claim_type=? AND claim_id=?",
                (service_id, pid, season_id, "arena_rank", claim_id),
            ).fetchone()
            if exists:
                continue
            attachments = []
            for k, v in (pack.get("rewards") or {}).items():
                if k in ("gold", "diamond", "arena_coin"):
                    attachments.append({"type": "currency", "currency_id": k, "amount": int(v)})
                else:
                    attachments.append({"type": "item", "item_id": k, "quantity": int(v)})
            mail_service.send_mail(
                service_id,
                {
                    "player_id": pid,
                    "title": str(pack.get("mail_title") or f"竞技赛季 {season_id} 排名奖励"),
                    "body": str(pack.get("mail_body") or f"恭喜获得第 {idx} 名赛季奖励"),
                    "attachments": attachments,
                },
                actor=actor,
            )
            cur.execute(
                "INSERT INTO baas_season_claims (service_id, player_id, season_key, claim_type, claim_id, claimed_at) VALUES (?,?,?,?,?,?)",
                (service_id, pid, season_id, "arena_rank", claim_id, _now_iso()),
            )
            sent += 1
    return {"season_id": season_id, "mails_sent": sent}


def list_arena_tier_status(service_id: str, player_id: str) -> Dict[str, Any]:
    cfg = get_feature_config(service_id, "arena")
    season_id = str(cfg.get("season_id") or "arena_s1")
    from services.baas.arena_service import get_state

    rating = int(get_state(service_id, player_id).get("rating") or 0)
    init_db()
    with get_cursor() as cur:
        _ensure_season_table(cur)
        claimed = cur.execute(
            "SELECT claim_id FROM baas_season_claims WHERE service_id=? AND player_id=? AND season_key=? AND claim_type=?",
            (service_id, player_id, season_id, "arena_tier"),
        ).fetchall()
    claimed_ids = {str(r["claim_id"]) for r in claimed}
    tiers = []
    for t in cfg.get("tier_rewards") or []:
        tid = str(t.get("tier") or "")
        tiers.append({
            "tier": tid,
            "min_rating": int(t.get("min_rating") or 0),
            "rewards": t.get("rewards"),
            "status": "claimed" if tid in claimed_ids else ("eligible" if rating >= int(t.get("min_rating") or 0) else "locked"),
        })
    current = arena_tier_for_rating(cfg, rating)
    return {
        "season_id": season_id,
        "season_name": cfg.get("season_name"),
        "season_ends_at": cfg.get("season_ends_at"),
        "rating": rating,
        "current_tier": current.get("tier") if current else None,
        "tiers": tiers,
    }


def _bump_season_id(season_id: str) -> str:
    import re

    sid = str(season_id or "s1")
    m = re.fullmatch(r"(.+_s)(\d+)", sid)
    if m:
        return f"{m.group(1)}{int(m.group(2)) + 1}"
    m2 = re.search(r"(\d+)$", sid)
    if m2:
        return sid[: m2.start()] + str(int(m2.group(1)) + 1)
    return sid + "_next"


def _rewards_to_mail_attachments(rewards: Dict[str, Any]) -> List[Dict[str, Any]]:
    attachments: List[Dict[str, Any]] = []
    for k, v in (rewards or {}).items():
        if int(v or 0) <= 0:
            continue
        if k in ("gold", "diamond", "arena_coin", "guild_coin", "guild_badge"):
            attachments.append({"type": "currency", "currency_id": k, "amount": int(v)})
        else:
            attachments.append({"type": "item", "item_id": k, "quantity": int(v)})
    return attachments


def rollover_battlepass_season(service_id: str, *, actor: str = "system") -> Dict[str, Any]:
    """战令赛季结束：补发未领奖励邮件，推进 season_id。"""
    if not feature_enabled(service_id, "battlepass"):
        raise ValueError("战令未启用")
    from datetime import datetime, timedelta, timezone

    from services.baas.service_crud import patch_feature_config

    cfg = get_feature_config(service_id, "battlepass")
    season_id = str(cfg.get("season_id") or "s1")
    level_rewards = list(cfg.get("level_rewards") or [])
    mailed = 0
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS baas_battlepass_premium_claims (
                service_id TEXT NOT NULL, player_id TEXT NOT NULL, season_id TEXT NOT NULL,
                claimed_levels_json TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY (service_id, player_id, season_id)
            )
            """
        )
        rows = cur.execute(
            "SELECT * FROM baas_battlepass_progress WHERE service_id=? AND season_id=?",
            (service_id, season_id),
        ).fetchall()
        for row in rows:
            pid = str(row["player_id"] or "")
            if not pid:
                continue
            bp_level = int(row["level"] or 1)
            claimed = {int(x) for x in _json_load(row["claimed_levels_json"], [])}
            premium = bool(row["premium"])
            prem_row = cur.execute(
                "SELECT claimed_levels_json FROM baas_battlepass_premium_claims WHERE service_id=? AND player_id=? AND season_id=?",
                (service_id, pid, season_id),
            ).fetchone()
            claimed_premium = {int(x) for x in _json_load(prem_row["claimed_levels_json"], [])} if prem_row else set()
            pending: Dict[str, int] = {}
            for lr in level_rewards:
                lv = int(lr.get("level") or 0)
                if lv <= 0 or lv > bp_level:
                    continue
                if lv not in claimed:
                    for k, v in dict(lr.get("free_rewards") or {}).items():
                        pending[k] = pending.get(k, 0) + int(v or 0)
                if premium and lv not in claimed_premium:
                    for k, v in dict(lr.get("premium_rewards") or {}).items():
                        pending[k] = pending.get(k, 0) + int(v or 0)
            attachments = _rewards_to_mail_attachments(pending)
            if not attachments:
                continue
            mail_service.send_mail(
                service_id,
                {
                    "player_id": pid,
                    "title": str(cfg.get("season_name") or season_id) + " 未领战令奖励",
                    "body": "新赛季已开启，以下为上赛季未领取的战令奖励。",
                    "attachments": attachments,
                },
                actor=actor,
            )
            mailed += 1
    new_sid = _bump_season_id(season_id)
    new_ends = (datetime.now(timezone.utc) + timedelta(days=60)).strftime("%Y-%m-%dT23:59:59+00:00")
    patch_feature_config(
        service_id,
        "battlepass",
        {
            "season_id": new_sid,
            "season_ends_at": new_ends,
            "season_name": f"裂隙战令 {new_sid.split('_')[-1].upper()}",
        },
    )
    return {"old_season_id": season_id, "new_season_id": new_sid, "mails_sent": mailed, "season_ends_at": new_ends}

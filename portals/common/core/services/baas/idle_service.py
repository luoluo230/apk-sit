# -*- coding: utf-8 -*-
"""挂机离线收益 — 使用正式 ROI 公式。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from models.db import get_cursor, init_db
from services.baas.helpers import _now_iso
from services.baas.pve_service import get_progress
from services.baas.service_crud import feature_enabled, get_feature_config
from services.baas.wallet_helpers import credit_wallet
from services.baas.afk_config_loader import afk_formulas
from services.baas.afk_formula_engine import eval_formula, team_power_from_defs
from services.baas.afk_config_loader import hero_def_map


def _parse_iso(ts: str) -> datetime:
    raw = str(ts or "").strip().replace("Z", "+00:00")
    if not raw:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(raw)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def _max_cleared_stage(progress: Dict[str, Any]) -> int:
    best = 0
    for row in progress.get("stages") or []:
        if int(row.get("cleared") or 0) <= 0:
            continue
        sid = str(row.get("stage_id") or "")
        if sid.startswith("AFK_"):
            try:
                parts = sid.split("_")
                num = (int(parts[1]) - 1) * 10 + int(parts[2])
                best = max(best, num)
            except (IndexError, ValueError):
                pass
    return best


def _estimate_team_power(service_id: str, player_id: str) -> int:
    from services.baas.afk_power_service import team_power_unified

    info = team_power_unified(service_id, player_id)
    return int(info.get("team_power") or 0)


def get_status(service_id: str, player_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "idle"):
        raise ValueError("挂机功能未启用")
    cfg = get_feature_config(service_id, "idle")
    formulas = afk_formulas() or None
    max_hours = float(eval_formula("idle_max_hours", {}, formulas=formulas))
    required_stage = str(cfg.get("requires_stage_cleared") or "").strip()
    if required_stage:
        progress = get_progress(service_id, player_id)
        cleared = {s.get("stage_id") for s in (progress.get("stages") or []) if int(s.get("cleared") or 0)}
        if required_stage not in cleared:
            return {"eligible": False, "reason": "需先通关 " + required_stage, "accumulated_minutes": 0, "estimated_gold": 0}
    progress = get_progress(service_id, player_id)
    max_cleared = _max_cleared_stage(progress)
    if max_cleared < 1:
        return {"eligible": False, "reason": "通关第 1 关后解锁", "max_cleared_stage": 0, "accumulated_minutes": 0, "estimated_gold": 0}
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT last_claim_at FROM baas_idle_state WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchone()
        if row is None:
            from services.baas.afk_home_service import ensure_idle_started
            ensure_idle_started(cur, service_id, player_id)
            row = cur.execute("SELECT last_claim_at FROM baas_idle_state WHERE service_id=? AND player_id=?", (service_id, player_id)).fetchone()
    last = _parse_iso(row["last_claim_at"])
    now = datetime.now(timezone.utc)
    raw_minutes = max(0, int((now - last).total_seconds() // 60))
    team_pwr = _estimate_team_power(service_id, player_id)
    from services.baas.afk_formula_engine import idle_gold_per_hour_value, idle_item_rewards

    gold_per_hour = idle_gold_per_hour_value(max_cleared, team_pwr)
    vip_mul = 1.0
    try:
        from services.baas.afk_vip_service import idle_bonus_mul

        vip_mul = idle_bonus_mul(service_id, player_id)
    except Exception:
        pass
    idle_mul = 1.0
    try:
        from services.baas.afk_config_group import group_factors

        idle_mul = float(group_factors(service_id, player_id).get("idle_gold_mul") or 1)
    except Exception:
        idle_mul = 1.0
    gold_per_hour = int(gold_per_hour * vip_mul * idle_mul)
    cap_minutes = int(max_hours * 60)
    if max_cleared >= 700:
        cap_minutes = max(cap_minutes, 20 * 60)
    elif max_cleared >= 80:
        cap_minutes = max(cap_minutes, 16 * 60)
    minutes = min(raw_minutes, cap_minutes)
    est_gold = int(minutes / 60 * gold_per_hour)
    items = idle_item_rewards(max_cleared, minutes)
    from services.baas.afk_home_service import rules
    home_cfg = rules()
    exp_rate = max(int(home_cfg["idle_exp_min_per_hour"]), max_cleared * int(home_cfg["idle_exp_stage_multiplier"])) if max_cleared > 0 else 0
    diamond_rate = int(home_cfg["idle_diamond_per_hour"]) if max_cleared >= int(home_cfg["idle_diamond_unlock_stage"]) else 0
    return {
        "eligible": True,
        "accumulated_minutes": minutes,
        "max_minutes": cap_minutes,
        "gold_per_hour": gold_per_hour,
        "estimated_gold": est_gold,
        "estimated_items": items,
        "account_exp_per_hour": exp_rate, "diamond_per_hour": diamond_rate,
        "estimated_account_exp": minutes * exp_rate // 60, "estimated_diamond": minutes * diamond_rate // 60,
        "vip_idle_bonus_mul": vip_mul,
        "group_idle_mul": idle_mul,
        "team_power": team_pwr,
        "max_cleared_stage": max_cleared,
        "last_claim_at": row["last_claim_at"] if row else "",
    }


def claim(service_id: str, player_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "idle"):
        raise ValueError("挂机功能未启用")
    status = get_status(service_id, player_id)
    if not status.get("eligible"):
        raise ValueError(str(status.get("reason") or "暂不可领取"))
    gold = int(status.get("estimated_gold") or 0)
    items = dict(status.get("estimated_items") or {})
    exp = int(status.get("estimated_account_exp") or 0)
    diamonds = int(status.get("estimated_diamond") or 0)
    if gold <= 0 and exp <= 0 and diamonds <= 0 and not items:
        raise ValueError("暂无离线收益")
    now = _now_iso()
    init_db()
    granted_items: Dict[str, int] = {}
    with get_cursor() as cur:
        # Consume the exact preview anchor in the same transaction as every reward.
        consumed = cur.execute("""UPDATE baas_idle_state SET last_claim_at=?,updated_at=?
            WHERE service_id=? AND player_id=? AND last_claim_at=? RETURNING last_claim_at""",
            (now,now,service_id,player_id,status["last_claim_at"])).fetchone()
        if consumed is None:
            raise ValueError("收益已领取，请刷新后重试")
        from services.baas.afk_home_service import grant_account_exp
        account = grant_account_exp(cur, service_id, player_id, exp) if exp > 0 else None
        if diamonds > 0: credit_wallet(cur, service_id, player_id, "diamond", diamonds)
        if gold > 0:
            credit_wallet(cur, service_id, player_id, "gold", gold)
        if items and feature_enabled(service_id, "inventory"):
            from services.baas import inventory_service

            for key, qty in items.items():
                try:
                    inventory_service.grant_item(cur, service_id, player_id, str(key), quantity=int(qty))
                    granted_items[str(key)] = int(qty)
                except ValueError:
                    continue
        cur.execute(
            """
            INSERT INTO baas_idle_state (service_id, player_id, last_claim_at, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(service_id, player_id) DO UPDATE SET
                last_claim_at=excluded.last_claim_at, updated_at=excluded.updated_at
            """,
            (service_id, player_id, now, now),
        )
    try:
        from services.baas.afk_retention_hooks import on_idle_claim
        on_idle_claim(service_id, player_id)
    except Exception:
        pass
    return {
        "claimed_gold": gold,
        "claimed_account_exp": exp, "claimed_diamond": diamonds, "account": account,
        "claimed_items": granted_items,
        "accumulated_minutes": status.get("accumulated_minutes"),
        "max_cleared_stage": status.get("max_cleared_stage"),
        "claimed_at": now,
    }

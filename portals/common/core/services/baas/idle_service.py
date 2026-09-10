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
        return datetime.fromisoformat(raw)
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
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT last_claim_at FROM baas_idle_state WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchone()
    last = _parse_iso(row["last_claim_at"] if row else "")
    now = datetime.now(timezone.utc)
    minutes = max(0, int((now - last).total_seconds() // 60))
    cap_minutes = int(max_hours * 60)
    minutes = min(minutes, cap_minutes)
    progress = get_progress(service_id, player_id)
    max_cleared = _max_cleared_stage(progress)
    team_pwr = _estimate_team_power(service_id, player_id)
    gold_per_hour = eval_formula(
        "idle_gold_per_hour",
        {"max_cleared_stage": max_cleared, "team_power": team_pwr},
        formulas=formulas,
    )
    vip_mul = 1.0
    try:
        from services.baas.afk_vip_service import idle_bonus_mul

        vip_mul = idle_bonus_mul(service_id, player_id)
    except Exception:
        pass
    gold_per_hour = int(gold_per_hour * vip_mul)
    est_gold = int(minutes / 60 * gold_per_hour)
    return {
        "eligible": True,
        "accumulated_minutes": minutes,
        "max_minutes": cap_minutes,
        "gold_per_hour": gold_per_hour,
        "estimated_gold": est_gold,
        "vip_idle_bonus_mul": vip_mul,
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
    if gold <= 0:
        raise ValueError("暂无离线收益")
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        credit_wallet(cur, service_id, player_id, "gold", gold)
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
    return {"claimed_gold": gold, "accumulated_minutes": status.get("accumulated_minutes"), "claimed_at": now}

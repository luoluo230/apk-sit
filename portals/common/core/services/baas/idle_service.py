# -*- coding: utf-8 -*-
"""挂机离线收益：按离线时长发放金币等资源。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from models.db import get_cursor, init_db
from services.baas.helpers import _now_iso
from services.baas.pve_service import get_progress
from services.baas.service_crud import feature_enabled, get_feature_config
from services.baas.wallet_helpers import credit_wallet


def _parse_iso(ts: str) -> datetime:
    raw = str(ts or "").strip().replace("Z", "+00:00")
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime.now(timezone.utc)


def get_status(service_id: str, player_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "idle"):
        raise ValueError("挂机功能未启用")
    cfg = get_feature_config(service_id, "idle")
    max_hours = float(cfg.get("max_hours") or 12)
    gold_per_hour = int(cfg.get("gold_per_hour") or 500)
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
    est_gold = int(minutes / 60 * gold_per_hour)
    return {
        "eligible": True,
        "accumulated_minutes": minutes,
        "max_minutes": cap_minutes,
        "gold_per_hour": gold_per_hour,
        "estimated_gold": est_gold,
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
    return {"claimed_gold": gold, "accumulated_minutes": status.get("accumulated_minutes"), "claimed_at": now}

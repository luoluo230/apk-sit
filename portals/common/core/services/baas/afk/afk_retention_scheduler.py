# -*- coding: utf-8 -*-
"""AFK 留存定时任务：竞技赛季结算、战令赛季 rollover。"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db
from services.baas.helpers import _now_iso
from services.baas.service_crud import feature_enabled, get_feature_config, patch_feature_config

logger = logging.getLogger(__name__)


def _parse_iso(ts: str) -> datetime:
    raw = str(ts or "").strip().replace("Z", "+00:00")
    if not raw:
        return datetime.max.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return datetime.max.replace(tzinfo=timezone.utc)


def _season_expired(ends_at: Optional[str]) -> bool:
    if not ends_at:
        return False
    return datetime.now(timezone.utc) >= _parse_iso(ends_at)


def _ensure_kv(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS baas_scheduler_kv (
            kv_key TEXT PRIMARY KEY,
            kv_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _kv_get(cur, key: str) -> str:
    _ensure_kv(cur)
    row = cur.execute("SELECT kv_value FROM baas_scheduler_kv WHERE kv_key=?", (key,)).fetchone()
    return str(row["kv_value"] or "") if row else ""


def _kv_set(cur, key: str, value: str) -> None:
    _ensure_kv(cur)
    now = _now_iso()
    cur.execute(
        """
        INSERT INTO baas_scheduler_kv (kv_key, kv_value, updated_at)
        VALUES (?,?,?)
        ON CONFLICT(kv_key) DO UPDATE SET kv_value=excluded.kv_value, updated_at=excluded.updated_at
        """,
        (key, value, now),
    )


def _bump_season_id(season_id: str) -> str:
    sid = str(season_id or "s1")
    m = re.fullmatch(r"(.+_s)(\d+)", sid)
    if m:
        return f"{m.group(1)}{int(m.group(2)) + 1}"
    m2 = re.search(r"(\d+)$", sid)
    if m2:
        return sid[: m2.start()] + str(int(m2.group(1)) + 1)
    return sid + "_next"


def list_active_service_ids() -> List[str]:
    init_db()
    with get_cursor() as cur:
        rows = cur.execute("SELECT service_id FROM baas_services WHERE status='active'").fetchall()
    return [str(r["service_id"]) for r in rows]


def tick_service_retention(service_id: str) -> Dict[str, Any]:
    """对单个 BaaS 服务检查并执行赛季结算 / 战令 rollover。"""
    from services.baas import afk_season_service

    out: Dict[str, Any] = {"service_id": service_id}
    init_db()
    with get_cursor() as cur:
        if feature_enabled(service_id, "arena"):
            cfg = get_feature_config(service_id, "arena")
            season_id = str(cfg.get("season_id") or "arena_s1")
            ends_at = cfg.get("season_ends_at")
            kv_key = f"arena_settle:{service_id}:{season_id}"
            if _season_expired(ends_at) and _kv_get(cur, kv_key) != "done":
                result = afk_season_service.settle_arena_season(service_id, actor="scheduler")
                new_sid = _bump_season_id(season_id)
                new_ends = (datetime.now(timezone.utc) + timedelta(days=90)).strftime("%Y-%m-%dT23:59:59+00:00")
                patch_feature_config(
                    service_id,
                    "arena",
                    {
                        "season_id": new_sid,
                        "season_ends_at": new_ends,
                        "season_name": f"裂隙竞技 {new_sid.split('_')[-1].upper()}",
                    },
                )
                _kv_set(cur, kv_key, "done")
                out["arena"] = {"settled": True, **result, "new_season_id": new_sid}

        if feature_enabled(service_id, "battlepass"):
            cfg = get_feature_config(service_id, "battlepass")
            season_id = str(cfg.get("season_id") or "s1")
            ends_at = cfg.get("season_ends_at")
            kv_key = f"bp_rollover:{service_id}:{season_id}"
            if _season_expired(ends_at) and _kv_get(cur, kv_key) != "done":
                result = afk_season_service.rollover_battlepass_season(service_id, actor="scheduler")
                _kv_set(cur, kv_key, "done")
                out["battlepass"] = {"rolled_over": True, **result}
    return out


def run_retention_tick() -> Dict[str, Any]:
    """遍历全部活跃 BaaS 服务，执行留存赛季任务。"""
    touched: List[Dict[str, Any]] = []
    for sid in list_active_service_ids():
        try:
            stat = tick_service_retention(sid)
            if stat.get("arena") or stat.get("battlepass"):
                touched.append(stat)
                logger.info("retention tick: %s", stat)
        except Exception as exc:
            logger.warning("retention tick failed for %s: %s", sid, exc)
    return {"services_checked": len(list_active_service_ids()), "actions": touched}

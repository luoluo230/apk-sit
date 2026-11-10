# -*- coding: utf-8 -*-
"""Wave B capacity helpers: Redis URL, pool sizing, load smoke targets."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional


def redis_url() -> str:
    return str(os.environ.get("REDIS_URL") or "").strip()


def redis_enabled() -> bool:
    return bool(redis_url())


def postgres_pool_settings() -> Dict[str, Any]:
    """Advisory pool sizes for 10万 DAU skeleton (per process)."""
    workers = max(1, int(os.environ.get("BAAS_WORKERS") or 1))
    # Keep total connections under typical Postgres max_connections budget
    max_conn = max(4, min(32, workers * 4))
    return {
        "workers": workers,
        "pool_size": max(2, workers * 2),
        "max_overflow": max(2, workers),
        "max_conn_hint": max_conn,
        "database_url_set": bool(str(os.environ.get("DATABASE_URL") or "").strip()),
        "redis_enabled": redis_enabled(),
    }


def get_redis_client() -> Optional[Any]:
    url = redis_url()
    if not url:
        return None
    try:
        import redis  # type: ignore

        return redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
    except Exception:
        return None


def redis_ping() -> Dict[str, Any]:
    client = get_redis_client()
    if client is None:
        return {"ok": False, "configured": False}
    try:
        client.ping()
        return {"ok": True, "configured": True}
    except Exception as exc:
        return {"ok": False, "configured": True, "error": str(exc)[:200]}


def rate_limit_key(service_id: str, player_id: str, bucket: str) -> str:
    return f"baas:rl:{service_id}:{player_id}:{bucket}"


def dau100k_smoke_targets() -> Dict[str, Any]:
    """Rough peak targets used by load smoke evidence (not a full soak)."""
    # 10万 DAU × ~20 req/day ≈ 2e6/day ≈ 23 RPS avg; peak ~10x → ~230 RPS
    return {
        "dau_target": 100_000,
        "avg_rps": 25,
        "peak_rps_smoke": 50,
        "duration_sec": 10,
        "success_ratio_min": 0.95,
    }

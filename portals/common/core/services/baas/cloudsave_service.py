# -*- coding: utf-8 -*-
"""Cloud save KV feature."""

from __future__ import annotations

from typing import Any, Dict, List

from models.db import get_cursor, init_db
from services.baas.helpers import _json_dump, _json_load, _now_iso
from services.baas.service_crud import feature_enabled, get_feature_config


def get_key(service_id: str, player_id: str, key: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "cloudsave"):
        raise ValueError("云存档功能未启用")
    k = str(key or "").strip()
    if not k:
        raise ValueError("key 必填")
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            """
            SELECT * FROM baas_player_data
            WHERE service_id=? AND player_id=? AND data_key=?
            """,
            (service_id, player_id, k),
        ).fetchone()
    if not row:
        return {"key": k, "value": None, "version": 0}
    return {
        "key": k,
        "value": _json_load(row["value_json"], None),
        "version": int(row["version"] or 0),
        "updated_at": row["updated_at"],
    }


def put_key(service_id: str, player_id: str, key: str, value: Any, *, expected_version: int = -1) -> Dict[str, Any]:
    if not feature_enabled(service_id, "cloudsave"):
        raise ValueError("云存档功能未启用")
    cfg = get_feature_config(service_id, "cloudsave")
    k = str(key or "").strip()
    if not k:
        raise ValueError("key 必填")
    payload = _json_dump(value)
    if len(payload.encode("utf-8")) > int(cfg.get("max_value_bytes") or 65536):
        raise ValueError("存档数据过大")
    init_db()
    with get_cursor() as cur:
        count = cur.execute(
            "SELECT COUNT(*) AS c FROM baas_player_data WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchone()
        existing = cur.execute(
            "SELECT * FROM baas_player_data WHERE service_id=? AND player_id=? AND data_key=?",
            (service_id, player_id, k),
        ).fetchone()
        max_keys = int(cfg.get("max_keys_per_player") or 32)
        if not existing and int(count["c"] or 0) >= max_keys:
            raise ValueError("存档 key 数量已达上限")
        if existing and expected_version >= 0 and int(existing["version"] or 0) != expected_version:
            raise ValueError("版本冲突")
        version = int(existing["version"] or 0) + 1 if existing else 1
        now = _now_iso()
        cur.execute(
            """
            INSERT INTO baas_player_data (service_id, player_id, data_key, value_json, version, updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(service_id, player_id, data_key) DO UPDATE SET
                value_json=excluded.value_json, version=excluded.version, updated_at=excluded.updated_at
            """,
            (service_id, player_id, k, payload, version, now),
        )
    return {"key": k, "value": value, "version": version, "updated_at": now}


def list_keys(service_id: str, player_id: str) -> List[str]:
    if not feature_enabled(service_id, "cloudsave"):
        return []
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            "SELECT data_key FROM baas_player_data WHERE service_id=? AND player_id=? ORDER BY data_key",
            (service_id, player_id),
        ).fetchall()
    return [str(r["data_key"]) for r in rows]

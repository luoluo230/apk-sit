# -*- coding: utf-8
"""Persist casual room / replay state to SQLite or PostgreSQL."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db
from services.baas.helpers import _now_iso


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _json_load(raw: str) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def save_room(room: Dict[str, Any]) -> None:
    if not room or not room.get("room_id"):
        return
    init_db()
    now = _now_iso()
    payload = dict(room)
    payload.pop("updated_ts", None)
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_rooms (room_id, service_id, status, state_json, updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(room_id) DO UPDATE SET
                service_id=excluded.service_id,
                status=excluded.status,
                state_json=excluded.state_json,
                updated_at=excluded.updated_at
            """,
            (
                str(room.get("room_id") or ""),
                str(room.get("service_id") or ""),
                str(room.get("status") or "waiting"),
                _json_dump(payload),
                now,
            ),
        )


def load_room(room_id: str) -> Optional[Dict[str, Any]]:
    rid = str(room_id or "").strip()
    if not rid:
        return None
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT state_json FROM baas_rooms WHERE room_id=? LIMIT 1",
            (rid,),
        ).fetchone()
    if not row:
        return None
    data = _json_load(row["state_json"] if hasattr(row, "keys") else row[0])
    if not isinstance(data, dict):
        return None
    data["room_id"] = data.get("room_id") or rid
    return data


def delete_room(room_id: str) -> None:
    rid = str(room_id or "").strip()
    if not rid:
        return
    init_db()
    with get_cursor() as cur:
        cur.execute("DELETE FROM baas_rooms WHERE room_id=?", (rid,))


def list_room_ids(service_id: str, *, status: str = "") -> List[str]:
    init_db()
    sid = str(service_id or "").strip()
    st = str(status or "").strip().lower()
    with get_cursor() as cur:
        if st:
            rows = cur.execute(
                "SELECT room_id FROM baas_rooms WHERE service_id=? AND status=?",
                (sid, st),
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT room_id FROM baas_rooms WHERE service_id=?",
                (sid,),
            ).fetchall()
    return [str(r["room_id"] if hasattr(r, "keys") else r[0]) for r in rows]


def save_replay(replay: Dict[str, Any]) -> None:
    if not replay or not replay.get("replay_id"):
        return
    init_db()
    now = str(replay.get("created_at") or _now_iso())
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_room_replays (replay_id, service_id, room_id, battle_id, payload_json, created_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(replay_id) DO UPDATE SET
                payload_json=excluded.payload_json,
                created_at=excluded.created_at
            """,
            (
                str(replay.get("replay_id") or ""),
                str(replay.get("service_id") or ""),
                str(replay.get("room_id") or ""),
                str(replay.get("battle_id") or ""),
                _json_dump(dict(replay)),
                now,
            ),
        )


def load_replay(replay_id: str) -> Optional[Dict[str, Any]]:
    rid = str(replay_id or "").strip()
    if not rid:
        return None
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT payload_json FROM baas_room_replays WHERE replay_id=? LIMIT 1",
            (rid,),
        ).fetchone()
    if not row:
        return None
    data = _json_load(row["payload_json"] if hasattr(row, "keys") else row[0])
    return dict(data) if isinstance(data, dict) else None


def list_replays(service_id: str, *, limit: int = 20) -> List[Dict[str, Any]]:
    init_db()
    lim = max(1, min(int(limit or 20), 100))
    with get_cursor() as cur:
        rows = cur.execute(
            """
            SELECT payload_json FROM baas_room_replays
            WHERE service_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (str(service_id or ""), lim),
        ).fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        data = _json_load(row["payload_json"] if hasattr(row, "keys") else row[0])
        if isinstance(data, dict):
            out.append(data)
    return out

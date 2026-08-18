# -*- coding: utf-8 -*-
"""Phase 4: PVP room state sync (REST-based MVP)."""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas.service_crud import feature_enabled, get_feature_config

_lock = threading.RLock()
_rooms: Dict[str, Dict[str, Any]] = {}


def matchmake(service_id: str, player_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "pvp"):
        raise ValueError("PVP 功能未启用")
    cfg = get_feature_config(service_id, "pvp")
    max_players = int(cfg.get("max_players") or 2)
    with _lock:
        for room_id, room in _rooms.items():
            if room.get("service_id") != service_id:
                continue
            if room.get("status") != "waiting":
                continue
            players = room.get("players") or []
            if player_id in players:
                return {"room_id": room_id, "players": players, "status": room.get("status")}
            if len(players) < max_players:
                players.append(player_id)
                room["players"] = players
                room["updated_at"] = _now_iso()
                if len(players) >= max_players:
                    room["status"] = "active"
                return {"room_id": room_id, "players": players, "status": room["status"]}
        room_id = new_id("room_")
        _rooms[room_id] = {
            "room_id": room_id,
            "service_id": service_id,
            "status": "waiting",
            "players": [player_id],
            "state": {},
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        return {"room_id": room_id, "players": [player_id], "status": "waiting"}


def get_room(service_id: str, room_id: str) -> Dict[str, Any]:
    with _lock:
        room = _rooms.get(room_id)
        if not room or room.get("service_id") != service_id:
            raise ValueError("房间不存在")
        return {
            "room_id": room_id,
            "status": room.get("status"),
            "players": list(room.get("players") or []),
            "state": dict(room.get("state") or {}),
            "updated_at": room.get("updated_at"),
        }


def sync_state(service_id: str, room_id: str, player_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    if not feature_enabled(service_id, "pvp"):
        raise ValueError("PVP 功能未启用")
    with _lock:
        room = _rooms.get(room_id)
        if not room or room.get("service_id") != service_id:
            raise ValueError("房间不存在")
        if player_id not in (room.get("players") or []):
            raise ValueError("不在房间内")
        merged = dict(room.get("state") or {})
        merged[player_id] = state
        room["state"] = merged
        room["updated_at"] = _now_iso()
        return get_room(service_id, room_id)


def leave_room(service_id: str, room_id: str, player_id: str) -> Dict[str, Any]:
    with _lock:
        room = _rooms.get(room_id)
        if not room or room.get("service_id") != service_id:
            raise ValueError("房间不存在")
        players = [p for p in (room.get("players") or []) if p != player_id]
        room["players"] = players
        state = dict(room.get("state") or {})
        state.pop(player_id, None)
        room["state"] = state
        room["status"] = "closed" if not players else room.get("status")
        room["updated_at"] = _now_iso()
        return {"room_id": room_id, "players": players, "status": room["status"]}

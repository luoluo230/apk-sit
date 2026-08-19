# -*- coding: utf-8
"""Casual game room + battle sync (REST MVP with fast client integration)."""

from __future__ import annotations

import secrets
import threading
import time
from typing import Any, Dict, List, Optional

from services.baas.helpers import _now_iso, new_id
from services.baas.service_crud import feature_enabled, get_feature_config

_lock = threading.RLock()
_rooms: Dict[str, Dict[str, Any]] = {}
_replays: Dict[str, Dict[str, Any]] = {}
_match_queues: Dict[str, List[str]] = {}


def _cfg(service_id: str) -> Dict[str, Any]:
    cfg = get_feature_config(service_id, "pvp")
    if not isinstance(cfg, dict):
        cfg = {}
    return {
        "max_players": max(2, int(cfg.get("max_players") or 2)),
        "max_spectators": max(0, int(cfg.get("max_spectators") or 8)),
        "room_ttl_seconds": max(60, int(cfg.get("room_ttl_seconds") or 3600)),
        "reconnect_grace_seconds": max(5, int(cfg.get("reconnect_grace_seconds") or 120)),
        "mode": str(cfg.get("mode") or "state_sync"),
        "env_key": str(cfg.get("env_key") or "development"),
    }


def _require_feature(service_id: str) -> None:
    if not feature_enabled(service_id, "pvp"):
        raise ValueError("房间/对战功能未启用")


def _cleanup_expired() -> None:
    now = time.time()
    expired: List[str] = []
    with _lock:
        for room_id, room in _rooms.items():
            ttl = int(room.get("ttl_seconds") or 3600)
            updated = float(room.get("updated_ts") or 0)
            if updated and now - updated > ttl:
                expired.append(room_id)
        for room_id in expired:
            _rooms.pop(room_id, None)


def _public_view(room: Dict[str, Any], *, viewer_id: str = "") -> Dict[str, Any]:
    players = list(room.get("players") or [])
    spectators = list(room.get("spectators") or [])
    disconnected = dict(room.get("disconnected") or {})
    return {
        "room_id": room.get("room_id"),
        "invite_code": room.get("invite_code") if room.get("visibility") == "private" else "",
        "visibility": room.get("visibility"),
        "status": room.get("status"),
        "env_key": room.get("env_key"),
        "mode": room.get("mode"),
        "battle_mode": room.get("battle_mode"),
        "max_players": room.get("max_players"),
        "host_id": room.get("host_id"),
        "players": players,
        "spectators": spectators,
        "disconnected": disconnected,
        "battle_id": room.get("battle_id"),
        "state": dict(room.get("state") or {}),
        "frame_seq": int(room.get("frame_seq") or 0),
        "updated_at": room.get("updated_at"),
        "viewer_role": (
            "host"
            if viewer_id and viewer_id == room.get("host_id")
            else "player"
            if viewer_id in players
            else "spectator"
            if viewer_id in spectators
            else "guest"
        ),
    }


def _touch(room: Dict[str, Any]) -> None:
    room["updated_at"] = _now_iso()
    room["updated_ts"] = time.time()


def create_room(
    service_id: str,
    player_id: str,
    *,
    visibility: str = "public",
    max_players: Optional[int] = None,
    env_key: str = "",
    battle_mode: str = "pvp_1v1",
    password: str = "",
) -> Dict[str, Any]:
    _require_feature(service_id)
    _cleanup_expired()
    cfg = _cfg(service_id)
    cap = max(2, int(max_players or cfg["max_players"]))
    vis = "private" if str(visibility or "").strip().lower() in {"private", "invite"} else "public"
    room_id = new_id("room_")
    invite_code = secrets.token_hex(4).upper() if vis == "private" else ""
    now = _now_iso()
    with _lock:
        _rooms[room_id] = {
            "room_id": room_id,
            "service_id": service_id,
            "visibility": vis,
            "invite_code": invite_code,
            "password": str(password or ""),
            "status": "waiting",
            "env_key": str(env_key or cfg["env_key"]),
            "mode": cfg["mode"],
            "battle_mode": str(battle_mode or "pvp_1v1"),
            "max_players": cap,
            "max_spectators": cfg["max_spectators"],
            "ttl_seconds": cfg["room_ttl_seconds"],
            "reconnect_grace_seconds": cfg["reconnect_grace_seconds"],
            "host_id": player_id,
            "players": [player_id],
            "spectators": [],
            "disconnected": {},
            "state": {},
            "frames": [],
            "frame_seq": 0,
            "battle_id": "",
            "created_at": now,
            "updated_at": now,
            "updated_ts": time.time(),
        }
        return _public_view(_rooms[room_id], viewer_id=player_id)


def list_public_rooms(service_id: str, *, env_key: str = "", limit: int = 20) -> List[Dict[str, Any]]:
    _require_feature(service_id)
    _cleanup_expired()
    ek = str(env_key or "").strip().lower()
    out: List[Dict[str, Any]] = []
    with _lock:
        for room in _rooms.values():
            if room.get("service_id") != service_id:
                continue
            if room.get("visibility") != "public":
                continue
            if room.get("status") not in {"waiting", "active"}:
                continue
            if ek and str(room.get("env_key") or "").lower() != ek:
                continue
            out.append(
                {
                    "room_id": room.get("room_id"),
                    "status": room.get("status"),
                    "env_key": room.get("env_key"),
                    "battle_mode": room.get("battle_mode"),
                    "players": len(room.get("players") or []),
                    "max_players": room.get("max_players"),
                    "updated_at": room.get("updated_at"),
                }
            )
    out.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
    return out[: max(1, min(100, int(limit or 20)))]


def join_room(
    service_id: str,
    player_id: str,
    *,
    room_id: str = "",
    invite_code: str = "",
    password: str = "",
    as_spectator: bool = False,
) -> Dict[str, Any]:
    _require_feature(service_id)
    rid = str(room_id or "").strip()
    code = str(invite_code or "").strip().upper()
    with _lock:
        room = None
        if rid:
            room = _rooms.get(rid)
        elif code:
            room = next(
                (
                    row
                    for row in _rooms.values()
                    if row.get("service_id") == service_id and str(row.get("invite_code") or "").upper() == code
                ),
                None,
            )
        if not room or room.get("service_id") != service_id:
            raise ValueError("房间不存在")
        if room.get("status") == "closed":
            raise ValueError("房间已关闭")
        if str(room.get("password") or "") and str(room.get("password") or "") != str(password or ""):
            raise ValueError("房间密码错误")
        disconnected = dict(room.get("disconnected") or {})
        if player_id in disconnected:
            disconnected.pop(player_id, None)
            room["disconnected"] = disconnected
        players = list(room.get("players") or [])
        spectators = list(room.get("spectators") or [])
        if as_spectator:
            if player_id not in spectators and player_id not in players:
                if len(spectators) >= int(room.get("max_spectators") or 0):
                    raise ValueError("观战人数已满")
                spectators.append(player_id)
        else:
            if player_id not in players:
                if len(players) >= int(room.get("max_players") or 2):
                    raise ValueError("房间已满")
                if room.get("status") == "active" and player_id not in players:
                    raise ValueError("对局已开始，请使用重连接口")
                players.append(player_id)
            spectators = [s for s in spectators if s != player_id]
        room["players"] = players
        room["spectators"] = spectators
        if len(players) >= int(room.get("max_players") or 2) and room.get("status") == "waiting":
            room["status"] = "ready"
        _touch(room)
        return _public_view(room, viewer_id=player_id)


def rejoin_room(service_id: str, room_id: str, player_id: str) -> Dict[str, Any]:
    _require_feature(service_id)
    with _lock:
        room = _rooms.get(room_id)
        if not room or room.get("service_id") != service_id:
            raise ValueError("房间不存在")
        players = list(room.get("players") or [])
        disconnected = dict(room.get("disconnected") or {})
        if player_id not in players and player_id not in disconnected:
            raise ValueError("玩家不在该房间")
        disconnected.pop(player_id, None)
        room["disconnected"] = disconnected
        if room.get("status") == "paused":
            room["status"] = "active"
        _touch(room)
        return _public_view(room, viewer_id=player_id)


def leave_room(service_id: str, room_id: str, player_id: str) -> Dict[str, Any]:
    with _lock:
        room = _rooms.get(room_id)
        if not room or room.get("service_id") != service_id:
            raise ValueError("房间不存在")
        players = [p for p in (room.get("players") or []) if p != player_id]
        spectators = [s for s in (room.get("spectators") or []) if s != player_id]
        disconnected = dict(room.get("disconnected") or {})
        disconnected.pop(player_id, None)
        state = dict(room.get("state") or {})
        state.pop(player_id, None)
        room["players"] = players
        room["spectators"] = spectators
        room["disconnected"] = disconnected
        room["state"] = state
        if str(room.get("host_id") or "") == player_id:
            room["host_id"] = players[0] if players else ""
        if not players and not spectators:
            room["status"] = "closed"
        elif room.get("status") == "active" and len(players) < 2:
            room["status"] = "paused"
        _touch(room)
        return _public_view(room, viewer_id=player_id)


def kick_player(service_id: str, room_id: str, host_id: str, target_id: str) -> Dict[str, Any]:
    with _lock:
        room = _rooms.get(room_id)
        if not room or room.get("service_id") != service_id:
            raise ValueError("房间不存在")
        if str(room.get("host_id") or "") != host_id:
            raise ValueError("仅房主可踢人")
        if target_id == host_id:
            raise ValueError("不能踢出房主")
        room["players"] = [p for p in (room.get("players") or []) if p != target_id]
        room["spectators"] = [s for s in (room.get("spectators") or []) if s != target_id]
        state = dict(room.get("state") or {})
        state.pop(target_id, None)
        room["state"] = state
        _touch(room)
        return _public_view(room, viewer_id=host_id)


def mark_disconnected(service_id: str, room_id: str, player_id: str) -> Dict[str, Any]:
    with _lock:
        room = _rooms.get(room_id)
        if not room or room.get("service_id") != service_id:
            raise ValueError("房间不存在")
        if player_id not in (room.get("players") or []):
            raise ValueError("玩家不在房间内")
        disconnected = dict(room.get("disconnected") or {})
        disconnected[player_id] = _now_iso()
        room["disconnected"] = disconnected
        if room.get("status") == "active":
            room["status"] = "paused"
        _touch(room)
        return _public_view(room, viewer_id=player_id)


def start_battle(service_id: str, room_id: str, player_id: str) -> Dict[str, Any]:
    with _lock:
        room = _rooms.get(room_id)
        if not room or room.get("service_id") != service_id:
            raise ValueError("房间不存在")
        if str(room.get("host_id") or "") != player_id:
            raise ValueError("仅房主可开始对局")
        players = list(room.get("players") or [])
        if len(players) < 2:
            raise ValueError("玩家人数不足，无法开始对局")
        battle_id = str(room.get("battle_id") or "") or new_id("battle_")
        room["battle_id"] = battle_id
        room["status"] = "active"
        room["frames"] = []
        room["frame_seq"] = 0
        _touch(room)
        view = _public_view(room, viewer_id=player_id)
        view["battle_id"] = battle_id
        return view


def sync_state(service_id: str, room_id: str, player_id: str, state: Dict[str, Any]) -> Dict[str, Any]:
    with _lock:
        room = _rooms.get(room_id)
        if not room or room.get("service_id") != service_id:
            raise ValueError("房间不存在")
        if player_id not in (room.get("players") or []):
            raise ValueError("不在房间内")
        merged = dict(room.get("state") or {})
        merged[player_id] = state
        room["state"] = merged
        _touch(room)
        return _public_view(room, viewer_id=player_id)


def push_frame(service_id: str, room_id: str, player_id: str, frame: Dict[str, Any]) -> Dict[str, Any]:
    with _lock:
        room = _rooms.get(room_id)
        if not room or room.get("service_id") != service_id:
            raise ValueError("房间不存在")
        if room.get("status") != "active":
            raise ValueError("对局未开始")
        if player_id not in (room.get("players") or []):
            raise ValueError("不在对局中")
        seq = int(room.get("frame_seq") or 0) + 1
        entry = {"seq": seq, "player_id": player_id, "frame": frame, "at": _now_iso()}
        frames = list(room.get("frames") or [])
        frames.append(entry)
        if len(frames) > 5000:
            frames = frames[-5000:]
        room["frames"] = frames
        room["frame_seq"] = seq
        _touch(room)
        view = _public_view(room, viewer_id=player_id)
        view["last_frame"] = entry
        return view


def get_frames(service_id: str, room_id: str, *, since_seq: int = 0, limit: int = 120) -> Dict[str, Any]:
    with _lock:
        room = _rooms.get(room_id)
        if not room or room.get("service_id") != service_id:
            raise ValueError("房间不存在")
        frames = [f for f in (room.get("frames") or []) if int(f.get("seq") or 0) > int(since_seq or 0)]
        return {
            "room_id": room_id,
            "battle_id": room.get("battle_id"),
            "frames": frames[: max(1, min(500, int(limit or 120)))],
            "frame_seq": int(room.get("frame_seq") or 0),
        }


def finish_battle(service_id: str, room_id: str, player_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    with _lock:
        room = _rooms.get(room_id)
        if not room or room.get("service_id") != service_id:
            raise ValueError("房间不存在")
        if str(room.get("host_id") or "") != player_id:
            raise ValueError("仅房主可结束对局")
        room["status"] = "finished"
        room["result"] = dict(result or {})
        replay_id = new_id("replay_")
        _replays[replay_id] = {
            "replay_id": replay_id,
            "service_id": service_id,
            "room_id": room_id,
            "battle_id": room.get("battle_id"),
            "players": list(room.get("players") or []),
            "frames": list(room.get("frames") or []),
            "result": dict(result or {}),
            "created_at": _now_iso(),
        }
        room["replay_id"] = replay_id
        _touch(room)
        view = _public_view(room, viewer_id=player_id)
        view["replay_id"] = replay_id
        return view


def get_replay(service_id: str, replay_id: str) -> Dict[str, Any]:
    row = _replays.get(replay_id)
    if not row or row.get("service_id") != service_id:
        raise ValueError("回放不存在")
    return dict(row)


def matchmake(service_id: str, player_id: str, *, env_key: str = "", battle_mode: str = "") -> Dict[str, Any]:
    _require_feature(service_id)
    cfg = _cfg(service_id)
    ek = str(env_key or cfg["env_key"])
    bm = str(battle_mode or "pvp_1v1")
    with _lock:
        for room in _rooms.values():
            if room.get("service_id") != service_id:
                continue
            if room.get("visibility") != "public" or room.get("status") != "waiting":
                continue
            if str(room.get("env_key") or "") != ek:
                continue
            if str(room.get("battle_mode") or "") != bm:
                continue
            players = list(room.get("players") or [])
            if player_id in players:
                return _public_view(room, viewer_id=player_id)
            if len(players) < int(room.get("max_players") or 2):
                return join_room(service_id, player_id, room_id=str(room.get("room_id") or ""))
    return create_room(service_id, player_id, visibility="public", env_key=ek, battle_mode=bm)


def get_room(service_id: str, room_id: str, *, viewer_id: str = "") -> Dict[str, Any]:
    with _lock:
        room = _rooms.get(room_id)
        if not room or room.get("service_id") != service_id:
            raise ValueError("房间不存在")
        return _public_view(room, viewer_id=viewer_id)

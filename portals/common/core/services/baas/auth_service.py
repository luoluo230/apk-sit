# -*- coding: utf-8 -*-
"""Player auth for casual BaaS."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from models.db import get_cursor, init_db
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id, new_player_token, token_expiry
from services.baas.service_crud import feature_enabled, get_feature_config


def _player_row(row) -> Dict[str, Any]:
    if not row:
        return {}
    return {
        "player_id": row["player_id"],
        "service_id": row["service_id"],
        "auth_provider": row["auth_provider"],
        "external_id": row["external_id"],
        "display_name": row["display_name"],
        "profile": _json_load(row["profile_json"], {}),
        "token": row["token"],
        "token_expires_at": row["token_expires_at"],
    }


def _ensure_login_enabled(service_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "login"):
        raise ValueError("登录功能未启用")
    return get_feature_config(service_id, "login")


def guest_login(service_id: str, *, display_name: str = "") -> Dict[str, Any]:
    cfg = _ensure_login_enabled(service_id)
    if not cfg.get("guest_login_enabled", True):
        raise ValueError("游客登录未启用")
    external_id = new_id("guest_")
    return _create_session(service_id, "guest", external_id, display_name or f"游客{external_id[-6:]}", cfg)


def password_login(service_id: str, *, username: str, password: str) -> Dict[str, Any]:
    cfg = _ensure_login_enabled(service_id)
    if not cfg.get("password_login_enabled", True):
        raise ValueError("账号密码登录未启用")
    uname = str(username or "").strip()
    pwd = str(password or "").strip()
    if not uname or not pwd:
        raise ValueError("用户名和密码必填")
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            """
            SELECT * FROM baas_players
            WHERE service_id=? AND auth_provider='password' AND external_id=?
            """,
            (service_id, uname),
        ).fetchone()
        if not row:
            raise ValueError("账号不存在")
        profile = _json_load(row["profile_json"], {})
        if str(profile.get("password_hash") or "") != _hash_password(pwd, profile.get("password_salt") or ""):
            raise ValueError("密码错误")
        return _refresh_token(cur, row, cfg)


def register_password(service_id: str, *, username: str, password: str, display_name: str = "") -> Dict[str, Any]:
    cfg = _ensure_login_enabled(service_id)
    if not cfg.get("password_login_enabled", True):
        raise ValueError("账号密码登录未启用")
    uname = str(username or "").strip()
    pwd = str(password or "").strip()
    if len(uname) < 3:
        raise ValueError("用户名至少 3 个字符")
    if len(pwd) < 6:
        raise ValueError("密码至少 6 个字符")
    init_db()
    with get_cursor() as cur:
        exists = cur.execute(
            "SELECT 1 FROM baas_players WHERE service_id=? AND auth_provider='password' AND external_id=?",
            (service_id, uname),
        ).fetchone()
        if exists:
            raise ValueError("账号已存在")
        salt = new_id("s_")
        profile = {"password_salt": salt, "password_hash": _hash_password(pwd, salt)}
        return _create_session(
            service_id,
            "password",
            uname,
            display_name or uname,
            cfg,
            profile=profile,
            cur=cur,
        )


def refresh_token(service_id: str, player_id: str, token: str) -> Dict[str, Any]:
    cfg = _ensure_login_enabled(service_id)
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_players WHERE service_id=? AND player_id=? AND token=?",
            (service_id, player_id, token),
        ).fetchone()
        if not row:
            raise ValueError("会话无效")
        return _refresh_token(cur, row, cfg)


def resolve_player(service_id: str, player_id: str, token: str) -> Dict[str, Any]:
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_players WHERE service_id=? AND player_id=? AND token=?",
            (service_id, player_id, token),
        ).fetchone()
        if not row:
            raise ValueError("未授权")
        expires = str(row["token_expires_at"] or "")
        if expires and expires < _now_iso():
            raise ValueError("登录已过期")
        return _player_row(row)


def _hash_password(password: str, salt: str) -> str:
    import hashlib

    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def _create_session(
    service_id: str,
    provider: str,
    external_id: str,
    display_name: str,
    cfg: Dict[str, Any],
    *,
    profile: Optional[Dict[str, Any]] = None,
    cur=None,
) -> Dict[str, Any]:
    player_id = new_id("p_")
    token = new_player_token()
    ttl = int(cfg.get("token_ttl_hours") or 168)
    now = _now_iso()
    expires = token_expiry(ttl)
    prof = dict(profile or {})
    init_db()
    if cur is None:
        with get_cursor() as inner:
            inner.execute(
                """
                INSERT INTO baas_players (
                    player_id, service_id, auth_provider, external_id, display_name,
                    profile_json, token, token_expires_at, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    player_id,
                    service_id,
                    provider,
                    external_id,
                    display_name,
                    _json_dump(prof),
                    token,
                    expires,
                    now,
                    now,
                ),
            )
    else:
        cur.execute(
            """
            INSERT INTO baas_players (
                player_id, service_id, auth_provider, external_id, display_name,
                profile_json, token, token_expires_at, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                player_id,
                service_id,
                provider,
                external_id,
                display_name,
                _json_dump(prof),
                token,
                expires,
                now,
                now,
            ),
        )
    return {
        "player_id": player_id,
        "token": token,
        "token_expires_at": expires,
        "display_name": display_name,
        "auth_provider": provider,
    }


def _refresh_token(cur, row, cfg: Dict[str, Any]) -> Dict[str, Any]:
    token = new_player_token()
    ttl = int(cfg.get("token_ttl_hours") or 168)
    expires = token_expiry(ttl)
    now = _now_iso()
    cur.execute(
        "UPDATE baas_players SET token=?, token_expires_at=?, updated_at=? WHERE player_id=?",
        (token, expires, now, row["player_id"]),
    )
    data = _player_row(row)
    data["token"] = token
    data["token_expires_at"] = expires
    return {
        "player_id": data["player_id"],
        "token": token,
        "token_expires_at": expires,
        "display_name": data["display_name"],
        "auth_provider": data["auth_provider"],
    }

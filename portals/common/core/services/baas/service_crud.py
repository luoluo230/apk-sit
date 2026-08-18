# -*- coding: utf-8 -*-
"""BaaS service CRUD and config management."""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from models.db import get_cursor, init_db
from services.baas.helpers import (
    _json_dump,
    _json_load,
    _now_iso,
    generate_api_secret,
    hash_api_secret,
    row_to_service,
)
from services.baas.registry import default_feature_configs, default_feature_flags


def validate_service_id(service_id: str) -> str:
    sid = str(service_id or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,63}", sid):
        raise ValueError("服务 ID 须为 3–64 位小写字母、数字、下划线或连字符，且以字母或数字开头")
    return sid


def service_id_exists(service_id: str) -> bool:
    init_db()
    sid = str(service_id or "").strip()
    if not sid:
        return False
    with get_cursor() as cur:
        row = cur.execute("SELECT 1 FROM baas_services WHERE service_id=? LIMIT 1", (sid,)).fetchone()
        return bool(row)

def _load_feature_configs(cur, service_id: str) -> Dict[str, Dict[str, Any]]:
    rows = cur.execute(
        "SELECT feature_key, config_json FROM baas_feature_configs WHERE service_id=?",
        (service_id,),
    ).fetchall()
    out = default_feature_configs()
    for row in rows:
        out[str(row["feature_key"])] = _json_load(row["config_json"], out.get(str(row["feature_key"]), {}))
    return out


def get_service(service_id: str, *, include_secret: bool = False) -> Optional[Dict[str, Any]]:
    init_db()
    with get_cursor() as cur:
        row = cur.execute("SELECT * FROM baas_services WHERE service_id=?", (service_id,)).fetchone()
        if not row:
            return None
        data = row_to_service(row)
        data["feature_configs"] = _load_feature_configs(cur, service_id)
        if include_secret:
            data["api_secret_hash"] = row["api_secret_hash"]
        return data


def get_service_auth_row(service_id: str):
    init_db()
    with get_cursor() as cur:
        return cur.execute(
            "SELECT * FROM baas_services WHERE service_id=? AND status='active'",
            (service_id,),
        ).fetchone()


def list_services(project_id: str, env_key: str = "") -> List[Dict[str, Any]]:
    init_db()
    ek = str(env_key or "").strip()
    with get_cursor() as cur:
        if ek:
            rows = cur.execute(
                "SELECT * FROM baas_services WHERE project_id=? AND env_key=? ORDER BY updated_at DESC",
                (project_id, ek),
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT * FROM baas_services WHERE project_id=? ORDER BY env_key, updated_at DESC",
                (project_id,),
            ).fetchall()
        return [row_to_service(r) for r in rows]


def list_all_services(project_id: str = "", env_key: str = "") -> List[Dict[str, Any]]:
    init_db()
    pid = str(project_id or "").strip()
    ek = str(env_key or "").strip()
    sql = "SELECT * FROM baas_services"
    params: List[str] = []
    clauses: List[str] = []
    if pid:
        clauses.append("project_id=?")
        params.append(pid)
    if ek:
        clauses.append("env_key=?")
        params.append(ek)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY project_id, env_key, updated_at DESC"
    with get_cursor() as cur:
        rows = cur.execute(sql, params).fetchall()
        return [row_to_service(r) for r in rows]


def create_service(payload: Dict[str, Any], *, actor: str = "") -> Tuple[Dict[str, Any], str]:
    init_db()
    project_id = str(payload.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("project_id required")
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("服务名称不能为空")
    env_key = str(payload.get("env_key") or "development").strip() or "development"
    service_id = validate_service_id(payload.get("service_id") or "")
    if service_id_exists(service_id):
        raise ValueError("服务 ID 已存在")
    secret = generate_api_secret()
    now = _now_iso()
    flags = default_feature_flags()
    description = str(payload.get("description") or "").strip()
    icon_url = str(payload.get("icon_url") or "").strip() or "/static/project_ui/svg/nav_project_setting.svg"
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_services (
                service_id, project_id, env_key, name, description, icon_url, disabled,
                status, feature_flags, api_secret_hash, config_version, created_at, updated_at, created_by
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                service_id,
                project_id,
                env_key,
                name,
                description,
                icon_url,
                0,
                "active",
                _json_dump(flags),
                hash_api_secret(secret),
                1,
                now,
                now,
                actor or "",
            ),
        )
        for key, cfg in default_feature_configs().items():
            cur.execute(
                """
                INSERT INTO baas_feature_configs (service_id, feature_key, config_json, updated_at)
                VALUES (?,?,?,?)
                """,
                (service_id, key, _json_dump(cfg), now),
            )
    svc = get_service(service_id) or {}
    return svc, secret


def delete_service(project_id: str, service_id: str) -> bool:
    init_db()
    sid = str(service_id or "").strip()
    pid = str(project_id or "").strip()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT service_id FROM baas_services WHERE service_id=? AND project_id=?",
            (sid, pid),
        ).fetchone()
        if not row:
            return False
        player_count = cur.execute(
            "SELECT COUNT(*) AS cnt FROM baas_players WHERE service_id=?",
            (sid,),
        ).fetchone()
        if player_count and int(player_count["cnt"] or 0) > 0:
            raise ValueError("服务仍有玩家数据，请先禁用或迁移")
        cur.execute("DELETE FROM baas_feature_configs WHERE service_id=?", (sid,))
        cur.execute("DELETE FROM baas_services WHERE service_id=? AND project_id=?", (sid, pid))
    return True


def ensure_service(project_id: str, env_key: str = "development", *, actor: str = "") -> Tuple[Dict[str, Any], str]:
    """Return (service, api_secret_plain). Creates service + default configs if missing."""
    init_db()
    ek = str(env_key or "development").strip() or "development"
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_services WHERE project_id=? AND env_key=? LIMIT 1",
            (project_id, ek),
        ).fetchone()
        if row:
            svc = row_to_service(row)
            svc["feature_configs"] = _load_feature_configs(cur, svc["service_id"])
            return svc, ""
        service_id = str(uuid.uuid4())
        secret = generate_api_secret()
        now = _now_iso()
        flags = default_feature_flags()
        cur.execute(
            """
            INSERT INTO baas_services (
                service_id, project_id, env_key, name, status, feature_flags,
                api_secret_hash, config_version, created_at, updated_at, created_by
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                service_id,
                project_id,
                ek,
                f"{ek} 休闲服务",
                "active",
                _json_dump(flags),
                hash_api_secret(secret),
                1,
                now,
                now,
                actor or "",
            ),
        )
        for key, cfg in default_feature_configs().items():
            cur.execute(
                """
                INSERT INTO baas_feature_configs (service_id, feature_key, config_json, updated_at)
                VALUES (?,?,?,?)
                """,
                (service_id, key, _json_dump(cfg), now),
            )
    svc = get_service(service_id) or {}
    return svc, secret


def update_service(
    project_id: str,
    service_id: str,
    payload: Dict[str, Any],
    *,
    actor: str = "",
) -> Dict[str, Any]:
    init_db()
    svc = get_service(service_id)
    if not svc or svc.get("project_id") != project_id:
        raise ValueError("休闲服务不存在")
    if payload.get("name") is not None or payload.get("service_id") is not None:
        raise ValueError("名称与 ID 创建后不可修改")
    status = str(payload.get("status") if "status" in payload else svc.get("status") or "active").strip()
    description = str(payload.get("description") if "description" in payload else svc.get("description") or "").strip()
    icon_url = str(payload.get("icon_url") if "icon_url" in payload else svc.get("icon_url") or "").strip()
    disabled = bool(payload.get("disabled")) if "disabled" in payload else bool(svc.get("disabled"))
    flags = dict(svc.get("feature_flags") or {})
    if isinstance(payload.get("feature_flags"), dict):
        flags.update({k: bool(v) for k, v in payload["feature_flags"].items()})
    now = _now_iso()
    config_version = int(svc.get("config_version") or 0)
    if isinstance(payload.get("feature_configs"), dict):
        config_version += 1
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE baas_services
            SET status=?, description=?, icon_url=?, disabled=?, feature_flags=?, config_version=?, updated_at=?
            WHERE service_id=? AND project_id=?
            """,
            (
                status,
                description,
                icon_url,
                1 if disabled else 0,
                _json_dump(flags),
                config_version,
                now,
                service_id,
                project_id,
            ),
        )
        if isinstance(payload.get("feature_configs"), dict):
            for key, cfg in payload["feature_configs"].items():
                if not isinstance(cfg, dict):
                    continue
                cur.execute(
                    """
                    INSERT INTO baas_feature_configs (service_id, feature_key, config_json, updated_at)
                    VALUES (?,?,?,?)
                    ON CONFLICT(service_id, feature_key) DO UPDATE SET
                        config_json=excluded.config_json, updated_at=excluded.updated_at
                    """,
                    (service_id, str(key), _json_dump(cfg), now),
                )
    return get_service(service_id) or {}


def rotate_api_secret(project_id: str, service_id: str) -> Tuple[str, Dict[str, Any]]:
    secret = generate_api_secret()
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            "UPDATE baas_services SET api_secret_hash=?, updated_at=? WHERE service_id=? AND project_id=?",
            (hash_api_secret(secret), now, service_id, project_id),
        )
    svc = get_service(service_id)
    if not svc or svc.get("project_id") != project_id:
        raise ValueError("休闲服务不存在")
    return secret, svc


def get_feature_config(service_id: str, feature_key: str) -> Dict[str, Any]:
    svc = get_service(service_id)
    if not svc:
        return {}
    configs = svc.get("feature_configs") or {}
    return dict(configs.get(feature_key) or default_feature_configs().get(feature_key, {}))


def feature_enabled(service_id: str, feature_key: str) -> bool:
    svc = get_service(service_id)
    if not svc or svc.get("status") != "active":
        return False
    return bool((svc.get("feature_flags") or {}).get(feature_key))

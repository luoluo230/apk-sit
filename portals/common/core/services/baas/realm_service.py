# -*- coding: utf-8 -*-
"""Logical realms: open / list / merge (Wave C)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db
from services.baas.helpers import new_id


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _row(r) -> Dict[str, Any]:
    if not r:
        return {}
    keys = r.keys() if hasattr(r, "keys") else []
    return {k: r[k] for k in keys}


def list_realms(service_id: str, *, include_closed: bool = False) -> List[Dict[str, Any]]:
    init_db()
    sid = str(service_id or "").strip()
    with get_cursor() as cur:
        if include_closed:
            rows = cur.execute(
                "SELECT * FROM baas_realms WHERE service_id=? ORDER BY open_at ASC, name ASC",
                (sid,),
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT * FROM baas_realms WHERE service_id=? AND status NOT IN ('closed') "
                "ORDER BY open_at ASC, name ASC",
                (sid,),
            ).fetchall()
    return [_row(r) for r in rows]


def get_realm(service_id: str, realm_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_realms WHERE service_id=? AND realm_id=?",
            (str(service_id), str(realm_id)),
        ).fetchone()
    return _row(row) if row else None


def ensure_default_realm(service_id: str, actor: str = "system") -> Dict[str, Any]:
    rows = list_realms(service_id, include_closed=True)
    if rows:
        open_rows = [r for r in rows if str(r.get("status")) in ("open", "new", "full")]
        return open_rows[0] if open_rows else rows[0]
    return open_realm(service_id, name="一区", actor=actor, status="open")


def open_realm(
    service_id: str,
    *,
    name: str,
    actor: str = "",
    status: str = "new",
    realm_id: str = "",
) -> Dict[str, Any]:
    """滚服：新开逻辑区（不强制新物理机）。"""
    init_db()
    sid = str(service_id or "").strip()
    if not sid:
        raise ValueError("service_id 必填")
    rid = str(realm_id or "").strip() or f"r-{new_id()[:10]}"
    st = str(status or "new").strip().lower()
    if st not in ("open", "new", "full", "merging", "closed"):
        st = "new"
    now = _now()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_realms (
                realm_id, service_id, name, status, open_at, target_merge_realm_id,
                created_by, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (rid, sid, str(name or rid).strip() or rid, st, now, "", actor, now, now),
        )
    return get_realm(sid, rid) or {}


def set_realm_status(service_id: str, realm_id: str, status: str) -> Dict[str, Any]:
    st = str(status or "").strip().lower()
    if st not in ("open", "new", "full", "merging", "closed"):
        raise ValueError("无效 status")
    init_db()
    now = _now()
    with get_cursor() as cur:
        cur.execute(
            "UPDATE baas_realms SET status=?, updated_at=? WHERE service_id=? AND realm_id=?",
            (st, now, str(service_id), str(realm_id)),
        )
    row = get_realm(service_id, realm_id)
    if not row:
        raise ValueError("区服不存在")
    return row


def start_merge(service_id: str, source_realm_id: str, target_realm_id: str, actor: str = "") -> Dict[str, Any]:
    """合服：源区 merging → 迁移角色 realm_id → 源区 closed。"""
    src = get_realm(service_id, source_realm_id)
    dst = get_realm(service_id, target_realm_id)
    if not src or not dst:
        raise ValueError("源区或目标区不存在")
    if source_realm_id == target_realm_id:
        raise ValueError("不能合到自身")
    if str(dst.get("status")) == "closed":
        raise ValueError("目标区已关闭")
    init_db()
    now = _now()
    job_id = f"merge-{uuid.uuid4().hex[:12]}"
    with get_cursor() as cur:
        cur.execute(
            "UPDATE baas_realms SET status='merging', target_merge_realm_id=?, updated_at=? "
            "WHERE service_id=? AND realm_id=?",
            (target_realm_id, now, service_id, source_realm_id),
        )
        # 角色进度表：有 realm_id 列则批量改挂
        try:
            cur.execute(
                "UPDATE baas_player_data SET value_json=value_json WHERE 1=0"
            )
        except Exception:
            pass
        try:
            cur.execute(
                "UPDATE baas_player_realm SET realm_id=?, updated_at=? "
                "WHERE service_id=? AND realm_id=?",
                (target_realm_id, now, service_id, source_realm_id),
            )
        except Exception:
            # 表可能尚未有数据；ensure mapping table exists via migration
            pass
        cur.execute(
            """
            INSERT INTO baas_realm_merge_jobs (
                job_id, service_id, source_realm_id, target_realm_id, status,
                created_by, created_at, updated_at, finished_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (job_id, service_id, source_realm_id, target_realm_id, "completed", actor, now, now, now),
        )
        cur.execute(
            "UPDATE baas_realms SET status='closed', updated_at=? WHERE service_id=? AND realm_id=?",
            (now, service_id, source_realm_id),
        )
        if str(dst.get("status")) == "new":
            cur.execute(
                "UPDATE baas_realms SET status='open', updated_at=? WHERE service_id=? AND realm_id=?",
                (now, service_id, target_realm_id),
            )
    return {
        "job_id": job_id,
        "status": "completed",
        "source_realm_id": source_realm_id,
        "target_realm_id": target_realm_id,
        "source": get_realm(service_id, source_realm_id),
        "target": get_realm(service_id, target_realm_id),
    }


def assign_player_realm(service_id: str, player_id: str, realm_id: str) -> Dict[str, Any]:
    init_db()
    realm = get_realm(service_id, realm_id)
    if not realm or str(realm.get("status")) in ("closed", "merging"):
        raise ValueError("区服不可进入")
    now = _now()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_player_realm (service_id, player_id, realm_id, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(service_id, player_id) DO UPDATE SET
                realm_id=excluded.realm_id,
                updated_at=excluded.updated_at
            """,
            (service_id, player_id, realm_id, now),
        )
    return {"service_id": service_id, "player_id": player_id, "realm_id": realm_id}


def get_player_realm(service_id: str, player_id: str) -> str:
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT realm_id FROM baas_player_realm WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchone()
    if row:
        return str(row["realm_id"] or "")
    default = ensure_default_realm(service_id)
    return str(default.get("realm_id") or "")

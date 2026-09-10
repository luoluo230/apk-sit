# -*- coding: utf-8 -*-
"""Mail feature."""

from __future__ import annotations

from typing import Any, Dict, List

from models.db import get_cursor, init_db
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas.service_crud import feature_enabled, get_feature_config


def inbox(service_id: str, player_id: str) -> List[Dict[str, Any]]:
    if not feature_enabled(service_id, "mail"):
        return []
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            """
            SELECT * FROM baas_mail_messages
            WHERE service_id=? AND player_id=? AND status!='deleted'
            ORDER BY created_at DESC
            """,
            (service_id, player_id),
        ).fetchall()
    return [_row(r) for r in rows]


def claim_mail(service_id: str, player_id: str, mail_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "mail"):
        raise ValueError("邮件功能未启用")
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            """
            SELECT * FROM baas_mail_messages
            WHERE service_id=? AND player_id=? AND mail_id=?
            """,
            (service_id, player_id, mail_id),
        ).fetchone()
        if not row:
            raise ValueError("邮件不存在")
        if row["status"] == "claimed":
            return _row(row)
        now = _now_iso()
        attachments = _json_load(row["attachments_json"], [])
        reward_map = {}
        for att in attachments or []:
            if not isinstance(att, dict):
                continue
            if str(att.get("type") or "") == "currency":
                cid = str(att.get("currency_id") or "gold")
                reward_map[cid] = reward_map.get(cid, 0) + int(att.get("amount") or 0)
            elif str(att.get("type") or "") in ("item", "material", "equipment"):
                iid = str(att.get("item_id") or att.get("key") or "")
                if iid:
                    reward_map[iid] = reward_map.get(iid, 0) + int(att.get("quantity") or att.get("amount") or 1)
            elif att.get("item_key"):
                reward_map[str(att["item_key"])] = reward_map.get(str(att["item_key"]), 0) + int(att.get("count") or att.get("quantity") or 1)
            elif att.get("gold"):
                reward_map["gold"] = reward_map.get("gold", 0) + int(att["gold"])
            elif att.get("diamond"):
                reward_map["diamond"] = reward_map.get("diamond", 0) + int(att["diamond"])
        if reward_map:
            from services.baas.afk_reward_grants import grant_rewards
            grant_rewards(cur, service_id, player_id, reward_map)
        cur.execute(
            "UPDATE baas_mail_messages SET status='claimed', claimed_at=?, updated_at=? WHERE mail_id=?",
            (now, now, mail_id),
        )
        row = cur.execute("SELECT * FROM baas_mail_messages WHERE mail_id=?", (mail_id,)).fetchone()
    return _row(row)


def send_mail(service_id: str, payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    player_id = str(payload.get("player_id") or "").strip()
    if not player_id:
        raise ValueError("player_id 必填")
    mail_id = new_id("mail_")
    now = _now_iso()
    attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
    body_links = payload.get("body_links") if isinstance(payload.get("body_links"), list) else []
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_mail_messages (
                mail_id, service_id, player_id, title, body, attachments_json, body_links_json, status,
                created_by, created_at, updated_at, claimed_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                mail_id,
                service_id,
                player_id,
                str(payload.get("title") or "系统邮件"),
                str(payload.get("body") or ""),
                _json_dump(attachments),
                _json_dump(body_links),
                "unread",
                actor,
                now,
                now,
                "",
            ),
        )
        row = cur.execute("SELECT * FROM baas_mail_messages WHERE mail_id=?", (mail_id,)).fetchone()
    return _row(row)


def admin_list(service_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            "SELECT * FROM baas_mail_messages WHERE service_id=? ORDER BY created_at DESC LIMIT ?",
            (service_id, limit),
        ).fetchall()
    return [_row(r) for r in rows]


def _row(row) -> Dict[str, Any]:
    return {
        "mail_id": row["mail_id"],
        "player_id": row["player_id"],
        "title": row["title"],
        "body": row["body"],
        "attachments": _json_load(row["attachments_json"], []),
        "body_links": _json_load(row["body_links_json"], []) if "body_links_json" in row.keys() else [],
        "status": row["status"],
        "created_at": row["created_at"],
        "claimed_at": row["claimed_at"],
    }

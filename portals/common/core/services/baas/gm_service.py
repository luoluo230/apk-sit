# -*- coding: utf-8 -*-
"""BaaS GM / ops maintenance APIs (players, mail, wallet, leaderboard, gifts, cloudsave)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from models.db import get_cursor, init_db, log_audit_db
from services.baas import announce_service, mail_service
from services.baas import activity_service
from services.baas.helpers import _json_dump, _json_load, _now_iso, new_id
from services.baas import retention_services


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
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_players(service_id: str, *, query: str = "", limit: int = 50) -> List[Dict[str, Any]]:
    init_db()
    q = str(query or "").strip()
    lim = max(1, min(int(limit or 50), 200))
    with get_cursor() as cur:
        if q:
            like = f"%{q}%"
            rows = cur.execute(
                """
                SELECT * FROM baas_players
                WHERE service_id=? AND (player_id LIKE ? OR display_name LIKE ? OR external_id LIKE ?)
                ORDER BY updated_at DESC LIMIT ?
                """,
                (service_id, like, like, like, lim),
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT * FROM baas_players WHERE service_id=? ORDER BY updated_at DESC LIMIT ?",
                (service_id, lim),
            ).fetchall()
    return [_player_row(r) for r in rows]


def get_player_detail(service_id: str, player_id: str) -> Dict[str, Any]:
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_players WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchone()
        if not row:
            raise ValueError("玩家不存在")
        wallets = cur.execute(
            "SELECT currency_id, balance, updated_at FROM baas_wallets WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchall()
        mail_count = cur.execute(
            "SELECT COUNT(*) AS cnt FROM baas_mail_messages WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchone()
    detail = _player_row(row)
    detail["wallets"] = [dict(w) for w in wallets]
    detail["mail_count"] = int((mail_count or {}).get("cnt") or 0)
    return detail


def adjust_wallet(
    service_id: str,
    player_id: str,
    currency_id: str,
    delta: int,
    *,
    actor: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    cid = str(currency_id or "gold").strip()
    change = int(delta)
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT balance FROM baas_wallets WHERE service_id=? AND player_id=? AND currency_id=?",
            (service_id, player_id, cid),
        ).fetchone()
        balance = int(row["balance"] or 0) if row else 0
        balance = max(0, balance + change)
        cur.execute(
            """
            INSERT INTO baas_wallets (service_id, player_id, currency_id, balance, updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(service_id, player_id, currency_id) DO UPDATE SET
                balance=excluded.balance, updated_at=excluded.updated_at
            """,
            (service_id, player_id, cid, balance, now),
        )
    log_audit_db("default", actor, "baas_gm_wallet", f"{service_id}/{player_id} {cid} {change:+d} {reason}", "")
    return {"currency_id": cid, "balance": balance, "delta": change}


def broadcast_mail(service_id: str, payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    player_ids = payload.get("player_ids")
    if isinstance(player_ids, list) and player_ids:
        targets = [str(p).strip() for p in player_ids if str(p).strip()]
    else:
        init_db()
        with get_cursor() as cur:
            rows = cur.execute(
                "SELECT player_id FROM baas_players WHERE service_id=?",
                (service_id,),
            ).fetchall()
        targets = [str(r["player_id"]) for r in rows]
    sent = []
    for pid in targets:
        sent.append(mail_service.send_mail(service_id, {**payload, "player_id": pid}, actor=actor))
    log_audit_db("default", actor, "baas_gm_mail_broadcast", f"{service_id} count={len(sent)}", "")
    return {"sent_count": len(sent), "mails": sent[:20]}


def upsert_gift_code(service_id: str, payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    code = str(payload.get("code") or "").strip().upper()
    if len(code) < 4:
        raise ValueError("兑换码至少 4 位")
    rewards = payload.get("rewards") if isinstance(payload.get("rewards"), list) else []
    max_uses = int(payload.get("max_uses") or 0)
    expires_at = str(payload.get("expires_at") or "")
    code_type = str(payload.get("code_type") or "shared").strip().lower()
    per_player_limit = int(payload.get("per_player_limit") or 1)
    assigned_player_id = str(payload.get("assigned_player_id") or "").strip()
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_gift_codes (
                service_id, code, rewards_json, max_uses, use_count, expires_at,
                created_by, created_at, code_type, per_player_limit, assigned_player_id, meta_json
            ) VALUES (?,?,?,?,0,?,?,?,?,?,?,?)
            ON CONFLICT(service_id, code) DO UPDATE SET
                rewards_json=excluded.rewards_json,
                max_uses=excluded.max_uses,
                expires_at=excluded.expires_at,
                code_type=excluded.code_type,
                per_player_limit=excluded.per_player_limit,
                assigned_player_id=excluded.assigned_player_id,
                meta_json=excluded.meta_json
            """,
            (
                service_id,
                code,
                _json_dump(rewards),
                max_uses,
                expires_at,
                actor,
                now,
                code_type,
                per_player_limit,
                assigned_player_id,
                _json_dump(meta),
            ),
        )
        row = cur.execute(
            "SELECT * FROM baas_gift_codes WHERE service_id=? AND code=?",
            (service_id, code),
        ).fetchone()
    log_audit_db("default", actor, "baas_gm_gift_code", f"{service_id}/{code}", "")
    return dict(row) if row else {"code": code}


def list_gift_codes(service_id: str) -> List[Dict[str, Any]]:
    init_db()
    with get_cursor() as cur:
        rows = cur.execute(
            "SELECT * FROM baas_gift_codes WHERE service_id=? ORDER BY created_at DESC",
            (service_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def reset_leaderboard(service_id: str, board_id: str, *, actor: str = "") -> Dict[str, Any]:
    bid = str(board_id or "default").strip()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM baas_leaderboard_scores WHERE service_id=? AND board_id=?",
            (service_id, bid),
        )
    log_audit_db("default", actor, "baas_gm_lb_reset", f"{service_id}/{bid}", "")
    return {"board_id": bid, "reset": True}


def admin_leaderboard(service_id: str, board_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    return retention_services.top_scores(service_id, board_id, limit=limit)


def inspect_cloudsave(service_id: str, player_id: str, key: str = "") -> Any:
    init_db()
    with get_cursor() as cur:
        if key:
            row = cur.execute(
                "SELECT * FROM baas_player_data WHERE service_id=? AND player_id=? AND data_key=?",
                (service_id, player_id, str(key).strip()),
            ).fetchone()
            if not row:
                return {"key": key, "value": None, "version": 0}
            return {
                "key": row["data_key"],
                "value": _json_load(row["value_json"], None),
                "version": int(row["version"] or 0),
                "updated_at": row["updated_at"],
            }
        rows = cur.execute(
            "SELECT data_key, version, updated_at FROM baas_player_data WHERE service_id=? AND player_id=? ORDER BY data_key",
            (service_id, player_id),
        ).fetchall()
    return [dict(r) for r in rows]


def set_cloudsave(service_id: str, player_id: str, key: str, value: Any, *, actor: str = "") -> Dict[str, Any]:
    k = str(key or "").strip()
    if not k:
        raise ValueError("key 必填")
    now = _now_iso()
    payload = _json_dump(value)
    init_db()
    with get_cursor() as cur:
        existing = cur.execute(
            "SELECT version FROM baas_player_data WHERE service_id=? AND player_id=? AND data_key=?",
            (service_id, player_id, k),
        ).fetchone()
        version = int(existing["version"] or 0) + 1 if existing else 1
        cur.execute(
            """
            INSERT INTO baas_player_data (service_id, player_id, data_key, value_json, version, updated_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(service_id, player_id, data_key) DO UPDATE SET
                value_json=excluded.value_json, version=excluded.version, updated_at=excluded.updated_at
            """,
            (service_id, player_id, k, payload, version, now),
        )
    log_audit_db("default", actor, "baas_gm_cloudsave", f"{service_id}/{player_id}/{key}", "")
    return {"key": k, "value": value, "version": version, "updated_at": now}


def gm_dashboard(service_id: str) -> Dict[str, Any]:
    init_db()
    with get_cursor() as cur:
        players = cur.execute(
            "SELECT COUNT(*) AS cnt FROM baas_players WHERE service_id=?",
            (service_id,),
        ).fetchone()
        mail_unread = cur.execute(
            "SELECT COUNT(*) AS cnt FROM baas_mail_messages WHERE service_id=? AND status='unread'",
            (service_id,),
        ).fetchone()
        codes = cur.execute(
            "SELECT COUNT(*) AS cnt FROM baas_gift_codes WHERE service_id=?",
            (service_id,),
        ).fetchone()
    return {
        "player_count": int(players["cnt"] or 0) if players else 0,
        "unread_mail_count": int(mail_unread["cnt"] or 0) if mail_unread else 0,
        "gift_code_count": int(codes["cnt"] or 0) if codes else 0,
        "announcements": announce_service.admin_list(service_id)[:5],
        "activity_count": len(activity_service.admin_list(service_id)),
    }


def ban_player(service_id: str, player_id: str, *, reason: str = "", expires_at: str = "", actor: str = "") -> Dict[str, Any]:
    pid = str(player_id or "").strip()
    if not pid:
        raise ValueError("player_id 必填")
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_player_bans (service_id, player_id, reason, expires_at, created_by, created_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(service_id, player_id) DO UPDATE SET
                reason=excluded.reason, expires_at=excluded.expires_at, created_by=excluded.created_by, created_at=excluded.created_at
            """,
            (service_id, pid, str(reason or ""), str(expires_at or ""), actor, now),
        )
    log_audit_db("default", actor, "baas_gm_ban_player", f"{service_id}/{pid}", "")
    return {"player_id": pid, "banned": True, "expires_at": expires_at}


def unban_player(service_id: str, player_id: str, *, actor: str = "") -> Dict[str, Any]:
    pid = str(player_id or "").strip()
    init_db()
    with get_cursor() as cur:
        cur.execute("DELETE FROM baas_player_bans WHERE service_id=? AND player_id=?", (service_id, pid))
    log_audit_db("default", actor, "baas_gm_unban_player", f"{service_id}/{pid}", "")
    return {"player_id": pid, "banned": False}


def ban_ip(service_id: str, ip_pattern: str, *, reason: str = "", expires_at: str = "", actor: str = "") -> Dict[str, Any]:
    ip = str(ip_pattern or "").strip()
    if not ip:
        raise ValueError("IP 必填")
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_ip_bans (service_id, ip_pattern, reason, expires_at, created_by, created_at)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(service_id, ip_pattern) DO UPDATE SET
                reason=excluded.reason, expires_at=excluded.expires_at, created_by=excluded.created_by, created_at=excluded.created_at
            """,
            (service_id, ip, str(reason or ""), str(expires_at or ""), actor, now),
        )
    log_audit_db("default", actor, "baas_gm_ban_ip", f"{service_id}/{ip}", "")
    return {"ip_pattern": ip, "banned": True}


def unban_ip(service_id: str, ip_pattern: str, *, actor: str = "") -> Dict[str, Any]:
    ip = str(ip_pattern or "").strip()
    init_db()
    with get_cursor() as cur:
        cur.execute("DELETE FROM baas_ip_bans WHERE service_id=? AND ip_pattern=?", (service_id, ip))
    log_audit_db("default", actor, "baas_gm_unban_ip", f"{service_id}/{ip}", "")
    return {"ip_pattern": ip, "banned": False}


def list_bans(service_id: str) -> Dict[str, Any]:
    init_db()
    with get_cursor() as cur:
        players = cur.execute(
            "SELECT * FROM baas_player_bans WHERE service_id=? ORDER BY created_at DESC",
            (service_id,),
        ).fetchall()
        ips = cur.execute(
            "SELECT * FROM baas_ip_bans WHERE service_id=? ORDER BY created_at DESC",
            (service_id,),
        ).fetchall()
        rows = cur.execute(
            "SELECT player_id, profile_json FROM baas_players WHERE service_id=?",
            (service_id,),
        ).fetchall()
    mutes = []
    now = _now_iso()
    for row in rows:
        profile = _json_load(row["profile_json"], {})
        mute_until = str(profile.get("mute_until") or "").strip()
        if mute_until and mute_until > now:
            mutes.append({
                "player_id": row["player_id"],
                "mute_until": mute_until,
                "reason": profile.get("mute_reason") or "",
            })
    return {"player_bans": [dict(r) for r in players], "ip_bans": [dict(r) for r in ips], "mutes": mutes}


def mute_player(service_id: str, player_id: str, *, hours: int = 0, reason: str = "", actor: str = "") -> Dict[str, Any]:
    pid = str(player_id or "").strip()
    if not pid:
        raise ValueError("player_id 必填")
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT profile_json FROM baas_players WHERE service_id=? AND player_id=?",
            (service_id, pid),
        ).fetchone()
        if not row:
            raise ValueError("玩家不存在")
        profile = _json_load(row["profile_json"], {})
        hrs = int(hours or 0)
        if hrs <= 0:
            profile.pop("mute_until", None)
            profile.pop("mute_reason", None)
        else:
            from datetime import datetime, timedelta, timezone

            profile["mute_until"] = (datetime.now(timezone.utc) + timedelta(hours=hrs)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
            profile["mute_reason"] = str(reason or "")
        now = _now_iso()
        cur.execute(
            "UPDATE baas_players SET profile_json=?, updated_at=? WHERE service_id=? AND player_id=?",
            (_json_dump(profile), now, service_id, pid),
        )
    log_audit_db("default", actor, "baas_gm_mute", f"{service_id}/{pid} hours={hours}", "")
    return {"player_id": pid, "mute_until": profile.get("mute_until") or "", "muted": hrs > 0}


def unmute_player(service_id: str, player_id: str, *, actor: str = "") -> Dict[str, Any]:
    return mute_player(service_id, player_id, hours=0, actor=actor)


def save_announcement(service_id: str, payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    return announce_service.save_announcement(service_id, payload, actor=actor)


def list_announcements(service_id: str) -> List[Dict[str, Any]]:
    return announce_service.admin_list(service_id)


def save_activity(service_id: str, payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    row = activity_service.save_activity(service_id, payload, actor=actor)
    log_audit_db("default", actor, "baas_gm_activity", f"{service_id}/{row.get('activity_id')}", "")
    return row


def list_activities(service_id: str) -> List[Dict[str, Any]]:
    return activity_service.admin_list(service_id)


def list_gm_audit(service_id: str, *, limit: int = 80) -> List[Dict[str, Any]]:
    init_db()
    prefix = f"{service_id}/"
    with get_cursor() as cur:
        rows = cur.execute(
            """
            SELECT timestamp, user, action, details, ip
            FROM audit_log
            WHERE action LIKE 'baas_gm%' AND (details LIKE ? OR details LIKE ?)
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (f"{prefix}%", f"%{service_id}%", max(1, min(int(limit or 80), 200))),
        ).fetchall()
    return [dict(r) for r in rows]


def list_mail_templates(service_id: str) -> List[Dict[str, Any]]:
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT config_json FROM baas_feature_configs WHERE service_id=? AND feature_key=?",
            (service_id, "gm_mail_templates"),
        ).fetchone()
    data = _json_load(row["config_json"], {}) if row else {}
    templates = data.get("templates") if isinstance(data.get("templates"), list) else []
    return templates


def save_mail_template(service_id: str, payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    template_id = str(payload.get("template_id") or new_id("tpl_")).strip()
    title = str(payload.get("title") or "系统邮件").strip()
    body = str(payload.get("body") or "").strip()
    attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
    body_links = payload.get("body_links") if isinstance(payload.get("body_links"), list) else []
    now = _now_iso()
    templates = list_mail_templates(service_id)
    updated = {
        "template_id": template_id,
        "title": title,
        "body": body,
        "attachments": attachments,
        "body_links": body_links,
        "updated_at": now,
    }
    replaced = False
    for idx, tpl in enumerate(templates):
        if str(tpl.get("template_id") or "") == template_id:
            templates[idx] = updated
            replaced = True
            break
    if not replaced:
        updated["created_at"] = now
        templates.insert(0, updated)
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_feature_configs (service_id, feature_key, config_json, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(service_id, feature_key) DO UPDATE SET
                config_json=excluded.config_json, updated_at=excluded.updated_at
            """,
            (service_id, "gm_mail_templates", _json_dump({"templates": templates}), now),
        )
    log_audit_db("default", actor, "baas_gm_mail_template", f"{service_id}/{template_id}", "")
    return updated


def delete_mail_template(service_id: str, template_id: str, *, actor: str = "") -> Dict[str, Any]:
    tid = str(template_id or "").strip()
    templates = [t for t in list_mail_templates(service_id) if str(t.get("template_id") or "") != tid]
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_feature_configs (service_id, feature_key, config_json, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(service_id, feature_key) DO UPDATE SET
                config_json=excluded.config_json, updated_at=excluded.updated_at
            """,
            (service_id, "gm_mail_templates", _json_dump({"templates": templates}), now),
        )
    log_audit_db("default", actor, "baas_gm_mail_template_delete", f"{service_id}/{tid}", "")
    return {"template_id": tid, "deleted": True}


def grant_items(
    service_id: str,
    player_id: str,
    items: List[Dict[str, Any]],
    *,
    title: str = "",
    body: str = "",
    actor: str = "",
) -> Dict[str, Any]:
    pid = str(player_id or "").strip()
    if not pid:
        raise ValueError("player_id 必填")
    attachments = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("item_id") or item.get("id") or "").strip()
        if not item_id:
            continue
        attachments.append({
            "type": str(item.get("type") or "item"),
            "item_id": item_id,
            "quantity": int(item.get("quantity") or item.get("count") or 1),
            "name": str(item.get("name") or item_id),
        })
    if not attachments:
        raise ValueError("至少发放一项道具")
    mail = mail_service.send_mail(
        service_id,
        {
            "player_id": pid,
            "title": title or "道具发放",
            "body": body or "GM 道具补偿，请在邮件中领取。",
            "attachments": attachments,
        },
        actor=actor,
    )
    log_audit_db("default", actor, "baas_gm_grant_items", f"{service_id}/{pid} count={len(attachments)}", "")
    return {"mail": mail, "attachments": attachments}


def resolve_player_session_token(service_id: str, player_id: str) -> str:
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT token FROM baas_players WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchone()
    if not row:
        raise ValueError("玩家不存在")
    token = str(row["token"] or "").strip()
    if not token:
        raise ValueError("玩家无有效 session token，可能未在线登录过")
    return token


def is_player_banned(service_id: str, player_id: str) -> bool:
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT expires_at FROM baas_player_bans WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchone()
    if not row:
        return False
    exp = str(row["expires_at"] or "").strip()
    return not exp or exp > now

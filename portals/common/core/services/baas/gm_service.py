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
    detail["mail_count"] = int(mail_count["cnt"] or 0) if mail_count else 0
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
        "room_stats": _room_stats_safe(service_id),
    }


def _room_stats_safe(service_id: str) -> Dict[str, Any]:
    try:
        from services.baas import room_service

        return room_service.room_stats(service_id)
    except Exception:
        return {"total": 0}


def list_rooms_admin(service_id: str, *, status: str = "", limit: int = 50) -> List[Dict[str, Any]]:
    from services.baas import room_service

    return room_service.list_all_rooms(service_id, status=status, limit=limit)


def get_room_admin(service_id: str, room_id: str) -> Dict[str, Any]:
    from services.baas import room_service

    return room_service.get_room_detail(service_id, room_id)


def close_room_admin(service_id: str, room_id: str, *, reason: str = "", actor: str = "") -> Dict[str, Any]:
    from services.baas import room_service

    data = room_service.admin_force_close(service_id, room_id, reason=reason)
    log_audit_db("default", actor, "baas_gm_room_close", f"{service_id}/{room_id} {reason[:80]}", "")
    return data


def kick_room_player_admin(service_id: str, room_id: str, target_id: str, *, actor: str = "") -> Dict[str, Any]:
    from services.baas import room_service

    data = room_service.admin_kick_player(service_id, room_id, target_id)
    log_audit_db("default", actor, "baas_gm_room_kick", f"{service_id}/{room_id}/{target_id}", "")
    return data


def finish_room_battle_admin(
    service_id: str,
    room_id: str,
    *,
    result: Optional[Dict[str, Any]] = None,
    actor: str = "",
) -> Dict[str, Any]:
    from services.baas import room_service

    data = room_service.admin_finish_battle(service_id, room_id, result=result)
    log_audit_db("default", actor, "baas_gm_room_finish", f"{service_id}/{room_id}", "")
    return data


def list_room_replays_admin(service_id: str, *, limit: int = 20) -> List[Dict[str, Any]]:
    from services.baas import room_service

    return room_service.list_replays(service_id, limit=limit)


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
            WHERE action LIKE 'baas_gm%%' AND (details LIKE ? OR details LIKE ?)
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


def get_player_afk_snapshot(service_id: str, player_id: str) -> Dict[str, Any]:
    """GM：AFK 玩家养成 / 推图 / 副本快照。"""
    from services.baas import hero_service, pve_service, afk_growth_service, inventory_service

    pid = str(player_id or "").strip()
    if not pid:
        raise ValueError("player_id 必填")
    detail = get_player_detail(service_id, pid)
    snapshot: Dict[str, Any] = {"player": detail}
    try:
        snapshot["roster"] = hero_service.get_roster(service_id, pid)
    except ValueError:
        snapshot["roster"] = {"heroes": [], "count": 0}
    try:
        snapshot["pve"] = {
            "progress": pve_service.get_progress(service_id, pid),
            "stamina": pve_service.get_stamina(service_id, pid),
        }
    except ValueError:
        snapshot["pve"] = {}
    try:
        snapshot["equipment"] = afk_growth_service.get_equipment_state(service_id, pid)
    except ValueError:
        snapshot["equipment"] = {}
    try:
        snapshot["dungeons"] = afk_growth_service.list_dungeons_status(service_id, pid)
    except ValueError:
        snapshot["dungeons"] = {}
    try:
        snapshot["inventory"] = inventory_service.list_inventory(service_id, pid)
    except ValueError:
        snapshot["inventory"] = {"items": [], "count": 0}
    try:
        snapshot["team_power"] = afk_growth_service.estimate_team_power(service_id, pid)
    except ValueError:
        snapshot["team_power"] = {"team_power": 0}
    return snapshot


def gm_grant_hero(service_id: str, player_id: str, hero_id: int, *, actor: str = "") -> Dict[str, Any]:
    from services.baas import hero_service

    init_db()
    with get_cursor() as cur:
        result = hero_service.grant_hero(cur, service_id, player_id, int(hero_id))
    log_audit_db("default", actor, "baas_gm_grant_hero", f"{service_id}/{player_id} hero={hero_id}", "")
    return result


def gm_set_hero(
    service_id: str,
    player_id: str,
    hero_id: int,
    *,
    level: Optional[int] = None,
    star: Optional[int] = None,
    shards: Optional[int] = None,
    talent_points: Optional[int] = None,
    actor: str = "",
) -> Dict[str, Any]:
    hid = int(hero_id or 0)
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_player_heroes WHERE service_id=? AND player_id=? AND hero_id=?",
            (service_id, player_id, hid),
        ).fetchone()
        if not row:
            from services.baas import hero_service
            hero_service.grant_hero(cur, service_id, player_id, hid)
        sets = []
        vals: List[Any] = []
        if level is not None:
            sets.append("level=?")
            vals.append(max(1, int(level)))
        if star is not None:
            sets.append("star=?")
            vals.append(max(1, min(5, int(star))))
        if shards is not None:
            sets.append("shards=?")
            vals.append(max(0, int(shards)))
        if talent_points is not None:
            sets.append("talent_points=?")
            vals.append(max(0, int(talent_points)))
        if not sets:
            raise ValueError("至少指定 level / star / shards / talent_points 之一")
        sets.append("updated_at=?")
        vals.append(now)
        vals.extend([service_id, player_id, hid])
        cur.execute(
            f"UPDATE baas_player_heroes SET {', '.join(sets)} WHERE service_id=? AND player_id=? AND hero_id=?",
            tuple(vals),
        )
    log_audit_db("default", actor, "baas_gm_set_hero", f"{service_id}/{player_id} hero={hid}", "")
    return {"hero_id": hid, "level": level, "star": star, "shards": shards, "talent_points": talent_points}


def gm_set_stamina(service_id: str, player_id: str, value: int, *, actor: str = "") -> Dict[str, Any]:
    from services.baas.pve_service import _save_stamina, _stamina_state
    from services.baas.service_crud import get_feature_config

    cfg = get_feature_config(service_id, "pve")
    init_db()
    with get_cursor() as cur:
        state = _stamina_state(cur, service_id, player_id, cfg)
        state["current"] = max(0, min(int(value), int(state.get("max") or cfg.get("stamina_max") or 9999)))
        _save_stamina(cur, service_id, player_id, state)
    log_audit_db("default", actor, "baas_gm_set_stamina", f"{service_id}/{player_id}={value}", "")
    return {"stamina": state}


def gm_set_pve_stage(service_id: str, player_id: str, stage_id: str, *, actor: str = "") -> Dict[str, Any]:
    sid = str(stage_id or "").strip()
    if not sid:
        raise ValueError("stage_id 必填")
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_chapter_progress (service_id, player_id, stage_id, stars, best_time_ms, cleared, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(service_id, player_id, stage_id) DO UPDATE SET
                stars=excluded.stars, cleared=excluded.cleared, updated_at=excluded.updated_at
            """,
            (service_id, player_id, sid, 3, 0, 1, now),
        )
    log_audit_db("default", actor, "baas_gm_set_pve_stage", f"{service_id}/{player_id} stage={sid}", "")
    return {"stage_id": sid, "cleared": True}


def gm_reset_dungeons(service_id: str, player_id: str, dungeon_id: str = "", *, actor: str = "") -> Dict[str, Any]:
    init_db()
    with get_cursor() as cur:
        if dungeon_id:
            cur.execute(
                "DELETE FROM baas_dungeon_daily WHERE service_id=? AND player_id=? AND dungeon_id=?",
                (service_id, player_id, str(dungeon_id)),
            )
        else:
            cur.execute(
                "DELETE FROM baas_dungeon_daily WHERE service_id=? AND player_id=?",
                (service_id, player_id),
            )
    log_audit_db("default", actor, "baas_gm_reset_dungeons", f"{service_id}/{player_id} dg={dungeon_id or '*'}", "")
    return {"reset": True, "dungeon_id": dungeon_id or "*"}


def gm_set_equipment(
    service_id: str,
    player_id: str,
    slot: str,
    *,
    quality: Optional[int] = None,
    enhance_level: Optional[int] = None,
    refine_level: Optional[int] = None,
    awaken: Optional[bool] = None,
    gem_count: Optional[int] = None,
    actor: str = "",
) -> Dict[str, Any]:
    from services.baas.afk.afk_growth_service import EQUIP_SLOTS

    slot_name = str(slot or "").strip()
    if slot_name not in EQUIP_SLOTS:
        raise ValueError("装备槽位无效")
    now = _now_iso()
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT slot FROM baas_player_equipment WHERE service_id=? AND player_id=? AND slot=?",
            (service_id, player_id, slot_name),
        ).fetchone()
        if not row:
            cur.execute(
                """
                INSERT INTO baas_player_equipment
                (service_id, player_id, slot, quality, enhance_level, refine_level, awaken, gem_count, affix_seed, updated_at)
                VALUES (?,?,?,?,0,0,0,0,0,?)
                """,
                (service_id, player_id, slot_name, int(quality or 3), now),
            )
        sets = ["updated_at=?"]
        vals: List[Any] = [now]
        if quality is not None:
            sets.append("quality=?")
            vals.append(int(quality))
        if enhance_level is not None:
            sets.append("enhance_level=?")
            vals.append(max(0, int(enhance_level)))
        if refine_level is not None:
            sets.append("refine_level=?")
            vals.append(max(0, int(refine_level)))
        if awaken is not None:
            sets.append("awaken=?")
            vals.append(1 if awaken else 0)
        if gem_count is not None:
            sets.append("gem_count=?")
            vals.append(max(0, int(gem_count)))
        vals.extend([service_id, player_id, slot_name])
        cur.execute(
            f"UPDATE baas_player_equipment SET {', '.join(sets)} WHERE service_id=? AND player_id=? AND slot=?",
            tuple(vals),
        )
    log_audit_db("default", actor, "baas_gm_set_equipment", f"{service_id}/{player_id} slot={slot_name}", "")
    return {"slot": slot_name, "quality": quality, "enhance_level": enhance_level, "refine_level": refine_level}


def update_player_profile(service_id: str, player_id: str, payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    """GM 修改玩家 profile：display_name / vip_level / level 等。"""
    pid = str(player_id or "").strip()
    if not pid:
        raise ValueError("player_id 必填")
    init_db()
    with get_cursor() as cur:
        row = cur.execute("SELECT * FROM baas_players WHERE service_id=? AND player_id=?", (service_id, pid)).fetchone()
        if not row:
            raise ValueError("玩家不存在")
        prof = _json_load(row["profile_json"], {})
        display = payload.get("display_name")
        if display is not None:
            display = str(display).strip()
        now = _now_iso()
        if display:
            cur.execute(
                "UPDATE baas_players SET display_name=?, updated_at=? WHERE service_id=? AND player_id=?",
                (display, now, service_id, pid),
            )
        for key in ("vip_level", "vip_exp", "level", "recharge_total", "muted"):
            if key in payload:
                prof[key] = payload[key]
        cur.execute(
            "UPDATE baas_players SET profile_json=?, updated_at=? WHERE service_id=? AND player_id=?",
            (_json_dump(prof), now, service_id, pid),
        )
        if "vip_level" in payload or "vip_exp" in payload:
            try:
                from services.baas.afk.afk_vip_service import add_vip_exp
                exp = int(prof.get("vip_exp") or payload.get("vip_exp") or 0)
                add_vip_exp(service_id, pid, max(0, exp - int(prof.get("vip_exp") or 0)))
            except Exception:
                pass
    log_audit_db("default", actor, "baas_gm_update_profile", f"{service_id}/{pid}", "")
    return get_player_detail(service_id, pid)


def gm_send_player_mail(service_id: str, payload: Dict[str, Any], *, actor: str = "") -> Dict[str, Any]:
    pid = str(payload.get("player_id") or "").strip()
    if not pid:
        raise ValueError("player_id 必填")
    return mail_service.send_mail(service_id, payload, actor=actor)


def gm_set_tower_floor(service_id: str, player_id: str, floor: int, *, tower_id: str = "main", actor: str = "") -> Dict[str, Any]:
    from services.baas import tower_service

    init_db()
    now = _now_iso()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO baas_tower_progress (service_id, player_id, tower_id, floor, best_stars, updated_at)
            VALUES (?,?,?,?,1,?)
            ON CONFLICT(service_id, player_id, tower_id) DO UPDATE SET floor=excluded.floor, updated_at=excluded.updated_at
            """,
            (service_id, player_id, tower_id, max(0, int(floor)), now),
        )
    log_audit_db("default", actor, "baas_gm_set_tower", f"{service_id}/{player_id} floor={floor}", "")
    return tower_service.get_progress(service_id, player_id, tower_id)


def gm_set_vip(service_id: str, player_id: str, vip_level: int, vip_exp: int = 0, *, actor: str = "") -> Dict[str, Any]:
    from services.baas.afk.afk_vip_service import add_vip_exp, get_state

    init_db()
    with get_cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS baas_vip_progress (
                service_id TEXT NOT NULL, player_id TEXT NOT NULL,
                vip_exp INTEGER NOT NULL DEFAULT 0, vip_level INTEGER NOT NULL DEFAULT 0,
                last_daily_claim_at TEXT NOT NULL DEFAULT '', premium_battlepass INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL, PRIMARY KEY (service_id, player_id)
            )
            """
        )
        now = _now_iso()
        cur.execute(
            """
            INSERT INTO baas_vip_progress (service_id, player_id, vip_exp, vip_level, last_daily_claim_at, premium_battlepass, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(service_id, player_id) DO UPDATE SET vip_exp=excluded.vip_exp, vip_level=excluded.vip_level, updated_at=excluded.updated_at
            """,
            (service_id, player_id, int(vip_exp), int(vip_level), "", 0, now),
        )
    log_audit_db("default", actor, "baas_gm_set_vip", f"{service_id}/{player_id} lv={vip_level}", "")
    return get_state(service_id, player_id)

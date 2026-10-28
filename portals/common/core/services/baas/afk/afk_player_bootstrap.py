# -*- coding: utf-8 -*-
"""Bootstrap AFK retention on new player: welcome mail."""

from __future__ import annotations

from services.baas.afk.afk_config_loader import load_afk_bundle
from services.baas.helpers import _json_dump, _now_iso, new_id
from services.baas.service_crud import feature_enabled


def bootstrap_new_player(cur, service_id: str, player_id: str) -> None:
    if not feature_enabled(service_id, "mail"):
        return
    bundle = load_afk_bundle() or {}
    mail_cfg = bundle.get("mail") or {}
    templates = mail_cfg.get("templates") or []
    welcome = next(
        (t for t in templates if str(t.get("template_id") or t.get("id") or "") in ("welcome", "mail_welcome", "welcome_new")),
        None,
    )
    if not welcome and templates:
        welcome = templates[0]
    if not welcome:
        welcome = {
            "subject_zh": "欢迎来到佣兵之萌",
            "body_zh": "冒险者，领取补给开始裂隙之旅！",
            "attachments": [
                {"type": "currency", "currency_id": "gold", "amount": 3000},
                {"type": "currency", "currency_id": "diamond", "amount": 100},
            ],
        }
    mail_id = new_id("mail_")
    now = _now_iso()
    attachments = welcome.get("attachments") or welcome.get("rewards_json") or []
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
            str(welcome.get("subject_zh") or welcome.get("subject") or welcome.get("title") or "系统邮件"),
            str(welcome.get("body_zh") or welcome.get("body") or ""),
            _json_dump(attachments),
            "[]",
            "unread",
            "bootstrap",
            now,
            now,
            "",
        ),
    )

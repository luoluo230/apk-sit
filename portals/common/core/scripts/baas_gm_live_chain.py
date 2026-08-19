#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GM API + Web console smoke using app_baas (same DB/routes as live :5004)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

CORE = Path(__file__).resolve().parents[1]
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

os.environ.setdefault("BAAS_STANDALONE", "1")
os.environ.setdefault("PORTAL_SERVER_FRAMEWORKS", "baas")


class _GmFlaskClient:
    def __init__(self, flask_client, project_id: str, service_id: str):
        self._client = flask_client
        self.gm_base = f"/api/projects/{project_id}/baas/services/{service_id}/gm"
        self.project_id = project_id
        self.service_id = service_id

    def get(self, path: str) -> dict:
        r = self._client.get(self.gm_base + path)
        return r.get_json(silent=True) or {}

    def post(self, path: str, body: dict) -> dict:
        r = self._client.post(self.gm_base + path, json=body)
        return r.get_json(silent=True) or {}

    def delete(self, path: str) -> dict:
        r = self._client.delete(self.gm_base + path)
        return r.get_json(silent=True) or {}


class BaasGmLiveChain:
    def __init__(self, portal: str, project_id: str, service_id: str, *, admin_user: str = "admin", admin_pass: str = "admin123"):
        self.portal = portal.rstrip("/")
        self.project_id = project_id
        self.service_id = service_id
        self.admin_user = admin_user
        self.admin_pass = admin_pass
        self.scenarios: List[Dict[str, Any]] = []

    def _record(self, name: str, ok: bool, detail: dict | None = None) -> bool:
        self.scenarios.append({"name": name, "ok": ok, "detail": detail or {}})
        return ok

    def run_all(self) -> dict:
        from app_baas import app

        app.config["WTF_CSRF_ENABLED"] = False
        client = app.test_client()
        login = client.post("/login", data={"username": self.admin_user, "password": self.admin_pass})
        if login.status_code not in (200, 302):
            return {"ok": False, "scenarios": [{"name": "admin_login", "ok": False, "detail": {"status": login.status_code}}]}
        self.gm = _GmFlaskClient(client, self.project_id, self.service_id)
        ok = True
        ok &= self._record("admin_login", True, {"status": login.status_code})
        ok &= self.scenario_gm_console_page(client)
        ok &= self.scenario_gm_api_chain()
        return {"ok": ok, "scenarios": self.scenarios}

    def scenario_gm_console_page(self, client) -> bool:
        try:
            url = f"/admin/projects/{self.project_id}/baas-gm/{self.service_id}"
            resp = client.get(url)
            page = resp.data.decode("utf-8", errors="replace")
            checks = {
                "page_200": resp.status_code == 200,
                "baas_gm_marker": 'data-delivery-page="baas-gm"' in page,
                "nav_players": "玩家查询" in page,
                "nav_rooms": "房间" in page,
                "js_loaded": "baas_gm_console" in page,
            }
            return self._record("gm_web_console", all(checks.values()), checks)
        except Exception as exc:
            return self._record("gm_web_console", False, {"error": str(exc)})

    def scenario_gm_api_chain(self) -> bool:
        try:
            dash = self.gm.get("/dashboard")
            players = self.gm.get("/players?limit=10")
            player_id = ""
            if players.get("ok") and (players.get("data") or []):
                player_id = str(players["data"][0].get("player_id") or "")

            wallet = self.gm.post("/wallet", {
                "player_id": player_id or "gm_test_player",
                "currency_id": "gold",
                "delta": 500,
                "reason": "production_e2e",
            })
            mail = self.gm.post("/mail/broadcast", {
                "subject": "E2E补偿",
                "body": "production readiness test",
                "attachments": [{"type": "currency", "currency_id": "gold", "amount": 50}],
                "target": "all",
            })
            gift = self.gm.post("/gift-codes", {
                "code": "PRODE2E2026",
                "code_type": "shared",
                "max_uses": 100,
                "rewards": [{"type": "currency", "currency_id": "gold", "amount": 10}],
            })
            ann = self.gm.post("/announcements", {
                "title": "E2E公告",
                "body": "全量联调",
                "display_type": "marquee",
                "status": "published",
            })
            act = self.gm.post("/activities", {
                "title": "E2E活动",
                "activity_type": "login_event",
                "starts_at": "2020-01-01T00:00:00",
                "ends_at": "2099-01-01T00:00:00",
                "gates": {},
                "payload": {},
                "status": "published",
            })
            tmpl = self.gm.post("/mail-templates", {
                "template_key": "e2e_tpl",
                "subject": "模板邮件",
                "body": "模板正文",
                "attachments": [],
            })
            lb = self.gm.delete("/leaderboards/default")
            rooms = self.gm.get("/rooms")
            replays = self.gm.get("/rooms/replays")
            audit = self.gm.get("/audit?limit=20")
            gs_health = self.gm.get("/gameserver/health")

            ok = all([
                dash.get("ok"),
                players.get("ok"),
                wallet.get("ok"),
                mail.get("ok"),
                gift.get("ok"),
                ann.get("ok"),
                act.get("ok"),
                tmpl.get("ok"),
                audit.get("ok"),
            ])
            return self._record("gm_api_chain", ok, {
                "dashboard": dash.get("ok"),
                "wallet": wallet.get("ok"),
                "mail_broadcast": mail.get("ok"),
                "gift_code": gift.get("ok"),
                "rooms": rooms.get("ok"),
                "audit": audit.get("ok"),
                "gameserver_health_reachable": gs_health is not None,
            })
        except Exception as exc:
            return self._record("gm_api_chain", False, {"error": str(exc)})


def run_gm_chain(creds: dict, *, admin_user: str = "admin", admin_pass: str = "admin123") -> dict:
    return BaasGmLiveChain(
        creds.get("portal", "http://127.0.0.1:5004"),
        creds["project_id"],
        creds["service_id"],
        admin_user=admin_user,
        admin_pass=admin_pass,
    ).run_all()

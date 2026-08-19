#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seed full-feature BaaS project for production-readiness E2E."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")
os.environ.setdefault("BAAS_STANDALONE", "1")
os.environ.setdefault("PORTAL_SERVER_FRAMEWORKS", "baas")

from config import load_dotenv

load_dotenv()

_PROJECT = "baas_production_e2e"
_GAME_ID = "baas-production-e2e"
_GAME_KEY = "baas-production-e2e-key"

_ALL_FLAGS = {
    "login": True,
    "announce": True,
    "mail": True,
    "cloudsave": True,
    "leaderboard": True,
    "economy": True,
    "achievement": True,
    "gift": True,
    "guild": True,
    "battlepass": True,
    "periodic_task": True,
    "compliance": True,
    "pvp": True,
}

_FEATURE_CONFIGS = {
    "economy": {
        "currencies": [{"id": "gold", "name": "金币", "initial": 5000}],
        "products": [{"id": "potion_small", "name": "小血瓶", "price": 100, "currency_id": "gold"}],
    },
    "achievement": {
        "definitions": [{"id": "first_login", "name": "首次登录", "target": 1}],
    },
    "gift": {"packs": [], "codes": []},
    "periodic_task": {
        "daily_tasks": [{"id": "daily_login", "name": "每日登录", "target": 1, "reward_xp": 10}],
        "weekly_tasks": [],
    },
    "compliance": {
        "enabled": True,
        "daily_limit_minutes": 180,
        "curfew_start": "22:00",
        "curfew_end": "08:00",
        "require_real_name": False,
    },
    "pvp": {"mode": "state_sync", "room_ttl_seconds": 600, "max_players": 2},
}


def main() -> int:
    from models.data import projects_db
    from models.db import init_db
    from repositories.admin import projects_repo
    from services.baas.registry import default_feature_configs
    from services.baas.service_crud import ensure_service, rotate_api_secret, update_service

    init_db()
    projects_db[_PROJECT] = {
        "name": "BaaS Production E2E",
        "game_id": _GAME_ID,
        "game_key": _GAME_KEY,
        "server_mode": "casual_baas",
        "status": "active",
        "created_by": "admin",
    }
    projects_repo.upsert_project(_PROJECT, projects_db[_PROJECT])
    svc, secret = ensure_service(_PROJECT, "development", actor="admin")
    service_id = svc["service_id"]
    if not secret:
        secret, _ = rotate_api_secret(_PROJECT, service_id)

    configs = default_feature_configs()
    configs.update(_FEATURE_CONFIGS)
    update_service(
        _PROJECT,
        service_id,
        {"feature_flags": _ALL_FLAGS, "feature_configs": configs},
        actor="admin",
    )

    portal = os.environ.get("BAAS_E2E_PORTAL", "http://127.0.0.1:5004")
    payload = {
        "project_id": _PROJECT,
        "game_id": _GAME_ID,
        "game_key": _GAME_KEY,
        "service_id": service_id,
        "api_key": secret,
        "portal": portal,
        "env_key": "development",
    }
    out = Path(os.environ.get("BAAS_E2E_CREDENTIALS") or ROOT.parents[2] / "docs/evidence/baas-production-e2e-credentials.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"[seed-production] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

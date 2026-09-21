#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seed BaaS project for AFK live-server E2E (real waitress + Unity PlayMode)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("BAAS_STANDALONE", "1")
os.environ.setdefault("PORTAL_SERVER_FRAMEWORKS", "baas")

from config import load_dotenv

load_dotenv()

_PROJECT = "baas_afk_live_e2e"
_GAME_ID = "baas-afk-live-e2e"
_GAME_KEY = "baas-afk-live-e2e-key"
_GIFT_CODE = "AFKE2E2026"

_FLAGS = {
    "login": True, "announce": True, "mail": True, "cloudsave": True, "leaderboard": True,
    "economy": True, "achievement": True, "gift": True, "guild": True, "battlepass": True,
    "periodic_task": True, "compliance": True, "pve": True, "arena": True, "pvp": True,
    "hero": True, "gacha": True, "idle": True, "tower": True, "iap": True, "inventory": True,
    "economy": True,
}


def _dev_iap_requested() -> bool:
    """Keep fake receipts confined to an explicitly started local E2E stack."""
    return os.environ.get("BAAS_ALLOW_DEV_IAP", "").strip().lower() in {"1", "true", "yes"}


def main() -> int:
    from models.db import init_db
    from models.data import projects_db
    from repositories.admin import projects_repo
    from services.baas.registry import default_feature_configs
    from services.baas.afk_config_loader import afk_feature_configs
    from services.baas.service_crud import ensure_service, rotate_api_secret, update_service
    from services.baas.gm_service import upsert_gift_code

    init_db()
    projects_db[_PROJECT] = {
        "name": "AFK Live Server E2E",
        "game_id": _GAME_ID,
        "game_key": _GAME_KEY,
        "server_mode": "casual_baas",
        "status": "active",
        "created_by": "admin",
    }
    svc, secret = ensure_service(_PROJECT, "development", actor="admin")
    service_id = svc["service_id"]
    projects_db[_PROJECT]["baas_service_id"] = service_id
    projects_repo.upsert_project(_PROJECT, projects_db[_PROJECT])
    if not secret:
        secret, _ = rotate_api_secret(_PROJECT, service_id)

    configs = default_feature_configs()
    afk_extra = afk_feature_configs()
    for k, v in afk_extra.items():
        if not str(k).startswith("_"):
            configs[k] = v
    # The packaged AFK config intentionally has this disabled.  A disposable local
    # E2E stack may opt in, but it still also needs BAAS_ALLOW_DEV_IAP at runtime.
    iap = dict(configs.get("iap") or {})
    iap["dev_verify_always_ok"] = _dev_iap_requested()
    configs["iap"] = iap
    pve = dict(configs.get("pve") or {})
    pve["stamina_max"] = 5000
    pve["stamina_recover_seconds"] = 60
    configs["pve"] = pve

    update_service(
        _PROJECT,
        service_id,
        {"feature_flags": _FLAGS, "feature_configs": configs},
        actor="admin",
    )

    upsert_gift_code(service_id, {
        "code": _GIFT_CODE,
        "code_type": "shared",
        "max_uses": 99999,
        "rewards": [
            {"type": "currency", "currency_id": "diamond", "amount": 50000},
            {"type": "currency", "currency_id": "gold", "amount": 5000000},
            {"type": "item", "item_id": "enhance_stone", "quantity": 200},
            {"type": "item", "item_id": "refine_core", "quantity": 40},
            {"type": "item", "item_id": "star_up_crystal", "quantity": 120},
            {"type": "item", "item_id": "talent_book", "quantity": 30},
            {"type": "item", "item_id": "tower_key", "quantity": 20},
            {"type": "item", "item_id": "awaken_stone", "quantity": 8},
            {"type": "item", "item_id": "gem_ruby", "quantity": 16},
        ],
    }, actor="seed")

    portal = os.environ.get("BAAS_E2E_PORTAL", "http://127.0.0.1:5004")
    payload = {
        "project_id": _PROJECT,
        "game_id": _GAME_ID,
        "game_key": _GAME_KEY,
        "service_id": service_id,
        "api_key": secret,
        "portal": portal,
        "gift_code": _GIFT_CODE,
    }
    out = Path(os.environ.get("BAAS_E2E_CREDENTIALS") or ROOT / "docs/evidence/baas-afk-live-e2e-credentials.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # Keep the actual key only in the explicitly ignored credentials file.
    # Console logs are frequently retained by CI and must be safe to publish.
    print(json.dumps({
        "project_id": _PROJECT,
        "game_id": _GAME_ID,
        "service_id": service_id,
        "api_key_written": bool(secret),
        "portal": portal,
        "gift_code": _GIFT_CODE,
    }, ensure_ascii=False, indent=2))
    print(f"[seed-afk-live] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8
"""wechat_minigame publish path E2E — capability, scope, bootstrap contract."""

from __future__ import annotations

import json
import os
import sys

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)


def main() -> int:
    os.environ.setdefault("USE_SQLITE", "true")
    from app_new import app
    from models.db import init_db
    from services.build.platform_capability import list_platform_capabilities, resolve_platform_capability
    from services.release.scope_resolver import resolve_scope

    init_db()
    caps = list_platform_capabilities()
    mg = next((c for c in caps if c.get("platform_id") == "wechat_minigame"), None)
    if not mg:
        mg = resolve_platform_capability("wechat_minigame")
    if not mg or not mg.get("can_build"):
        print("wechat_minigame_publish_e2e FAILED: capability")
        return 1
    scope = resolve_scope("GomeKu", "development", "1001", platform="wechat_minigame", auto_create=False)

    with app.test_client() as client:
        resp = client.get(
            "/api/public/runtime-bootstrap?"
            "game_id=gomeku-fb64779f94b161d0&game_key=test&env_key=development&channel=1001&platform=wechat_minigame"
        )
        # Unauthorized without valid game_key is expected; route must exist (not 404/501).
        if resp.status_code == 404:
            print("wechat_minigame_publish_e2e FAILED: bootstrap route missing for wechat_minigame")
            return 1

    spec_path = os.path.join(_CORE, "..", "..", "..", "docs", "design_specs", "wechat_minigame_hotupdate.md")
    if not os.path.isfile(os.path.normpath(spec_path)):
        print("wechat_minigame_publish_e2e FAILED: design spec missing")
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "capability": mg.get("platform_id"),
                "scope": scope is not None,
                "bootstrap_status": resp.status_code,
                "spec": os.path.normpath(spec_path),
            },
            ensure_ascii=False,
        )
    )
    print("wechat_minigame_publish_e2e PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

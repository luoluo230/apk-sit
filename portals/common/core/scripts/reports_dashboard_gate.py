# -*- coding: utf-8 -*-
"""§11.3 reports dashboard gate."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    from app_new import app
    from data.repositories.user_repository import UserRepository

    repo = UserRepository()
    repo.reload()
    user = next(iter(repo.list_all().keys()), "admin")
    errors: list[str] = []
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = user
        resp = client.get("/admin/reports/dashboard")
        if resp.status_code != 200:
            errors.append(f"dashboard status {resp.status_code}")
        else:
            body = resp.get_json(silent=True) or {}
            cards = body.get("cards") if isinstance(body.get("cards"), list) else []
            if len(cards) < 4:
                errors.append("dashboard cards < 4")
            schedule = body.get("schedule") if isinstance(body.get("schedule"), dict) else {}
            if not schedule.get("email_enabled"):
                errors.append("dashboard schedule.email_enabled missing")
    ok = not errors
    print(json.dumps({"ok": ok, "errors": errors}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

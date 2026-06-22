# -*- coding: utf-8 -*-
"""§11.5 RBAC dynamic config API gate."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    from app_new import app

    app.config["WTF_CSRF_ENABLED"] = False
    from data.repositories.user_repository import UserRepository

    repo = UserRepository()
    users = repo.list_all()
    actor = next((u for u, rec in users.items() if (rec or {}).get("role") in ("super_admin", "admin")), "admin")
    target = next(
        (u for u, rec in users.items() if u != "admin" and (rec or {}).get("role") not in ("super_admin",)),
        None,
    )
    if not target:
        target = "rbac_gate_user"
        repo.create(
            target,
            {
                "password": "unused",
                "role": "user",
                "allowed_modules": ["dashboard"],
                "disabled": False,
            },
        )
    errors: list[str] = []
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = actor
        get_r = client.get(f"/admin/rbac/users/{target}")
        if get_r.status_code != 200:
            errors.append(f"rbac get {get_r.status_code}")
        page_r = client.get("/admin/rbac")
        if page_r.status_code != 200:
            errors.append(f"rbac page {page_r.status_code}")
        elif "RBAC" not in (page_r.get_data(as_text=True) or ""):
            errors.append("rbac page missing title")
        put_r = client.put(
            f"/admin/rbac/users/{target}",
            json={"allowed_modules": ["reports", "dashboard"]},
        )
        if put_r.status_code != 200:
            errors.append(f"rbac put {put_r.status_code}")
    ok = not errors
    print(json.dumps({"ok": ok, "errors": errors}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

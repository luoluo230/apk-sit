# -*- coding: utf-8 -*-
"""Auth login flows through UserRepository."""

from __future__ import annotations

from app_new import app
from repositories.admin import users_repo


def test_login_uses_repository():
    app.config["WTF_CSRF_ENABLED"] = False
    username = next(iter(users_repo.list_users().keys()), "admin")
    with app.test_client() as client:
        resp = client.post("/login", data={"username": username, "password": "admin123"}, follow_redirects=False)
        assert resp.status_code in (302, 303)
        with client.session_transaction() as sess:
            assert sess.get("user") == username
    row = users_repo.get_user(username)
    assert row and row.get("last_login")


def test_change_password_via_repository():
    app.config["WTF_CSRF_ENABLED"] = False
    username = next(iter(users_repo.list_users().keys()), "admin")
    users_repo.update_password(username, "admin123")
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = username
        resp = client.post(
            "/profile/change-password",
            json={"current": "admin123", "new_password": "admin123"},
        )
        assert resp.status_code == 200
        assert users_repo.verify_password(username, "admin123")

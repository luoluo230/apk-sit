"""User management service."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Dict, Tuple

from repositories.admin import users_repo
from services.admin.envelope import ok, fail, attach_legacy_error


VALID_ROLES = ("admin", "super_admin", "user")


def list_users() -> Tuple[Dict[str, Any], int]:
    rows = []
    for username, rec in users_repo.list_users().items():
        rows.append(
            {
                "username": username,
                "role": rec.get("role", "user"),
                "created_at": rec.get("created_at"),
                "last_login": rec.get("last_login"),
                "allowed_modules": rec.get("allowed_modules") or [],
                "allowed_scopes": rec.get("allowed_scopes") or [],
                "disabled": rec.get("disabled", False),
            }
        )
    payload = ok({"users": rows}, legacy={"users": rows})
    return payload, 200


def get_user(username: str) -> Tuple[Dict[str, Any], int]:
    rec = users_repo.get_user(username)
    if not rec:
        return attach_legacy_error(fail("用户不存在", code="not_found", legacy={"error": "用户不存在"})), 404
    user_payload = {
        "username": username,
        "role": rec.get("role", "user"),
        "allowed_modules": rec.get("allowed_modules") or [],
        "allowed_scopes": rec.get("allowed_scopes") or [],
        "disabled": rec.get("disabled", False),
    }
    payload = ok({"user": user_payload}, legacy={"user": user_payload})
    return payload, 200


def create_user(data: Dict[str, Any], min_password_len: int) -> Tuple[Dict[str, Any], int]:
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "").strip()
    role = str(data.get("role") or "user").strip()
    if not username or not password:
        return attach_legacy_error(fail("用户名和密码不能为空", code="validation_error", legacy={"error": "用户名和密码不能为空"})), 400
    if len(password) < int(min_password_len):
        return attach_legacy_error(fail(f"密码至少 {min_password_len} 位", code="validation_error", legacy={"error": f"密码至少 {min_password_len} 位"})), 400
    if users_repo.get_user(username):
        return attach_legacy_error(fail("用户已存在", code="conflict", legacy={"error": "用户已存在"})), 409
    role = role if role in VALID_ROLES else "user"
    rec = {
        "password": hashlib.sha256(password.encode()).hexdigest(),
        "role": role,
        "created_at": datetime.now().isoformat(),
    }
    if role == "user":
        allowed = data.get("allowed_modules")
        if isinstance(allowed, list) and allowed:
            rec["allowed_modules"] = allowed
        else:
            rec["allowed_modules"] = ["*"]
        scopes = data.get("allowed_scopes")
        if isinstance(scopes, list):
            rec["allowed_scopes"] = scopes
        elif scopes is not None:
            rec["allowed_scopes"] = [s.strip() for s in str(scopes).split(",") if s.strip()]
    users_repo.upsert_user(username, rec)
    users_repo.audit("create_user", username)
    payload = ok({"id": username}, legacy={"success": True})
    return payload, 200


def _count_active_super_admins(exclude: str = "") -> int:
    n = 0
    for name, row in (users_repo.list_users() or {}).items():
        if exclude and name == exclude:
            continue
        if str((row or {}).get("role") or "") != "super_admin":
            continue
        if (row or {}).get("disabled"):
            continue
        n += 1
    return n


def update_user(data: Dict[str, Any], *, actor: str = "") -> Tuple[Dict[str, Any], int]:
    username = str(data.get("username") or "").strip()
    actor_name = str(actor or "").strip()
    rec = users_repo.get_user(username)
    if not username or not rec:
        return attach_legacy_error(fail("用户不存在", code="not_found", legacy={"error": "用户不存在"})), 404
    if username == "admin":
        return attach_legacy_error(fail("不能修改内置账号 admin", code="forbidden", legacy={"error": "不能修改内置账号 admin"})), 403
    if actor_name and username == actor_name and data.get("disabled") is True:
        return attach_legacy_error(fail("不能禁用当前登录账号", code="forbidden", legacy={"error": "不能禁用当前登录账号"})), 403

    next_role = str(data.get("role") or rec.get("role") or "user").strip()
    if next_role not in VALID_ROLES:
        next_role = str(rec.get("role") or "user")
    will_disable = bool(data["disabled"]) if "disabled" in data else bool(rec.get("disabled"))
    was_super = str(rec.get("role") or "") == "super_admin" and not rec.get("disabled")
    stays_super = next_role == "super_admin" and not will_disable
    if was_super and not stays_super and _count_active_super_admins(exclude=username) < 1:
        return attach_legacy_error(
            fail("至少保留一名可用的超级管理员", code="forbidden", legacy={"error": "至少保留一名可用的超级管理员"}),
        ), 403

    if "role" in data:
        rec["role"] = next_role
    if "allowed_modules" in data:
        rec["allowed_modules"] = data["allowed_modules"] if isinstance(data["allowed_modules"], list) else []
    if "allowed_scopes" in data:
        scopes = data["allowed_scopes"]
        if isinstance(scopes, list):
            rec["allowed_scopes"] = scopes
        else:
            rec["allowed_scopes"] = [s.strip() for s in str(scopes).split(",") if s.strip()]
    if "disabled" in data:
        rec["disabled"] = bool(data["disabled"])
    if next_role in ("admin", "super_admin"):
        rec["allowed_modules"] = ["*"]
        rec["allowed_scopes"] = []
    users_repo.save()
    users_repo.audit("update_user", username)
    return ok({"id": username}, legacy={"success": True}), 200


def reset_password(data: Dict[str, Any], min_password_len: int) -> Tuple[Dict[str, Any], int]:
    username = str(data.get("username") or "").strip()
    new_password = str(data.get("new_password") or "").strip()
    rec = users_repo.get_user(username)
    if not username or not rec:
        return attach_legacy_error(fail("用户不存在", code="not_found", legacy={"error": "用户不存在"})), 404
    if username == "admin":
        return attach_legacy_error(fail("不能修改内置账号 admin 密码", code="forbidden", legacy={"error": "不能修改内置账号 admin 密码"})), 403
    if not new_password:
        return attach_legacy_error(fail("新密码不能为空", code="validation_error", legacy={"error": "新密码不能为空"})), 400
    if len(new_password) < int(min_password_len):
        return attach_legacy_error(fail(f"密码至少 {min_password_len} 位", code="validation_error", legacy={"error": f"密码至少 {min_password_len} 位"})), 400
    rec["password"] = hashlib.sha256(new_password.encode()).hexdigest()
    users_repo.save()
    users_repo.audit("reset_password", username)
    return ok({"id": username}, legacy={"success": True}), 200


def delete_user(username: str, *, actor: str = "") -> Tuple[Dict[str, Any], int]:
    if username == "admin":
        return attach_legacy_error(fail("不能删除内置账号 admin", code="forbidden", legacy={"error": "不能删除内置账号 admin"})), 403
    if actor and username == actor:
        return attach_legacy_error(fail("不能删除当前登录账号", code="forbidden", legacy={"error": "不能删除当前登录账号"})), 403
    rec = users_repo.get_user(username)
    if not rec:
        return attach_legacy_error(fail("用户不存在", code="not_found", legacy={"error": "用户不存在"})), 404
    if str(rec.get("role") or "") == "super_admin" and _count_active_super_admins(exclude=username) < 1:
        return attach_legacy_error(
            fail("不能删除最后一名超级管理员", code="forbidden", legacy={"error": "不能删除最后一名超级管理员"}),
        ), 403
    users_repo.remove_user(username)
    users_repo.audit("delete_user", username)
    return ok({"id": username}, legacy={"success": True}), 200

"""CSV import/export helpers for admin users."""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime
from typing import Any, Dict, Tuple

from repositories.admin import users_repo


def export_users_csv() -> Tuple[bytes, str]:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["用户名", "角色", "禁用", "模块权限", "操作权限", "创建时间", "最后登录"])
    for username, user in sorted(users_repo.list_users().items()):
        modules = user.get("allowed_modules") or []
        scopes = user.get("allowed_scopes") or []
        writer.writerow(
            [
                username,
                user.get("role", "user"),
                "是" if user.get("disabled") else "否",
                ",".join(modules) if isinstance(modules, list) else str(modules),
                ",".join(scopes) if isinstance(scopes, list) else str(scopes),
                (user.get("created_at") or "")[:19],
                (user.get("last_login") or "")[:19],
            ]
        )
    filename = "users_export_%s.csv" % datetime.now().strftime("%Y%m%d_%H%M")
    return buf.getvalue().encode("utf-8-sig"), filename


def _decode_upload_bytes(raw: bytes) -> str | None:
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return raw.decode(encoding)
        except Exception:
            continue
    return None


def import_users_csv(file_storage: Any, min_password_len: int) -> Tuple[Dict[str, Any], int]:
    filename = str(getattr(file_storage, "filename", "") or "")
    if not file_storage or not filename.lower().endswith(".csv"):
        return {"error": "请上传 CSV 文件"}, 400

    raw = file_storage.read() or b""
    content = _decode_upload_bytes(raw)
    if content is None:
        return {"error": "文件编码不支持，请使用 UTF-8 或 GBK"}, 400

    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        return {"error": "CSV 为空"}, 400

    header = [h.strip() for h in rows[0]]
    username_idx = next((i for i, h in enumerate(header) if "用户" in h or "username" in h.lower()), 0)
    password_idx = next((i for i, h in enumerate(header) if "密码" in h or "password" in h.lower()), 1)
    role_idx = next((i for i, h in enumerate(header) if "角色" in h or "role" in h.lower()), 2)

    users = users_repo.list_users()
    created = 0
    skipped = 0
    for row in rows[1:]:
        if len(row) <= max(username_idx, password_idx):
            continue
        username = str(row[username_idx] or "").strip()
        password = str(row[password_idx] or "").strip()
        role = str(row[role_idx] or "user").strip() if role_idx < len(row) else "user"
        if not username:
            continue
        if username in ("admin",) or users.get(username, {}).get("role") == "super_admin":
            skipped += 1
            continue
        if username in users:
            skipped += 1
            continue
        if len(password) < int(min_password_len):
            skipped += 1
            continue
        role = role if role in ("admin", "user") else "user"
        payload = {
            "password": hashlib.sha256(password.encode()).hexdigest(),
            "role": role,
            "created_at": datetime.now().isoformat(),
        }
        if role == "user":
            payload["allowed_modules"] = ["*"]
        users_repo.upsert_user(username, payload)
        created += 1

    users_repo.audit("users_import", f"created={created} skipped={skipped}")
    return {"success": True, "created": created, "skipped": skipped}, 200

# -*- coding: utf-8 -*-
"""Persist per-user page and project favorites in users_repo."""

from __future__ import annotations

from typing import Any, Dict, List

from repositories.admin import users_repo


def _empty_favorites() -> Dict[str, Any]:
    return {"page_favorites": {}, "project_favorites": []}


def _normalize_page_favorites(raw: Any) -> Dict[str, bool]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, bool] = {}
    for key, val in raw.items():
        k = str(key or "").strip()
        if not k:
            continue
        out[k] = bool(val) if isinstance(val, bool) else str(val) in {"1", "true", "yes", "on"}
    return out


def _normalize_project_favorites(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    seen = set()
    for item in raw:
        pid = str(item or "").strip()
        if not pid or pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
    return out


def get_user_favorites(username: str) -> Dict[str, Any]:
    user = str(username or "").strip()
    if not user:
        raise ValueError("未登录")
    row = users_repo.get_user(user) or {}
    prefs = row.get("preferences") if isinstance(row.get("preferences"), dict) else {}
    fav = prefs.get("favorites") if isinstance(prefs.get("favorites"), dict) else {}
    return {
        "page_favorites": _normalize_page_favorites(fav.get("page_favorites")),
        "project_favorites": _normalize_project_favorites(fav.get("project_favorites")),
    }


def save_user_favorites(username: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    user = str(username or "").strip()
    if not user:
        raise ValueError("未登录")
    row = dict(users_repo.get_user(user) or {})
    prefs = dict(row.get("preferences") or {}) if isinstance(row.get("preferences"), dict) else {}
    current = prefs.get("favorites") if isinstance(prefs.get("favorites"), dict) else {}
    merged = {
        "page_favorites": _normalize_page_favorites(
            payload.get("page_favorites") if "page_favorites" in payload else current.get("page_favorites")
        ),
        "project_favorites": _normalize_project_favorites(
            payload.get("project_favorites") if "project_favorites" in payload else current.get("project_favorites")
        ),
    }
    prefs["favorites"] = merged
    row["preferences"] = prefs
    users_repo.upsert_user(user, row)
    users_repo.save()
    return merged


def toggle_page_favorite(username: str, key: str, *, active: bool | None = None) -> Dict[str, Any]:
    fav = get_user_favorites(username)
    page = dict(fav.get("page_favorites") or {})
    k = str(key or "").strip()
    if not k:
        raise ValueError("favorite key 必填")
    if active is None:
        page[k] = not bool(page.get(k))
    else:
        page[k] = bool(active)
    if not page[k]:
        page.pop(k, None)
    return save_user_favorites(username, {"page_favorites": page, "project_favorites": fav.get("project_favorites") or []})


def toggle_project_favorite(username: str, project_id: str, *, active: bool | None = None) -> Dict[str, Any]:
    fav = get_user_favorites(username)
    ids = list(fav.get("project_favorites") or [])
    pid = str(project_id or "").strip()
    if not pid:
        raise ValueError("project_id 必填")
    if active is None:
        if pid in ids:
            ids = [x for x in ids if x != pid]
        else:
            ids.append(pid)
    elif active:
        if pid not in ids:
            ids.append(pid)
    else:
        ids = [x for x in ids if x != pid]
    return save_user_favorites(username, {"page_favorites": fav.get("page_favorites") or {}, "project_favorites": ids})

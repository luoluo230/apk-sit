# -*- coding: utf-8 -*-
"""Shared game credential → project_id resolution for all server frameworks."""

from __future__ import annotations

from models.data import projects_db


def resolve_project_id(
    *,
    project_id: str = "",
    game_id: str = "",
    game_key: str = "",
) -> str:
    """Resolve project_id from explicit id or game_id + game_key pair."""
    pid = str(project_id or "").strip()
    if pid:
        return pid if pid in projects_db else ""
    gid = str(game_id or "").strip()
    gkey = str(game_key or "").strip()
    if not gid or not gkey:
        return ""
    for cand, proj in projects_db.items():
        if str(proj.get("game_id") or "") == gid and str(proj.get("game_key") or "") == gkey:
            return str(cand)
    return ""

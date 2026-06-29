# -*- coding: utf-8 -*-
"""ReleaseScope ID and channel helpers (no circular service dependencies)."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from data.platforms import is_valid_platform_id
from models.data import get_channel_by_id, projects_db
from services.release.env_registry import normalize_release_env_key
from services.release.storage import find_manifest


def project_slug(project_id: str) -> str:
    text = str(project_id or "").strip()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9]+", "", text.lower()) or text.lower()


def build_scope_id(slug: str, env_key: str, channel_id: str, platform: str = "") -> str:
    slug_norm = project_slug(slug) or str(slug or "").strip().lower()
    base = f"{slug_norm}:{normalize_release_env_key(env_key)}:{str(channel_id or '').strip()}"
    plat = str(platform or "").strip().lower()
    if is_valid_platform_id(plat):
        return f"{base}:{plat}"
    return base


def parse_scope_id(scope_id: str) -> Dict[str, str]:
    parts = [p for p in str(scope_id or "").split(":") if p != ""]
    out = {"slug": "", "env_key": "", "channel_id": "", "platform": ""}
    if len(parts) >= 3:
        out["slug"] = parts[0]
        out["env_key"] = parts[1]
        out["channel_id"] = parts[2]
    if len(parts) >= 4 and is_valid_platform_id(parts[3]):
        out["platform"] = parts[3]
    return out


def is_legacy_scope_id(scope_id: str) -> bool:
    parts = [p for p in str(scope_id or "").split(":") if p != ""]
    return len(parts) == 3


def scope_platform(scope: Dict[str, Any]) -> str:
    if not isinstance(scope, dict):
        return ""
    plat = str(scope.get("platform") or "").strip().lower()
    if is_valid_platform_id(plat):
        return plat
    return str(parse_scope_id(str(scope.get("scope_id") or "")).get("platform") or "").strip().lower()


def _channel_defs(manifest: Dict[str, Any], project_id: str) -> List[Dict[str, Any]]:
    channels = manifest.get("channels") if isinstance(manifest.get("channels"), list) else []
    if channels:
        out = []
        for ch in channels:
            if not isinstance(ch, dict):
                continue
            cid = str(ch.get("channel_id") or "").strip()
            if not cid:
                continue
            ckey = str(ch.get("channel_key") or "").strip()
            if not ckey:
                cfg = get_channel_by_id(cid)
                if isinstance(cfg, dict):
                    ckey = str(cfg.get("apk_subdir") or cfg.get("name") or cid).strip()
            out.append({
                "channel_id": cid,
                "channel_key": ckey or cid,
                "platforms": [
                    str(p).strip().lower()
                    for p in (ch.get("platforms") or [])
                    if is_valid_platform_id(p)
                ],
            })
        if out:
            return out
    proj = projects_db.get(project_id) if isinstance(projects_db, dict) else {}
    ids = proj.get("channels") if isinstance(proj, dict) and isinstance(proj.get("channels"), list) else []
    disabled = set()
    raw_disabled = proj.get("disabled_channels") if isinstance(proj, dict) else []
    if isinstance(raw_disabled, list):
        disabled = {str(x).strip() for x in raw_disabled if str(x).strip()}
    out = []
    for cid in ids:
        cid_s = str(cid or "").strip()
        if not cid_s or cid_s in disabled:
            continue
        cfg = get_channel_by_id(cid_s)
        ckey = cid_s
        if isinstance(cfg, dict):
            ckey = str(cfg.get("apk_subdir") or cfg.get("name") or cid_s).strip() or cid_s
        out.append({"channel_id": cid_s, "channel_key": ckey})
    return out


def list_channel_defs(manifest: Dict[str, Any], project_id: str) -> List[Dict[str, Any]]:
    return _channel_defs(manifest, project_id)


def resolve_channel_id(project_id: str, channel: str) -> str:
    text = str(channel or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+", text):
        return text
    manifest = find_manifest(project_id)
    for ch in _channel_defs(manifest, project_id):
        if str(ch.get("channel_key") or "").strip().lower() == text.lower():
            return str(ch.get("channel_id") or "").strip()
        if str(ch.get("channel_id") or "").strip() == text:
            return text
    cfg = get_channel_by_id(text)
    if isinstance(cfg, dict) and str(cfg.get("id") or "").strip():
        return str(cfg.get("id") or "").strip()
    return text

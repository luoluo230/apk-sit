# -*- coding: utf-8 -*-
"""Canonical env_key registry for unified release platform."""

from __future__ import annotations

import re
from typing import Any, Dict, List

CANONICAL_ENV_KEYS = ("development", "testing", "staging", "production")

_BUILTIN_ENV_LABELS = {
    "development": "开发环境",
    "testing": "测试环境",
    "staging": "预发环境",
    "production": "生产环境",
}

_BUILTIN_ENV_ORDERS = {
    "development": 10,
    "testing": 20,
    "staging": 30,
    "production": 40,
}

_ENV_ALIASES = {
    "dev": "development",
    "develop": "development",
    "development": "development",
    "test": "testing",
    "testing": "testing",
    "qa": "testing",
    "stage": "staging",
    "staging": "staging",
    "pre": "staging",
    "preprod": "staging",
    "pre-release": "staging",
    "prod": "production",
    "production": "production",
    "online": "production",
    "release": "production",
}

_STAGE_BY_ENV_KEY = {
    "development": "dev",
    "testing": "test",
    "staging": "staging",
    "production": "production",
}

_GM_ENV_BY_ENV_KEY = {
    "development": "dev",
    "testing": "test",
    "staging": "staging",
    "production": "prod",
}

_JENKINS_ENV_BY_ENV_KEY = {
    "development": "Development",
    "testing": "Testing",
    "staging": "Staging",
    "production": "Production",
}

_CUSTOM_ENV_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def _builtin_env_defs() -> List[Dict[str, Any]]:
    return [
        {
            "env_key": key,
            "label": _BUILTIN_ENV_LABELS[key],
            "builtin": True,
            "enabled": True,
            "order": _BUILTIN_ENV_ORDERS[key],
        }
        for key in CANONICAL_ENV_KEYS
    ]


def get_project_env_defs(project_id: str) -> List[Dict[str, Any]]:
    from models.data import projects_db

    proj = projects_db.get(project_id) if project_id else {}
    raw = proj.get("release_environments") if isinstance(proj, dict) else None
    if not isinstance(raw, list) or not raw:
        return _builtin_env_defs()
    builtin_map = {row["env_key"]: row for row in _builtin_env_defs()}
    merged: Dict[str, Dict[str, Any]] = dict(builtin_map)
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = str(item.get("env_key") or "").strip().lower()
        if not key:
            continue
        base = merged.get(key) or {
            "env_key": key,
            "label": key,
            "builtin": False,
            "enabled": True,
            "order": 50,
        }
        merged[key] = {
            "env_key": key,
            "label": str(item.get("label") or base.get("label") or key),
            "builtin": bool(item.get("builtin", base.get("builtin", False))),
            "enabled": bool(item.get("enabled", base.get("enabled", True))),
            "order": int(item.get("order") or base.get("order") or 50),
        }
        if isinstance(item.get("channels"), list):
            merged[key]["channels"] = item.get("channels")
        if isinstance(item.get("platforms"), list):
            merged[key]["platforms"] = item.get("platforms")
        if isinstance(item.get("disabled_channels"), list):
            merged[key]["disabled_channels"] = item.get("disabled_channels")
        if isinstance(item.get("disabled_platforms"), list):
            merged[key]["disabled_platforms"] = item.get("disabled_platforms")
    return sorted(merged.values(), key=lambda row: (int(row.get("order") or 0), row.get("env_key") or ""))


def list_project_env_keys(project_id: str, *, enabled_only: bool = True) -> List[str]:
    defs = get_project_env_defs(project_id)
    if enabled_only:
        defs = [row for row in defs if row.get("enabled")]
    return [str(row.get("env_key") or "") for row in defs if str(row.get("env_key") or "").strip()]


def project_env_label(project_id: str, env_key: str) -> str:
    key = str(env_key or "").strip().lower()
    for row in get_project_env_defs(project_id):
        if str(row.get("env_key") or "").strip().lower() == key:
            return str(row.get("label") or key)
    return _BUILTIN_ENV_LABELS.get(key, key)


def is_valid_custom_env_key(env_key: str) -> bool:
    text = str(env_key or "").strip().lower()
    if not _CUSTOM_ENV_KEY_RE.fullmatch(text):
        return False
    if text in CANONICAL_ENV_KEYS:
        return False
    if text in _ENV_ALIASES:
        return False
    return True


def normalize_release_env_key(raw: Any, *, default: str = "production", project_id: str = "") -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return default if default in CANONICAL_ENV_KEYS else "production"
    if project_id:
        for row in get_project_env_defs(project_id):
            if str(row.get("env_key") or "").strip().lower() == text:
                return str(row["env_key"]).strip().lower()
    mapped = _ENV_ALIASES.get(text)
    if mapped:
        return mapped
    if text in CANONICAL_ENV_KEYS:
        return text
    return default if default in CANONICAL_ENV_KEYS else "production"


def stage_to_env_key(stage: Any) -> str:
    return normalize_release_env_key(stage, default="development")


def env_key_to_stage(env_key: str) -> str:
    key = normalize_release_env_key(env_key)
    return _STAGE_BY_ENV_KEY.get(key, "dev")


def env_key_to_gm_env(env_key: str) -> str:
    key = normalize_release_env_key(env_key)
    return _GM_ENV_BY_ENV_KEY.get(key, "prod")


def env_key_to_jenkins_env(env_key: str) -> str:
    key = normalize_release_env_key(env_key)
    return _JENKINS_ENV_BY_ENV_KEY.get(key, "Production")

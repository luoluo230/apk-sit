# -*- coding: utf-8 -*-
"""Canonical env_key registry for unified release platform."""

from __future__ import annotations

from typing import Any

CANONICAL_ENV_KEYS = ("development", "testing", "staging", "production")

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


def normalize_release_env_key(raw: Any, *, default: str = "production") -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return default if default in CANONICAL_ENV_KEYS else "production"
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

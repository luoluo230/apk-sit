# -*- coding: utf-8 -*-
"""Portal-level routing isolation for split deployments."""

import os

from flask import abort, redirect, request

from config import Config

ALWAYS_ALLOWED_PREFIXES = (
    "/health",
    "/static",
    "/product-media/",
    "/uploaded-media/",
    "/favicon.ico",
    "/status",
    "/openapi.json",
)

PLAYER_SITE_PREFIXES = (
    "/",
    "/product/",
    "/about/company",
    "/news",
    "/welfare",
)

FORUM_PREFIXES = (
    "/forum",
)

ADMIN_PREFIXES = (
    "/admin",
    "/workspace",
    "/docs",
    "/dashboard",
    "/download-center",
    "/download/",
    "/upload",
    "/qr/",
    "/api/",
    "/login",
    "/logout",
    "/profile",
)

_MODE_ALIASES = {
    "all": "all",
    "": "all",
    "player": "player",
    "player-site": "player",
    "player_site": "player",
    "public": "player",
    "forum": "forum",
    "community": "forum",
    "admin": "admin",
    "backend": "admin",
    "developer": "admin",
    "dev": "admin",
}


def current_portal_mode():
    raw = (os.getenv("APP_PORTAL_MODE") or getattr(Config, "PORTAL_MODE", "all") or "all").strip().lower()
    return _MODE_ALIASES.get(raw, raw)


def _host_matches(configured_host):
    if not configured_host:
        return True
    current = (request.host or "").split(":")[0].strip().lower()
    configured = configured_host.strip().lower()
    return current == configured


def _matches_prefix(path, prefixes):
    for prefix in prefixes:
        if prefix == "/":
            if path == "/":
                return True
            continue
        if path == prefix or path.startswith(prefix):
            return True
    return False


def _host_guard_for_mode(mode):
    if mode == "player":
        return getattr(Config, "PLAYER_DOMAIN", "") or ""
    if mode == "forum":
        return getattr(Config, "FORUM_DOMAIN", "") or ""
    if mode == "admin":
        return getattr(Config, "ADMIN_DOMAIN", "") or ""
    return ""


def _default_admin_base():
    configured = (getattr(Config, "ADMIN_PUBLIC_URL", "") or "").strip().rstrip("/")
    if configured:
        return configured
    return f"http://127.0.0.1:{getattr(Config, 'ADMIN_PORT', 5003)}"


def _forward_to_admin(path):
    base = _default_admin_base()
    target = f"{base}{path}"
    query = (request.query_string or b"").decode("utf-8", errors="ignore")
    if query:
        target = f"{target}?{query}"
    return redirect(target)


def enforce_portal_access():
    path = request.path or "/"
    mode = current_portal_mode()

    if mode == "all":
        return None

    expected_host = _host_guard_for_mode(mode)
    if expected_host and not _host_matches(expected_host):
        abort(404)

    if _matches_prefix(path, ALWAYS_ALLOWED_PREFIXES):
        return None

    if mode == "player":
        if _matches_prefix(path, ("/login", "/logout", "/admin", "/download-center")):
            return _forward_to_admin(path)
        if _matches_prefix(path, ADMIN_PREFIXES) or _matches_prefix(path, FORUM_PREFIXES):
            abort(404)
        return None

    if mode == "forum":
        if _matches_prefix(path, ("/login", "/logout", "/admin", "/download-center")):
            return _forward_to_admin(path)
        if path == "/":
            return redirect("/forum")
        if not _matches_prefix(path, FORUM_PREFIXES):
            abort(404)
        return None

    if mode == "admin":
        if path == "/":
            return None
        if _matches_prefix(path, PLAYER_SITE_PREFIXES) or _matches_prefix(path, FORUM_PREFIXES):
            if not _matches_prefix(path, ADMIN_PREFIXES):
                abort(404)
        return None

    return None

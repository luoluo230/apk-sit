# -*- coding: utf-8 -*-
"""Unified HMAC verification for internal and inbound webhooks. Plan: P0-01 Step 3."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import re
import time
from typing import Iterable, Optional, Set, Tuple

from flask import Request, request

from config import Config

_SIGNATURE_RE = re.compile(r"^t=(\d+),v1=([0-9a-fA-F]+)$")
_DEFAULT_MAX_SKEW_SECONDS = 300


def webhook_auth_disabled() -> bool:
    """Dev-only escape hatch. Must not be documented for production."""
    if Config.is_production():
        return False
    return str(os.getenv("WEBHOOK_AUTH_DISABLED") or "").strip().lower() in {"1", "true", "yes"}


def resolve_webhook_secret(*env_names: str) -> str:
    """Read webhook secret from env. Production never falls back to session secret."""
    for name in env_names:
        value = str(os.getenv(name) or "").strip()
        if value:
            return value
    if Config.is_production():
        return ""
    return str(Config.get_secret_key() or "").strip()


def parse_allowed_ips(raw: Optional[str] = None) -> Set[str]:
    text = str(raw if raw is not None else os.getenv("INTERNAL_WEBHOOK_IPS") or "127.0.0.1,::1").strip()
    items = [part.strip() for part in text.split(",") if part.strip()]
    return set(items or {"127.0.0.1", "::1"})


def _normalize_ip(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("::ffff:"):
        raw = raw.split(":", 2)[-1]
    return raw


def client_ip(req: Request) -> str:
    forwarded = str(req.headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        return _normalize_ip(forwarded.split(",")[0])
    return _normalize_ip(req.remote_addr or "")


def ip_allowed(req: Request, allowed: Optional[Iterable[str]] = None) -> bool:
    allowed_set = set(allowed) if allowed is not None else parse_allowed_ips()
    ip = client_ip(req)
    if not ip:
        return False
    if ip in allowed_set:
        return True
    try:
        addr = ipaddress.ip_address(ip)
        for item in allowed_set:
            if not item:
                continue
            if "/" in item:
                if addr in ipaddress.ip_network(item, strict=False):
                    return True
            else:
                if addr == ipaddress.ip_address(_normalize_ip(item)):
                    return True
    except ValueError:
        return False
    return False


def sign_webhook_body(body: bytes, secret: str, timestamp: Optional[int] = None) -> Tuple[str, str]:
    """Return (signature_header, timestamp_str) using t=...,v1=... format."""
    ts = int(timestamp if timestamp is not None else time.time())
    payload = f"{ts}.".encode("utf-8") + (body or b"")
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    header = f"t={ts},v1={digest}"
    return header, str(ts)


def verify_hmac_signature(
    body: bytes,
    signature_header: str,
    secret: str,
    *,
    max_skew_seconds: int = _DEFAULT_MAX_SKEW_SECONDS,
) -> bool:
    """Verify timestamped or legacy hex / sha256= signatures."""
    secret = str(secret or "").strip()
    if not secret:
        return False

    header = str(signature_header or "").strip()
    if not header:
        return False

    match = _SIGNATURE_RE.match(header)
    if match:
        ts_raw, supplied = match.group(1), match.group(2)
        try:
            ts = int(ts_raw)
        except ValueError:
            return False
        if abs(int(time.time()) - ts) > max_skew_seconds:
            return False
        payload = f"{ts}.".encode("utf-8") + (body or b"")
        expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected.lower(), supplied.lower())

    sig = header
    if sig.lower().startswith("sha256="):
        sig = sig.split("=", 1)[1].strip()
    expected = hmac.new(secret.encode("utf-8"), body or b"", hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.lower(), sig.lower())


def assert_internal_webhook_request(
    req: Request,
    body: bytes,
    signature_header: str,
    *secret_env_names: str,
) -> Optional[str]:
    """
    Validate IP allowlist + HMAC for internal webhook routes.
    Returns None when OK, otherwise an error code string.
    """
    if webhook_auth_disabled():
        return None
    if not ip_allowed(req):
        return "client_ip_not_allowed"
    secret = resolve_webhook_secret(*secret_env_names)
    if not secret:
        return "webhook_secret_not_configured"
    if not verify_hmac_signature(body, signature_header, secret):
        return "invalid_signature"
    return None

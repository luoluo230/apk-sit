# -*- coding: utf-8 -*-
"""安全加固。"""

from config import Config


def is_https_expected():
    base = Config.get_public_base_url()
    return bool(base and base.lower().startswith('https://'))


def apply_security_headers(response):
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-XSS-Protection', '1; mode=block')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('X-Permitted-Cross-Domain-Policies', 'none')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    response.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: https:; img-src 'self' data: blob: https:; frame-ancestors 'self'; object-src 'none'; base-uri 'self'"
    )
    if is_https_expected():
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return response


def configure_session_cookies(app):
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_PATH'] = '/'
    if is_https_expected():
        app.config['SESSION_COOKIE_SECURE'] = True

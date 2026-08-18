# -*- coding: utf-8 -*-
"""Standalone BaaS Portal — no topology / ops / jenkins dependencies."""

from __future__ import annotations

import os

from flask import Flask, jsonify, redirect, render_template, request, session

from config import Config, load_dotenv
from utils import setup_logging

load_dotenv()
logger = setup_logging()


def create_baas_app() -> Flask:
    os.environ.setdefault("BAAS_STANDALONE", "1")
    os.environ.setdefault("PORTAL_SERVER_FRAMEWORKS", "baas")
    os.environ.setdefault("APP_PORTAL_MODE", "admin")

    app = Flask(__name__)
    app.secret_key = Config.get_secret_key()
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

    csrf = None
    try:
        from flask_wtf.csrf import CSRFProtect

        app.config["WTF_CSRF_ENABLED"] = True
        csrf = CSRFProtect(app)
    except ImportError:
        pass

    from services.security import apply_security_headers, configure_session_cookies

    configure_session_cookies(app)

    @app.after_request
    def _headers(resp):
        return apply_security_headers(resp)

    @app.route("/health")
    def health():
        from models.db import init_db

        init_db()
        return jsonify({"ok": True, "service": "casual_baas_standalone", "framework": "casual_baas"})

    from routes.auth import bp as auth_bp

    app.register_blueprint(auth_bp)

    from routes.baas.public_api import baas_public_bp
    from routes.baas.standalone_shell import bp as baas_shell_bp

    app.register_blueprint(baas_public_bp)
    app.register_blueprint(baas_shell_bp)

    if csrf is not None:
        csrf.exempt(baas_public_bp)

    @app.route("/")
    def root():
        if session.get("user"):
            return redirect("/admin/baas")
        return redirect("/login")

    logger.info("BaaS standalone app ready (topology modules disabled)")
    return app

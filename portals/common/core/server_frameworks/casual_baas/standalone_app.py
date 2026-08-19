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

    _core_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    app = Flask(
        __name__,
        template_folder=os.path.join(_core_dir, "templates"),
        static_folder=os.path.join(_core_dir, "static"),
    )
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

    @app.before_request
    def _monitor_start():
        from services.monitor import record_request_start

        request._baas_monitor_start = record_request_start()  # type: ignore[attr-defined]

    @app.after_request
    def _monitor_end(resp):
        from services.monitor import record_request_end

        start = getattr(request, "_baas_monitor_start", None)
        if start is not None:
            record_request_end(request.path, start, resp.status_code)
        return apply_security_headers(resp)

    @app.route("/health")
    def health():
        from models.db import init_db

        init_db()
        return jsonify({"ok": True, "service": "casual_baas_standalone", "framework": "casual_baas"})

    @app.route("/health/detailed")
    def health_detailed():
        from models.db import get_cursor, init_db

        init_db()
        db_ok = False
        tables = 0
        try:
            with get_cursor() as cur:
                row = cur.execute(
                    "SELECT COUNT(*) AS cnt FROM sqlite_master WHERE type='table' AND name LIKE 'baas_%'"
                ).fetchone()
                tables = int(row["cnt"] or 0) if row else 0
                db_ok = tables > 0
        except Exception as exc:
            return jsonify({"ok": False, "service": "casual_baas_standalone", "db_error": str(exc)}), 503
        return jsonify({
            "ok": db_ok,
            "service": "casual_baas_standalone",
            "framework": "casual_baas",
            "database": {"ok": db_ok, "baas_tables": tables},
            "standalone": True,
        })

    @app.route("/metrics")
    def metrics():
        from services.monitor import get_stats

        stats = get_stats()
        lines = [
            "# HELP baas_http_requests_total In-process sampled HTTP requests.",
            "# TYPE baas_http_requests_total gauge",
            f"baas_http_requests_total {stats.get('count', 0)}",
            "# HELP baas_http_request_p95_ms P95 latency ms (sampled).",
            "# TYPE baas_http_request_p95_ms gauge",
            f"baas_http_request_p95_ms {stats.get('p95_ms', 0)}",
            "# HELP baas_http_request_avg_ms Average latency ms (sampled).",
            "# TYPE baas_http_request_avg_ms gauge",
            f"baas_http_request_avg_ms {stats.get('avg_ms', 0)}",
        ]
        from flask import Response

        return Response("\n".join(lines) + "\n", mimetype="text/plain; version=0.0.4")

    from routes.auth import bp as auth_bp

    app.register_blueprint(auth_bp)

    from routes.baas.public_api import baas_public_bp
    from routes.baas.standalone_shell import bp as baas_shell_bp

    app.register_blueprint(baas_public_bp)
    app.register_blueprint(baas_shell_bp)

    if csrf is not None:
        csrf.exempt(baas_public_bp)
        csrf.exempt(auth_bp)

    @app.route("/")
    def root():
        if session.get("user"):
            return redirect("/admin/baas")
        return redirect("/login")

    logger.info("BaaS standalone app ready (topology modules disabled)")
    return app

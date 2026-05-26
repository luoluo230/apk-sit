#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Application bootstrap and portal-mode composition."""

import os
import sys
import threading
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config, load_dotenv
from utils import setup_logging

load_dotenv()
logger = setup_logging()

from flask import Flask, jsonify, redirect, request, session

from services.monitor import record_request_end, record_request_start
from services.portal import current_portal_mode, enforce_portal_access
from services.security import apply_security_headers, configure_session_cookies

app = Flask(__name__)
app.secret_key = Config.get_secret_key()
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

try:
    from flask_wtf.csrf import CSRFProtect

    app.config["WTF_CSRF_ENABLED"] = True
    app.config["WTF_CSRF_CHECK_DEFAULT"] = True
    app.config["WTF_CSRF_SSL_STRICT"] = False
    app.config["WTF_CSRF_TIME_LIMIT"] = None
    csrf = CSRFProtect(app)
    _csrf_enabled = True
except ImportError:
    csrf = None
    _csrf_enabled = False

configure_session_cookies(app)


@app.after_request
def _security_headers(response):
    return apply_security_headers(response)


@app.before_request
def _request_id():
    from flask import g

    g.request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:12]


@app.before_request
def _monitor_start():
    from flask import g

    g._request_start = record_request_start()


@app.before_request
def _portal_guard():
    return enforce_portal_access()


@app.after_request
def _monitor_end(response):
    from flask import g

    if hasattr(g, "request_id"):
        response.headers["X-Request-ID"] = g.request_id
    if hasattr(g, "_request_start"):
        duration = record_request_end(request.path, g._request_start, response.status_code)
        if getattr(Config, "USE_SQLITE", False):
            try:
                from models.db import record_request_event

                record_request_event(
                    g.request_id,
                    request.path,
                    request.method,
                    response.status_code,
                    duration * 1000,
                )
            except Exception:
                logger.debug("request event persistence skipped", exc_info=True)

    # Keep cross-portal links usable after split deployment.
    mode = current_portal_mode()
    content_type = (response.headers.get("Content-Type") or "").lower()
    # Prevent stale admin pages after hot updates.
    if request.path.startswith('/admin') or request.path in ('/login', '/logout'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

    if response.status_code == 200 and "text/html" in content_type and mode in ("player", "forum"):
        try:
            html_text = response.get_data(as_text=True)
            admin_base = (getattr(Config, "ADMIN_PUBLIC_URL", "") or "").strip().rstrip("/")
            player_base = (getattr(Config, "PLAYER_PUBLIC_URL", "") or "").strip().rstrip("/")
            forum_base = (getattr(Config, "FORUM_PUBLIC_URL", "") or "").strip().rstrip("/")
            if not admin_base:
                admin_base = f"http://127.0.0.1:{getattr(Config, 'ADMIN_PORT', 5003)}"
            if not player_base:
                player_base = f"http://127.0.0.1:{getattr(Config, 'PLAYER_PORT', 5004)}"
            if not forum_base:
                forum_base = f"http://127.0.0.1:{getattr(Config, 'FORUM_PORT', 5005)}"

            replacements = {
                'href="/login"': f'href="{admin_base}/login"',
                'href="/logout"': f'href="{admin_base}/logout"',
                'href="/admin"': f'href="{admin_base}/admin"',
                'href="/download-center"': f'href="{admin_base}/download-center"',
            }
            if mode == "player":
                replacements.update(
                    {
                        'href="/forum"': f'href="{forum_base}/forum"',
                        'href="/forum/': f'href="{forum_base}/forum/',
                    }
                )
            if mode == "forum":
                replacements.update(
                    {
                        'href="/about/company"': f'href="{player_base}/about/company"',
                        'href="/news"': 'href="/news"',
                        'href="/welfare"': 'href="/welfare"',
                    }
                )

            for source, target in replacements.items():
                html_text = html_text.replace(source, target)
            response.set_data(html_text)
        except Exception:
            logger.debug("split link rewrite skipped", exc_info=True)
    return response


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "apk-site"}), 200


def _register_blueprints():
    """Register only required modules for each deployment target."""
    mode = current_portal_mode()

    from services.authz import admin_required, is_admin, login_required

    app.login_required = login_required
    app.admin_required = admin_required
    app.is_admin = is_admin

    if mode == "player":
        from routes.player_community import bp as player_community_bp
        from routes.products_public import bp as products_public_bp

        app.register_blueprint(products_public_bp)
        app.register_blueprint(player_community_bp)

    if mode == "forum":
        from routes.player_community import bp as player_community_bp

        app.register_blueprint(player_community_bp)

    if mode in ("all", "admin"):
        from routes.admin_products import bp as admin_products_bp
        from routes.admin_routes import bp as admin_routes_bp
        from routes.api import bp as api_bp
        from routes.auth import bp as auth_bp
        from routes.build_routes import bp as build_routes_bp
        from routes.dashboard_routes import bp as dashboard_routes_bp
        from routes.docs_routes import bp as docs_bp
        from routes.download import bp as download_bp
        from routes.home import bp as home_bp
        from routes.jenkins_manage_routes import bp as jenkins_manage_bp
        from routes.versions_routes import bp as versions_routes_bp
        from routes.workspace_routes import bp as workspace_bp
        from routes.gm_ops import bp as gm_ops_bp
        from routes.gm_legacy import bp as gm_legacy_bp
        from routes.commercial_release_routes import bp as commercial_release_bp
        if mode == "all":
            from routes.player_community import bp as player_community_bp
            from routes.products_public import bp as products_public_bp

            app.register_blueprint(products_public_bp)
            app.register_blueprint(player_community_bp)
        elif mode == "admin":
            from routes.player_community import bp as player_community_bp

            app.register_blueprint(player_community_bp)
        app.register_blueprint(auth_bp)
        app.register_blueprint(home_bp)
        app.register_blueprint(download_bp)
        app.register_blueprint(api_bp)
        app.register_blueprint(workspace_bp)
        app.register_blueprint(docs_bp)
        app.register_blueprint(admin_routes_bp)
        app.register_blueprint(admin_products_bp)
        app.register_blueprint(build_routes_bp)
        app.register_blueprint(dashboard_routes_bp)
        app.register_blueprint(versions_routes_bp)
        app.register_blueprint(jenkins_manage_bp)
        app.register_blueprint(gm_ops_bp)
        app.register_blueprint(gm_legacy_bp)
        app.register_blueprint(commercial_release_bp)
        if _csrf_enabled and csrf is not None:
            # Ops/Gm legacy frontend uses JSON fetch API; exempt this blueprint to avoid CSRF 400 on internal ops calls.
            csrf.exempt(gm_legacy_bp)


_register_blueprints()


if current_portal_mode() in ("admin", "forum"):

    @app.route("/")
    def portal_index():
        if current_portal_mode() == "forum":
            return redirect("/forum")
        if session.get("user"):
            return redirect("/admin")
        return redirect("/login")


ERROR_404_HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>404</title><link rel="stylesheet" href="/static/tailwind.css"></head><body class="min-h-screen flex items-center justify-center bg-slate-50"><div class="text-center"><h1 class="text-2xl font-bold text-slate-800">页面不存在</h1><p class="mt-2 text-slate-500">请检查访问地址。</p><a href="/" class="inline-flex mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-white">返回首页</a></div></body></html>"""
ERROR_500_HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>500</title><link rel="stylesheet" href="/static/tailwind.css"></head><body class="min-h-screen flex items-center justify-center bg-slate-50"><div class="text-center"><h1 class="text-2xl font-bold text-slate-800">服务异常</h1><p class="mt-2 text-slate-500">请稍后重试。</p><a href="/" class="inline-flex mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-white">返回首页</a></div></body></html>"""
ERROR_403_HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>403</title><link rel="stylesheet" href="/static/tailwind.css"></head><body class="min-h-screen flex items-center justify-center bg-slate-50"><div class="text-center"><h1 class="text-2xl font-bold text-slate-800">无权限访问</h1><p class="mt-2 text-slate-500">请先登录或联系管理员。</p><a href="/login" class="inline-flex mt-4 rounded-lg bg-indigo-600 px-4 py-2 text-white">去登录</a></div></body></html>"""


@app.errorhandler(404)
def not_found(_error):
    return ERROR_404_HTML, 404


@app.errorhandler(500)
def internal_error(_error):
    try:
        logger.error("Internal 500 on %s %s", request.method, request.path, exc_info=True)
        logger.error("500 error object: %r", _error)
    except Exception:
        pass
    return ERROR_500_HTML, 500


@app.errorhandler(403)
def forbidden(_error):
    return ERROR_403_HTML, 403


def _startup_checks():
    from config import DATA_DIR

    log_dir = Config.LOG_DIR
    if not os.path.isdir(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
        logger.info("created data dir: %s", DATA_DIR)
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)
        logger.info("created log dir: %s", log_dir)
    test_file = os.path.join(log_dir, ".write_test")
    try:
        with open(test_file, "w", encoding="utf-8") as fp:
            fp.write("1")
        os.remove(test_file)
    except OSError as exc:
        logger.warning("log dir is not writable %s: %s", log_dir, exc)


def _on_start():
    from services import startup

    if getattr(Config, "USE_SQLITE", False):
        try:
            from models.db import init_db

            init_db()
        except Exception:
            logger.warning("SQLite init failed", exc_info=True)

    _startup_checks()
    base_url = startup.write_base_url_file()
    startup.write_jenkins_clone_env()
    startup.apply_jenkins_clone_overlay()

    enable_download_service = str(os.getenv("ENABLE_DOWNLOAD_FILE_SERVICE", "true")).lower() in ("true", "1", "yes")
    enable_scheduler = str(os.getenv("ENABLE_BACKGROUND_SCHEDULER", "true")).lower() in ("true", "1", "yes")

    if enable_download_service:
        startup.start_download_service()
    try:
        if enable_scheduler:
            t = threading.Thread(target=startup.run_background_scheduler, daemon=True)
            t.start()
    except Exception as exc:
        logger.warning("background scheduler not started: %s", exc)

    local_ip = startup.get_lan_ip()
    pub_url = f"{base_url}/pub/download/xxx.apk"
    public_base = Config.get_public_base_url()
    https_hint = ""
    if public_base and public_base.lower().startswith("https://"):
        https_hint = "\n[HTTPS enabled] Make sure Nginx/Caddy reverse proxy is configured."
    startup_banner = (
        "\n"
        "========================================\n"
        " APK Download Center started\n"
        f" Mode:    {current_portal_mode()}\n"
        f" Local:   http://localhost:{Config.PORT}\n"
        f" LAN:     http://{local_ip}:{Config.PORT}\n"
        f" Public:  {public_base or 'PUBLIC_URL not configured'}\n"
        f" Sample:  {pub_url}\n"
        f" APK dir: {Config.APK_DIR}\n"
        f" Jenkins: {Config.JENKINS_URL}\n"
        f" Health:  /health | admin/admin123{https_hint}\n"
        "========================================"
    )
    try:
        print(startup_banner)
    except Exception:
        pass
    logger.info("APK site started")


def _runtime_entrypoint_signature():
    return {
        "portal_mode": os.getenv("APP_PORTAL_MODE", ""),
        "entrypoint": os.getenv("RUNTIME_ENTRYPOINT", ""),
        "entry_version": os.getenv("RUNTIME_ENTRY_VERSION", ""),
        "apk_port": os.getenv("APK_PORT", ""),
    }


@app.route("/internal/runtime/entrypoint")
def runtime_entrypoint():
    user = session.get("user")
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    if hasattr(app, "is_admin") and not app.is_admin():
        return jsonify({"error": "forbidden"}), 403
    payload = _runtime_entrypoint_signature()
    payload["runtime_route_map"] = {
        "admin": "/admin",
        "project_workspace": "/admin/projects/{id}",
        "gm_ops": "/admin/gm-ops",
        "gm_center": "/admin/gm-center",
        "ops_center": "/admin/ops-center",
        "gm_classic": "/admin/gm-classic",
        "ops_platform": "/admin/ops-platform",
    }
    return jsonify(payload), 200


if __name__ == "__main__":
    _on_start()
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end delivery audit for database scope, media scope, routes, and split bundles."""

import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DB_PATH = ROOT / "data" / "apk_site.db"
RELEASE_ROOT = ROOT / "release_bundles"

PROJECT_SCOPED_DOCS = [
    "data/products.json",
    "data/player_news.json",
    "data/player_welfare.json",
    "data/forum_posts.json",
    "data/approvals.json",
    "data/report_templates.json",
    "data/export_records.json",
    "data/documents.json",
]


def _load_doc(cur, key):
    row = cur.execute("SELECT payload FROM json_documents WHERE document_key=?", (key,)).fetchone()
    if not row:
        return None
    return json.loads(row[0])


def _is_bad_media_url(value):
    text = str(value or "").strip()
    if not text:
        return False
    if text.startswith("/uploaded-media/") or text.startswith("/product-media/") or text.startswith("/static/"):
        return False
    if text.startswith("http://") or text.startswith("https://"):
        return True
    if text.startswith("/"):
        return True
    return False


def _walk_media(obj, out, path=""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{path}.{key}" if path else key
            if key in {"video_url", "image_url", "cover_image", "hero_image", "image", "video"}:
                if _is_bad_media_url(value):
                    out.append((child, value))
            if key in {"media_urls", "gallery", "images"} and isinstance(value, list):
                for idx, item in enumerate(value):
                    if _is_bad_media_url(item):
                        out.append((f"{child}[{idx}]", item))
            _walk_media(value, out, child)
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            _walk_media(item, out, f"{path}[{idx}]")


def _check_data_dir():
    data_dir = ROOT / "data"
    json_files = sorted([p.name for p in data_dir.glob("*.json")])
    allowed_files = {"apk_site.db", "secret.key"}
    files = sorted([p.name for p in data_dir.iterdir() if p.is_file()])
    return {
        "ok": len(json_files) == 0 and set(files).issubset(allowed_files),
        "json_files": json_files,
        "files": files,
    }


def _check_db_docs():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    result = {"ok": True, "missing_docs": [], "missing_project_ids": {}, "bad_media": []}

    for key in PROJECT_SCOPED_DOCS:
        doc = _load_doc(cur, key)
        if doc is None:
            result["ok"] = False
            result["missing_docs"].append(key)
            continue
        if isinstance(doc, list):
            missing = sum(1 for item in doc if isinstance(item, dict) and not str(item.get("project_id") or "").strip())
            if missing:
                result["ok"] = False
                result["missing_project_ids"][key] = missing
        else:
            result["ok"] = False
            result["missing_project_ids"][key] = "not_list"

    for key in [
        "data/player_news.json",
        "data/player_welfare.json",
        "data/forum_posts.json",
        "data/products.json",
        "data/player_portal_content.json",
        "data/developer_portal_content.json",
        "data/company_profile.json",
    ]:
        doc = _load_doc(cur, key)
        if doc is None:
            continue
        bad = []
        _walk_media(doc, bad)
        if bad:
            result["ok"] = False
            result["bad_media"].append({"doc": key, "count": len(bad), "sample": bad[:5]})

    junk = cur.execute("SELECT COUNT(*) FROM json_documents WHERE document_key LIKE 'data/._%'").fetchone()[0]
    if junk:
        result["ok"] = False
        result["junk_docs"] = junk
    conn.close()
    return result


def _check_routes():
    import importlib

    checks = {"ok": True, "items": []}

    def reset_modules():
        prefixes = ("app_new", "routes.", "services.", "admin_wsgi", "player_wsgi", "forum_wsgi")
        for name in list(sys.modules.keys()):
            if name in prefixes or name.startswith("routes.") or name.startswith("services."):
                sys.modules.pop(name, None)

    def run_mode(mode, import_name, paths, with_login=False):
        reset_modules()
        os.environ["APP_PORTAL_MODE"] = mode
        mod = importlib.import_module(import_name)
        app = mod.app
        with app.test_client() as client:
            if with_login:
                with client.session_transaction() as sess:
                    sess["user"] = "admin"
            for path, expected in paths:
                resp = client.get(path, follow_redirects=False)
                ok = resp.status_code == expected
                checks["items"].append({"mode": mode, "path": path, "status": resp.status_code, "expected": expected, "ok": ok})
                if not ok:
                    checks["ok"] = False
        return app

    run_mode(
        "admin",
        "admin_wsgi",
        [
            ("/admin", 200),
            ("/download-center", 200),
            ("/admin/projects", 200),
            ("/admin/versions", 200),
            ("/admin/community", 200),
            ("/admin/approval", 200),
            ("/admin/reports", 200),
            ("/admin/products/new", 200),
            ("/admin/site-config", 200),
            ("/health", 200),
        ],
        with_login=True,
    )

    player_app = run_mode(
        "player",
        "player_wsgi",
        [
            ("/", 200),
            ("/products", 302),
            ("/about/company", 200),
            ("/news", 200),
            ("/welfare", 200),
            ("/health", 200),
        ],
        with_login=False,
    )

    # Dynamic product detail checks (both /product and /products alias).
    try:
        from models.data import products_db

        if isinstance(products_db, list):
            first = next((item for item in products_db if isinstance(item, dict) and str(item.get("id") or "").strip()), None)
            if first:
                pid = str(first.get("id") or "").strip()
                with player_app.test_client() as client:
                    for route_path in (f"/product/{pid}", f"/products/{pid}"):
                        resp = client.get(route_path, follow_redirects=False)
                        ok = resp.status_code == 200
                        checks["items"].append(
                            {"mode": "player", "path": route_path, "status": resp.status_code, "expected": 200, "ok": ok}
                        )
                        if not ok:
                            checks["ok"] = False
    except Exception:
        checks["ok"] = False
        checks["items"].append(
            {"mode": "player", "path": "/product/<dynamic>", "status": "error", "expected": 200, "ok": False}
        )
    run_mode(
        "forum",
        "forum_wsgi",
        [
            ("/forum", 200),
            ("/forum/welcome-thread", 200),
            ("/health", 200),
        ],
        with_login=False,
    )
    return checks


def _check_release_bundles():
    expected = {
        "admin-backend": ["start_admin.bat", "start_admin.ps1", "README.md", "admin_wsgi.py", "app_new.py"],
        "forum-backend": ["start_forum.bat", "start_forum.ps1", "README.md", "forum_wsgi.py", "app_new.py"],
        "player-static": ["README.md", "serve_static.ps1", "serve_static.bat"],
    }
    result = {"ok": True, "missing": []}
    for bundle, files in expected.items():
        base = RELEASE_ROOT / bundle
        if not base.exists():
            result["ok"] = False
            result["missing"].append(str(base))
            continue
        for name in files:
            target = base / name
            if not target.exists():
                result["ok"] = False
                result["missing"].append(str(target))
    static_index = RELEASE_ROOT / "player-static" / "www" / "index.html"
    if not static_index.exists():
        result["ok"] = False
        result["missing"].append(str(static_index))
    return result


def _check_brand_sync():
    import importlib

    result = {"ok": True, "items": []}
    os.environ["APP_PORTAL_MODE"] = "all"

    for name in list(sys.modules.keys()):
        if name in {"app_new", "admin_wsgi", "player_wsgi", "forum_wsgi"} or name.startswith("routes.") or name.startswith(
            "services."
        ):
            sys.modules.pop(name, None)

    mod = importlib.import_module("app_new")
    app = mod.app

    from services.company_profile import get_company_profile, save_company_profile
    from services.portal_content import (
        get_dev_portal_content,
        get_player_portal_content,
        save_dev_portal_content,
        save_player_portal_content,
    )

    old_company = get_company_profile()
    old_player = get_player_portal_content()
    old_dev = get_dev_portal_content()

    old_name = str(old_company.get("company_name") or "").strip() or "星云游戏站"
    probe_name = "BrandSyncAuditCo"

    try:
        # Force portals to follow current company name, then verify brand propagation.
        save_player_portal_content({"site_name": old_name})
        save_dev_portal_content({"site_name": old_name})

        new_company = dict(old_company)
        new_company["company_name"] = probe_name
        save_company_profile(new_company)

        player_site = str(get_player_portal_content().get("site_name") or "").strip()
        dev_site = str(get_dev_portal_content().get("site_name") or "").strip()
        player_ok = player_site == probe_name
        dev_ok = dev_site == probe_name
        result["items"].append(
            {
                "check": "portal_site_name_sync",
                "player_site_name": player_site,
                "dev_site_name": dev_site,
                "expected": probe_name,
                "ok": player_ok and dev_ok,
            }
        )
        if not (player_ok and dev_ok):
            result["ok"] = False

        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user"] = "admin"
            for path in ("/login", "/", "/about/company"):
                resp = client.get(path, follow_redirects=False)
                body = resp.get_data(as_text=True)
                ok = resp.status_code == 200 and probe_name in body
                result["items"].append(
                    {
                        "check": "brand_render",
                        "path": path,
                        "status": resp.status_code,
                        "expected_status": 200,
                        "contains_probe_name": probe_name in body,
                        "ok": ok,
                    }
                )
                if not ok:
                    result["ok"] = False
    finally:
        try:
            save_company_profile(old_company)
        finally:
            save_player_portal_content(old_player)
            save_dev_portal_content(old_dev)

    return result


def main():
    checks = {
        "data_dir": _check_data_dir(),
        "db_docs": _check_db_docs(),
        "routes": _check_routes(),
        "release_bundles": _check_release_bundles(),
        "brand_sync": _check_brand_sync(),
    }
    overall_ok = all(item.get("ok") for item in checks.values())
    print(json.dumps({"ok": overall_ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

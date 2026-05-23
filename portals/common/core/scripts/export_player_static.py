#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export player-facing pages as a static bundle for OSS+CDN deployment."""

import argparse
import importlib
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _reset_app_module():
    for name in list(sys.modules.keys()):
        if name == "app_new" or name.startswith("routes.") or name.startswith("services."):
            sys.modules.pop(name, None)


def _load_player_app(player_base="", forum_base="", admin_base=""):
    os.environ["APP_PORTAL_MODE"] = "player"
    if player_base:
        os.environ["PLAYER_PUBLIC_URL"] = player_base.rstrip("/")
    if forum_base:
        os.environ["FORUM_PUBLIC_URL"] = forum_base.rstrip("/")
    if admin_base:
        os.environ["ADMIN_PUBLIC_URL"] = admin_base.rstrip("/")
    os.environ.setdefault("USE_SQLITE", "true")
    _reset_app_module()
    app_mod = importlib.import_module("app_new")
    app = app_mod.app
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    return app


def _copytree(src: Path, dst: Path):
    if not src.exists():
        return
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _path_to_output(path: str) -> Path:
    normalized = str(path or "/").split("?", 1)[0].strip()
    if not normalized or normalized == "/":
        return Path("index.html")
    normalized = normalized.lstrip("/")
    return Path(normalized) / "index.html"


def _write_html(root: Path, route_path: str, body: bytes):
    target = root / _path_to_output(route_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)


def _collect_routes():
    from models.data import products_db

    routes = ["/", "/about/company", "/news", "/welfare"]
    for product in products_db if isinstance(products_db, list) else []:
        product_id = str((product or {}).get("id") or "").strip()
        if product_id:
            routes.append(f"/product/{product_id}")
    deduped = []
    seen = set()
    for route in routes:
        if route in seen:
            continue
        seen.add(route)
        deduped.append(route)
    return deduped


def main():
    parser = argparse.ArgumentParser(description="Export player portal as static HTML")
    parser.add_argument("--out", default=str(ROOT / "dist" / "player-static"), help="output directory")
    parser.add_argument("--player-base", default="", help="public player base URL (optional)")
    parser.add_argument("--forum-base", default="", help="public forum base URL (optional)")
    parser.add_argument("--admin-base", default="", help="public admin base URL (optional)")
    args = parser.parse_args()

    out_dir = Path(args.out).resolve()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    app = _load_player_app(
        player_base=args.player_base,
        forum_base=args.forum_base,
        admin_base=args.admin_base,
    )
    client = app.test_client()

    exported = 0
    for route in _collect_routes():
        response = client.get(route)
        if response.status_code != 200:
            print(f"[WARN] skip {route} -> {response.status_code}")
            continue
        _write_html(out_dir, route, response.data)
        exported += 1
        print(f"[OK] {route}")

    _copytree(ROOT / "static", out_dir / "static")
    _copytree(ROOT / "data" / "uploaded_media", out_dir / "uploaded-media")
    _copytree(ROOT / "data" / "product_media", out_dir / "product-media")

    print(f"[DONE] exported pages={exported} output={out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


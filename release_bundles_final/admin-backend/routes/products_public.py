# -*- coding: utf-8 -*-
"""Public-facing brand, company, and product pages."""

import html
import os
from urllib.parse import quote

from flask import Blueprint, abort, redirect, render_template, request, send_file, session
from werkzeug.utils import secure_filename

from config import Config
from models.data import (
    PRODUCT_MEDIA_DIR,
    can_view_project,
    extract_package_info,
    extract_project_name,
    get_project_portal_urls,
    get_project_record,
    iter_package_files,
    products_db,
    resolve_project_id,
    resolve_project_id_for_product,
)
from services.company_profile import get_company_profile
from services.media_library import normalize_local_media_url, normalize_local_media_urls
from services.player_content import get_active_welfare, get_forum_posts, get_latest_news
from services.portal import current_portal_mode
from services.portal_content import (
    DEFAULT_DEV_PORTAL,
    DEFAULT_PLAYER_PORTAL,
    get_dev_portal_content,
    get_player_portal_content,
)

bp = Blueprint("products_public", __name__)


def _product_media_base():
    media_dir = PRODUCT_MEDIA_DIR
    if not os.path.isabs(media_dir):
        media_dir = os.path.normpath(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), media_dir)
        )
    os.makedirs(media_dir, exist_ok=True)
    return media_dir


def _portal_links(project_id=""):
    mode = current_portal_mode()
    project_urls = get_project_portal_urls(project_id)
    player_base = (project_urls.get("player_public_url") or "").strip().rstrip("/")
    forum_base = (project_urls.get("forum_public_url") or "").strip().rstrip("/")
    admin_base = (project_urls.get("admin_public_url") or "").strip().rstrip("/")

    if not player_base and mode not in ("player", "all"):
        player_base = f"http://127.0.0.1:{getattr(Config, 'PLAYER_PORT', 5004)}"
    if not admin_base and mode not in ("admin", "all"):
        admin_base = f"http://127.0.0.1:{getattr(Config, 'ADMIN_PORT', 5003)}"
    if not forum_base and mode not in ("forum", "all"):
        forum_base = f"http://127.0.0.1:{getattr(Config, 'FORUM_PORT', 5005)}"

    def _join(base, path):
        return (base + path) if base else path

    forum_entry_base = forum_base or player_base

    return {
        "home_url": _join(player_base, "/"),
        "company_url": _join(player_base, "/about/company"),
        "news_url": _join(player_base, "/news"),
        "welfare_url": _join(player_base, "/welfare"),
        "forum_entry_url": _join(forum_entry_base, "/forum"),
        "admin_entry_url": _join(admin_base, "/admin"),
        "login_url": _join(admin_base, "/login"),
        "logout_url": _join(admin_base, "/logout"),
        "download_center_url": _join(admin_base, "/download-center"),
    }


def _clean_text(value, fallback=""):
    text = str(value or "").strip()
    if not text:
        return fallback
    noisy = ("??", "?", "?", "?", "?", "?", "?")
    if any(marker in text for marker in noisy) and sum(ord(ch) > 127 for ch in text) > len(text) // 3:
        return fallback
    return text


def _parse_id_list(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _filter_products_by_ids(products, ids):
    if not ids:
        return list(products)
    id_order = {pid: idx for idx, pid in enumerate(ids)}
    filtered = [item for item in products if item.get("id") in id_order]
    filtered.sort(key=lambda item: id_order.get(item.get("id"), 9999))
    return filtered


def _module_flags(portal_content, defaults):
    modules = portal_content.get("home_modules") if isinstance(portal_content, dict) else None
    if not isinstance(modules, list) or not modules:
        modules = list(defaults) if isinstance(defaults, list) else []
    enabled = []
    for item in modules:
        if isinstance(item, dict):
            if item.get("enabled") is False:
                continue
            key = (item.get("type") or item.get("id") or "").strip()
            if key:
                enabled.append(key)
        else:
            key = str(item).strip()
            if key:
                enabled.append(key)
    default_names = []
    for item in defaults or []:
        if isinstance(item, dict):
            key = (item.get("type") or item.get("id") or "").strip()
        else:
            key = str(item).strip()
        if key:
            default_names.append(key)
    flags = {name: False for name in default_names}
    for name in enabled:
        flags[name] = True
    return flags


def _normalize_modules(portal_content, defaults):
    modules = portal_content.get("home_modules") if isinstance(portal_content, dict) else None
    if not isinstance(modules, list) or not modules:
        modules = list(defaults)
    normalized = []
    for idx, item in enumerate(modules):
        if not isinstance(item, dict):
            continue
        if item.get("enabled") is False:
            continue
        mtype = str(item.get("type") or "").strip()
        if not mtype:
            continue
        try:
            order = int(item.get("order", idx))
        except (TypeError, ValueError):
            order = idx
        limit_val = item.get("limit")
        try:
            limit = int(limit_val) if str(limit_val).strip() else None
        except (TypeError, ValueError):
            limit = None
        media_urls = normalize_local_media_urls(item.get("media_urls") or item.get("images") or [], max_count=20)
        normalized.append(
            {
                "id": str(item.get("id") or "").strip(),
                "type": mtype,
                "title": str(item.get("title") or "").strip(),
                "description": str(item.get("description") or "").strip(),
                "order": order,
                "size": str(item.get("size") or "full").strip() or "full",
                "limit": limit,
                "source": str(item.get("source") or "").strip(),
                "image_url": normalize_local_media_url(item.get("image_url") or item.get("image")),
                "video_url": normalize_local_media_url(item.get("video_url") or item.get("video")),
                "media_urls": media_urls,
                "cta_text": str(item.get("cta_text") or "").strip(),
                "cta_link": str(item.get("cta_link") or "").strip(),
                "layout": item.get("layout") if isinstance(item.get("layout"), dict) else {},
            }
        )
    normalized.sort(key=lambda x: x.get("order", 0))
    return normalized


def _group_modules(modules):
    card_types = {"image", "video", "text", "stat"}
    blocks = []
    grid_items = []
    for module in modules:
        mtype = module.get("type")
        if mtype == "hero":
            if grid_items:
                blocks.append({"kind": "grid", "items": list(grid_items)})
                grid_items = []
            blocks.append({"kind": "hero", "module": module})
            continue
        if mtype in card_types:
            grid_items.append(module)
            continue
        if grid_items:
            blocks.append({"kind": "grid", "items": list(grid_items)})
            grid_items = []
        blocks.append({"kind": "section", "module": module})
    if grid_items:
        blocks.append({"kind": "grid", "items": list(grid_items)})
    return blocks


def _default_canvas_layout(module_type, index):
    defaults = {
        "hero": {"x": 1, "y": 1, "w": 8, "h": 5, "z": 1},
        "products": {"x": 1, "y": 6, "w": 5, "h": 4, "z": 1},
        "news": {"x": 6, "y": 6, "w": 4, "h": 2, "z": 2},
        "welfare": {"x": 10, "y": 6, "w": 3, "h": 2, "z": 2},
        "forum": {"x": 6, "y": 8, "w": 4, "h": 3, "z": 2},
        "company": {"x": 1, "y": 10, "w": 4, "h": 3, "z": 1},
        "media": {"x": 5, "y": 10, "w": 5, "h": 3, "z": 1},
        "timeline": {"x": 10, "y": 8, "w": 3, "h": 5, "z": 1},
        "image": {"x": 1, "y": 14 + (index * 2), "w": 4, "h": 3, "z": 1},
        "video": {"x": 5, "y": 14 + (index * 2), "w": 4, "h": 3, "z": 1},
        "text": {"x": 9, "y": 14 + (index * 2), "w": 4, "h": 2, "z": 1},
        "stat": {"x": 9, "y": 16 + (index * 2), "w": 4, "h": 2, "z": 2},
    }
    return dict(defaults.get(module_type, {"x": 1, "y": 14 + (index * 2), "w": 4, "h": 3, "z": 1}))


def _normalize_canvas_layout(module, index):
    layout = module.get("layout") if isinstance(module, dict) else None
    if not isinstance(layout, dict):
        layout = {}
    fallback = _default_canvas_layout(module.get("type"), index)

    def _int_value(key, minimum, maximum, fallback_value):
        value = layout.get(key, module.get(key))
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = fallback_value
        return max(minimum, min(maximum, value))

    width = _int_value("w", 1, 12, fallback["w"])
    x = _int_value("x", 1, 12, fallback["x"])
    x = min(x, max(1, 13 - width))
    height = _int_value("h", 1, 12, fallback["h"])
    y = _int_value("y", 1, 60, fallback["y"])
    z = _int_value("z", 0, 20, fallback["z"])
    return {"x": x, "y": y, "w": width, "h": height, "z": z}


def _prepare_canvas_modules(modules):
    prepared = []
    for index, module in enumerate(modules):
        item = dict(module)
        item["layout"] = _normalize_canvas_layout(item, index)
        prepared.append(item)
    return prepared


def _canvas_row_count(modules):
    max_row = 10
    for module in modules:
        layout = module.get("layout") or {}
        try:
            bottom = int(layout.get("y", 1)) + int(layout.get("h", 1)) - 1
        except (TypeError, ValueError):
            bottom = 1
        max_row = max(max_row, bottom)
    return max_row


def _product_cover_url(product):
    cover = normalize_local_media_url(product.get("cover_image"))
    if cover:
        return cover
    cover = str(product.get("cover_image") or "").strip()
    if cover:
        return "/product-media/%s/%s" % (
            html.escape(product.get("id", "")),
            quote(os.path.basename(cover)),
        )
    return "/static/placeholders/product-cover.svg"


def _gallery_urls(product):
    urls = normalize_local_media_urls(product.get("gallery") or [], max_count=20)
    if urls:
        return urls
    urls = []
    product_id = product.get("id", "")
    for item in product.get("gallery") or []:
        item = str(item or "").strip()
        if not item:
            continue
        if item.startswith("/"):
            urls.append(item)
            continue
        urls.append("/product-media/%s/%s" % (html.escape(product_id), quote(os.path.basename(item))))
    return urls


def _display_product_name(product):
    return (
        _clean_text(product.get("name"))
        or _clean_text(product.get("title"))
        or _clean_text(product.get("project_id"))
        or "重点项目"
    )


def _display_product_intro(product):
    return (
        _clean_text(product.get("intro"))
        or _clean_text(product.get("description"))
        or "围绕长线运营、版本节奏与玩家社区，构建更完整的商业游戏官网游戏体验。"
    )


def _display_product_description(product):
    return (
        _clean_text(product.get("description"))
        or _clean_text(product.get("intro"))
        or "该项目以品牌展示、新闻公告、福利活动和社区运营为核心，对外承接完整的游戏官网体验。"
    )


def _product_platforms(project_id):
    project_id = resolve_project_id(project_id) or str(project_id or "").strip()
    platforms = []
    seen = set()
    if project_id and os.path.exists(Config.APK_DIR):
        for filename, filepath in iter_package_files():
            if extract_project_name(filename) != project_id:
                continue
            info = extract_package_info(filename, filepath)
            platform = (info.get("platform") or "").lower()
            if not platform or platform in seen:
                continue
            seen.add(platform)
            platforms.append("iOS" if platform == "ios" else "Android")
    return platforms or ["Android", "iOS"]


def _public_product_card(product, index):
    project_id = resolve_project_id_for_product(product) or str(product.get("project_id") or "").strip()
    _, project = get_project_record(project_id)
    return {
        "id": product.get("id") or "",
        "name": _display_product_name(product),
        "intro": _display_product_intro(product),
        "description": _display_product_description(product),
        "cover": _product_cover_url(product),
        "gallery": _gallery_urls(product)[:3],
        "detail_href": "/product/" + html.escape(product.get("id", "")),
        "project_id": project_id,
        "project_name": _clean_text((project or {}).get("name"), project_id or "未绑定项目"),
        "platforms": _product_platforms(project_id),
        "eyebrow": "本周主推" if index == 0 else "项目展示",
        "badge": "HOT" if index == 0 else ("NEW" if index < 3 else "LIVE"),
    }


def _player_store_links(product):
    store_links = product.get("store_links") or {}
    android_channels = store_links.get("android_channels") or []
    rows = []
    if store_links.get("android_direct"):
        rows.append({"label": "Android 官方下载", "url": store_links.get("android_direct"), "platform": "Android", "kind": "官方下载"})
    if store_links.get("ios_store"):
        rows.append({"label": "App Store", "url": store_links.get("ios_store"), "platform": "iOS", "kind": "商店入口"})
    for item in android_channels:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        rows.append({"label": item.get("name") or "Android 渠道", "url": url, "platform": "Android", "kind": "渠道下载"})
    return rows


def _get_product_downloads(project_id, username):
    project_id = resolve_project_id(project_id) or str(project_id or "").strip()
    if not username or not project_id or not os.path.exists(Config.APK_DIR):
        return []
    files = []
    for filename, filepath in iter_package_files():
        if extract_project_name(filename) != project_id:
            continue
        if not can_view_project(project_id, username):
            continue
        info = extract_package_info(filename, filepath)
        info["download_url"] = "/download/" + quote(filename, safe="")
        files.append(info)
    files.sort(key=lambda item: item.get("timestamp", 0), reverse=True)
    return files


def _product_detail_context(product, username):
    project_id = resolve_project_id_for_product(product) or str(product.get("project_id") or "").strip()
    _, project = get_project_record(project_id)
    internal_downloads = _get_product_downloads(project_id, username) if username else []
    return {
        "product": {
            "id": product.get("id") or "",
            "name": _display_product_name(product),
            "intro": _display_product_intro(product),
            "description": _display_product_description(product),
            "cover": _product_cover_url(product),
            "gallery": _gallery_urls(product),
            "project_id": project_id,
            "project_name": _clean_text((project or {}).get("name"), project_id or "未绑定项目"),
            "platforms": _product_platforms(project_id),
            "video_url": normalize_local_media_url(product.get("video_url")),
        },
        "store_links": _player_store_links(product),
        "internal_downloads": internal_downloads,
        "related_news": get_latest_news(product_id=project_id or None, limit=5),
        "related_welfare": get_active_welfare(product_id=project_id or None, limit=5),
        "related_posts": get_forum_posts(product_id=project_id or None, limit=5),
        "current_user": username,
        "show_internal_downloads": bool(internal_downloads) and current_portal_mode() != "player",
    }


@bp.route("/")
def index():
    mode = current_portal_mode()
    current_user = session.get("user") or ""
    scoped_project_id = resolve_project_id((request.args.get("project_id") or "").strip()) or ""
    if mode == "admin" and not current_user:
        return redirect("/login")

    raw_products = sorted(
        [item for item in (products_db if isinstance(products_db, list) else []) if item.get("id")],
        key=lambda item: (item.get("order", 999), item.get("updated_at", "")),
    )
    if scoped_project_id:
        raw_products = [item for item in raw_products if resolve_project_id_for_product(item) == scoped_project_id]

    company_profile = get_company_profile()
    if mode == "player":
        portal_content = get_player_portal_content()
        default_modules = list(DEFAULT_PLAYER_PORTAL.get("home_modules") or [])
    else:
        portal_content = get_dev_portal_content()
        default_modules = list(DEFAULT_DEV_PORTAL.get("home_modules") or [])

    company_name = (
        (company_profile.get("company_name") or "").strip()
        or (portal_content.get("site_name") or "").strip()
        or "APK Portal"
    )
    site_title = (portal_content.get("site_name") or "").strip() or company_name

    visible_ids = _parse_id_list(portal_content.get("visible_product_ids"))
    featured_ids = _parse_id_list(portal_content.get("featured_product_ids"))
    filtered_products = _filter_products_by_ids(raw_products, visible_ids) if visible_ids else list(raw_products)
    products = [_public_product_card(product, idx) for idx, product in enumerate(filtered_products)]
    featured = None
    if featured_ids:
        featured = next((item for item in products if item.get("id") in featured_ids), None)
    if not featured:
        featured = products[0] if products else None

    latest_news = get_latest_news(project_id=scoped_project_id or None, limit=5)
    latest_welfare = get_active_welfare(project_id=scoped_project_id or None, limit=4)
    featured_posts = get_forum_posts(project_id=scoped_project_id or None, limit=4)
    module_flags = _module_flags(portal_content, default_modules)
    home_modules = _normalize_modules(portal_content, default_modules)
    home_blocks = _group_modules(home_modules)
    home_canvas_modules = _prepare_canvas_modules(home_modules)
    use_visual_layout = str(portal_content.get("layout_mode") or "").strip().lower() == "visual"
    home_canvas_rows = _canvas_row_count(home_canvas_modules)
    portal_links = _portal_links(scoped_project_id)
    stats = {
        "game_count": len(products),
        "platform_count": 2,
        "studio_focus": "长线运营",
        "art_style": "品牌感与商业转化",
    }

    if mode == "player":
        return render_template(
            "player_home.html",
            page_title=site_title,
            site_title=site_title,
            company_name=company_name,
            current_user=current_user,
            products=products,
            featured=featured,
            stats=stats,
            portal_content=portal_content,
            latest_news=latest_news,
            latest_welfare=latest_welfare,
            featured_posts=featured_posts,
            company_profile=company_profile,
            module_flags=module_flags,
            home_modules=home_modules,
            home_blocks=home_blocks,
            home_canvas_modules=home_canvas_modules,
            home_canvas_rows=home_canvas_rows,
            use_visual_layout=use_visual_layout,
            portal_kind="player",
            **portal_links,
        )

    return render_template(
        "public_home.html",
        page_title=site_title,
        site_title=site_title,
        company_name=company_name,
        current_user=current_user,
        products=products,
        featured=featured,
        stats=stats,
        portal_content=portal_content,
        latest_news=latest_news,
        latest_welfare=latest_welfare,
        featured_posts=featured_posts,
        company_profile=company_profile,
        module_flags=module_flags,
        home_modules=home_modules,
        home_blocks=home_blocks,
        home_canvas_modules=home_canvas_modules,
        home_canvas_rows=home_canvas_rows,
        use_visual_layout=use_visual_layout,
        portal_kind="dev",
        **portal_links,
    )


@bp.route("/products")
def products_entry():
    return redirect("/")


@bp.route("/product/<product_id>")
@bp.route("/products/<product_id>")
def product_detail(product_id):
    product = next((item for item in (products_db if isinstance(products_db, list) else []) if item.get("id") == product_id), None)
    if not product:
        abort(404)
    company_profile = get_company_profile()
    company_name = (company_profile.get("company_name") or "").strip() or "APK Portal"
    project_id = resolve_project_id_for_product(product) or str(product.get("project_id") or "").strip()
    return render_template(
        "product_detail_public.html",
        page_title=_display_product_name(product) + " - " + company_name,
        **_portal_links(project_id),
        **_product_detail_context(product, session.get("user") or ""),
    )


@bp.route("/about/company")
def company_profile_page():
    profile = get_company_profile()
    company_name = (profile.get("company_name") or "").strip() or "APK Portal"
    return render_template(
        "company_profile_public.html",
        page_title="公司简介 - " + company_name,
        profile=profile,
        **_portal_links(),
    )


@bp.route("/product-media/<product_id>/<path:filename>")
def product_media(product_id, filename):
    import re
    if not re.match(r"^[a-zA-Z0-9_\-]+$", product_id):
        abort(404)
    base = _product_media_base()
    safe_name = secure_filename(os.path.basename(filename))
    if not safe_name:
        abort(404)
    path = os.path.join(base, product_id, safe_name)
    if not os.path.isfile(path) or not os.path.normpath(path).startswith(os.path.normpath(base) + os.sep):
        abort(404)
    return send_file(path, mimetype="application/octet-stream", as_attachment=False)

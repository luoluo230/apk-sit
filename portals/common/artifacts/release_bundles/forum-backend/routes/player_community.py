# -*- coding: utf-8 -*-
"""Player community routes."""

import html
import json
from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, jsonify, redirect, render_template, render_template_string, request, session, url_for

from config import Config
from models.data import (
    create_approval,
    get_project_portal_urls,
    get_project_record,
    products_db,
    projects_db,
    resolve_project_id,
    resolve_project_id_for_product,
)
from services.authz import admin_required
from services.company_profile import get_company_profile
from services.media_library import normalize_local_media_url, normalize_local_media_urls, save_uploaded_files
from services.player_content import (
    add_forum_comment,
    archive_forum_post_item,
    archive_news_item,
    archive_welfare_item,
    create_forum_post,
    create_news_item,
    create_welfare_item,
    forum_categories_db,
    forum_posts_db,
    get_active_welfare,
    get_forum_post,
    get_forum_posts,
    get_latest_news,
    get_player_moderation,
    list_forum_posts_for_admin,
    list_moderated_players,
    list_news_items,
    list_welfare_items,
    moderate_player,
    moderate_post,
    player_news_db,
    save_forum_posts,
    set_forum_post_publish_state,
    set_news_publish_state,
    set_welfare_publish_state,
    update_forum_post_item,
    update_news_item,
    update_welfare_item,
)
from services.portal_content import (
    get_dev_portal_content,
    get_player_portal_content,
    save_dev_portal_content,
    save_player_portal_content,
)
from services.portal import current_portal_mode
from services.rate_limit import rate_limit_forum_comment, rate_limit_forum_post

bp = Blueprint("player_community", __name__)


def _get_csrf_token():
    try:
        from flask_wtf.csrf import generate_csrf

        return generate_csrf()
    except ImportError:
        return ""


def _fmt_time(value):
    if not value:
        return ""
    return str(value).replace("T", " ")[:16]


def _parse_iso_time(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _player_status_meta(player):
    now = datetime.now()
    raw_status = str(player.get("status") or "active").strip() or "active"
    muted_until_raw = str(player.get("muted_until") or "").strip()
    banned_until_raw = str(player.get("banned_until") or "").strip()
    muted_until = _parse_iso_time(muted_until_raw)
    banned_until = _parse_iso_time(banned_until_raw)

    banned_active = False
    muted_active = False

    if raw_status == "banned":
        banned_active = (not banned_until_raw) or (banned_until and banned_until > now)
    elif banned_until and banned_until > now:
        banned_active = True

    if not banned_active:
        if raw_status == "muted":
            muted_active = (not muted_until_raw) or (muted_until and muted_until > now)
        elif muted_until and muted_until > now:
            muted_active = True

    if banned_active:
        detail = "永久封禁" if not banned_until_raw else f"封禁至 {_fmt_time(banned_until_raw)}"
        return {
            "key": "banned",
            "label": "已封禁",
            "badge_class": "bg-rose-100 text-rose-700",
            "detail": detail,
            "can_mute": False,
            "can_unmute": False,
            "can_ban": False,
            "can_unban": True,
            "muted_until_label": _fmt_time(muted_until_raw),
            "banned_until_label": _fmt_time(banned_until_raw),
        }
    if muted_active:
        detail = "永久禁言" if not muted_until_raw else f"禁言至 {_fmt_time(muted_until_raw)}"
        return {
            "key": "muted",
            "label": "已禁言",
            "badge_class": "bg-amber-100 text-amber-700",
            "detail": detail,
            "can_mute": True,
            "can_unmute": True,
            "can_ban": True,
            "can_unban": False,
            "muted_until_label": _fmt_time(muted_until_raw),
            "banned_until_label": _fmt_time(banned_until_raw),
        }
    return {
        "key": "active",
        "label": "正常",
        "badge_class": "bg-emerald-100 text-emerald-700",
        "detail": "当前无生效中的禁言或封禁。",
        "can_mute": True,
        "can_unmute": False,
        "can_ban": True,
        "can_unban": False,
        "muted_until_label": _fmt_time(muted_until_raw),
        "banned_until_label": _fmt_time(banned_until_raw),
    }


def _render_media_block(video_url="", media_urls=None):
    video_url = normalize_local_media_url(video_url)
    media_urls = normalize_local_media_urls(media_urls or [], max_count=6)
    blocks = []
    if video_url:
        blocks.append(
            f'<video class="w-full rounded-3xl border border-slate-200 bg-black" controls src="{html.escape(video_url)}"></video>'
        )
    if media_urls:
        images = "".join(
            f'<img src="{html.escape(url)}" class="h-48 w-full rounded-2xl object-cover" alt="media">'
            for url in media_urls[:6]
        )
        blocks.append(f'<div class="grid gap-4 md:grid-cols-2">{images}</div>')
    if not blocks:
        return ""
    return '<div class="mt-6 space-y-4">' + "".join(blocks) + "</div>"


def _projects():
    rows = []
    if isinstance(projects_db, dict):
        for project_id, payload in projects_db.items():
            project = payload if isinstance(payload, dict) else {}
            rows.append(
                {
                    "id": str(project_id),
                    "name": _display_text(project.get("name"), str(project_id)),
                    "order": int(project.get("order") or 9999),
                }
            )
    rows.sort(key=lambda item: (item.get("order", 9999), item.get("name") or item.get("id") or ""))
    return rows


def _project_name(project_id):
    resolved_id, project = get_project_record(project_id)
    if isinstance(project, dict):
        return _display_text(project.get("name"), resolved_id or str(project_id or "未绑定项目"))
    return _display_text(project_id, "未绑定项目")


def _products(project_id=None):
    rows = [item for item in products_db if isinstance(item, dict)]
    if project_id:
        rows = [item for item in rows if resolve_project_id_for_product(item) == project_id]
    rows.sort(key=lambda item: (item.get("order", 9999), item.get("name") or ""))
    return rows


def _project_id_from_product_id(product_id):
    product_id = str(product_id or "").strip()
    if not product_id:
        return ""
    product = next(
        (item for item in products_db if isinstance(item, dict) and str(item.get("id") or "").strip() == product_id),
        None,
    )
    if not product:
        return ""
    return resolve_project_id_for_product(product) or str(product.get("project_id") or "").strip()


def _product_map():
    return {str(item.get("id") or ""): item for item in _products()}


def _product_option(item):
    product_id = str(item.get("id") or "").strip()
    if not product_id:
        return None
    project_id = resolve_project_id_for_product(item) or str(item.get("project_id") or "").strip()
    return {
        "id": product_id,
        "name": _display_text(item.get("name"), product_id),
        "project_id": project_id,
        "project_name": _project_name(project_id) if project_id else "未绑定项目",
    }


def _display_text(value, fallback=""):
    text = "" if value is None else str(value).strip()
    if not text:
        return fallback
    question_ratio = text.count("?") / max(len(text), 1)
    if question_ratio >= 0.35 or "锟" in text or "�" in text:
        return fallback or text.replace("?", "").strip() or fallback
    return text


def _product_name(product_id):
    item = _product_map().get(product_id or "")
    return _display_text((item or {}).get("name"), product_id or "未绑定项目")


def _request_project_scope(default_product_id=""):
    project_id = resolve_project_id((request.args.get("project_id") or "").strip())
    if project_id:
        return project_id
    product_id = (request.args.get("product_id") or default_product_id or "").strip()
    if product_id:
        return _project_id_from_product_id(product_id)
    return ""


def _require_product_id(data):
    product_id = (data.get("product_id") or "").strip()
    if not product_id:
        return None, jsonify({"error": "请先选择所属游戏项目"}), 400
    return product_id, None, None


def _ensure_published(item):
    if not item:
        return False
    return (item.get("publish_status") or "published") == "published"


def _portal_layout(title, content, active=""):
    company_profile = get_company_profile()
    portal_content = get_player_portal_content()
    site_title = (
        (portal_content.get("site_name") or "").strip()
        or (company_profile.get("company_name") or "").strip()
        or "APK Portal"
    )
    nav_items = [
        ("/", "首页", ""),
        ("/about/company", "公司简介", "about"),
        ("/news", "新闻公告", "news"),
        ("/welfare", "福利中心", "welfare"),
        ("/forum", "玩家论坛", "forum"),
        ("/download-center", "下载中心", "download"),
    ]
    nav_html = "".join(
        f'<a href="{href}" class="text-sm font-semibold {"text-violet-700" if key == active else "text-slate-700"} hover:text-violet-700 transition">{label}</a>'
        for href, label, key in nav_items
    )
    auth_html = (
        '<div class="flex items-center gap-3">'
        '<a href="/admin" class="text-sm font-semibold text-slate-500 hover:text-slate-900">工作台</a>'
        '<a href="/logout" class="inline-flex items-center justify-center px-4 py-2 rounded-full bg-slate-900 text-white text-sm font-semibold">退出</a>'
        "</div>"
        if session.get("user")
        else '<a href="/login" class="inline-flex items-center justify-center px-4 py-2 rounded-full bg-slate-900 text-white text-sm font-semibold">登录工作台</a>'
    )
    username = session.get("user") or ""
    if username:
        auth_html = (
            '<div class="flex items-center gap-3">'
            f'<span class="hidden sm:inline-flex text-xs font-semibold text-slate-500">{html.escape(username)}</span>'
            '<a href="/admin" class="text-sm font-semibold text-slate-500 hover:text-slate-900">宸工作台</a>'
            '<a href="/logout" class="inline-flex items-center justify-center px-4 py-2 rounded-full bg-slate-900 text-white text-sm font-semibold">退出</a>'
            "</div>"
        )
    else:
        auth_html = '<a href="/login" class="inline-flex items-center justify-center px-4 py-2 rounded-full bg-slate-900 text-white text-sm font-semibold">登录工作台</a>'
    if username:
        auth_html = (
            '<div class="flex items-center gap-3">'
            f'<span class="hidden sm:inline-flex text-xs font-semibold text-slate-500">{html.escape(username)}</span>'
            '<a href="/admin" class="text-sm font-semibold text-slate-500 hover:text-slate-900">\u5de5\u4f5c\u53f0</a>'
            '<a href="/logout" class="inline-flex items-center justify-center px-4 py-2 rounded-full bg-slate-900 text-white text-sm font-semibold">\u9000\u51fa</a>'
            "</div>"
        )
    else:
        auth_html = '<a href="/login" class="inline-flex items-center justify-center px-4 py-2 rounded-full bg-slate-900 text-white text-sm font-semibold">\u767b\u5f55\u5de5\u4f5c\u53f0</a>'
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{html.escape(_get_csrf_token())}">
    <title>{html.escape(title)} - {html.escape(site_title)}</title>
    <link rel="stylesheet" href="/static/tailwind.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;900&family=ZCOOL+XiaoWei&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Noto Sans SC', sans-serif; background: radial-gradient(circle at top left, #b7edff 0%, #f6f1e3 55%, #ffffff 100%); color: #111827; }}
        .font-display {{ font-family: 'ZCOOL XiaoWei', serif; }}
        .glass {{ background: rgba(255, 255, 255, 0.82); border: 1px solid rgba(255,255,255,0.75); box-shadow: 0 24px 60px rgba(15,23,42,0.08); backdrop-filter: blur(14px); }}
    </style>
</head>
<body class="min-h-screen">
    <header class="sticky top-0 z-30 bg-white/75 backdrop-blur border-b border-slate-200/80">
        <div class="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
            <a href="/" class="font-display text-2xl text-slate-900">{html.escape(site_title)}</a>
            <nav class="hidden md:flex items-center gap-5">{nav_html}</nav>
            <div>{auth_html}</div>
        </div>
    </header>
    <main class="max-w-6xl mx-auto px-4 py-8">{content}</main>
    <script>
    window.portalCsrfToken = (document.querySelector('meta[name="csrf-token"]') || {{}}).content || '';
    </script>
</body>
</html>"""


def _portal_layout_v2(title, content, active="", project_id=""):
    company_profile = get_company_profile()
    portal_content = get_player_portal_content()
    site_title = (
        (portal_content.get("site_name") or "").strip()
        or (company_profile.get("company_name") or "").strip()
        or "APK Portal"
    )
    mode = current_portal_mode()
    portal_urls = get_project_portal_urls(project_id)
    player_base = (portal_urls.get("player_public_url") or "").strip().rstrip("/")
    forum_base = (portal_urls.get("forum_public_url") or "").strip().rstrip("/")
    admin_base = (portal_urls.get("admin_public_url") or "").strip().rstrip("/")

    if not player_base and mode not in ("player", "all"):
        player_base = f"http://127.0.0.1:{getattr(Config, 'PLAYER_PORT', 5004)}"
    if not forum_base and mode not in ("forum", "all"):
        forum_base = f"http://127.0.0.1:{getattr(Config, 'FORUM_PORT', 5005)}"
    if not admin_base and mode not in ("admin", "all"):
        admin_base = f"http://127.0.0.1:{getattr(Config, 'ADMIN_PORT', 5003)}"

    def _join(base, path):
        return (base + path) if base else path

    def _with_project_scope(url):
        if not project_id:
            return url
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}project_id={quote(project_id, safe='')}"

    home_url = _with_project_scope(_join(player_base, "/"))
    about_url = _with_project_scope(_join(player_base, "/about/company"))
    news_url = _with_project_scope(_join(player_base, "/news"))
    welfare_url = _with_project_scope(_join(player_base, "/welfare"))
    forum_url = _with_project_scope(_join(forum_base or player_base, "/forum"))
    download_url = _with_project_scope(_join(admin_base, "/download-center"))
    admin_entry_url = _join(admin_base, "/admin")
    login_url = _join(admin_base, "/login")
    logout_url = _join(admin_base, "/logout")

    nav_items = [
        (home_url, "首页", ""),
        (about_url, "公司简介", "about"),
        (news_url, "新闻公告", "news"),
        (welfare_url, "福利中心", "welfare"),
        (forum_url, "玩家论坛", "forum"),
        (download_url, "下载中心", "download"),
    ]
    nav_html = "".join(
        f'<a href="{href}" class="text-sm font-semibold {"text-violet-700" if key == active else "text-slate-700"} hover:text-violet-700 transition">{label}</a>'
        for href, label, key in nav_items
    )

    username = session.get("user") or ""
    if username:
        auth_html = (
            '<div class="flex items-center gap-3">'
            f'<span class="hidden sm:inline-flex text-xs font-semibold text-slate-500">{html.escape(username)}</span>'
            f'<a href="{admin_entry_url}" class="text-sm font-semibold text-slate-500 hover:text-slate-900">工作台</a>'
            f'<a href="{logout_url}" class="inline-flex items-center justify-center px-4 py-2 rounded-full bg-slate-900 text-white text-sm font-semibold">退出</a>'
            "</div>"
        )
    else:
        auth_html = f'<a href="{login_url}" class="inline-flex items-center justify-center px-4 py-2 rounded-full bg-slate-900 text-white text-sm font-semibold">登录工作台</a>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="{html.escape(_get_csrf_token())}">
    <title>{html.escape(title)} - {html.escape(site_title)}</title>
    <link rel="stylesheet" href="/static/tailwind.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;900&family=ZCOOL+XiaoWei&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Noto Sans SC', sans-serif; background: radial-gradient(circle at top left, #b7edff 0%, #f6f1e3 55%, #ffffff 100%); color: #111827; }}
        .font-display {{ font-family: 'ZCOOL XiaoWei', serif; }}
        .glass {{ background: rgba(255, 255, 255, 0.82); border: 1px solid rgba(255,255,255,0.75); box-shadow: 0 24px 60px rgba(15,23,42,0.08); backdrop-filter: blur(14px); }}
    </style>
</head>
<body class="min-h-screen">
    <header class="sticky top-0 z-30 bg-white/75 backdrop-blur border-b border-slate-200/80">
        <div class="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
            <a href="{home_url}" class="font-display text-2xl text-slate-900">{html.escape(site_title)}</a>
            <nav class="hidden md:flex items-center gap-5">{nav_html}</nav>
            <div>{auth_html}</div>
        </div>
    </header>
    <main class="max-w-6xl mx-auto px-4 py-8">{content}</main>
    <script>
    window.portalCsrfToken = (document.querySelector('meta[name="csrf-token"]') || {{}}).content || '';
    </script>
</body>
</html>"""


def _portal_layout(title, content, active="", project_id=""):
    scope_project_id = resolve_project_id(project_id)
    if not scope_project_id:
        scope_project_id = _request_project_scope()

    endpoint = request.endpoint or ""
    view_args = request.view_args or {}
    if not scope_project_id and endpoint.endswith("news_detail"):
        item_id = str(view_args.get("item_id") or "").strip()
        item = next((x for x in player_news_db if isinstance(x, dict) and x.get("id") == item_id), None)
        scope_project_id = resolve_project_id((item or {}).get("project_id")) or _project_id_from_product_id((item or {}).get("product_id"))
    if not scope_project_id and endpoint.endswith("welfare_detail"):
        item_id = str(view_args.get("item_id") or "").strip()
        item = next((x for x in player_welfare_db if isinstance(x, dict) and x.get("id") == item_id), None)
        scope_project_id = resolve_project_id((item or {}).get("project_id")) or _project_id_from_product_id((item or {}).get("product_id"))
    if not scope_project_id and endpoint.endswith("forum_detail"):
        post_id = str(view_args.get("post_id") or "").strip()
        post = next((x for x in forum_posts_db if isinstance(x, dict) and x.get("id") == post_id), None)
        scope_project_id = resolve_project_id((post or {}).get("project_id")) or _project_id_from_product_id((post or {}).get("product_id"))

    return _portal_layout_v2(title, content, active=active, project_id=scope_project_id or "")


def _status_meta(status):
    mapping = {
        "published": ("已发布", "bg-emerald-100 text-emerald-700"),
        "pending_approval": ("待审批", "bg-amber-100 text-amber-700"),
        "rejected": ("已驳回", "bg-rose-100 text-rose-700"),
        "archived": ("已归档", "bg-slate-200 text-slate-600"),
        "draft": ("草稿", "bg-slate-100 text-slate-700"),
    }
    return mapping.get(status or "draft", mapping["draft"])


def _approval_result(item_id, approval_id):
    return jsonify({"ok": True, "id": item_id, "approval_id": approval_id, "status": "pending_approval"})


@bp.route("/news")
def news_index():
    current_project_id = _request_project_scope()
    detail_suffix = f"?project_id={quote(current_project_id, safe='')}" if current_project_id else ""
    rows = get_latest_news(project_id=current_project_id or None, limit=24)
    cards = "".join(
        f"""
        <a href="/news/{html.escape(item.get('id', ''))}{detail_suffix}" class="glass block rounded-[28px] p-6 hover:-translate-y-1 transition">
            <div class="text-xs font-extrabold tracking-[0.2em] uppercase text-violet-600">{html.escape(item.get('kind') or '新闻公告')}</div>
            <h2 class="font-display text-3xl text-slate-900 mt-3">{html.escape(item.get('title') or '未命名内容')}</h2>
            <p class="mt-3 text-slate-600 leading-7">{html.escape(item.get('summary') or '')}</p>
            <div class="mt-4 text-sm text-slate-500">{html.escape(_fmt_time(item.get('published_at') or item.get('created_at')))}</div>
        </a>
        """
        for item in rows
    ) or '<div class="glass rounded-[28px] p-10 text-center text-slate-500">暂时还没有公开新闻。</div>'
    content = f"""
    <section class="mb-8">
        <div class="text-xs font-extrabold tracking-[0.22em] uppercase text-violet-600">Newsroom</div>
        <h1 class="font-display text-5xl text-slate-900 mt-3">新闻公告中心</h1>
        <p class="mt-3 text-slate-600 text-lg leading-8">集中展示最近发布的公告、版本动态、活动消息和维护通知。</p>
    </section>
    <section class="grid gap-6 md:grid-cols-2">{cards}</section>
    """
    return _portal_layout("新闻公告", content, active="news")


@bp.route("/news/<item_id>")
def news_detail(item_id):
    scope_project_id = _request_project_scope()
    item = next((x for x in player_news_db if isinstance(x, dict) and x.get("id") == item_id), None)
    if not _ensure_published(item):
        return _portal_layout("新闻不存在", '<div class="glass rounded-[28px] p-10 text-center text-slate-500">这条新闻不存在或尚未发布。</div>', active="news"), 404
    scope_project_id = scope_project_id or resolve_project_id(item.get("project_id")) or _project_id_from_product_id(item.get("product_id"))
    body = html.escape(item.get("content") or item.get("summary") or "").replace("\n", "<br>")
    media_html = _render_media_block(item.get("video_url"), item.get("media_urls"))
    content = f"""
    <article class="glass rounded-[32px] p-8">
        <div class="text-xs font-extrabold tracking-[0.2em] uppercase text-violet-600">{html.escape(item.get('kind') or '新闻公告')}</div>
        <h1 class="font-display text-5xl text-slate-900 mt-3">{html.escape(item.get('title') or '未命名内容')}</h1>
        <p class="mt-3 text-sm text-slate-500">{html.escape(_fmt_time(item.get('published_at') or item.get('created_at')))}</p>
        <p class="mt-2 text-sm text-slate-500">所属项目：{html.escape(_product_name(item.get('product_id')))}</p>
        {media_html}
        <div class="mt-6 text-slate-700 leading-8">{body}</div>
    </article>
    """
    return _portal_layout(item.get("title") or "新闻详情", content, active="news")


@bp.route("/welfare")
def welfare_index():
    current_project_id = _request_project_scope()
    detail_suffix = f"?project_id={quote(current_project_id, safe='')}" if current_project_id else ""
    rows = get_active_welfare(project_id=current_project_id or None, limit=24)
    cards = "".join(
        f"""
        <a href="/welfare/{html.escape(item.get('id', ''))}{detail_suffix}" class="glass block rounded-[28px] p-6 hover:-translate-y-1 transition">
            <div class="flex items-start justify-between gap-4">
                <div>
                    <div class="text-xs font-extrabold tracking-[0.2em] uppercase text-emerald-600">福利活动</div>
                    <h2 class="font-display text-3xl text-slate-900 mt-3">{html.escape(item.get('title') or '福利内容')}</h2>
                </div>
                <span class="px-3 py-1 rounded-full bg-emerald-100 text-emerald-700 text-xs font-bold">{html.escape(item.get('status') or '进行中')}</span>
            </div>
            <p class="mt-3 text-slate-600 leading-7">{html.escape(item.get('description') or '')}</p>
            <div class="mt-5 grid sm:grid-cols-2 gap-3 text-sm">
                <div class="rounded-2xl bg-white px-4 py-3 border border-slate-200">
                    <span class="text-slate-500">礼包码</span>
                    <div class="font-bold text-slate-900 mt-1">{html.escape(item.get('redeem_code') or '敬请期待')}</div>
                </div>
                <div class="rounded-2xl bg-white px-4 py-3 border border-slate-200">
                    <span class="text-slate-500">有效期</span>
                    <div class="font-bold text-slate-900 mt-1">{html.escape(item.get('valid_until') or '长期有效')}</div>
                </div>
            </div>
            <div class="mt-4 text-sm text-slate-500">所属项目：{html.escape(_product_name(item.get('product_id')))}</div>
        </a>
        """
        for item in rows
    ) or '<div class="glass rounded-[28px] p-10 text-center text-slate-500">暂时还没有公开福利。</div>'
    content = f"""
    <section class="mb-8">
        <div class="text-xs font-extrabold tracking-[0.22em] uppercase text-emerald-600">Benefits</div>
        <h1 class="font-display text-5xl text-slate-900 mt-3">福利中心</h1>
        <p class="mt-3 text-slate-600 text-lg leading-8">按项目聚合展示礼包、兑换码、预约奖励与活动权益。</p>
    </section>
    <section class="grid gap-6 md:grid-cols-2">{cards}</section>
    """
    return _portal_layout("福利中心", content, active="welfare")


@bp.route("/welfare/<item_id>")
def welfare_detail(item_id):
    scope_project_id = _request_project_scope()
    item = next((x for x in get_active_welfare(limit=999) if isinstance(x, dict) and x.get("id") == item_id), None)
    if not item or not _ensure_published(item):
        return _portal_layout("福利不存在", '<div class="glass rounded-[28px] p-10 text-center text-slate-500">这条福利不存在或尚未发布。</div>', active="welfare"), 404
    scope_project_id = scope_project_id or resolve_project_id(item.get("project_id")) or _project_id_from_product_id(item.get("product_id"))
    media_html = _render_media_block(item.get("video_url"), item.get("media_urls"))
    content = f"""
    <article class="glass rounded-[32px] p-8">
        <div class="flex flex-wrap items-center gap-3">
            <span class="text-xs font-extrabold tracking-[0.2em] uppercase text-emerald-600">福利活动</span>
            <span class="px-3 py-1 rounded-full bg-emerald-100 text-emerald-700 text-xs font-bold">{html.escape(item.get('status') or '进行中')}</span>
        </div>
        <h1 class="font-display text-5xl text-slate-900 mt-4">{html.escape(item.get('title') or '福利详情')}</h1>
        <p class="mt-4 text-sm text-slate-500">所属项目：{html.escape(_product_name(item.get('product_id')))} · 有效期：{html.escape(item.get('valid_until') or '长期有效')}</p>
        {media_html}
        <div class="mt-8 grid md:grid-cols-2 gap-4">
            <div class="rounded-3xl bg-white border border-slate-200 p-6">
                <div class="text-sm text-slate-500">礼包码</div>
                <div class="mt-3 text-3xl font-black tracking-wide text-slate-900">{html.escape(item.get('redeem_code') or '敬请期待')}</div>
            </div>
            <div class="rounded-3xl bg-white border border-slate-200 p-6">
                <div class="text-sm text-slate-500">活动状态</div>
                <div class="mt-3 text-2xl font-black text-slate-900">{html.escape(item.get('status') or '进行中')}</div>
            </div>
        </div>
        <div class="mt-8 rounded-3xl bg-white border border-slate-200 p-6">
            <div class="text-sm text-slate-500">福利说明</div>
            <div class="mt-3 text-slate-700 leading-8 whitespace-pre-wrap">{html.escape(item.get('description') or '暂无说明')}</div>
        </div>
        <div class="mt-8">
            <a href="/welfare" class="inline-flex items-center gap-2 text-sm font-semibold text-emerald-700 hover:underline"><i class="fas fa-arrow-left"></i> 返回福利列表</a>
        </div>
    </article>
    """
    return _portal_layout(item.get("title") or "福利详情", content, active="welfare")


@bp.route("/forum")
def forum_index():
    product_id = (request.args.get("product_id") or "").strip()
    category_id = (request.args.get("category") or "").strip()
    current_project_id = _request_project_scope(product_id)
    rows = get_forum_posts(
        product_id=product_id or None,
        project_id=current_project_id or None,
        category_id=category_id or None,
        limit=40,
    )
    products = _products(current_project_id or None)
    detail_suffix = f"?project_id={quote(current_project_id, safe='')}" if current_project_id else ""
    categories_html = "".join(
        f'<a href="/forum?category={html.escape(item.get("id", ""))}'
        + (f'&product_id={quote(product_id, safe="")}' if product_id else "")
        + (f'&project_id={quote(current_project_id, safe="")}' if current_project_id else "")
        + f'" class="px-4 py-2 rounded-full {"bg-violet-600 text-white" if category_id == item.get("id") else "bg-white text-slate-700 border border-slate-200"} text-sm font-semibold">{html.escape(item.get("name") or "")}</a>'
        for item in forum_categories_db
    )
    posts_html = "".join(
        f"""
        <a href="/forum/{html.escape(post.get('id', ''))}{detail_suffix}" class="glass block rounded-[28px] p-6 hover:-translate-y-1 transition">
            <div class="flex items-center justify-between gap-4">
                <span class="text-xs font-extrabold tracking-[0.2em] uppercase text-violet-600">{html.escape(post.get('category_id') or 'general')}</span>
                {"<span class='px-3 py-1 rounded-full bg-amber-100 text-amber-700 text-xs font-bold'>官方</span>" if post.get("is_official") else ""}
            </div>
            <h2 class="font-display text-3xl text-slate-900 mt-3">{html.escape(post.get('title') or '未命名帖子')}</h2>
            <p class="mt-3 text-slate-600 leading-7">{html.escape((post.get('content') or '')[:150])}</p>
            <div class="mt-4 flex items-center justify-between text-sm text-slate-500">
                <span>{html.escape(post.get('display_name') or '匿名玩家')}</span>
                <span>{len(post.get('comments') or [])} 条评论</span>
            </div>
        </a>
        """
        for post in rows
    ) or '<div class="glass rounded-[28px] p-10 text-center text-slate-500">这个分区暂时还没有内容。</div>'
    product_options = "".join(
        f'<option value="{html.escape(str(item.get("id") or ""))}" {"selected" if product_id == str(item.get("id") or "") else ""}>{html.escape(item.get("name") or str(item.get("id") or ""))}</option>'
        for item in products
    )
    content = f"""
    <section class="mb-8">
        <div class="text-xs font-extrabold tracking-[0.22em] uppercase text-violet-600">Community</div>
        <h1 class="font-display text-5xl text-slate-900 mt-3">玩家论坛</h1>
        <p class="mt-3 text-slate-600 text-lg leading-8">官方帖子与玩家讨论共存，支持按项目分区和按主题浏览。</p>
    </section>
    <section class="glass rounded-[28px] p-6 mb-6">
        <div class="flex flex-wrap gap-3">{categories_html}</div>
        <form id="forumCreateForm" class="mt-6 grid gap-4">
            <div class="grid md:grid-cols-2 gap-4">
                <input type="text" name="display_name" placeholder="昵称（游客可填写）" class="px-4 py-3 rounded-2xl border border-slate-200">
                <input type="text" name="title" placeholder="帖子标题" class="px-4 py-3 rounded-2xl border border-slate-200" required>
            </div>
            <div class="grid md:grid-cols-2 gap-4">
                <select name="category_id" class="px-4 py-3 rounded-2xl border border-slate-200">
                    {''.join(f'<option value="{html.escape(item.get("id",""))}">{html.escape(item.get("name",""))}</option>' for item in forum_categories_db)}
                </select>
                <select name="product_id" class="px-4 py-3 rounded-2xl border border-slate-200">
                    <option value="">全站社区</option>
                    {product_options}
                </select>
            </div>
            <textarea name="content" rows="5" placeholder="分享你的问题、心得、建议或截图故事" class="px-4 py-3 rounded-2xl border border-slate-200" required></textarea>
            <div class="flex items-center gap-3">
                <button class="px-6 py-3 rounded-full bg-violet-600 text-white font-bold" type="submit">发布帖子</button>
                <span id="forumCreateResult" class="text-sm text-slate-500"></span>
            </div>
        </form>
    </section>
    <section class="grid gap-6">{posts_html}</section>
    <script>
    document.getElementById('forumCreateForm').addEventListener('submit', function(e) {{
        e.preventDefault();
        var fd = new FormData(this);
        fetch('/forum/create', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json', 'X-CSRFToken': window.portalCsrfToken || '' }},
            credentials: 'same-origin',
            body: JSON.stringify({{
                display_name: fd.get('display_name') || '',
                title: fd.get('title') || '',
                category_id: fd.get('category_id') || 'general',
                product_id: fd.get('product_id') || '',
                content: fd.get('content') || ''
            }})
        }}).then(function(r){{ return r.json(); }}).then(function(d){{
            document.getElementById('forumCreateResult').textContent = d.error || '发布成功，正在跳转…';
            if(!d.error) setTimeout(function(){{ location.href = '/forum/' + d.post.id + '{detail_suffix}'; }}, 400);
        }});
    }});
    </script>
    """
    return _portal_layout("玩家论坛", content, active="forum")


@bp.route("/forum/<post_id>")
def forum_detail(post_id):
    scope_project_id = _request_project_scope()
    post = get_forum_post(post_id)
    if not post or post.get("deleted") or not post.get("visible", True) or not _ensure_published(post):
        return _portal_layout("帖子不存在", '<div class="glass rounded-[28px] p-10 text-center text-slate-500">帖子不存在或尚未发布。</div>', active="forum"), 404
    scope_project_id = scope_project_id or resolve_project_id(post.get("project_id")) or _project_id_from_product_id(post.get("product_id"))
    media_html = _render_media_block(post.get("video_url"), post.get("media_urls"))
    comments_html = "".join(
        f"""
        <div class="rounded-2xl bg-white p-4 border border-slate-200">
            <div class="flex items-center justify-between gap-3">
                <div class="font-semibold text-slate-900">{html.escape(item.get('display_name') or '匿名玩家')}</div>
                <div class="text-xs text-slate-500">{html.escape(_fmt_time(item.get('created_at')))}</div>
            </div>
            <div class="mt-2 text-slate-700 leading-7">{html.escape(item.get('content') or '')}</div>
        </div>
        """
        for item in (post.get("comments") or [])
    ) or '<div class="rounded-2xl bg-white p-6 border border-slate-200 text-slate-500">还没有评论，来做第一个发言的人吧。</div>'
    content = f"""
    <article class="glass rounded-[32px] p-8">
        <div class="flex flex-wrap items-center gap-3">
            <span class="text-xs font-extrabold tracking-[0.2em] uppercase text-violet-600">{html.escape(post.get('category_id') or 'general')}</span>
            {"<span class='px-3 py-1 rounded-full bg-amber-100 text-amber-700 text-xs font-bold'>官方帖子</span>" if post.get("is_official") else ""}
        </div>
        <h1 class="font-display text-5xl text-slate-900 mt-4">{html.escape(post.get('title') or '帖子详情')}</h1>
        <p class="mt-4 text-sm text-slate-500">作者：{html.escape(post.get('display_name') or '匿名玩家')} · {html.escape(_fmt_time(post.get('created_at')))} · 项目：{html.escape(_product_name(post.get('product_id')))}</p>
        {media_html}
        <div class="mt-6 text-slate-700 leading-8 whitespace-pre-wrap">{html.escape(post.get('content') or '')}</div>
    </article>
    <section class="glass rounded-[32px] p-8 mt-8">
        <h2 class="font-display text-4xl text-slate-900">评论区</h2>
        <form id="commentForm" class="mt-6 grid gap-4">
            <input type="text" name="display_name" placeholder="昵称（游客可填写）" class="px-4 py-3 rounded-2xl border border-slate-200">
            <textarea name="content" rows="4" class="px-4 py-3 rounded-2xl border border-slate-200" placeholder="说点什么…" required></textarea>
            <div class="flex items-center gap-3">
                <button class="px-6 py-3 rounded-full bg-violet-600 text-white font-bold" type="submit">发表评论</button>
                <span id="commentResult" class="text-sm text-slate-500"></span>
            </div>
        </form>
        <div class="mt-8 grid gap-4">{comments_html}</div>
    </section>
    <script>
    document.getElementById('commentForm').addEventListener('submit', function(e) {{
        e.preventDefault();
        var fd = new FormData(this);
        fetch('/forum/{html.escape(post_id)}/comment', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json', 'X-CSRFToken': window.portalCsrfToken || '' }},
            credentials: 'same-origin',
            body: JSON.stringify({{
                display_name: fd.get('display_name') || '',
                content: fd.get('content') || ''
            }})
        }}).then(function(r){{ return r.json(); }}).then(function(d){{
            document.getElementById('commentResult').textContent = d.error || '评论成功，正在刷新…';
            if(!d.error) setTimeout(function(){{ location.reload(); }}, 300);
        }});
    }});
    </script>
    """
    return _portal_layout(post.get("title") or "帖子详情", content, active="forum")


@bp.route("/forum/create", methods=["POST"])
def forum_create():
    allowed, retry_after = rate_limit_forum_post()
    if not allowed:
        return jsonify({"error": f"发帖过于频繁，请在 {retry_after} 秒后重试"}), 429
    data = request.get_json(silent=True) or {}
    post = create_forum_post(data, session.get("user") or "")
    if not post:
        return jsonify({"error": "帖子提交失败，请检查内容长度或发言状态"}), 400
    return jsonify({"ok": True, "post": {"id": post.get("id")}})


@bp.route("/forum/<post_id>/comment", methods=["POST"])
def forum_comment(post_id):
    allowed, retry_after = rate_limit_forum_comment()
    if not allowed:
        return jsonify({"error": f"评论过于频繁，请在 {retry_after} 秒后重试"}), 429
    data = request.get_json(silent=True) or {}
    comment = add_forum_comment(post_id, data, session.get("user") or "")
    if not comment:
        return jsonify({"error": "评论失败，帖子可能未发布或当前账号受限"}), 400
    return jsonify({"ok": True, "comment": comment})


@bp.route("/admin/community")
@admin_required("community")
def community_admin():
    current_project_id = resolve_project_id((request.args.get("project_id") or "").strip()) or ""
    current_product_id = (request.args.get("product_id") or "").strip()
    player_query = (request.args.get("player_query") or "").strip()
    player_status = (request.args.get("player_status") or "all").strip() or "all"
    player_target = (request.args.get("player_target") or "").strip()
    if current_product_id:
        inferred_project_id = _project_id_from_product_id(current_product_id)
        if inferred_project_id:
            current_project_id = inferred_project_id
    project_list = _projects()
    all_products = _products()
    product_list = _products(current_project_id)
    if current_product_id and not any(str(item.get("id") or "") == current_product_id for item in all_products):
        current_product_id = ""
    news_rows = []
    welfare_rows = []
    forum_rows = []
    for item in list_news_items(product_id=current_product_id or None, project_id=current_project_id or None)[:30]:
        status_label, status_class = _status_meta(item.get("publish_status"))
        row = dict(item)
        row["status_label"] = status_label
        row["status_class"] = status_class
        row["title"] = _display_text(item.get("title"), "未命名新闻")
        row["summary"] = _display_text(item.get("summary"), "暂无摘要")
        row["content"] = _display_text(item.get("content"), "暂无正文")
        row["kind"] = _display_text(item.get("kind"), "新闻公告")
        row["project_id"] = resolve_project_id(item.get("project_id")) or _project_id_from_product_id(item.get("product_id"))
        row["project_name"] = _project_name(row.get("project_id"))
        row["product_name"] = _product_name(item.get("product_id"))
        row["time_label"] = _fmt_time(item.get("published_at") or item.get("updated_at") or item.get("created_at"))
        row["edit_payload"] = {
            "id": row.get("id", ""),
            "title": row["title"],
            "kind": row["kind"],
            "project_id": row.get("project_id", ""),
            "product_id": row.get("product_id", ""),
            "summary": row["summary"],
            "content": row["content"],
            "video_url": _display_text(row.get("video_url"), ""),
            "media_urls": item.get("media_urls") or [],
            "pinned": bool(row.get("pinned")),
        }
        news_rows.append(row)
    for item in list_welfare_items(product_id=current_product_id or None, project_id=current_project_id or None)[:30]:
        status_label, status_class = _status_meta(item.get("publish_status"))
        row = dict(item)
        row["status_label"] = status_label
        row["status_class"] = status_class
        row["title"] = _display_text(item.get("title"), "未命名福利")
        row["description"] = _display_text(item.get("description"), "暂无福利说明")
        row["status"] = _display_text(item.get("status"), "进行中")
        row["redeem_code"] = _display_text(item.get("redeem_code"), "敬请期待")
        row["project_id"] = resolve_project_id(item.get("project_id")) or _project_id_from_product_id(item.get("product_id"))
        row["project_name"] = _project_name(row.get("project_id"))
        row["product_name"] = _product_name(item.get("product_id"))
        row["time_label"] = _fmt_time(item.get("valid_until") or item.get("updated_at") or item.get("created_at"))
        row["edit_payload"] = {
            "id": row.get("id", ""),
            "title": row["title"],
            "project_id": row.get("project_id", ""),
            "product_id": row.get("product_id", ""),
            "redeem_code": row["redeem_code"],
            "valid_until": row.get("valid_until", ""),
            "status": row["status"],
            "description": row["description"],
            "video_url": _display_text(row.get("video_url"), ""),
            "media_urls": item.get("media_urls") or [],
        }
        welfare_rows.append(row)
    for item in list_forum_posts_for_admin(product_id=current_product_id or None, project_id=current_project_id or None)[:30]:
        status_label, status_class = _status_meta(item.get("publish_status"))
        row = dict(item)
        row["status_label"] = status_label
        row["status_class"] = status_class
        row["title"] = _display_text(item.get("title"), "未命名帖子")
        row["content"] = _display_text(item.get("content"), "暂无帖子正文")
        row["project_id"] = resolve_project_id(item.get("project_id")) or _project_id_from_product_id(item.get("product_id"))
        row["project_name"] = _project_name(row.get("project_id"))
        row["product_name"] = _product_name(item.get("product_id"))
        row["time_label"] = _fmt_time(item.get("updated_at") or item.get("created_at"))
        row["edit_payload"] = {
            "id": row.get("id", ""),
            "title": row["title"],
            "project_id": row.get("project_id", ""),
            "product_id": row.get("product_id", ""),
            "category_id": row.get("category_id", "general"),
            "video_url": _display_text(row.get("video_url"), ""),
            "media_urls": item.get("media_urls") or [],
            "content": row["content"],
            "pinned": bool(row.get("pinned")),
        }
        forum_rows.append(row)
    player_overview = {"total": 0, "active": 0, "muted": 0, "banned": 0, "filtered": 0}
    moderated_players_all = []
    for player in list_moderated_players():
        row = dict(player)
        author_key = str(player.get("author_key") or "").strip()
        row["author_key_raw"] = author_key
        if not author_key or "?" in author_key:
            row["author_key_display"] = "匿名访客"
        else:
            row["author_key_display"] = _display_text(author_key, "匿名访客")
        row["display_name"] = _display_text(player.get("display_name"), "匿名玩家")
        row["notes"] = _display_text(player.get("notes"), "")
        row["updated_label"] = _fmt_time(player.get("updated_at"))
        status_meta = _player_status_meta(player)
        row["effective_status"] = status_meta["key"]
        row["status_label"] = status_meta["label"]
        row["status_badge_class"] = status_meta["badge_class"]
        row["status_detail"] = status_meta["detail"]
        row["muted_until_label"] = status_meta["muted_until_label"] or "未设置"
        row["banned_until_label"] = status_meta["banned_until_label"] or "未设置"
        row["can_mute"] = status_meta["can_mute"]
        row["can_unmute"] = status_meta["can_unmute"]
        row["can_ban"] = status_meta["can_ban"]
        row["can_unban"] = status_meta["can_unban"]
        row["search_blob"] = " ".join(
            [
                row["display_name"],
                row["author_key_display"],
                row["author_key_raw"],
                row["notes"],
                row["effective_status"],
            ]
        ).lower()
        player_overview["total"] += 1
        player_overview[row["effective_status"]] += 1
        moderated_players_all.append(row)

    player_has_filter = bool(player_query)
    filtered_players = []
    if player_query:
        filtered_players = moderated_players_all
        query_blob = player_query.lower()
        filtered_players = [row for row in filtered_players if query_blob in row["search_blob"]]
    if player_query and player_status in {"active", "muted", "banned"}:
        filtered_players = [row for row in filtered_players if row["effective_status"] == player_status]

    player_overview["filtered"] = len(filtered_players) if player_has_filter else 0
    player_candidate_limit = 50
    player_candidates = filtered_players[:player_candidate_limit] if player_has_filter else []
    player_candidates_truncated = len(filtered_players) > player_candidate_limit

    selected_player = None
    if player_candidates:
        if player_target:
            selected_player = next(
                (row for row in player_candidates if row["author_key_raw"] == player_target),
                None,
            )
        if not selected_player:
            selected_player = player_candidates[0]

    product_options = []
    for product in all_products:
        option = _product_option(product)
        if option:
            product_options.append(option)

    return render_template(
        "admin_player_community.html",
        project_list=project_list,
        product_list=product_list,
        all_products=all_products,
        product_options=product_options,
        current_project_id=current_project_id,
        current_product_id=current_product_id,
        player_query=player_query,
        player_target=player_target,
        player_status=player_status,
        player_has_filter=player_has_filter,
        player_overview=player_overview,
        player_candidates=player_candidates,
        player_candidates_truncated=player_candidates_truncated,
        player_candidate_limit=player_candidate_limit,
        selected_player=selected_player,
        categories=forum_categories_db,
        news_rows=news_rows,
        welfare_rows=welfare_rows,
        forum_rows=forum_rows,
        csrf_token_value=_get_csrf_token(),
    )


@bp.route("/admin/community/news", methods=["POST"])
@admin_required("community")
def create_or_update_news():
    data = request.get_json(silent=True) or {}
    product_id, error_response, status_code = _require_product_id(data)
    if error_response:
        return error_response, status_code
    data["product_id"] = product_id
    project_id = resolve_project_id((data.get("project_id") or "").strip()) or _project_id_from_product_id(product_id)
    data["project_id"] = project_id
    edit_id = (data.get("edit_id") or "").strip()
    if edit_id:
        item = update_news_item(edit_id, data, reset_publish_status="pending_approval")
        if not item:
            return jsonify({"error": "新闻更新失败"}), 400
        reason = f"编辑新闻：{item.get('title') or ''}"
    else:
        item = create_news_item({**data, "publish_status": "pending_approval"}, session.get("user") or "")
        if not item:
            return jsonify({"error": "新闻创建失败"}), 400
        reason = item.get("title") or ""
    approval_id = create_approval(
        "news_publish",
        session.get("user") or "",
        "news",
        item.get("id") or "",
        reason,
        project_id=project_id,
    )
    set_news_publish_state(item.get("id") or "", "pending_approval", approval_id)
    return _approval_result(item.get("id"), approval_id)


@bp.route("/admin/community/welfare", methods=["POST"])
@admin_required("community")
def create_or_update_welfare():
    data = request.get_json(silent=True) or {}
    product_id, error_response, status_code = _require_product_id(data)
    if error_response:
        return error_response, status_code
    data["product_id"] = product_id
    project_id = resolve_project_id((data.get("project_id") or "").strip()) or _project_id_from_product_id(product_id)
    data["project_id"] = project_id
    edit_id = (data.get("edit_id") or "").strip()
    if edit_id:
        item = update_welfare_item(edit_id, data, reset_publish_status="pending_approval")
        if not item:
            return jsonify({"error": "福利更新失败"}), 400
        reason = f"编辑福利：{item.get('title') or ''}"
    else:
        item = create_welfare_item({**data, "publish_status": "pending_approval"}, session.get("user") or "")
        if not item:
            return jsonify({"error": "福利创建失败"}), 400
        reason = item.get("title") or ""
    approval_id = create_approval(
        "welfare_publish",
        session.get("user") or "",
        "welfare",
        item.get("id") or "",
        reason,
        project_id=project_id,
    )
    set_welfare_publish_state(item.get("id") or "", "pending_approval", approval_id)
    return _approval_result(item.get("id"), approval_id)


@bp.route("/admin/community/forum-post", methods=["POST"])
@admin_required("community")
def create_or_update_forum_post():
    data = request.get_json(silent=True) or {}
    product_id, error_response, status_code = _require_product_id(data)
    if error_response:
        return error_response, status_code
    data["product_id"] = product_id
    project_id = resolve_project_id((data.get("project_id") or "").strip()) or _project_id_from_product_id(product_id)
    data["project_id"] = project_id
    edit_id = (data.get("edit_id") or "").strip()
    if edit_id:
        post = update_forum_post_item(edit_id, data, reset_publish_status="pending_approval")
        if not post:
            return jsonify({"error": "官方帖子更新失败"}), 400
        reason = f"编辑官方帖子：{post.get('title') or ''}"
    else:
        post = create_forum_post({**data, "publish_status": "pending_approval"}, session.get("user") or "")
        if not post:
            return jsonify({"error": "官方帖子创建失败"}), 400
        reason = post.get("title") or ""
    approval_id = create_approval(
        "forum_post_publish",
        session.get("user") or "",
        "forum_post",
        post.get("id") or "",
        reason,
        project_id=project_id,
    )
    set_forum_post_publish_state(post.get("id") or "", "pending_approval", approval_id)
    return _approval_result(post.get("id"), approval_id)


@bp.route("/admin/community/news/<item_id>/delete", methods=["POST"])
@admin_required("community")
def delete_news_item(item_id):
    item = archive_news_item(item_id)
    if not item:
        return jsonify({"error": "新闻不存在"}), 404
    return jsonify({"ok": True})


@bp.route("/admin/community/welfare/<item_id>/delete", methods=["POST"])
@admin_required("community")
def delete_welfare_item(item_id):
    item = archive_welfare_item(item_id)
    if not item:
        return jsonify({"error": "福利不存在"}), 404
    return jsonify({"ok": True})


@bp.route("/admin/community/forum-post/<post_id>/delete", methods=["POST"])
@admin_required("community")
def delete_forum_post_item(post_id):
    item = archive_forum_post_item(post_id)
    if not item:
        return jsonify({"error": "帖子不存在"}), 404
    return jsonify({"ok": True})


@bp.route("/admin/community/forum-post/<post_id>/moderate", methods=["POST"])
@admin_required("community")
def moderate_forum_post(post_id):
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "").strip()
    if action not in {"hide", "restore", "pin", "unpin", "delete"}:
        return jsonify({"error": "不支持的帖子操作"}), 400
    post = moderate_post(post_id, action)
    if not post:
        return jsonify({"error": "帖子不存在"}), 404
    return jsonify({"ok": True, "post": post})


@bp.route("/admin/community/player/<path:author_key>/moderate", methods=["POST"])
@admin_required("community")
def moderate_player_route(author_key):
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "").strip()
    if action not in {"ban", "mute", "unban", "unmute"}:
        return jsonify({"error": "不支持的玩家操作"}), 400
    info = get_player_moderation(author_key)
    result = moderate_player(
        author_key,
        action,
        display_name=info.get("display_name") or author_key,
        note=(data.get("note") or "").strip(),
        duration_hours=int(data.get("duration_hours") or 0),
    )
    return jsonify({"ok": True, "player": result})


@bp.route("/admin/community/portal/player", methods=["POST"])
@admin_required("community")
def save_player_portal():
    payload = request.get_json(silent=True) or request.form.to_dict()
    return jsonify({"ok": True, "content": save_player_portal_content(payload)})


@bp.route("/admin/community/portal/dev", methods=["POST"])
@admin_required("community")
def save_dev_portal():
    payload = request.get_json(silent=True) or request.form.to_dict()
    return jsonify({"ok": True, "content": save_dev_portal_content(payload)})


@bp.route("/admin/community/portal/player", methods=["GET"])
@admin_required("community")
def get_player_portal():
    return jsonify({"ok": True, "content": get_player_portal_content()})


@bp.route("/admin/community/portal/dev", methods=["GET"])
@admin_required("community")
def get_dev_portal():
    return jsonify({"ok": True, "content": get_dev_portal_content()})

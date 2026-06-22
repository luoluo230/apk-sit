# -*- coding: utf-8 -*-
"""Admin site config pages."""

import html
import json
import uuid

from flask import render_template

from models.data import products_db
from services.company_profile import get_company_profile
from services.media_library import normalize_local_media_url, normalize_local_media_urls
from services.player_content import (
    get_active_welfare,
    get_forum_posts,
    get_latest_news,
)
from services.portal_content import get_dev_portal_content, get_player_portal_content
from routes.admin.views.common import clean_display_text

_clean_display_text = clean_display_text

def render_site_config_page():
    company = get_company_profile()
    player_portal = get_player_portal_content()
    dev_portal = get_dev_portal_content()
    def _safe(value, fallback=""):
        return html.escape(_clean_display_text(value, fallback))

    def _parse_ids(value):
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return [v.strip() for v in str(value or "").split(",") if v.strip()]

    def _render_product_options(selected_ids):
        options = []
        for product in (products_db if isinstance(products_db, list) else []):
            pid = str(product.get("id") or "").strip()
            if not pid:
                continue
            label = _clean_display_text(product.get("name") or product.get("title") or pid, pid)
            selected = " selected" if pid in selected_ids else ""
            options.append(f'<option value="{html.escape(pid)}"{selected}>{html.escape(label)}</option>')
        if not options:
            options.append('<option value="" disabled>暂无产品</option>')
        return ''.join(options)

    default_player_modules = [
        {"type": "hero", "title": "Hero", "enabled": True, "order": 0, "size": "full"},
        {"type": "products", "title": "产品入口", "enabled": True, "order": 1},
        {"type": "news", "title": "新闻公告", "enabled": True, "order": 2},
        {"type": "welfare", "title": "福利中心", "enabled": True, "order": 3},
        {"type": "forum", "title": "玩家论坛", "enabled": True, "order": 4},
        {"type": "company", "title": "公司简介", "enabled": True, "order": 5},
        {"type": "media", "title": "视觉展示", "enabled": True, "order": 6},
        {"type": "timeline", "title": "公司历程", "enabled": True, "order": 7},
    ]
    default_dev_modules = [
        {"type": "hero", "title": "Hero", "enabled": True, "order": 0, "size": "full"},
        {"type": "products", "title": "产品入口", "enabled": True, "order": 1},
        {"type": "company", "title": "公司简介", "enabled": True, "order": 2},
        {"type": "media", "title": "视觉展示", "enabled": True, "order": 3},
        {"type": "timeline", "title": "公司历程", "enabled": True, "order": 4},
    ]

    def _normalize_modules(modules, defaults):
        if isinstance(modules, list) and modules:
            cleaned = []
            for item in modules:
                if not isinstance(item, dict):
                    continue
                if not str(item.get("type") or "").strip():
                    continue
                cleaned.append(item)
            if cleaned:
                return cleaned
        return defaults

    module_types = [
        ("hero", "Hero"),
        ("products", "产品入口"),
        ("news", "新闻公告"),
        ("welfare", "福利中心"),
        ("forum", "玩家论坛"),
        ("company", "公司简介"),
        ("media", "视觉展示"),
        ("timeline", "公司历程"),
        ("image", "Image"),
        ("video", "Video"),
        ("text", "Text"),
        ("stat", "Stat"),
    ]

    def _module_type_options(selected):
        return ''.join(
            f'<option value="{mid}"{" selected" if mid == selected else ""}>{label}</option>'
            for mid, label in module_types
        )

    def _size_options(selected):
        sizes = [("full", "整行"), ("half", "半屏"), ("third", "三分之一")]
        return ''.join(
            f'<option value="{val}"{" selected" if val == selected else ""}>{label}</option>'
            for val, label in sizes
        )

    def _render_module_rows(modules):
        rows = []
        for idx, module in enumerate(modules):
            mtype = str(module.get("type") or "products")
            title = html.escape(str(module.get("title") or ""))
            description = html.escape(str(module.get("description") or ""))
            enabled = "checked" if module.get("enabled", True) else ""
            order = module.get("order", idx + 1)
            size = str(module.get("size") or "full")
            limit = module.get("limit", "")
            source = html.escape(str(module.get("source") or ""))
            image_url = html.escape(normalize_local_media_url(module.get("image_url")))
            video_url = html.escape(normalize_local_media_url(module.get("video_url")))
            media_urls = normalize_local_media_urls(module.get("media_urls") or [], max_count=12)
            media_urls = html.escape(", ".join(media_urls))
            cta_text = html.escape(str(module.get("cta_text") or ""))
            cta_link = html.escape(str(module.get("cta_link") or ""))
            rows.append(
                f'''
                <div class="rounded-2xl border border-slate-200 bg-white p-4 space-y-3 cursor-move" data-module-row draggable="true">
                    <div class="grid gap-3 md:grid-cols-2">
                        <div>
                            <label class="text-xs font-semibold text-slate-500">模块类型</label>
                            <select class="module-type mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm">{_module_type_options(mtype)}</select>
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">模块标题</label>
                            <input type="text" value="{title}" class="module-title mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" placeholder="展示标题">
                        </div>
                    </div>
                    <div class="grid gap-3 md:grid-cols-3">
                        <div>
                            <label class="text-xs font-semibold text-slate-500">显示</label>
                            <div class="mt-2 flex items-center gap-2">
                                <input type="checkbox" class="module-enabled" {enabled}>
                                <span class="text-xs text-slate-500">启用</span>
                            </div>
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">排序</label>
                            <input type="number" value="{order}" min="1" class="module-order mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm">
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">数量限制</label>
                            <input type="number" value="{limit}" min="1" class="module-limit mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" placeholder="可选">
                        </div>
                    </div>
                    <div>
                        <label class="text-xs font-semibold text-slate-500">模块描述</label>
                        <textarea class="module-description mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" rows="2" placeholder="模块说明">{description}</textarea>
                    </div>
                    <div class="grid gap-3 md:grid-cols-2">
                        <div>
                            <label class="text-xs font-semibold text-slate-500">样式</label>
                            <select class="module-size mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm">{_size_options(size)}</select>
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">数据来源</label>
                            <input type="text" value="{source}" class="module-source mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" placeholder="如 latest / featured">
                        </div>
                    </div>
                    <div class="grid gap-3 md:grid-cols-2">
                        <div>
                            <label class="text-xs font-semibold text-slate-500">本地图片</label>
                            <input type="text" value="{image_url}" class="module-image-url mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" placeholder="上传后自动填充本地路径" readonly>
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">本地视频</label>
                            <input type="text" value="{video_url}" class="module-video-url mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" placeholder="上传后自动填充本地路径" readonly>
                        </div>
                    </div>
                    <div>
                        <label class="text-xs font-semibold text-slate-500">本地图集</label>
                        <textarea class="module-media-urls mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" rows="2" placeholder="上传后自动填充本地路径，支持多张" readonly>{media_urls}</textarea>
                    </div>
                    <div class="grid gap-3 md:grid-cols-2">
                        <div>
                            <label class="text-xs font-semibold text-slate-500">CTA 文案</label>
                            <input type="text" value="{cta_text}" class="module-cta-text mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" placeholder="按钮文案">
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">CTA 链接</label>
                            <input type="text" value="{cta_link}" class="module-cta-link mt-1 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm" placeholder="按钮链接">
                        </div>
                    </div>
                    <div class="flex items-center justify-between text-xs text-slate-400">
                        <span>拖动卡片可调整模块顺序</span>
                        <button type="button" class="remove-module text-rose-500 hover:text-rose-600">移除</button>
                    </div>
                </div>
                '''
            )
        return ''.join(rows)

    player_modules = _normalize_modules(player_portal.get("home_modules"), default_player_modules)
    dev_modules = _normalize_modules(dev_portal.get("home_modules"), default_dev_modules)
    player_featured_ids = _parse_ids(player_portal.get("featured_product_ids"))
    player_visible_ids = _parse_ids(player_portal.get("visible_product_ids"))
    dev_featured_ids = _parse_ids(dev_portal.get("featured_product_ids"))
    dev_visible_ids = _parse_ids(dev_portal.get("visible_product_ids"))
    timeline_json = html.escape(json.dumps(company.get('timeline', []), ensure_ascii=False, indent=2))
    achievements_json = html.escape(json.dumps(company.get('achievements', []), ensure_ascii=False, indent=2))
    player_options = _render_product_options(player_visible_ids)
    player_featured_options = _render_product_options(player_featured_ids)
    dev_options = _render_product_options(dev_visible_ids)
    dev_featured_options = _render_product_options(dev_featured_ids)
    template_row = _render_module_rows([{"type": "products", "title": "", "enabled": True, "order": 1, "size": "full"}])
    content = f"""
    <section class="space-y-6">
        <div class="flex items-end justify-between gap-4">
            <div>
                <p class="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">\u914d\u7f6e\u4e2d\u5fc3</p>
                <h2 class="mt-1 text-2xl font-semibold text-slate-900">\u5b98\u7f51\u4e0e\u5916\u90e8\u6a21\u5757\u914d\u7f6e</h2>
                <p class="mt-1 text-sm text-slate-500">\u5c06\u516c\u53f8\u7b80\u4ecb\u3001\u73a9\u5bb6\u5b98\u7f51\u3001\u5f00\u53d1\u8005\u5b98\u7f51\u548c\u5916\u90e8\u5165\u53e3\u7edf\u4e00\u6536\u53e3\uff0c\u907f\u514d\u7ad9\u70b9\u914d\u7f6e\u548c\u5185\u5bb9\u8fd0\u8425\u6df7\u5728\u4e00\u8d77\u3002</p>
            </div>
            <div class="flex items-center gap-2">
                <a href="/admin/site-config/editor/player" class="rounded-xl border border-violet-200 bg-violet-50 px-4 py-1.5 text-sm font-semibold text-violet-700">\u73a9\u5bb6\u5b98\u7f51\u53ef\u89c6\u5316\u7f16\u8f91\u5668</a>
                <a href="/admin/site-config/editor/dev" class="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-1.5 text-sm font-semibold text-emerald-700">\u5f00\u53d1\u8005\u5b98\u7f51\u53ef\u89c6\u5316\u7f16\u8f91\u5668</a>
                <a href="/admin" class="rounded-xl border border-slate-200 bg-white px-4 py-1.5 text-sm font-medium text-slate-700">\u8fd4\u56de\u7ba1\u7406\u4e2d\u5fc3</a>
            </div>
        </div>
        <div class="grid gap-6 xl:grid-cols-3">
            <form id="companyProfileForm" class="space-y-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 class="text-lg font-semibold text-slate-900">\u516c\u53f8\u7b80\u4ecb\u9875</h3>
                <input name="company_name" value="{_safe(company.get('company_name'), '星云游戏站')}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u516c\u53f8\u540d\u79f0">
                <input name="hero_eyebrow" value="{_safe(company.get('hero_eyebrow'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u7709\u6807\u6807\u9898">
                <textarea name="hero_title" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="3" placeholder="\u4e3b\u6807\u9898">{_safe(company.get('hero_title'))}</textarea>
                <textarea name="hero_summary" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="4" placeholder="\u54c1\u724c\u6458\u8981">{_safe(company.get('hero_summary'))}</textarea>
                <textarea name="company_intro" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="5" placeholder="\u516c\u53f8\u4ecb\u7ecd">{_safe(company.get('company_intro'))}</textarea>
                <input name="mission_title" value="{_safe(company.get('mission_title'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u4f7f\u547d\u6807\u9898">
                <textarea name="mission_body" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="4" placeholder="\u4f7f\u547d\u6b63\u6587">{_safe(company.get('mission_body'))}</textarea>
                <textarea name="timeline_json" class="w-full rounded-2xl border border-slate-200 px-4 py-3 font-mono text-xs" rows="6" placeholder="\u65f6\u95f4\u7ebf JSON">{timeline_json}</textarea>
                <textarea name="achievements_json" class="w-full rounded-2xl border border-slate-200 px-4 py-3 font-mono text-xs" rows="5" placeholder="\u6210\u5c31 JSON">{achievements_json}</textarea>
                <button class="rounded-full bg-slate-900 px-5 py-3 font-bold text-white">\u4fdd\u5b58\u516c\u53f8\u7b80\u4ecb</button>
                <div id="companyProfileResult" class="text-sm text-slate-500"></div>
            </form>
            <form id="playerPortalConfigForm" class="space-y-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 class="text-lg font-semibold text-slate-900">\u73a9\u5bb6\u5b98\u7f51\u914d\u7f6e</h3>
                <input name="site_name" value="{_safe(player_portal.get('site_name'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u7ad9\u70b9\u540d\u79f0">
                <input name="site_subtitle" value="{_safe(player_portal.get('site_subtitle'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u526f\u6807\u9898">
                <input name="logo_icon" value="{_safe(player_portal.get('logo_icon'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="Logo \u56fe\u6807">
                <input name="hero_image_url" value="{_safe(player_portal.get('hero_image_url'))}" class="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3" placeholder="Hero \u672c\u5730\u56fe\u7247\u8def\u5f84\uff08\u4e0a\u4f20\u540e\u81ea\u52a8\u586b\u5199\uff09" readonly>
                <input name="hero_video_url" value="{_safe(player_portal.get('hero_video_url'))}" class="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3" placeholder="Hero \u672c\u5730\u89c6\u9891\u8def\u5f84\uff08\u4e0a\u4f20\u540e\u81ea\u52a8\u586b\u5199\uff09" readonly>
                <textarea name="hero_gallery_urls" class="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3" rows="2" placeholder="Hero \u672c\u5730\u56fe\u96c6\u8def\u5f84\uff08\u4e0a\u4f20\u540e\u81ea\u52a8\u586b\u5199\uff09" readonly>{_safe(",".join(player_portal.get('hero_gallery_urls') or []))}</textarea>
                <p class="text-xs text-slate-500">\u8bf4\u660e\uff1a\u8fd9\u91cc\u53ea\u5141\u8bb8\u672c\u5730\u4e0a\u4f20\u5a92\u4f53\uff0c\u5916\u94fe URL \u4f1a\u88ab\u540e\u7aef\u81ea\u52a8\u8fc7\u6ee4\u3002</p>
                <input name="nav_about" value="{_safe(player_portal.get('nav_about'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u516c\u53f8\u7b80\u4ecb\u5bfc\u822a\u6587\u6848">
                <input name="nav_games" value="{_safe(player_portal.get('nav_games'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u6e38\u620f\u4ea7\u54c1\u5bfc\u822a\u6587\u6848">
                <textarea name="hero_title" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="3" placeholder="Hero \u6807\u9898">{_safe(player_portal.get('hero_title'))}</textarea>
                <textarea name="hero_description" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="4" placeholder="Hero \u63cf\u8ff0">{_safe(player_portal.get('hero_description'))}</textarea>
                <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">\u4ea7\u54c1\u5c55\u793a\u8303\u56f4</p>
                    <div class="mt-3 space-y-3">
                        <div>
                            <label class="text-xs font-semibold text-slate-500">\u5c55\u793a\u4ea7\u54c1\uff08\u591a\u9009\uff09</label>
                            <select name="visible_product_ids" multiple class="mt-2 h-28 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm">{player_options}</select>
                            <p class="mt-2 text-xs text-slate-500">\u672a\u9009\u62e9\u5219\u5c55\u793a\u5168\u90e8\u9879\u76ee</p>
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">\u4e3b\u63a8\u4ea7\u54c1\uff08\u591a\u9009\uff09</label>
                            <select name="featured_product_ids" multiple class="mt-2 h-24 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm">{player_featured_options}</select>
                            <p class="mt-2 text-xs text-slate-500">\u9996\u4e2a\u4e3b\u63a8\u4ea7\u54c1\u5c06\u4f5c\u4e3a\u9996\u9875\u4e3b\u89c6\u89c9</p>
                        </div>
                    </div>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div class="flex items-center justify-between">
                        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">\u9996\u9875\u6a21\u5757\u7f16\u6392</p>
                        <button type="button" class="add-module text-xs font-semibold text-indigo-600">\u6dfb\u52a0\u6a21\u5757</button>
                    </div>
                    <div id="playerModules" class="mt-3 space-y-3">
                        {_render_module_rows(player_modules)}
                    </div>
                </div>
                <button class="rounded-full bg-violet-600 px-5 py-3 font-bold text-white">\u4fdd\u5b58\u73a9\u5bb6\u5b98\u7f51</button>
                <div id="playerPortalConfigResult" class="text-sm text-slate-500"></div>
            </form>
            <form id="devPortalConfigForm" class="space-y-4 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <h3 class="text-lg font-semibold text-slate-900">\u5f00\u53d1\u8005\u5b98\u7f51\u914d\u7f6e</h3>
                <input name="site_name" value="{_safe(dev_portal.get('site_name'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u7ad9\u70b9\u540d\u79f0">
                <input name="site_subtitle" value="{_safe(dev_portal.get('site_subtitle'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u526f\u6807\u9898">
                <input name="logo_icon" value="{_safe(dev_portal.get('logo_icon'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="Logo \u56fe\u6807">
                <input name="hero_image_url" value="{_safe(dev_portal.get('hero_image_url'))}" class="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3" placeholder="Hero \u672c\u5730\u56fe\u7247\u8def\u5f84\uff08\u4e0a\u4f20\u540e\u81ea\u52a8\u586b\u5199\uff09" readonly>
                <input name="hero_video_url" value="{_safe(dev_portal.get('hero_video_url'))}" class="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3" placeholder="Hero \u672c\u5730\u89c6\u9891\u8def\u5f84\uff08\u4e0a\u4f20\u540e\u81ea\u52a8\u586b\u5199\uff09" readonly>
                <textarea name="hero_gallery_urls" class="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3" rows="2" placeholder="Hero \u672c\u5730\u56fe\u96c6\u8def\u5f84\uff08\u4e0a\u4f20\u540e\u81ea\u52a8\u586b\u5199\uff09" readonly>{_safe(",".join(dev_portal.get('hero_gallery_urls') or []))}</textarea>
                <p class="text-xs text-slate-500">\u8bf4\u660e\uff1a\u8fd9\u91cc\u53ea\u5141\u8bb8\u672c\u5730\u4e0a\u4f20\u5a92\u4f53\uff0c\u5916\u94fe URL \u4f1a\u88ab\u540e\u7aef\u81ea\u52a8\u8fc7\u6ee4\u3002</p>
                <input name="nav_games" value="{_safe(dev_portal.get('nav_games'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u6e38\u620f\u9635\u5bb9\u6587\u6848">
                <input name="nav_showcase" value="{_safe(dev_portal.get('nav_showcase'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u89c6\u89c9\u5c55\u793a\u6587\u6848">
                <input name="nav_news" value="{_safe(dev_portal.get('nav_news'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u65b0\u95fb\u516c\u544a\u6587\u6848">
                <input name="nav_welfare" value="{_safe(dev_portal.get('nav_welfare'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u798f\u5229\u4e2d\u5fc3\u6587\u6848">
                <input name="nav_forum" value="{_safe(dev_portal.get('nav_forum'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u73a9\u5bb6\u8bba\u575b\u6587\u6848">
                <input name="nav_download" value="{_safe(dev_portal.get('nav_download'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="\u4e0b\u8f7d\u4e2d\u5fc3\u6587\u6848">
                <input name="workspace_badge" value="{_safe(dev_portal.get('workspace_badge'))}" class="w-full rounded-2xl border border-slate-200 px-4 py-3" placeholder="Workspace \u6807\u8bc6">
                <textarea name="workspace_title" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="2" placeholder="Workspace \u4e3b\u6807\u9898">{_safe(dev_portal.get('workspace_title'))}</textarea>
                <textarea name="workspace_intro" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="3" placeholder="Workspace \u7b80\u4ecb">{_safe(dev_portal.get('workspace_intro'))}</textarea>
                <textarea name="hero_title" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="3" placeholder="Hero \u6807\u9898">{_safe(dev_portal.get('hero_title'))}</textarea>
                <textarea name="hero_description" class="w-full rounded-2xl border border-slate-200 px-4 py-3" rows="4" placeholder="Hero \u63cf\u8ff0">{_safe(dev_portal.get('hero_description'))}</textarea>
                <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">\u4ea7\u54c1\u5c55\u793a\u8303\u56f4</p>
                    <div class="mt-3 space-y-3">
                        <div>
                            <label class="text-xs font-semibold text-slate-500">\u5c55\u793a\u4ea7\u54c1\uff08\u591a\u9009\uff09</label>
                            <select name="visible_product_ids" multiple class="mt-2 h-28 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm">{dev_options}</select>
                            <p class="mt-2 text-xs text-slate-500">\u672a\u9009\u62e9\u5219\u5c55\u793a\u5168\u90e8\u9879\u76ee</p>
                        </div>
                        <div>
                            <label class="text-xs font-semibold text-slate-500">\u4e3b\u63a8\u4ea7\u54c1\uff08\u591a\u9009\uff09</label>
                            <select name="featured_product_ids" multiple class="mt-2 h-24 w-full rounded-xl border border-slate-200 px-3 py-1.5 text-sm">{dev_featured_options}</select>
                            <p class="mt-2 text-xs text-slate-500">\u9996\u4e2a\u4e3b\u63a8\u4ea7\u54c1\u5c06\u4f5c\u4e3a\u9996\u9875\u4e3b\u89c6\u89c9</p>
                        </div>
                    </div>
                </div>
                <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div class="flex items-center justify-between">
                        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">\u9996\u9875\u6a21\u5757\u7f16\u6392</p>
                        <button type="button" class="add-module text-xs font-semibold text-indigo-600">\u6dfb\u52a0\u6a21\u5757</button>
                    </div>
                    <div id="devModules" class="mt-3 space-y-3">
                        {_render_module_rows(dev_modules)}
                    </div>
                </div>
                <button class="rounded-full bg-emerald-600 px-5 py-3 font-bold text-white">\u4fdd\u5b58\u5f00\u53d1\u8005\u5b98\u7f51</button>
                <div id="devPortalConfigResult" class="text-sm text-slate-500"></div>
            </form>
        </div>
    </section>
    <script>
    function collectModules(form) {{
        var rows = form.querySelectorAll('[data-module-row]');
        var modules = [];
        rows.forEach(function(row, index) {{
            var type = (row.querySelector('.module-type') || {{}}).value || '';
            if (!type) return;
            var orderValue = parseInt((row.querySelector('.module-order') || {{}}).value || '', 10);
            var limitValue = parseInt((row.querySelector('.module-limit') || {{}}).value || '', 10);
            modules.push({{
                type: type.trim(),
                title: ((row.querySelector('.module-title') || {{}}).value || '').trim(),
                description: ((row.querySelector('.module-description') || {{}}).value || '').trim(),
                enabled: (row.querySelector('.module-enabled') || {{}}).checked,
                order: isNaN(orderValue) ? (index + 1) : orderValue,
                limit: isNaN(limitValue) ? '' : limitValue,
                size: ((row.querySelector('.module-size') || {{}}).value || '').trim(),
                source: ((row.querySelector('.module-source') || {{}}).value || '').trim(),
                image_url: ((row.querySelector('.module-image-url') || {{}}).value || '').trim(),
                video_url: ((row.querySelector('.module-video-url') || {{}}).value || '').trim(),
                media_urls: String(((row.querySelector('.module-media-urls') || {{}}).value || '')).replace(/\\n/g, ',').split(',').map(function(item) {{ return item.trim(); }}).filter(Boolean),
                cta_text: ((row.querySelector('.module-cta-text') || {{}}).value || '').trim(),
                cta_link: ((row.querySelector('.module-cta-link') || {{}}).value || '').trim(),
            }});
        }});
        return modules;
    }}
    function bindModuleEditor(formId, containerId) {{
        var form = document.getElementById(formId);
        var container = document.getElementById(containerId);
        var addBtn = form.querySelector('.add-module');
        var dragging = null;
        function syncOrder() {{
            var rows = container.querySelectorAll('[data-module-row]');
            rows.forEach(function(row, idx) {{
                var orderInput = row.querySelector('.module-order');
                if (orderInput) orderInput.value = idx + 1;
            }});
        }}
        if (addBtn) {{
            addBtn.addEventListener('click', function() {{
                var wrapper = document.createElement('div');
                wrapper.innerHTML = `{template_row}`;
                var row = wrapper.firstElementChild;
                if (row) {{
                    container.appendChild(row);
                    enhanceModuleRow(row, 'portal-module', formId === 'playerPortalConfigForm' ? 'player-portal' : 'dev-portal');
                }}
                syncOrder();
            }});
        }}
        container.addEventListener('click', function(e) {{
            var btn = e.target.closest('.remove-module');
            if (btn) {{
                var row = btn.closest('[data-module-row]');
                if (row) row.remove();
                syncOrder();
            }}
        }});
        container.addEventListener('dragstart', function(e) {{
            var row = e.target.closest('[data-module-row]');
            if (!row) return;
            dragging = row;
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', '');
        }});
        container.addEventListener('dragover', function(e) {{
            if (!dragging) return;
            e.preventDefault();
            var row = e.target.closest('[data-module-row]');
            if (!row || row === dragging) return;
            var rect = row.getBoundingClientRect();
            var next = (e.clientY - rect.top) > rect.height / 2;
            container.insertBefore(dragging, next ? row.nextSibling : row);
        }});
        container.addEventListener('drop', function(e) {{
            if (!dragging) return;
            e.preventDefault();
            dragging = null;
            syncOrder();
        }});
        container.addEventListener('dragend', function() {{
            dragging = null;
            syncOrder();
        }});
    }}
    function collectMultiSelect(form, name) {{
        var select = form.querySelector('select[name="' + name + '"]');
        if (!select) return '';
        var values = [];
        Array.prototype.forEach.call(select.selectedOptions, function(opt) {{
            values.push(opt.value);
        }});
        return values.join(',');
    }}
    function escapeHtmlText(value) {{
        return String(value || '').replace(/[&<>"]/g, function(ch) {{
            return {{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }}[ch] || ch;
        }});
    }}
    function renderMediaPreview(target, urls, kind) {{
        if (!target) return;
        var list = Array.isArray(urls) ? urls.filter(Boolean) : (urls ? [urls] : []);
        if (!list.length) {{
            target.innerHTML = '<div class="text-xs text-slate-400">未选择本地媒体</div>';
            return;
        }}
        target.innerHTML = list.map(function(url) {{
            var safe = escapeHtmlText(url);
            if (kind === 'video') {{
                return '<div class="rounded-xl border border-slate-200 bg-slate-50 p-2"><video src="' + safe + '" controls class="h-32 w-full rounded-lg bg-black object-cover"></video><p class="mt-2 truncate text-[11px] text-slate-500">' + safe + '</p></div>';
            }}
            return '<div class="rounded-xl border border-slate-200 bg-slate-50 p-2"><img src="' + safe + '" class="h-28 w-full rounded-lg object-cover" alt=""><p class="mt-2 truncate text-[11px] text-slate-500">' + safe + '</p></div>';
        }}).join('');
    }}
    function uploadMediaFiles(files, scope, bucket) {{
        var formData = new FormData();
        Array.prototype.forEach.call(files || [], function(file) {{
            formData.append('files', file);
        }});
        formData.append('scope', scope || 'site-config');
        formData.append('bucket', bucket || 'shared');
        return fetch('/admin/media/upload', {{
            method: 'POST',
            body: formData,
            credentials: 'same-origin'
        }}).then(function(r) {{ return r.json(); }});
    }}
    function attachSingleMediaUploader(input, options) {{
        if (!input || input.dataset.uploaderReady === '1') return;
        input.dataset.uploaderReady = '1';
        var kind = options.kind === 'video' ? 'video' : 'image';
        var wrap = document.createElement('div');
        wrap.className = 'mt-2 rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-3';
        wrap.innerHTML = '' +
            '<label class="block text-xs font-semibold text-slate-500">本地' + (kind === 'video' ? '视频' : '图片') + '</label>' +
            '<input type="file" accept="' + (kind === 'video' ? 'video/*' : 'image/*') + '" class="mt-2 block w-full text-sm text-slate-600">' +
            '<div class="mt-3"></div>';
        input.insertAdjacentElement('afterend', wrap);
        var picker = wrap.querySelector('input[type="file"]');
        var preview = wrap.querySelector('div');
        renderMediaPreview(preview, input.value || '', kind);
        picker.addEventListener('change', function() {{
            if (!picker.files || !picker.files.length) return;
            preview.innerHTML = '<div class="text-xs text-slate-500">上传中...</div>';
            uploadMediaFiles(picker.files, options.scope, options.bucket).then(function(data) {{
                if (!data || data.error || !data.file) {{
                    preview.innerHTML = '<div class="text-xs text-rose-500">' + escapeHtmlText((data && data.error) || '上传失败') + '</div>';
                    return;
                }}
                input.value = data.file.url || '';
                renderMediaPreview(preview, input.value || '', kind);
            }});
        }});
    }}
    function attachGalleryUploader(textarea, options) {{
        if (!textarea || textarea.dataset.uploaderReady === '1') return;
        textarea.dataset.uploaderReady = '1';
        var wrap = document.createElement('div');
        wrap.className = 'mt-2 rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-3';
        wrap.innerHTML = '' +
            '<label class="block text-xs font-semibold text-slate-500">本地图集</label>' +
            '<input type="file" accept="image/*" multiple class="mt-2 block w-full text-sm text-slate-600">' +
            '<div class="mt-3 grid gap-3 sm:grid-cols-2"></div>';
        textarea.insertAdjacentElement('afterend', wrap);
        var picker = wrap.querySelector('input[type="file"]');
        var preview = wrap.querySelector('div');
        function readUrls() {{
            return String(textarea.value || '').replace(/\\n/g, ',').split(',').map(function(item) {{ return item.trim(); }}).filter(Boolean);
        }}
        function writeUrls(urls) {{
            textarea.value = (urls || []).join(',');
            renderMediaPreview(preview, urls || [], 'image');
        }}
        writeUrls(readUrls());
        picker.addEventListener('change', function() {{
            if (!picker.files || !picker.files.length) return;
            preview.innerHTML = '<div class="text-xs text-slate-500">上传中...</div>';
            uploadMediaFiles(picker.files, options.scope, options.bucket).then(function(data) {{
                if (!data || data.error || !data.files) {{
                    preview.innerHTML = '<div class="text-xs text-rose-500">' + escapeHtmlText((data && data.error) || '上传失败') + '</div>';
                    return;
                }}
                var urls = readUrls().concat((data.files || []).map(function(item) {{ return item.url; }}).filter(Boolean));
                writeUrls(urls);
            }});
        }});
    }}
    function enhanceModuleRow(row, scope, bucket) {{
        if (!row || row.dataset.mediaReady === '1') return;
        row.dataset.mediaReady = '1';
        attachSingleMediaUploader(row.querySelector('.module-image-url'), {{ kind: 'image', scope: scope, bucket: bucket }});
        attachSingleMediaUploader(row.querySelector('.module-video-url'), {{ kind: 'video', scope: scope, bucket: bucket }});
        attachGalleryUploader(row.querySelector('.module-media-urls'), {{ scope: scope, bucket: bucket }});
    }}
    function enhancePortalForm(formId, bucket) {{
        var form = document.getElementById(formId);
        if (!form) return;
        attachSingleMediaUploader(form.querySelector('[name="hero_image_url"]'), {{ kind: 'image', scope: 'portal', bucket: bucket }});
        attachSingleMediaUploader(form.querySelector('[name="hero_video_url"]'), {{ kind: 'video', scope: 'portal', bucket: bucket }});
        attachGalleryUploader(form.querySelector('[name="hero_gallery_urls"]'), {{ scope: 'portal', bucket: bucket }});
        form.querySelectorAll('[data-module-row]').forEach(function(row) {{
            enhanceModuleRow(row, 'portal-module', bucket);
        }});
    }}
    function bindSiteConfigForm(formId, endpoint, resultId, transform) {{
        var form = document.getElementById(formId);
        form.addEventListener('submit', function(e) {{
            e.preventDefault();
            var fd = new FormData(form);
            var payload = transform(fd, form);
            fetch(endpoint, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                credentials: 'same-origin',
                body: JSON.stringify(payload)
            }}).then(function(r) {{ return r.json(); }}).then(function(d) {{
                document.getElementById(resultId).textContent = d.error || '\u5df2\u4fdd\u5b58\uff0c\u5237\u65b0\u540e\u53ef\u67e5\u770b\u6700\u65b0\u6548\u679c';
            }});
        }});
    }}
    bindModuleEditor('playerPortalConfigForm', 'playerModules');
    bindModuleEditor('devPortalConfigForm', 'devModules');
    enhancePortalForm('playerPortalConfigForm', 'player-portal');
    enhancePortalForm('devPortalConfigForm', 'dev-portal');
    bindSiteConfigForm('companyProfileForm', '/admin/site-config/company', 'companyProfileResult', function(fd) {{
        var timeline = [];
        var achievements = [];
        try {{ timeline = JSON.parse(fd.get('timeline_json') || '[]'); }} catch (e) {{}}
        try {{ achievements = JSON.parse(fd.get('achievements_json') || '[]'); }} catch (e) {{}}
        return {{
            company_name: fd.get('company_name') || '',
            hero_eyebrow: fd.get('hero_eyebrow') || '',
            hero_title: fd.get('hero_title') || '',
            hero_summary: fd.get('hero_summary') || '',
            company_intro: fd.get('company_intro') || '',
            mission_title: fd.get('mission_title') || '',
            mission_body: fd.get('mission_body') || '',
            timeline: timeline,
            achievements: achievements
        }};
    }});
    bindSiteConfigForm('playerPortalConfigForm', '/admin/site-config/portal/player', 'playerPortalConfigResult', function(fd, form) {{
        var payload = Object.fromEntries(fd.entries());
        payload.visible_product_ids = collectMultiSelect(form, 'visible_product_ids');
        payload.featured_product_ids = collectMultiSelect(form, 'featured_product_ids');
        payload.hero_gallery_urls = String(fd.get('hero_gallery_urls') || '').replace(/\\n/g, ',').split(',').map(function(item) {{ return item.trim(); }}).filter(Boolean);
        payload.home_modules = collectModules(form);
        return payload;
    }});
    bindSiteConfigForm('devPortalConfigForm', '/admin/site-config/portal/dev', 'devPortalConfigResult', function(fd, form) {{
        var payload = Object.fromEntries(fd.entries());
        payload.visible_product_ids = collectMultiSelect(form, 'visible_product_ids');
        payload.featured_product_ids = collectMultiSelect(form, 'featured_product_ids');
        payload.hero_gallery_urls = String(fd.get('hero_gallery_urls') || '').replace(/\\n/g, ',').split(',').map(function(item) {{ return item.trim(); }}).filter(Boolean);
        payload.home_modules = collectModules(form);
        return payload;
    }});
    </script>
    """
    return _admin_layout(content, '\u5b98\u7f51\u4e0e\u5916\u90e8\u6a21\u5757\u914d\u7f6e', back_href='/admin')


def _visual_editor_default_modules(portal_kind):
    if portal_kind == 'player':
        return [
            {"type": "hero", "title": "首页主视觉", "enabled": True, "order": 1},
            {"type": "products", "title": "游戏产品", "enabled": True, "order": 2},
            {"type": "news", "title": "新闻公告", "enabled": True, "order": 3},
            {"type": "welfare", "title": "福利中心", "enabled": True, "order": 4},
            {"type": "forum", "title": "玩家论坛", "enabled": True, "order": 5},
            {"type": "company", "title": "公司简介", "enabled": True, "order": 6},
            {"type": "media", "title": "视觉展示", "enabled": True, "order": 7},
            {"type": "timeline", "title": "公司历程", "enabled": True, "order": 8},
        ]
    return [
        {"type": "hero", "title": "首页主视觉", "enabled": True, "order": 1},
        {"type": "products", "title": "产品矩阵", "enabled": True, "order": 2},
        {"type": "company", "title": "品牌介绍", "enabled": True, "order": 3},
        {"type": "media", "title": "视觉展示", "enabled": True, "order": 4},
        {"type": "timeline", "title": "发展历程", "enabled": True, "order": 5},
    ]


def _visual_editor_default_layout(module_type, index):
    defaults = {
        'hero': {'x': 1, 'y': 1, 'w': 8, 'h': 5, 'z': 1},
        'products': {'x': 1, 'y': 6, 'w': 5, 'h': 4, 'z': 1},
        'news': {'x': 6, 'y': 6, 'w': 4, 'h': 2, 'z': 2},
        'welfare': {'x': 10, 'y': 6, 'w': 3, 'h': 2, 'z': 2},
        'forum': {'x': 6, 'y': 8, 'w': 4, 'h': 3, 'z': 2},
        'company': {'x': 1, 'y': 10, 'w': 4, 'h': 3, 'z': 1},
        'media': {'x': 5, 'y': 10, 'w': 5, 'h': 3, 'z': 1},
        'timeline': {'x': 10, 'y': 8, 'w': 3, 'h': 5, 'z': 1},
        'image': {'x': 1, 'y': 14 + (index * 2), 'w': 4, 'h': 3, 'z': 1},
        'video': {'x': 5, 'y': 14 + (index * 2), 'w': 4, 'h': 3, 'z': 1},
        'text': {'x': 9, 'y': 14 + (index * 2), 'w': 4, 'h': 2, 'z': 1},
        'stat': {'x': 9, 'y': 16 + (index * 2), 'w': 4, 'h': 2, 'z': 2},
    }
    return dict(defaults.get(module_type, {'x': 1, 'y': 14 + (index * 2), 'w': 4, 'h': 3, 'z': 1}))


def _visual_editor_normalize_modules(modules, portal_kind):
    if not isinstance(modules, list) or not modules:
        modules = list(_visual_editor_default_modules(portal_kind))
    cleaned = []
    for index, item in enumerate(modules):
        if not isinstance(item, dict):
            continue
        module_type = str(item.get('type') or '').strip()
        if not module_type:
            continue
        layout = item.get('layout') if isinstance(item.get('layout'), dict) else {}
        fallback = _visual_editor_default_layout(module_type, index)

        def _layout_value(name, minimum, maximum, fallback_value):
            value = layout.get(name, item.get(name))
            try:
                value = int(value)
            except (TypeError, ValueError):
                value = fallback_value
            return max(minimum, min(maximum, value))

        width = _layout_value('w', 1, 12, fallback['w'])
        x = _layout_value('x', 1, 12, fallback['x'])
        x = min(x, max(1, 13 - width))
        height = _layout_value('h', 1, 12, fallback['h'])
        y = _layout_value('y', 1, 80, fallback['y'])
        z = _layout_value('z', 0, 20, fallback['z'])
        media_urls = normalize_local_media_urls(item.get('media_urls') or [], max_count=12)

        cleaned.append(
            {
                'id': str(item.get('id') or f'module-{uuid.uuid4().hex[:8]}'),
                'type': module_type,
                'title': str(item.get('title') or '').strip(),
                'description': str(item.get('description') or '').strip(),
                'enabled': item.get('enabled', True) is not False,
                'order': index + 1,
                'limit': item.get('limit') if str(item.get('limit') or '').strip() else '',
                'size': str(item.get('size') or 'full').strip() or 'full',
                'source': str(item.get('source') or '').strip(),
                'image_url': normalize_local_media_url(item.get('image_url')),
                'video_url': normalize_local_media_url(item.get('video_url')),
                'media_urls': media_urls,
                'cta_text': str(item.get('cta_text') or '').strip(),
                'cta_link': str(item.get('cta_link') or '').strip(),
                'layout': {'x': x, 'y': y, 'w': width, 'h': height, 'z': z},
            }
        )
    return cleaned


def _visual_editor_product_options():
    options = []
    for product in (products_db if isinstance(products_db, list) else []):
        product_id = str(product.get('id') or '').strip()
        if not product_id:
            continue
        name = _clean_display_text(product.get('name') or product.get('title') or product_id, product_id)
        options.append({'id': product_id, 'name': name})
    return options


def _visual_editor_preview_data():
    return {
        'news': list(get_latest_news(limit=6) or []),
        'welfare': list(get_active_welfare(limit=6) or []),
        'forum': list(get_forum_posts(limit=6) or []),
        'company': get_company_profile(),
    }


def render_site_config_visual_editor(portal_kind, get_csrf_token):
    if portal_kind not in ('player', 'dev'):
        return _admin_layout('<div class="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-rose-700">未知官网类型</div>', '可视化官网编辑器')

    company = get_company_profile()
    portal = get_player_portal_content() if portal_kind == 'player' else get_dev_portal_content()
    modules = _visual_editor_normalize_modules(portal.get('home_modules'), portal_kind)
    product_options = _visual_editor_product_options()
    portal_label = '玩家官网' if portal_kind == 'player' else '开发者官网'
    company_name = _clean_display_text(company.get('company_name') or portal.get('site_name') or '星云游戏站', '星云游戏站')
    return render_template(
        'site_visual_editor.html',
        company_name=company_name,
        portal_kind=portal_kind,
        portal_label=portal_label,
        portal_content=portal,
        modules=modules,
        module_types=[
            {'type': 'hero', 'label': '首页主视觉'},
            {'type': 'products', 'label': '产品入口'},
            {'type': 'news', 'label': '新闻公告'},
            {'type': 'welfare', 'label': '福利中心'},
            {'type': 'forum', 'label': '玩家论坛'},
            {'type': 'company', 'label': '公司简介'},
            {'type': 'media', 'label': '视觉展示'},
            {'type': 'timeline', 'label': '公司历程'},
            {'type': 'image', 'label': '图片模块'},
            {'type': 'video', 'label': '视频模块'},
            {'type': 'text', 'label': '文案模块'},
            {'type': 'stat', 'label': '指标模块'},
        ],
        product_options=product_options,
        preview_data=_visual_editor_preview_data(),
        csrf_token_value=get_csrf_token(),
    )


# API registration alias
visual_editor_normalize_modules = _visual_editor_normalize_modules

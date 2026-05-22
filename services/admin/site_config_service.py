"""Site config save service."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from repositories.admin import site_config_repo
from services.media_library import normalize_local_media_url, normalize_local_media_urls


def save_company(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    site_config_repo.save_company(payload)
    return {"ok": True}, 200


def save_portal(portal_kind: str, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if portal_kind == "player":
        site_config_repo.save_player_portal(payload)
    elif portal_kind == "dev":
        site_config_repo.save_dev_portal(payload)
    else:
        return {"error": "未知官网类型"}, 400
    return {"ok": True}, 200


def save_visual_editor(portal_kind: str, payload: Dict[str, Any], normalize_modules_fn) -> Tuple[Dict[str, Any], int]:
    if portal_kind not in ("player", "dev"):
        return {"error": "未知官网类型"}, 400

    modules = normalize_modules_fn(payload.get("home_modules"), portal_kind)
    hero_gallery_urls = normalize_local_media_urls(payload.get("hero_gallery_urls") or [], max_count=12)

    common_keys = [
        "site_name",
        "site_subtitle",
        "logo_icon",
        "hero_image_url",
        "hero_video_url",
        "hero_title",
        "hero_description",
        "visible_product_ids",
        "featured_product_ids",
    ]
    player_keys = ["nav_about", "nav_games", "hero_badge", "hero_button"]
    dev_keys = [
        "nav_games",
        "nav_showcase",
        "nav_news",
        "nav_welfare",
        "nav_forum",
        "nav_download",
        "hero_badge",
        "primary_button",
        "secondary_button",
        "workspace_badge",
        "workspace_title",
        "workspace_intro",
    ]
    allowed_keys = common_keys + (player_keys if portal_kind == "player" else dev_keys)

    cleaned_payload = {
        "layout_mode": str(payload.get("layout_mode") or "visual").strip() or "visual",
        "hero_image_url": normalize_local_media_url(payload.get("hero_image_url")),
        "hero_video_url": normalize_local_media_url(payload.get("hero_video_url")),
    }
    for key in allowed_keys:
        if key in ("hero_image_url", "hero_video_url"):
            continue
        if key in payload:
            cleaned_payload[key] = payload.get(key)
    cleaned_payload["hero_gallery_urls"] = hero_gallery_urls
    cleaned_payload["home_modules"] = modules

    if portal_kind == "player":
        site_config_repo.save_player_portal(cleaned_payload)
    else:
        site_config_repo.save_dev_portal(cleaned_payload)
    return {"ok": True, "message": "可视化布局已保存"}, 200

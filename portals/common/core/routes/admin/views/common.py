# -*- coding: utf-8 -*-
"""Shared helpers for admin view modules."""

from models.data import can_view_project, projects_db, products_db
from services.player_content import forum_posts_db, player_news_db, player_welfare_db


def clean_display_text(value, fallback=""):
    text = "" if value is None else str(value).strip()
    if not text:
        return fallback
    question_ratio = text.count("?") / max(len(text), 1)
    if question_ratio >= 0.35 or "锟" in text or "�" in text:
        return fallback or text.replace("?", "").strip() or fallback
    return text


def visible_project_choices(username):
    rows = []
    for project_id, item in (projects_db or {}).items():
        if can_view_project(project_id, username):
            rows.append(
                {
                    "id": project_id,
                    "name": clean_display_text((item or {}).get("name"), project_id),
                }
            )
    rows.sort(key=lambda item: (item["name"], item["id"]))
    return rows


def product_project_map():
    mapping = {}
    for item in products_db if isinstance(products_db, list) else []:
        if not isinstance(item, dict):
            continue
        product_id = str(item.get("id") or "").strip()
        project_id = str(item.get("project_id") or "").strip()
        if product_id:
            mapping[product_id] = project_id
    return mapping


def content_project_id(approval_type, target_id):
    mapping = product_project_map()
    if approval_type == "news_publish":
        item = next(
            (row for row in player_news_db if isinstance(row, dict) and row.get("id") == target_id),
            None,
        )
        return mapping.get((item or {}).get("product_id") or "", "")
    if approval_type == "welfare_publish":
        item = next(
            (row for row in player_welfare_db if isinstance(row, dict) and row.get("id") == target_id),
            None,
        )
        return mapping.get((item or {}).get("product_id") or "", "")
    if approval_type == "forum_post_publish":
        item = next(
            (row for row in forum_posts_db if isinstance(row, dict) and row.get("id") == target_id),
            None,
        )
        return mapping.get((item or {}).get("product_id") or "", "")
    return ""


def approval_project_id(approval, projects_db_ref=None):
    db = projects_db_ref if projects_db_ref is not None else projects_db
    target_id = str((approval or {}).get("target_id") or "").strip()
    if target_id in (db or {}):
        return target_id
    return content_project_id((approval or {}).get("type") or "", target_id)

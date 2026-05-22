#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Backfill project scoping fields in SQLite json_documents.

What this fixes:
1. Legacy project_id drift / typo (e.g. GameKu -> GomeKu).
2. Missing project_id in player content, approvals, report templates, export records, docs.
3. Legacy remote media URLs in player content are normalized to local-only URLs.
"""

import argparse
import json
import os
import sys
from copy import deepcopy
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import load_dotenv  # noqa: E402
from models.db import delete_json_documents_by_prefix, get_json_document, init_db, set_json_document  # noqa: E402
from services.media_library import normalize_local_media_url, normalize_local_media_urls  # noqa: E402


DOC_KEYS = {
    "projects": "data/projects.json",
    "products": "data/products.json",
    "player_news": "data/player_news.json",
    "player_welfare": "data/player_welfare.json",
    "forum_posts": "data/forum_posts.json",
    "approvals": "data/approvals.json",
    "report_templates": "data/report_templates.json",
    "export_records": "data/export_records.json",
    "documents": "data/documents.json",
}


def _normalize_token(value):
    import re

    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def _build_project_index(projects):
    index = {
        "by_lower": {},
        "by_normalized": {},
        "project_ids": [],
    }
    if not isinstance(projects, dict):
        return index
    for project_id, payload in projects.items():
        pid = str(project_id or "").strip()
        if not pid:
            continue
        index["project_ids"].append(pid)
        item = payload if isinstance(payload, dict) else {}
        aliases_raw = item.get("aliases") or item.get("alias") or []
        if isinstance(aliases_raw, str):
            aliases = [part.strip() for part in aliases_raw.split(",") if part.strip()]
        elif isinstance(aliases_raw, (list, tuple, set)):
            aliases = [str(part or "").strip() for part in aliases_raw if str(part or "").strip()]
        else:
            aliases = []
        candidates = [pid, str(item.get("name") or "").strip(), str(item.get("name_en") or "").strip()] + aliases
        for alias in candidates:
            if not alias:
                continue
            lower = alias.lower()
            normalized = _normalize_token(alias)
            index["by_lower"][lower] = pid
            if normalized:
                index["by_normalized"][normalized] = pid
    return index


def _resolve_project_id(project_ref, project_index):
    text = str(project_ref or "").strip()
    if not text:
        return ""
    if text in project_index["project_ids"]:
        return text
    lower = text.lower()
    if lower in project_index["by_lower"]:
        return project_index["by_lower"][lower]
    normalized = _normalize_token(text)
    if normalized and normalized in project_index["by_normalized"]:
        return project_index["by_normalized"][normalized]
    if normalized:
        best_pid = ""
        best_ratio = 0.0
        for token, pid in project_index["by_normalized"].items():
            ratio = SequenceMatcher(None, normalized, token).ratio()
            if ratio > best_ratio:
                best_pid = pid
                best_ratio = ratio
        if best_pid and best_ratio >= 0.82:
            return best_pid
    return ""


def _resolve_product_project_id(product, project_index, single_project_id):
    if not isinstance(product, dict):
        return ""
    candidates = [
        product.get("project_id"),
        product.get("name"),
        product.get("title"),
        product.get("name_en"),
        product.get("slug"),
        product.get("intro"),
    ]
    for candidate in candidates:
        pid = _resolve_project_id(candidate, project_index)
        if pid:
            return pid
    return single_project_id or ""


def _coerce_list(value):
    return value if isinstance(value, list) else []


def _coerce_dict(value):
    return value if isinstance(value, dict) else {}


def _json_equal(a, b):
    return json.dumps(a, ensure_ascii=False, sort_keys=True) == json.dumps(b, ensure_ascii=False, sort_keys=True)


def _content_backfill(rows, product_project_map, project_index, single_project_id):
    changed = 0
    media_fixed = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        before_project = str(item.get("project_id") or "").strip()
        resolved_project = _resolve_project_id(before_project, project_index)
        if not resolved_project:
            product_id = str(item.get("product_id") or "").strip()
            resolved_project = product_project_map.get(product_id, "") or single_project_id
        if resolved_project and before_project != resolved_project:
            item["project_id"] = resolved_project
            changed += 1

        before_video = str(item.get("video_url") or "").strip()
        after_video = normalize_local_media_url(before_video)
        if before_video != after_video:
            item["video_url"] = after_video
            media_fixed += 1

        before_media = item.get("media_urls") or item.get("images") or []
        after_media = normalize_local_media_urls(before_media, max_count=10)
        if before_media != after_media:
            item["media_urls"] = after_media
            if "images" in item:
                item["images"] = after_media
            media_fixed += 1
    return changed, media_fixed


def main():
    parser = argparse.ArgumentParser(description="Backfill project_id and local media fields in SQLite docs")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    args = parser.parse_args()

    load_dotenv()
    init_db()

    docs = {
        name: deepcopy(get_json_document(key, {} if name == "projects" else []))
        for name, key in DOC_KEYS.items()
    }
    original_docs = deepcopy(docs)

    projects = _coerce_dict(docs["projects"])
    products = _coerce_list(docs["products"])
    news_rows = _coerce_list(docs["player_news"])
    welfare_rows = _coerce_list(docs["player_welfare"])
    forum_rows = _coerce_list(docs["forum_posts"])
    approvals = _coerce_list(docs["approvals"])
    report_templates = _coerce_list(docs["report_templates"])
    export_records = _coerce_list(docs["export_records"])
    documents = _coerce_list(docs["documents"])

    project_index = _build_project_index(projects)
    single_project_id = project_index["project_ids"][0] if len(project_index["project_ids"]) == 1 else ""

    stats = {
        "products_project_fixed": 0,
        "content_project_fixed": 0,
        "content_media_fixed": 0,
        "approvals_project_fixed": 0,
        "reports_project_fixed": 0,
        "exports_project_fixed": 0,
        "docs_project_fixed": 0,
        "junk_docs_removed": 0,
    }

    if not args.dry_run:
        # Clean up AppleDouble metadata docs accidentally migrated into SQLite.
        stats["junk_docs_removed"] = delete_json_documents_by_prefix("data/._")

    # 1) products mapping
    product_project_map = {}
    for product in products:
        if not isinstance(product, dict):
            continue
        product_id = str(product.get("id") or "").strip()
        if not product_id:
            continue
        resolved_project = _resolve_product_project_id(product, project_index, single_project_id)
        if resolved_project:
            if str(product.get("project_id") or "").strip() != resolved_project:
                product["project_id"] = resolved_project
                stats["products_project_fixed"] += 1
            product_project_map[product_id] = resolved_project

    # 2) player content mapping + media normalization
    fixed, media_fixed = _content_backfill(news_rows, product_project_map, project_index, single_project_id)
    stats["content_project_fixed"] += fixed
    stats["content_media_fixed"] += media_fixed
    fixed, media_fixed = _content_backfill(welfare_rows, product_project_map, project_index, single_project_id)
    stats["content_project_fixed"] += fixed
    stats["content_media_fixed"] += media_fixed
    fixed, media_fixed = _content_backfill(forum_rows, product_project_map, project_index, single_project_id)
    stats["content_project_fixed"] += fixed
    stats["content_media_fixed"] += media_fixed

    news_project_by_id = {str(item.get("id") or "").strip(): str(item.get("project_id") or "").strip() for item in news_rows if isinstance(item, dict)}
    welfare_project_by_id = {str(item.get("id") or "").strip(): str(item.get("project_id") or "").strip() for item in welfare_rows if isinstance(item, dict)}
    forum_project_by_id = {str(item.get("id") or "").strip(): str(item.get("project_id") or "").strip() for item in forum_rows if isinstance(item, dict)}

    # 3) approvals mapping
    for approval in approvals:
        if not isinstance(approval, dict):
            continue
        current_project = _resolve_project_id(approval.get("project_id"), project_index)
        if not current_project:
            atype = str(approval.get("type") or "").strip()
            target_id = str(approval.get("target_id") or "").strip()
            inferred = ""
            if atype == "news_publish":
                inferred = news_project_by_id.get(target_id, "")
            elif atype == "welfare_publish":
                inferred = welfare_project_by_id.get(target_id, "")
            elif atype == "forum_post_publish":
                inferred = forum_project_by_id.get(target_id, "")
            elif atype == "delete_project":
                inferred = _resolve_project_id(target_id, project_index)
            elif atype == "delete_version":
                inferred = _resolve_project_id(target_id.split(":", 1)[0], project_index)
            if not inferred and target_id in product_project_map:
                inferred = product_project_map.get(target_id, "")
            if not inferred:
                inferred = single_project_id
            current_project = inferred
        if current_project and str(approval.get("project_id") or "").strip() != current_project:
            approval["project_id"] = current_project
            stats["approvals_project_fixed"] += 1

    template_project_by_id = {}
    for tpl in report_templates:
        if not isinstance(tpl, dict):
            continue
        cfg = _coerce_dict(tpl.get("config"))
        current_project = _resolve_project_id(tpl.get("project_id"), project_index) or _resolve_project_id(cfg.get("project_id"), project_index)
        if not current_project:
            current_project = single_project_id
        if current_project:
            if str(tpl.get("project_id") or "").strip() != current_project:
                tpl["project_id"] = current_project
                stats["reports_project_fixed"] += 1
            if str(cfg.get("project_id") or "").strip() != current_project:
                cfg["project_id"] = current_project
                tpl["config"] = cfg
                stats["reports_project_fixed"] += 1
        template_id = str(tpl.get("id") or "").strip()
        if template_id and current_project:
            template_project_by_id[template_id] = current_project

    for rec in export_records:
        if not isinstance(rec, dict):
            continue
        params = _coerce_dict(rec.get("params"))
        current_project = _resolve_project_id(rec.get("project_id"), project_index) or _resolve_project_id(params.get("project_id"), project_index)
        if not current_project:
            template_id = str(rec.get("template_id") or "").strip()
            current_project = template_project_by_id.get(template_id, "")
        if not current_project:
            current_project = single_project_id
        if current_project:
            if str(rec.get("project_id") or "").strip() != current_project:
                rec["project_id"] = current_project
                stats["exports_project_fixed"] += 1
            if str(params.get("project_id") or "").strip() != current_project:
                params["project_id"] = current_project
                rec["params"] = params
                stats["exports_project_fixed"] += 1

    for doc in documents:
        if not isinstance(doc, dict):
            continue
        current_project = _resolve_project_id(doc.get("project_id"), project_index)
        if not current_project:
            current_project = single_project_id
        if current_project and str(doc.get("project_id") or "").strip() != current_project:
            doc["project_id"] = current_project
            stats["docs_project_fixed"] += 1

    updated_docs = {
        "projects": projects,
        "products": products,
        "player_news": news_rows,
        "player_welfare": welfare_rows,
        "forum_posts": forum_rows,
        "approvals": approvals,
        "report_templates": report_templates,
        "export_records": export_records,
        "documents": documents,
    }

    changed_doc_keys = []
    for name, key in DOC_KEYS.items():
        if not _json_equal(original_docs[name], updated_docs[name]):
            changed_doc_keys.append(key)
            if not args.dry_run:
                set_json_document(key, updated_docs[name])

    print("[INFO] project_count=%d single_project=%s" % (len(project_index["project_ids"]), single_project_id or "-"))
    print("[INFO] docs_changed=%d" % len(changed_doc_keys))
    for key in changed_doc_keys:
        print("  -", key)
    for metric, value in stats.items():
        print("[INFO] %s=%d" % (metric, int(value)))
    if args.dry_run:
        print("[DONE] dry-run only (no write)")
    else:
        print("[DONE] backfill applied")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

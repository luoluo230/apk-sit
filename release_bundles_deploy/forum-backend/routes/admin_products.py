# -*- coding: utf-8 -*-
"""Admin product management for public site content."""

import json
import os
import uuid
from datetime import datetime
from urllib.parse import quote

from flask import Blueprint, jsonify, render_template, request, session
from werkzeug.utils import secure_filename

from models.data import (
    get_project_record,
    products_db,
    projects_db,
    resolve_project_id,
    resolve_project_id_for_product,
    save_products,
)
from services.authz import admin_required, is_super_admin_or_admin
from services.company_profile import get_company_profile
from services.media_library import normalize_local_media_url

bp = Blueprint("admin_products", __name__)

PRODUCT_MEDIA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "product_media",
)


def _current_username():
    return session.get("user") or ""


def _product_dir(product_id):
    if not product_id:
        return None
    directory = os.path.join(PRODUCT_MEDIA_DIR, product_id)
    os.makedirs(directory, exist_ok=True)
    return directory


def _product_media_url(product_id, filename):
    product_id = str(product_id or "").strip()
    filename = os.path.basename(str(filename or "").strip())
    if not product_id or not filename:
        return ""
    return "/product-media/%s/%s" % (quote(product_id), quote(filename))


def _can_manage_products():
    return is_super_admin_or_admin()


def _get_csrf_token():
    try:
        from flask_wtf.csrf import generate_csrf

        return generate_csrf()
    except ImportError:
        return ""


def _products_list():
    return products_db if isinstance(products_db, list) else []


def _safe_int(value, default=0):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _normalize_gallery(raw):
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    normalized = []
    for item in data:
        text = os.path.basename(str(item or "").strip())
        if not text:
            continue
        normalized.append(text[:255])
    return normalized[:20]


def _normalize_project_id(value):
    project_id = str(value or "").strip()
    if not project_id:
        return ""
    resolved = resolve_project_id(project_id)
    return resolved or None


def _project_name(project_id):
    resolved_id, project = get_project_record(project_id)
    if isinstance(project, dict):
        return str(project.get("name") or resolved_id or project_id)
    return str(project_id or "")


def _project_choices(selected_project_id=""):
    selected_project_id = resolve_project_id(selected_project_id) or str(selected_project_id or "").strip()
    rows = []
    if isinstance(projects_db, dict):
        for project_id, project in projects_db.items():
            payload = project if isinstance(project, dict) else {}
            rows.append(
                {
                    "id": str(project_id),
                    "name": str(payload.get("name") or project_id),
                    "status": str(payload.get("status") or "active"),
                }
            )
    rows.sort(key=lambda item: (item["status"] == "archived", item["name"].lower(), item["id"].lower()))
    if selected_project_id and all(item["id"] != selected_project_id for item in rows):
        rows.append(
            {
                "id": selected_project_id,
                "name": "%s (已不存在)" % selected_project_id,
                "status": "missing",
            }
        )
    return rows


def _store_links_from_product(product):
    store_links = product.get("store_links") if isinstance(product, dict) else {}
    if not isinstance(store_links, dict):
        store_links = {}
    channels = store_links.get("android_channels")
    if not isinstance(channels, list):
        channels = []
    normalized = []
    for item in channels[:4]:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "name": str(item.get("name") or "").strip()[:40],
                "url": str(item.get("url") or "").strip()[:300],
            }
        )
    while len(normalized) < 4:
        normalized.append({"name": "", "url": ""})
    return {
        "android_direct": str(store_links.get("android_direct") or "").strip()[:300],
        "ios_store": str(store_links.get("ios_store") or "").strip()[:300],
        "android_channels": normalized,
    }


def _store_links_from_form(form):
    channels = []
    for idx in range(1, 5):
        name = (form.get(f"android_channel_name_{idx}") or "").strip()[:40]
        url = (form.get(f"android_channel_url_{idx}") or "").strip()[:300]
        if name or url:
            channels.append({"name": name or f"渠道 {idx}", "url": url})
    return {
        "android_direct": (form.get("android_direct") or "").strip()[:300],
        "ios_store": (form.get("ios_store") or "").strip()[:300],
        "android_channels": channels,
    }


def _render_edit_page(product=None):
    current = product if isinstance(product, dict) else {}
    product_id = str(current.get("id") or "").strip()
    store_links = _store_links_from_product(current)
    gallery_files = [item for item in _normalize_gallery(json.dumps(current.get("gallery") or []))] if current else []
    company_name = (get_company_profile().get("company_name") or "星云游戏站").strip()
    return render_template(
        "admin_product_edit.html",
        company_name=company_name,
        page_title="编辑产品" if product_id else "新增产品",
        csrf_token_value=_get_csrf_token(),
        product=current,
        product_id=product_id,
        project_choices=_project_choices(resolve_project_id_for_product(current) or current.get("project_id") or ""),
        selected_project_id=resolve_project_id_for_product(current) or str(current.get("project_id") or ""),
        store_links=store_links,
        cover_url=_product_media_url(product_id, current.get("cover_image") or ""),
        gallery_files=gallery_files,
        gallery_previews=[
            {"name": filename, "url": _product_media_url(product_id, filename)}
            for filename in gallery_files
        ],
    )


@bp.route("/admin/products")
@admin_required()
def list_page():
    if not _can_manage_products():
        return "无权限", 403
    products = sorted(
        [product for product in _products_list()],
        key=lambda item: (_safe_int(item.get("order"), 999), item.get("updated_at", "")),
        reverse=False,
    )
    rows = []
    for product in products:
        raw_project_id = str(product.get("project_id") or "").strip()
        project_id = resolve_project_id(raw_project_id) or raw_project_id
        canonical_project_id = resolve_project_id_for_product(product) or project_id
        rows.append(
            {
                "id": product.get("id", ""),
                "name": product.get("name") or "未命名产品",
                "intro": (product.get("intro") or "")[:50],
                "project_id": canonical_project_id,
                "raw_project_id": raw_project_id,
                "project_name": _project_name(canonical_project_id) if canonical_project_id else "",
                "updated_at": (product.get("updated_at") or "")[:16].replace("T", " "),
            }
        )
    company_name = (get_company_profile().get("company_name") or "星云游戏站").strip()
    return render_template(
        "admin_products_list.html",
        products=rows,
        csrf_token_value=_get_csrf_token(),
        company_name=company_name,
    )


@bp.route("/admin/products/new")
@bp.route("/admin/products/<product_id>/edit")
@admin_required()
def edit_page(product_id=None):
    if not _can_manage_products():
        return "无权限", 403
    product = None
    if product_id:
        product = next((item for item in _products_list() if item.get("id") == product_id), None)
        if not product:
            return "产品不存在", 404
    return _render_edit_page(product)


@bp.route("/admin/products", methods=["POST"])
@admin_required()
def create():
    if not _can_manage_products():
        return jsonify({"error": "无权限"}), 403
    name = (request.form.get("name") or "").strip()
    if not name:
        return jsonify({"error": "请填写产品名称"}), 400
    project_id = _normalize_project_id(request.form.get("project_id"))
    if project_id is None:
        return jsonify({"error": "关联项目不存在，请刷新页面后重试"}), 400
    products = _products_list()
    product_id = (request.form.get("id") or "").strip() or uuid.uuid4().hex[:12]
    if any(product.get("id") == product_id for product in products):
        return jsonify({"error": "产品 ID 已存在"}), 400
    now = datetime.now().isoformat()
    products.append(
        {
            "id": product_id,
            "name": name[:100],
            "slug": product_id,
            "intro": (request.form.get("intro") or "")[:300],
            "description": (request.form.get("description") or "")[:5000],
            "cover_image": os.path.basename(request.form.get("cover_image") or "")[:255],
            "gallery": _normalize_gallery(request.form.get("gallery")),
            "video_url": normalize_local_media_url((request.form.get("video_url") or "").strip()[:500], allowed_prefixes=("/product-media/", "/uploaded-media/", "/static/")),
            "store_links": _store_links_from_form(request.form),
            "project_id": project_id or None,
            "order": _safe_int(request.form.get("order"), 0),
            "created_at": now,
            "updated_at": now,
            "updated_by": _current_username(),
        }
    )
    save_products()
    return jsonify({"ok": True, "id": product_id})


@bp.route("/admin/products/<product_id>", methods=["PUT"])
@admin_required()
def update(product_id):
    if not _can_manage_products():
        return jsonify({"error": "无权限"}), 403
    product = next((item for item in _products_list() if item.get("id") == product_id), None)
    if not product:
        return jsonify({"error": "产品不存在"}), 404
    project_id = _normalize_project_id(request.form.get("project_id"))
    if project_id is None:
        return jsonify({"error": "关联项目不存在，请刷新页面后重试"}), 400
    product["name"] = (request.form.get("name") or product.get("name") or "")[:100]
    product["intro"] = (request.form.get("intro") or "")[:300]
    product["description"] = (request.form.get("description") or "")[:5000]
    product["cover_image"] = os.path.basename(request.form.get("cover_image") or product.get("cover_image") or "")[:255]
    product["gallery"] = _normalize_gallery(request.form.get("gallery"))
    product["video_url"] = normalize_local_media_url((request.form.get("video_url") or "").strip()[:500], allowed_prefixes=("/product-media/", "/uploaded-media/", "/static/"))
    product["store_links"] = _store_links_from_form(request.form)
    product["project_id"] = project_id or None
    product["order"] = _safe_int(request.form.get("order"), 0)
    product["updated_at"] = datetime.now().isoformat()
    product["updated_by"] = _current_username()
    save_products()
    return jsonify({"ok": True})


@bp.route("/admin/products/<product_id>", methods=["DELETE"])
@admin_required()
def delete(product_id):
    if not _can_manage_products():
        return jsonify({"error": "无权限"}), 403
    products = _products_list()
    products[:] = [product for product in products if product.get("id") != product_id]
    save_products()
    return jsonify({"ok": True})


@bp.route("/admin/products/upload-cover", methods=["POST"])
@admin_required()
def upload_cover():
    if not _can_manage_products():
        return jsonify({"error": "无权限"}), 403
    product_id = (request.form.get("product_id") or "").strip()
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "请选择文件"}), 400
    ext = os.path.splitext(secure_filename(file.filename))[1].lower() or ".jpg"
    if product_id:
        directory = _product_dir(product_id)
    else:
        product_id = uuid.uuid4().hex[:12]
        directory = _product_dir(product_id)
    if not directory:
        return jsonify({"error": "无效 product_id"}), 400
    filename = "cover" + ext
    file.save(os.path.join(directory, filename))
    return jsonify({"ok": True, "path": filename, "product_id": product_id})


@bp.route("/admin/products/upload-gallery", methods=["POST"])
@admin_required()
def upload_gallery():
    if not _can_manage_products():
        return jsonify({"error": "无权限"}), 403
    product_id = (request.form.get("product_id") or "").strip()
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "请选择文件"}), 400
    ext = os.path.splitext(secure_filename(file.filename))[1].lower() or ".jpg"
    if not product_id:
        product_id = uuid.uuid4().hex[:12]
    directory = _product_dir(product_id)
    if not directory:
        return jsonify({"error": "无效 product_id"}), 400
    filename = uuid.uuid4().hex[:8] + ext
    file.save(os.path.join(directory, filename))
    return jsonify({"ok": True, "path": filename, "product_id": product_id})


@bp.route("/admin/products/upload-video", methods=["POST"])
@admin_required()
def upload_video():
    if not _can_manage_products():
        return jsonify({"error": "无权限"}), 403
    product_id = (request.form.get("product_id") or "").strip()
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "请选择视频文件"}), 400
    ext = os.path.splitext(secure_filename(file.filename))[1].lower() or ".mp4"
    if not product_id:
        product_id = uuid.uuid4().hex[:12]
    directory = _product_dir(product_id)
    if not directory:
        return jsonify({"error": "无效 product_id"}), 400
    filename = "video" + ext
    file.save(os.path.join(directory, filename))
    return jsonify(
        {
            "ok": True,
            "path": filename,
            "url": _product_media_url(product_id, filename),
            "product_id": product_id,
        }
    )

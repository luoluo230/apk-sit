# -*- coding: utf-8 -*-
"""Shared local media storage for admin-managed images and videos."""

import os
import uuid
from urllib.parse import quote

from werkzeug.utils import secure_filename

from config import DATA_DIR

MEDIA_ROOT = os.path.join(DATA_DIR, "uploaded_media")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v", ".avi", ".mkv"}
LOCAL_MEDIA_PREFIXES = ("/uploaded-media/", "/product-media/", "/static/")


def media_root():
    os.makedirs(MEDIA_ROOT, exist_ok=True)
    return MEDIA_ROOT


def sanitize_segment(value, fallback="shared"):
    raw = secure_filename(str(value or "").strip())
    return raw or fallback


def media_kind_from_name(filename):
    ext = os.path.splitext(str(filename or ""))[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return ""


def is_allowed_media(filename):
    return media_kind_from_name(filename) in {"image", "video"}


def media_url(relative_path):
    clean = str(relative_path or "").replace("\\", "/").strip("/")
    if not clean:
        return ""
    return "/uploaded-media/" + quote(clean, safe="/")


def is_local_media_url(value, allowed_prefixes=None):
    """Allow only local hosted media urls."""
    text = str(value or "").strip()
    if not text:
        return False
    prefixes = tuple(allowed_prefixes or LOCAL_MEDIA_PREFIXES)
    return any(text.startswith(prefix) for prefix in prefixes)


def normalize_local_media_url(value, allowed_prefixes=None):
    text = str(value or "").strip()
    if not text:
        return ""
    return text if is_local_media_url(text, allowed_prefixes=allowed_prefixes) else ""


def normalize_local_media_urls(values, allowed_prefixes=None, max_count=10):
    if isinstance(values, str):
        raw_values = [segment.strip() for segment in values.replace("\n", ",").split(",")]
    elif isinstance(values, (list, tuple, set)):
        raw_values = [str(item).strip() for item in values]
    else:
        raw_values = []
    out = []
    for item in raw_values:
        if not item:
            continue
        normalized = normalize_local_media_url(item, allowed_prefixes=allowed_prefixes)
        if normalized:
            out.append(normalized)
    return out[: max(1, int(max_count or 1))]


def save_uploaded_files(files, scope="shared", bucket="shared"):
    saved = []
    base_dir = os.path.join(media_root(), sanitize_segment(scope), sanitize_segment(bucket))
    os.makedirs(base_dir, exist_ok=True)
    for storage in files or []:
        if not storage or not getattr(storage, "filename", ""):
            continue
        original_name = secure_filename(storage.filename)
        if not original_name or not is_allowed_media(original_name):
            continue
        ext = os.path.splitext(original_name)[1].lower()
        saved_name = uuid.uuid4().hex[:16] + ext
        absolute_path = os.path.join(base_dir, saved_name)
        storage.save(absolute_path)
        relative_path = "/".join([sanitize_segment(scope), sanitize_segment(bucket), saved_name])
        saved.append(
            {
                "name": original_name,
                "filename": saved_name,
                "relative_path": relative_path,
                "url": media_url(relative_path),
                "kind": media_kind_from_name(saved_name),
            }
        )
    return saved

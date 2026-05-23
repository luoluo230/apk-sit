"""Admin media route adapters."""

from __future__ import annotations

from flask import jsonify, request, send_from_directory

from services.authz import login_required
from repositories.admin import media_repo
from services.admin import media_service


def uploaded_media_file_response(relative_path: str):
    clean_relative = media_service.sanitize_relative_path(relative_path)
    if not clean_relative:
        return "", 404
    return send_from_directory(media_repo.root_path(), clean_relative, as_attachment=False)


def media_upload_response():
    files = request.files.getlist("files")
    if not files:
        single = request.files.get("file")
        if single:
            files = [single]
    payload, status = media_service.upload_media(request.form, files)
    return jsonify(payload), status


def register_routes(bp):
    def _uploaded_media(relative_path: str):
        return uploaded_media_file_response(relative_path)

    @login_required
    def _media_upload():
        return media_upload_response()

    bp.add_url_rule("/uploaded-media/<path:relative_path>", endpoint="uploaded_media_file", view_func=_uploaded_media)
    bp.add_url_rule("/admin/media/upload", endpoint="admin_media_upload", view_func=_media_upload, methods=["POST"])

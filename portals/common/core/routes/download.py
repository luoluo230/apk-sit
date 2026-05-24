# -*- coding: utf-8 -*-
"""下载、公开下载、二维码、上传、删除"""

from __future__ import annotations

import os
import io
import base64
import logging
from flask import Blueprint, request, send_from_directory, abort, jsonify, Response

import qrcode

from config import Config
from services.authz import login_required, admin_required
from models.data import (
    download_stats, save_stats, record_download_event, is_supported_package,
)
from services.startup import get_canonical_base_url

logger = logging.getLogger(__name__)
bp = Blueprint('download', __name__)


def _resolve_package_path(filename):
    """解析安装包路径，支持子目录（如 wechat/dev/xxx.apk 或 wechat/ios/xxx.ipa）。"""
    if '..' in filename or filename.startswith('/') or '\\' in filename:
        return None
    if not is_supported_package(filename):
        return None
    norm = os.path.normpath(filename).replace('\\', '/')
    if norm.startswith('..') or '/..' in norm:
        return None
    full = os.path.normpath(os.path.join(Config.APK_DIR, norm))
    base = os.path.normpath(Config.APK_DIR)
    if not full.startswith(base) or not os.path.isfile(full):
        return None
    return (os.path.dirname(full), os.path.basename(full))


@bp.route('/download/<path:filename>')
@login_required
def download(filename):
    client_ip = request.remote_addr or '127.0.0.1'
    logger.info("下载请求：%s, IP: %s", filename, client_ip)
    res = _resolve_package_path(filename)
    if not res:
        abort(403)
    directory, safe_filename = res
    stats_key = filename.replace('\\', '/') if '/' in filename else safe_filename
    download_stats[stats_key] = download_stats.get(stats_key, 0) + 1
    download_stats[safe_filename] = download_stats.get(safe_filename, 0) + 1
    save_stats()
    src = (request.args.get('source') or 'site').strip().lower()[:20]
    if src not in ('site', 'qr', 'direct'):
        src = 'site'
    record_download_event(stats_key, source=src, ip=client_ip)
    return send_from_directory(directory, safe_filename, as_attachment=True)


def _resolve_oss_object_key(object_key: str) -> str | None:
    """校验 OSS object key，仅允许 MyGame1 前缀下的安装包。"""
    key = (object_key or "").strip().replace("\\", "/").lstrip("/")
    if not key or ".." in key or key.startswith("/"):
        return None
    if not key.startswith("MyGame1/"):
        return None
    if not is_supported_package(os.path.basename(key)):
        return None
    return key


def _local_apk_for_oss_key(object_key: str) -> tuple[str, str] | None:
    """OSS 对象不存在时，尝试从 sidecar 元数据回退到本地 APK。"""
    key = (object_key or "").strip().replace("\\", "/").lstrip("/")
    if not key:
        return None
    apk_dir = Config.APK_DIR
    if not os.path.isdir(apk_dir):
        return None
    for root, _dirs, files in os.walk(apk_dir):
        for fname in files:
            if not fname.endswith(".apk.meta.json"):
                continue
            meta_path = os.path.join(root, fname)
            try:
                import json

                meta = json.loads(open(meta_path, encoding="utf-8").read())
                if (meta.get("oss_remote_key") or "").lstrip("/") == key:
                    rel_apk = (meta.get("pub_download_path") or fname[:-10]).replace("\\", "/")
                    full = os.path.join(apk_dir, rel_apk.replace("/", os.sep))
                    if os.path.isfile(full):
                        return os.path.dirname(full), os.path.basename(full)
            except Exception:
                continue
    return None


@bp.route('/pub/oss-download/<path:object_key>')
def pub_oss_download(object_key):
    """通过 apk-site 代理从 OSS 下载 APK（绕过阿里云默认域名 ApkDownloadForbidden）。"""
    key = _resolve_oss_object_key(object_key)
    if not key:
        abort(403)
    unity_project = (os.environ.get("UNITY_PROJECT_PATH") or "/Users/wangling/Desktop/MyGame/GameClient").strip()
    filename = os.path.basename(key)
    stats_key = f"oss:{key}"
    src = (request.args.get("source") or "direct").strip().lower()[:20]
    if src not in ("site", "qr", "direct"):
        src = "direct"

    try:
        from services.oss_client_helper import stream_object

        result, content_type, content_length = stream_object(key, unity_project)

        def generate():
            try:
                for chunk in result:
                    if chunk:
                        yield chunk
            finally:
                result.close()

        download_stats[stats_key] = download_stats.get(stats_key, 0) + 1
        save_stats()
        record_download_event(stats_key, source=src, ip=request.remote_addr or "")
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        if content_length:
            headers["Content-Length"] = str(content_length)
        return Response(
            generate(),
            mimetype=content_type or "application/vnd.android.package-archive",
            headers=headers,
        )
    except Exception as e:
        logger.warning("OSS 代理下载失败 %s: %s，尝试本地回退", key, e)
        local = _local_apk_for_oss_key(key)
        if local:
            directory, safe_filename = local
            download_stats[stats_key] = download_stats.get(stats_key, 0) + 1
            save_stats()
            record_download_event(stats_key, source=src, ip=request.remote_addr or "")
            return send_from_directory(directory, safe_filename, as_attachment=True)
        logger.error("OSS 代理下载失败且无本地回退: %s", key)
        abort(404)


@bp.route('/pub/download/<path:filename>')
def pub_download(filename):
    res = _resolve_package_path(filename)
    if not res:
        abort(403)
    directory, safe_filename = res
    stats_key = filename.replace('\\', '/') if '/' in filename else safe_filename
    download_stats[stats_key] = download_stats.get(stats_key, 0) + 1
    download_stats[safe_filename] = download_stats.get(safe_filename, 0) + 1
    save_stats()
    src = (request.args.get('source') or 'direct').strip().lower()[:20]
    if src not in ('site', 'qr', 'direct'):
        src = 'direct'
    record_download_event(stats_key, source=src, ip=request.remote_addr or '')
    return send_from_directory(directory, safe_filename, as_attachment=True)


def _download_base_url():
    """二维码/外部分享用：优先外网 PUBLIC_URL，否则局域网地址。"""
    return Config.get_public_base_url() or get_canonical_base_url()


@bp.route('/qr/<path:filename>')
@login_required
def generate_qr(filename):
    base_url = _download_base_url()
    download_url = f"{base_url}/pub/download/{filename}?source=qr"
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
    qr.add_data(download_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.getvalue()).decode()
    return jsonify({'qr_code': f'data:image/png;base64,{img_base64}', 'url': download_url})


@bp.route('/upload', methods=['POST'])
@admin_required('projects')
def upload_apk():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '没有选择文件'})
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': '没有选择文件'})
        if not is_supported_package(file.filename):
            return jsonify({'success': False, 'error': '只允许上传 .apk 或 .ipa 文件'})
        os.makedirs(Config.APK_DIR, exist_ok=True)
        # 安全：basename 防止路径穿越（如 ../../../evil.apk）
        filename = os.path.basename(file.filename)
        filepath = os.path.join(Config.APK_DIR, filename)
        file.save(filepath)
        logger.info("上传安装包成功: %s", filename)
        return jsonify({'success': True, 'filename': filename})
    except Exception as e:
        logger.error("上传安装包失败: %s", e)
        return jsonify({'success': False, 'error': str(e)})


@bp.route('/delete/<path:filename>', methods=['DELETE'])
@admin_required('projects')
def delete_apk(filename):
    try:
        if '..' in filename or filename.startswith('/'):
            return jsonify({'success': False, 'error': '非法文件名'})
        safe_filename = os.path.basename(filename)
        if not is_supported_package(safe_filename):
            return jsonify({'success': False, 'error': '不支持的安装包类型'})
        filepath = os.path.join(Config.APK_DIR, safe_filename)
        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': '文件不存在'})
        os.remove(filepath)
        if safe_filename in download_stats:
            del download_stats[safe_filename]
            save_stats()
        logger.info("删除安装包成功: %s", safe_filename)
        return jsonify({'success': True})
    except Exception as e:
        logger.error("删除安装包失败: %s", e)
        return jsonify({'success': False, 'error': str(e)})

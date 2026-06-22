# -*- coding: utf-8 -*-
"""Package file discovery and metadata extraction."""

import os
import re
from datetime import datetime

from config import Config
from data._store import SUPPORTED_PACKAGE_EXTENSIONS, PLATFORM_LABELS, get_logger


def is_supported_package(filename):
    return os.path.splitext(filename or '')[1].lower() in SUPPORTED_PACKAGE_EXTENSIONS


def detect_platform(filename):
    ext = os.path.splitext(filename or '')[1].lower()
    if ext == '.ipa':
        return 'ios'
    return 'android'


def get_platform_label(platform):
    return PLATFORM_LABELS.get((platform or '').lower(), 'Unknown')


def iter_package_files(root_dir=None):
    root = os.path.normpath(root_dir or Config.APK_DIR)
    if not os.path.isdir(root):
        return
    for current_root, _, filenames in os.walk(root):
        for filename in filenames:
            if not is_supported_package(filename):
                continue
            full_path = os.path.join(current_root, filename)
            if not os.path.isfile(full_path):
                continue
            rel_path = os.path.relpath(full_path, root).replace('\\', '/')
            yield rel_path, full_path


def extract_project_name(filename):
    from data.projects import resolve_project_id

    base = os.path.splitext(os.path.basename(filename or ''))[0]
    project_token = base
    if '_' in base:
        project_token = base.split('_')[0]
    resolved = resolve_project_id(project_token)
    return resolved or project_token


def extract_version_from_filename(filename):
    base = os.path.splitext(os.path.basename(filename or ''))[0]
    parts = base.split('_')
    for p in reversed(parts):
        if re.match(r'^\d+\.\d+\.\d+', p):
            return p
    return base if parts else ''


def parse_apk_metadata(apk_path):
    try:
        filename = os.path.basename(apk_path)
        base_name = os.path.splitext(filename)[0].replace('_', ' ')
        version_match = re.search(r'(\d+\.\d+\.\d+)', filename)
        version = version_match.group(1) if version_match else '1.0'
        app_name = base_name.title()
        return {
            'package': f'com.example.{base_name.replace(" ", "").lower()}',
            'version': version,
            'app_name': app_name
        }
    except Exception as e:
        get_logger().warning("解析 APK 失败 %s: %s", apk_path, e)
        return None


def extract_package_info(filename, filepath):
    from data.downloads import download_stats

    stat = os.stat(filepath)
    project_name = extract_project_name(filename)
    platform = detect_platform(filename)
    file_info = {
        'name': filename,
        'basename': os.path.basename(filename),
        'extension': os.path.splitext(filename)[1].lower(),
        'platform': platform,
        'platform_label': get_platform_label(platform),
        'size': stat.st_size,
        'size_mb': round(stat.st_size / 1024 / 1024, 1),
        'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
        'timestamp': stat.st_mtime,
        'download_count': download_stats.get(filename, download_stats.get(os.path.basename(filename), 0)),
        'project': project_name
    }
    metadata = parse_apk_metadata(filepath)
    if metadata:
        file_info.update(metadata)
    else:
        file_info['app_name'] = os.path.splitext(os.path.basename(filename))[0].replace('_', ' ').title()
        file_info['package'] = 'unknown'
        file_info['version'] = '1.0'
    return file_info


def extract_apk_info(filename, filepath):
    return extract_package_info(filename, filepath)

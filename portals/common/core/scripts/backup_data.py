#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APK 下载中心 - 数据备份脚本（跨平台：Windows / macOS）

用法：python scripts/backup_data.py
或：  python -m scripts.backup_data

备份范围：data/*.json、data/workspaces、data/project_icons、
         data/task_uploads、data/product_media、data/doc_attachments
         （不含 jenkins_instances，因其包含构建产物体积较大）
输出：backups/apk-site-YYYYMMDD-HHMMSS.zip
"""

import os
import sys
import zipfile
from datetime import datetime

# 项目根目录
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _ROOT)


def _resolve_path(val, base=_ROOT):
    if not val:
        return ''
    val = str(val).strip()
    if not os.path.isabs(val):
        val = os.path.normpath(os.path.join(base, val))
    return val


def _load_env():
    env_path = os.path.join(_ROOT, '.env')
    if os.path.isfile(env_path):
        with open(env_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.replace('\r', '').strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v


def run_backup():
    """执行备份，返回 (zip_path, count)。供定时任务或外部调用。"""
    _load_env()
    try:
        from config import DATA_DIR
        data_dir = DATA_DIR
    except ImportError:
        data_dir = _resolve_path(os.getenv('DATA_DIR', 'data'))
    backup_dir = _resolve_path(os.getenv('BACKUP_DIR', 'backups'), _ROOT)
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    zip_name = 'apk-site-%s.zip' % timestamp
    zip_path = os.path.join(backup_dir, zip_name)

    to_backup = []
    if os.path.isdir(data_dir):
        for name in os.listdir(data_dir):
            if name.endswith('.json') or name.endswith('.db'):
                to_backup.append(os.path.join(data_dir, name))
        for sub in ('workspaces', 'project_icons', 'task_uploads', 'product_media', 'doc_attachments'):
            sub_path = os.path.join(data_dir, sub)
            if os.path.isdir(sub_path):
                for root, dirs, files in os.walk(sub_path):
                    for f in files:
                        if not f.startswith('.'):
                            to_backup.append(os.path.join(root, f))

    count = 0
    base_for_arc = os.path.dirname(data_dir) if os.path.dirname(data_dir) else _ROOT
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in to_backup:
            if os.path.isfile(path):
                try:
                    arcname = os.path.relpath(path, base_for_arc)
                except ValueError:
                    arcname = os.path.basename(path)
                zf.write(path, arcname)
                count += 1

    return zip_path, count


def cleanup_old_backups(retain=7):
    """清理旧备份，保留最近 retain 份。"""
    _load_env()
    backup_dir = _resolve_path(os.getenv('BACKUP_DIR', 'backups'), _ROOT)
    if not os.path.isdir(backup_dir):
        return 0
    zips = []
    for name in os.listdir(backup_dir):
        if name.startswith('apk-site-') and name.endswith('.zip'):
            path = os.path.join(backup_dir, name)
            if os.path.isfile(path):
                zips.append((path, os.path.getmtime(path)))
    if len(zips) <= retain:
        return 0
    zips.sort(key=lambda x: x[1], reverse=True)
    removed = 0
    for path, _ in zips[retain:]:
        try:
            os.remove(path)
            removed += 1
        except OSError:
            pass
    return removed


def main():
    zip_path, count = run_backup()
    print('备份完成: %s (%d 个文件)' % (zip_path, count))
    retain = int(os.getenv('BACKUP_RETENTION_COUNT', '7'))
    cleaned = cleanup_old_backups(retain=retain)
    if cleaned > 0:
        print('已清理 %d 个旧备份（保留最近 %d 份）' % (cleaned, retain))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('备份失败: %s' % e, file=sys.stderr)
        sys.exit(1)

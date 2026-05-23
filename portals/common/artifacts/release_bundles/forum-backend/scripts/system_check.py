#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""系统体检：检查数据映射、版本路径、SQLite 和备份目录。"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from config import Config, DATA_DIR, load_dotenv
from models.data import products_db, project_versions_db, projects_db, iter_package_files, extract_project_name

load_dotenv()


def main():
    issues = []
    package_projects = {}
    for rel_path, _ in iter_package_files():
        package_projects.setdefault(extract_project_name(rel_path), 0)
        package_projects[extract_project_name(rel_path)] += 1

    if not os.path.isfile(os.path.join(DATA_DIR, 'apk_site.db')):
        issues.append('SQLite 数据库文件缺失: data/apk_site.db')

    backup_dir = os.path.join(_ROOT, 'backups')
    if not os.path.isdir(backup_dir):
        issues.append('备份目录不存在: backups/')

    for product in products_db if isinstance(products_db, list) else []:
        pid = product.get('project_id') or ''
        if pid and pid not in projects_db and pid not in package_projects:
            issues.append('产品 %s 绑定的项目 %s 不存在，且没有对应安装包' % (product.get('id') or '-', pid))

    for project_id, versions in (project_versions_db or {}).items():
        if not isinstance(versions, list):
            continue
        for version in versions:
            apk_path = (version.get('apk_path') or '').strip()
            if not apk_path:
                issues.append('项目 %s 版本 %s 缺少安装包路径' % (project_id, version.get('id') or '-'))
                continue
            if not apk_path.startswith('/'):
                full = os.path.join(Config.APK_DIR, apk_path.replace('/', os.path.sep))
                if not os.path.isfile(full):
                    issues.append('项目 %s 版本 %s 安装包不存在: %s' % (project_id, version.get('id') or '-', apk_path))

    if issues:
        print('SYSTEM_CHECK_FAILED')
        for item in issues:
            print('- ' + item)
        return 1

    print('SYSTEM_CHECK_OK')
    print('projects=%d package_projects=%d' % (len(projects_db), len(package_projects)))
    return 0


if __name__ == '__main__':
    sys.exit(main())

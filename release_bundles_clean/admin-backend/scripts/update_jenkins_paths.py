#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 jenkins-clone 内所有硬编码路径替换为 apk-site 下的路径，便于迁移后直接使用。
用法：在 apk-site 项目根执行
  python scripts/update_jenkins_paths.py          # 执行替换
  python scripts/update_jenkins_paths.py --dry-run # 仅打印将要替换的内容
要求：已将 jenkins-clone 复制到 apk-site/jenkins-clone/
"""

import os
import sys
import re

# 项目根 = 上上级（本脚本在 apk-site/scripts/）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APK_SITE_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, APK_SITE_ROOT)

JENKINS_CLONE = os.path.join(APK_SITE_ROOT, 'jenkins-clone')

# 要替换的路径（旧 -> 新）
OLD_JENKINS_CLONE = '/Users/wangling/Desktop/jenkins-clone'
OLD_BUILDS = '/Users/wangling/Desktop/Builds'

# 需要扫描并替换的文件
GLOB_PATTERNS = [
    'jobs/Android/config.xml',
    'scripts/*.sh',
    'notify_feishu.sh',
    'start_service.sh',
]


def get_apk_dir():
    from config import load_dotenv, Config
    load_dotenv()
    return Config.APK_DIR


def main():
    dry_run = '--dry-run' in sys.argv
    if not os.path.isdir(JENKINS_CLONE):
        print('错误：未找到 apk-site/jenkins-clone/')
        print('请先将 jenkins-clone 复制到项目内：')
        print('  cp -r /path/to/jenkins-clone "%s"' % JENKINS_CLONE)
        sys.exit(1)

    new_apk_dir = get_apk_dir()
    replacements = [
        (OLD_JENKINS_CLONE, JENKINS_CLONE),
        (OLD_BUILDS, new_apk_dir),
    ]

    updated = []
    for pattern in GLOB_PATTERNS:
        if '*' in pattern:
            base, suffix = pattern.split('*', 1)
            dir_path = os.path.join(JENKINS_CLONE, base.strip('/'))
            if not os.path.isdir(dir_path):
                continue
            for name in os.listdir(dir_path):
                if suffix == '.sh' and name.endswith('.sh'):
                    path = os.path.join(dir_path, name)
                else:
                    path = os.path.join(dir_path, name)
                if os.path.isfile(path):
                    updated.extend(process_file(path, replacements, dry_run))
        else:
            path = os.path.join(JENKINS_CLONE, pattern)
            if os.path.isfile(path):
                updated.extend(process_file(path, replacements, dry_run))

    if dry_run:
        if updated:
            print('以下文件将发生替换：')
            for f, n in updated:
                print('  %s (%d 处)' % (f, n))
        else:
            print('未发现需要替换的路径，或文件不存在。')
    else:
        for f, n in updated:
            print('已更新 %s（%d 处）' % (f, n))
        if updated:
            print('路径已统一为 apk-site 下配置，可直接使用。')


def process_file(path, replacements, dry_run):
    try:
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        print('读取失败 %s: %s' % (path, e))
        return []

    total = 0
    for old_val, new_val in replacements:
        if old_val in content:
            total += content.count(old_val)
            content = content.replace(old_val, new_val)
    if total == 0:
        return []

    rel_path = os.path.relpath(path, APK_SITE_ROOT)
    if dry_run:
        return [(rel_path, total)]

    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print('写入失败 %s: %s' % (path, e))
        return []
    return [(rel_path, total)]


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从备份 ZIP 恢复 data 目录。"""

import os
import sys
import zipfile

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _ROOT)

from config import DATA_DIR


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print('用法: python scripts/restore_backup.py backups/apk-site-xxxx.zip')
        return 1
    backup_path = os.path.abspath(argv[0])
    if not os.path.isfile(backup_path):
        print('备份文件不存在: %s' % backup_path)
        return 1
    with zipfile.ZipFile(backup_path, 'r') as zf:
        members = [m for m in zf.namelist() if m.startswith('data/')]
        if not members:
            print('备份中未找到 data/ 内容')
            return 1
        zf.extractall(_ROOT, members)
    print('恢复完成: %s' % backup_path)
    print('已恢复到: %s' % DATA_DIR)
    return 0


if __name__ == '__main__':
    sys.exit(main())

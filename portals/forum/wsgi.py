#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""论坛态（forum）唯一运行入口。"""

import argparse
import os
import sys
from datetime import datetime

CORE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'common', 'core'))
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

os.environ['APP_PORTAL_MODE'] = 'forum'
os.environ['APK_PORT'] = os.getenv('FORUM_PORT', os.getenv('APK_PORT', '5005'))
os.environ['ENABLE_DOWNLOAD_FILE_SERVICE'] = 'false'
os.environ['ENABLE_BACKGROUND_SCHEDULER'] = 'false'
os.environ['RUNTIME_ENTRYPOINT'] = 'portals/forum/wsgi.py'
os.environ['RUNTIME_ENTRY_VERSION'] = '2026-05-23-3folder-contract-v1'

from app_new import app  # noqa: E402,F401
from utils import setup_logging  # noqa: E402

logger = setup_logging()
logger.info('ENTRYPOINT_SIGNATURE portal=%s port=%s entry=%s version=%s ts=%s',
            os.environ.get('APP_PORTAL_MODE'),
            os.environ.get('APK_PORT'),
            os.environ.get('RUNTIME_ENTRYPOINT'),
            os.environ.get('RUNTIME_ENTRY_VERSION'),
            datetime.utcnow().isoformat())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=int(os.getenv('APK_PORT', '5005')))
    args = parser.parse_args()
    os.environ['APK_PORT'] = str(args.port)
    app.run(host=os.getenv('APK_HOST', '0.0.0.0'), port=args.port, debug=False)


if __name__ == '__main__':
    main()

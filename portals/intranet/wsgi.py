#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内网态（admin）唯一运行入口。"""

import argparse
import os
import sys
from datetime import datetime

CORE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'common', 'core'))
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

os.environ['APP_PORTAL_MODE'] = 'admin'
os.environ['APK_PORT'] = os.getenv('ADMIN_PORT', os.getenv('APK_PORT', '5003'))
os.environ['ENABLE_DOWNLOAD_FILE_SERVICE'] = 'true'
os.environ['ENABLE_BACKGROUND_SCHEDULER'] = 'true'
os.environ['RUNTIME_ENTRYPOINT'] = 'portals/intranet/wsgi.py'
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
    parser.add_argument('--port', type=int, default=int(os.getenv('APK_PORT', '5003')))
    args = parser.parse_args()
    os.environ['APK_PORT'] = str(args.port)
    app.run(host=os.getenv('APK_HOST', '0.0.0.0'), port=args.port, debug=False)


if __name__ == '__main__':
    main()

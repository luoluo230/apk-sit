#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""唯一运行入口（WSGI）。请通过 waitress admin_wsgi:app 启动。"""

import os
from datetime import datetime

os.environ['APP_PORTAL_MODE'] = 'admin'
os.environ['APK_PORT'] = os.getenv('ADMIN_PORT', os.getenv('APK_PORT', '5003'))
os.environ['ENABLE_DOWNLOAD_FILE_SERVICE'] = 'true'
os.environ['ENABLE_BACKGROUND_SCHEDULER'] = 'true'
os.environ['RUNTIME_ENTRYPOINT'] = 'admin_wsgi.py'
os.environ['RUNTIME_ENTRY_VERSION'] = '2026-05-15-entry-contract-v1'

from app_new import app  # noqa: E402,F401
from utils import setup_logging  # noqa: E402

logger = setup_logging()
logger.info('ENTRYPOINT_SIGNATURE portal=%s port=%s entry=%s version=%s ts=%s',
            os.environ.get('APP_PORTAL_MODE'),
            os.environ.get('APK_PORT'),
            os.environ.get('RUNTIME_ENTRYPOINT'),
            os.environ.get('RUNTIME_ENTRY_VERSION'),
            datetime.utcnow().isoformat())

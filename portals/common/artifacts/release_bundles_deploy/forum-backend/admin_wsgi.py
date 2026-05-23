#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

os.environ['APP_PORTAL_MODE'] = 'admin'
os.environ['APK_PORT'] = os.getenv('ADMIN_PORT', os.getenv('APK_PORT', '5003'))

from app_new import app, _on_start  # noqa: E402

_on_start()

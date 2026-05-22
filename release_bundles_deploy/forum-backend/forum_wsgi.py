#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os

os.environ["APP_PORTAL_MODE"] = "forum"
os.environ["APK_PORT"] = os.getenv("FORUM_PORT", "5005")
os.environ["ENABLE_DOWNLOAD_FILE_SERVICE"] = "false"
os.environ["ENABLE_BACKGROUND_SCHEDULER"] = "false"

from app_new import app  # noqa: E402,F401

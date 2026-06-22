# -*- coding: utf-8 -*-
"""Player portal WSGI entry (split bundle / production)."""

import os

os.environ.setdefault("APP_PORTAL_MODE", "player")

from app_new import app  # noqa: E402

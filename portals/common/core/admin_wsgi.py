# -*- coding: utf-8 -*-
"""Admin portal WSGI entry (split bundle / production)."""

import os

os.environ.setdefault("APP_PORTAL_MODE", "admin")

from app_new import app  # noqa: E402

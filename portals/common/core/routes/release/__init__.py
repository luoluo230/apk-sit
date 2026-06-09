# -*- coding: utf-8 -*-
"""Release platform public/admin API routes."""

from flask import Blueprint

release_bp = Blueprint("release", __name__)

from routes.release import scopes  # noqa: E402,F401

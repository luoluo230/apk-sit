# -*- coding: utf-8 -*-
"""Public release platform APIs."""

from flask import Blueprint

from routes.release.manifests import bp as manifests_bp
from routes.release.scopes import bp as scopes_bp

bp = Blueprint("release_platform", __name__)
bp.register_blueprint(scopes_bp)
bp.register_blueprint(manifests_bp)

__all__ = ["bp"]

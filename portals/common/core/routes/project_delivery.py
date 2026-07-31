# -*- coding: utf-8 -*-
"""Project-owned delivery pages and APIs."""

from __future__ import annotations

from flask import Blueprint

from models.data import projects_db
from services.ops.environment_runtime_service import build_environment_runtime_overview
from services.release.env_registry import get_project_env_defs
from services.release.release_order_service import resolve_channel_build_journey

from routes.delivery.build_events_api import register_build_events_routes
from routes.delivery.helpers import DELIVERY_ASSET_VER
from routes.delivery.journey_api import register_journey_routes
from routes.delivery.pages import register_page_routes
from routes.delivery.public_api import register_public_routes
from routes.delivery.release_console_api import register_release_console_routes
from routes.delivery.release_orders_api import register_release_order_routes
from routes.delivery.scope_api import register_scope_routes

from routes.approval_webhooks import register_approval_webhook_routes

bp = Blueprint("project_delivery", __name__)

register_page_routes(bp)
register_scope_routes(bp)
register_journey_routes(bp)
register_release_order_routes(bp)
register_release_console_routes(bp)
register_build_events_routes(bp)
register_public_routes(bp)
register_approval_webhook_routes(bp)

__all__ = [
    "bp",
    "DELIVERY_ASSET_VER",
    "projects_db",
    "get_project_env_defs",
    "build_environment_runtime_overview",
    "resolve_channel_build_journey",
]

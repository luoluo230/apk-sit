# -*- coding: utf-8 -*-
"""Server / client framework module registry (topology vs casual BaaS)."""

from server_frameworks.registry import (
    FRAMEWORK_MODULES,
    client_module_for_project,
    enabled_modules,
    is_module_enabled,
    register_server_frameworks,
    server_mode_for_project,
)

__all__ = [
    "FRAMEWORK_MODULES",
    "client_module_for_project",
    "enabled_modules",
    "is_module_enabled",
    "register_server_frameworks",
    "server_mode_for_project",
]

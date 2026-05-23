"""Admin route package for split adapters.

This package hosts domain adapters that keep URL/permission behavior stable while
the monolithic ``routes/admin_routes.py`` is incrementally decomposed.
"""

SPLIT_DOMAINS = (
    "users",
    "users_transfer",
    "projects",
    "projects_misc",
    "approval",
    "channels",
    "notifications",
    "audit",
    "media",
    "site_config",
    "tasks",
    "versions",
    "reports",
    "settings",
)

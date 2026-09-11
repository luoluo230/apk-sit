# -*- coding: utf-8 -*-
"""Compatibility exports for legacy ``models`` imports.

The implementation moved into :mod:`data`, whose initialization can consult the
registry database.  Importing every compatibility value here made importing a
database backend circular (``models -> data -> registry -> models.db_*``).
Resolve legacy values lazily so the package remains compatible without making
database startup order depend on incidental imports.
"""

__all__ = [
    'users_db', 'projects_db', 'download_stats', 'login_attempts', 'versions_db',
    'changelog_db', 'audit_log_db', 'project_versions_db', 'channels_db',
    'notifications_db', 'approvals_db', 'approval_records_db', 'system_config_db',
    'report_templates_db', 'export_records_db',
    'load_download_events', 'save_download_events', 'record_download_event',
    'extract_project_name', 'extract_version_from_filename', 'extract_apk_info',
    'get_project_apk_count', 'get_total_downloads', 'get_active_projects_count',
    'save_users', 'save_projects', 'save_stats', 'save_login_attempts', 'save_versions',
    'save_changelog', 'save_audit_log', 'log_audit',
    'save_notifications', 'save_approvals', 'save_approval_records', 'save_system_config',
    'save_report_templates', 'save_export_records',
    'add_notification', 'get_notifications_for_user',
    'get_system_config', 'set_system_config',
    'APPROVAL_TYPES', 'create_approval', 'get_pending_approvals_for_user', 'approve_or_reject',
    'parse_apk_metadata',
    'is_inner_network', 'check_login_attempts', 'record_login_attempt',
    'get_project', 'has_project', 'list_projects', 'save_project',
    'list_channels', 'list_project_versions', 'save_project_versions', 'list_all_project_versions',
]


def __getattr__(name):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from . import data as legacy_data

    return getattr(legacy_data, name)

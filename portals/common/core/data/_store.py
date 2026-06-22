# -*- coding: utf-8 -*-
"""Unified storage: SQLite primary + JSON file backup."""

import logging
import os

from config import DATA_DIR
from utils import load_json, save_json

# File path constants
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
PROJECTS_FILE = os.path.join(DATA_DIR, 'projects.json')
STATS_FILE = os.path.join(DATA_DIR, 'download_stats.json')
DOWNLOAD_EVENTS_FILE = os.path.join(DATA_DIR, 'download_events.json')
LOGIN_ATTEMPTS_FILE = os.path.join(DATA_DIR, 'login_attempts.json')
VERSIONS_FILE = os.path.join(DATA_DIR, 'versions.json')
CHANGELOG_FILE = os.path.join(DATA_DIR, 'changelog.json')
AUDIT_LOG_FILE = os.path.join(DATA_DIR, 'audit_log.json')
JENKINS_INSTANCES_FILE = os.path.join(DATA_DIR, 'jenkins_instances.json')
PROJECT_TASKS_FILE = os.path.join(DATA_DIR, 'project_tasks.json')
NOTIFICATIONS_FILE = os.path.join(DATA_DIR, 'notifications.json')
APPROVALS_FILE = os.path.join(DATA_DIR, 'approvals.json')
APPROVAL_RECORDS_FILE = os.path.join(DATA_DIR, 'approval_records.json')
SYSTEM_CONFIG_FILE = os.path.join(DATA_DIR, 'system_config.json')
REPORT_TEMPLATES_FILE = os.path.join(DATA_DIR, 'report_templates.json')
EXPORT_RECORDS_FILE = os.path.join(DATA_DIR, 'export_records.json')
USER_TASK_PLANS_FILE = os.path.join(DATA_DIR, 'user_task_plans.json')
PRODUCTS_FILE = os.path.join(DATA_DIR, 'products.json')
PRODUCT_MEDIA_DIR = os.path.join(DATA_DIR, 'product_media')
PROJECT_VERSIONS_FILE = os.path.join(DATA_DIR, 'project_versions.json')
CHANNELS_FILE = os.path.join(DATA_DIR, 'channels.json')
BUILD_VERSION_RECORDS_FILE = os.path.join(DATA_DIR, 'build_version_records.json')
CLIENT_TELEMETRY_FILE = os.path.join(DATA_DIR, 'client_telemetry.json')

DOWNLOAD_EVENTS_MAX_DAYS = 365
NOTIFICATIONS_RETENTION_DAYS = 90
SUPPORTED_PACKAGE_EXTENSIONS = ('.apk', '.ipa')
PLATFORM_LABELS = {
    'android': 'Android',
    'ios': 'iOS',
}


def get_logger():
    return logging.getLogger(__name__)


def load_document(filepath, default=None):
    """Load JSON document: SQLite primary, JSON file fallback/import."""
    if default is None:
        default = {}
    return load_json(filepath, default)


def save_document(filepath, data):
    """Persist JSON document: SQLite primary + optional JSON file mirror."""
    save_json(filepath, data)


class Storage:
    """In-memory view of a JSON document backed by unified storage."""

    def __init__(self, filepath, default=None):
        self.filepath = filepath
        self.default = default if default is not None else {}
        self.data = load_document(filepath, self.default)

    def load(self):
        self.data = load_document(self.filepath, self.default)
        return self.data

    def save(self, data=None):
        if data is not None:
            self.data = data
        save_document(self.filepath, self.data)
        return self.data

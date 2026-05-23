"""Version 领域规则：状态集合、别名映射、作用域。"""

from __future__ import annotations

VERSION_STATUSES = [
    ("draft", "草稿"),
    ("testing", "测试中"),
    ("active", "有效"),
    ("disabled", "失效"),
    ("archived", "归档"),
]
VERSION_STATUS_MAP = dict(VERSION_STATUSES)

VERSION_STATUS_ALIASES = {
    "draft": "draft",
    "valid": "active",
    "enabled": "active",
    "online": "active",
    "deprecated": "disabled",
    "obsolete": "disabled",
    "invalid": "disabled",
    "disabled": "disabled",
    "inactive": "disabled",
    "testing": "testing",
    "test": "testing",
    "beta": "testing",
    "archived": "archived",
    "archive": "archived",
}


def normalize_version_status(raw_status):
    status = (raw_status or "").strip().lower()
    status = VERSION_STATUS_ALIASES.get(status, status)
    if status not in VERSION_STATUS_MAP:
        status = "active"
    return status


def normalize_edit_scope(raw_scope):
    scope = (raw_scope or "").strip().lower()
    if scope in ("version_group", "version_code"):
        return scope
    return "version_group"


def build_status_audit_tags(old_status, new_status):
    old_s = normalize_version_status(old_status)
    new_s = normalize_version_status(new_status)
    if old_s == new_s:
        return []
    tags = ["status_transition:%s->%s" % (old_s, new_s)]
    if old_s == "active" and new_s == "disabled":
        tags.append("risk:active_to_disabled")
    if old_s == "testing" and new_s == "active":
        tags.append("release:testing_to_active")
    return tags


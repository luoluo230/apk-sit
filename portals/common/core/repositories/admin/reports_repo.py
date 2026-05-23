"""Reports data access wrappers."""

from __future__ import annotations

from typing import Any, Dict, List

from models.data import (
    report_templates_db,
    export_records_db,
    save_report_templates,
    save_export_records,
    log_audit,
    resolve_project_id,
    download_stats,
    load_download_events,
    extract_project_name,
    extract_version_from_filename,
)


def list_templates() -> List[Dict[str, Any]]:
    return report_templates_db


def append_template(item: Dict[str, Any]) -> None:
    report_templates_db.append(item)
    save_report_templates()


def find_template(template_id: str) -> Dict[str, Any] | None:
    return next((t for t in report_templates_db if t.get("id") == template_id), None)


def append_export_record(item: Dict[str, Any]) -> None:
    export_records_db.append(item)
    save_export_records()


def audit(action: str, target: str) -> None:
    log_audit(action, target)


def resolve_project(project_ref: str) -> str:
    return resolve_project_id(project_ref) or ""


def download_stats_items():
    return download_stats.items()


def load_events() -> List[Dict[str, Any]]:
    return load_download_events()


def parse_project(filename: str) -> str:
    return extract_project_name(filename)


def parse_version(filename: str) -> str:
    return extract_version_from_filename(filename)

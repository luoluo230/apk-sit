# -*- coding: utf-8 -*-
"""Report templates and export records."""

from data._store import EXPORT_RECORDS_FILE, REPORT_TEMPLATES_FILE, load_document, save_document

report_templates_db = load_document(REPORT_TEMPLATES_FILE, [])
export_records_db = load_document(EXPORT_RECORDS_FILE, [])


def save_report_templates():
    save_document(REPORT_TEMPLATES_FILE, report_templates_db)


def save_export_records():
    save_document(EXPORT_RECORDS_FILE, export_records_db)

# -*- coding: utf-8 -*-
"""Project tasks."""

from data._store import PROJECT_TASKS_FILE, load_document, save_document

project_tasks_db = load_document(PROJECT_TASKS_FILE, {})


def save_project_tasks():
    save_document(PROJECT_TASKS_FILE, project_tasks_db)

# -*- coding: utf-8 -*-
"""Product catalog."""

from data._store import PRODUCTS_FILE, PRODUCT_MEDIA_DIR, load_document, save_document

products_db = load_document(PRODUCTS_FILE, [])


def save_products():
    save_document(PRODUCTS_FILE, products_db)


def resolve_project_id_for_product(product):
    from data.projects import projects_db, resolve_project_id

    if not isinstance(product, dict):
        return ''
    raw_project = product.get('project_id')
    raw_resolved = resolve_project_id(raw_project)
    if raw_resolved:
        return raw_resolved
    candidates = [
        product.get('name'),
        product.get('title'),
        product.get('name_en'),
        product.get('slug'),
        product.get('intro'),
    ]
    for candidate in candidates:
        project_id = resolve_project_id(candidate)
        if project_id:
            return project_id
    # Last-resort compatibility for old datasets with a single project.
    if isinstance(projects_db, dict) and len(projects_db) == 1:
        return next(iter(projects_db.keys()))
    return ''

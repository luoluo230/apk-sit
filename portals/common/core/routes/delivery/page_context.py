# -*- coding: utf-8 -*-
"""Delivery page context builders."""

from __future__ import annotations


def project_docs_embed_context(project_id: str) -> dict:
    import os

    from routes.docs_routes import _docs_db

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))
    doc_path = os.path.join(repo_root, "docs", "client_bootstrap_contract.md")
    docs_markdown = ""
    if os.path.isfile(doc_path):
        with open(doc_path, "r", encoding="utf-8") as fh:
            docs_markdown = fh.read()
    project_docs = [
        row for row in (_docs_db() or [])
        if isinstance(row, dict) and str(row.get("project_id") or "").strip() in ("", project_id)
    ]
    project_docs.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return {"docs_markdown": docs_markdown, "project_docs": project_docs[:30]}

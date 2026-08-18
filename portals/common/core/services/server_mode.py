# -*- coding: utf-8 -*-
"""Shared project server_mode helpers (no BaaS / topology coupling)."""

from __future__ import annotations

from models.data import projects_db


def project_server_mode(project_id: str) -> str:
    proj = projects_db.get(project_id) or {}
    mode = str(proj.get("server_mode") or "topology").strip().lower()
    return mode if mode in ("topology", "casual_baas") else "topology"


def is_casual_baas_project(project_id: str) -> bool:
    return project_server_mode(project_id) == "casual_baas"


def is_topology_project(project_id: str) -> bool:
    return project_server_mode(project_id) == "topology"

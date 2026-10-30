# -*- coding: utf-8 -*-
"""Casual BaaS plane: service record, bootstrap, announcement, and mail."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from services.baas.announce_service import save_announcement
from services.baas.bootstrap_service import build_baas_bootstrap
from services.baas.mail_service import send_mail
from services.baas.service_crud import ensure_service, get_service, update_service


def open_service(project_id: str, env_key: str, actor: str = "admin") -> Tuple[Dict[str, Any], str]:
    return ensure_service(project_id, env_key, actor=actor)


def update_service_note(project_id: str, service_id: str, description: str, actor: str = "admin") -> Dict[str, Any]:
    return update_service(project_id, service_id, {"description": description}, actor=actor)


def read_service(service_id: str) -> Dict[str, Any]:
    row = get_service(service_id)
    if not row:
        raise ValueError("休闲服务不存在")
    return row


def client_bootstrap(project_id: str, env_key: str, game_id: str = "", game_key: str = "") -> Dict[str, Any]:
    return build_baas_bootstrap(
        project_id=project_id,
        game_id=game_id,
        game_key=game_key,
        env_key=env_key,
    )


def publish_announcement(service_id: str, title: str, body: str, actor: str = "admin") -> Dict[str, Any]:
    return save_announcement(service_id, {"title": title, "body": body, "status": "published"}, actor=actor)


def send_player_mail(service_id: str, player_id: str, title: str, body: str, actor: str = "admin") -> Dict[str, Any]:
    return send_mail(service_id, {"player_id": player_id, "title": title, "body": body}, actor=actor)

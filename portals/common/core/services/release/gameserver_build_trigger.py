# -*- coding: utf-8 -*-
"""Trigger the GameServer-Build Jenkins job. Client jobs are not used."""

from __future__ import annotations

from typing import Any, Dict


def trigger_gameserver_job(project_id: str, server_release_id: str, job_name: str) -> Dict[str, Any]:
    name = str(job_name or "").strip()
    if name in {"Android", "iOS", "WxMinigame"}:
        raise ValueError("游戏服构建不能使用客户端 Job")
    from services import jenkins as jenkins_svc

    params = {
        "PROJECT_ID": str(project_id or "").strip(),
        "SERVER_RELEASE_ID": str(server_release_id or "").strip(),
        "SERVER_VERSION_LABEL": "dev",
    }
    success, number, error = jenkins_svc.trigger_build(params, job_name=name)
    if not success:
        raise ValueError(error or "触发游戏服构建失败")
    return {"build_number": number, "job_name": name}

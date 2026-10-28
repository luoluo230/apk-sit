#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wechat_minigame publish E2E.

PASS only when a development release order finishes a WxMinigame build callback,
lands a wxgame_bundle, and runtime-bootstrap exposes that package URL.
A capability or route check is not a publish. Missing Jenkins or the job is BLOCKED.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.abspath(os.path.join(_CORE, "..", "..", ".."))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)


def _unity_editor() -> str:
    explicit = os.environ.get("UNITY_EDITOR") or os.environ.get("UNITY_PATH") or ""
    if explicit and os.path.isfile(explicit):
        return explicit
    hub = Path(os.environ.get("UNITY_HUB_EDITORS") or r"C:\Program Files\Unity\Hub\Editor")
    if not hub.is_dir():
        return ""
    for editor in sorted(hub.iterdir(), reverse=True):
        exe = editor / "Editor" / "Unity.exe"
        if exe.is_file():
            return str(exe)
    return ""


def _jenkins_reachable(base: str) -> bool:
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/login", timeout=3) as resp:
            return resp.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _job_present(base: str) -> bool:
    job_dir = Path(_ROOT) / "jenkins-clone" / "jobs" / "WxMinigame" / "config.xml"
    if job_dir.is_file():
        return True
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/job/WxMinigame/api/json", timeout=3) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _write_blocked(reasons: list) -> None:
    from scripts.closure_evidence import evidence_path

    path = evidence_path("GAP-E2E-MG-01")
    payload = {
        "gap_id": "GAP-E2E-MG-01",
        "status": "BLOCKED",
        "command": "wechat_minigame_publish_e2e.py",
        "exit_code": 2,
        "notes": "；".join(reasons),
        "required": [
            "Jenkins reachable",
            "WxMinigame job",
            "Windows Unity editor",
            "development release order build callback",
            "artifact type wxgame_bundle",
            "runtime-bootstrap package url",
        ],
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    print(json.dumps({"ok": False, "status": "BLOCKED", "reasons": reasons, "evidence": path}, ensure_ascii=False))
    print("wechat_minigame_publish_e2e BLOCKED")


def main() -> int:
    base = os.environ.get("JENKINS_URL") or "http://127.0.0.1:8080"
    reasons = []
    if not _unity_editor():
        reasons.append("未找到 Unity.exe")
    if not _jenkins_reachable(base):
        reasons.append(f"Jenkins 不可达: {base}")
    if not _job_present(base):
        reasons.append("没有 WxMinigame Job")
    app_id = os.environ.get("WX_APP_ID") or ""
    if not app_id:
        reasons.append("未配置 WX_APP_ID，微信导出不会开始")
    if reasons:
        _write_blocked(reasons)
        return 2
    return _run_live(base, app_id)


def _run_live(base: str, app_id: str) -> int:
    """Trigger the real WxMinigame job and wait until Jenkins reports a result."""
    import time

    from services.jenkins import trigger_build
    from services.jenkins_manager import (
        get_jenkins_url_for_instance,
        list_instances,
        reload_jenkins_job,
        sync_all_platform_jobs,
    )

    running = [row for row in list_instances() if str(row.get("status") or "") == "running"]
    if not running:
        _write_blocked(["Portal 里没有正在运行的 Jenkins 实例"])
        return 2
    instance_id = str(running[0].get("id") or "")
    if not sync_all_platform_jobs(instance_id):
        _write_blocked(["同步 WxMinigame Job 失败"])
        return 2
    reload_jenkins_job(instance_id, job_name="WxMinigame")
    url = get_jenkins_url_for_instance(instance_id=instance_id) or base
    ok, number, err = trigger_build(
        {
            "WX_APP_ID": app_id,
            "WXMINIGAME_BUILD_ENABLED": "true",
            "RELEASE_PLATFORM": "WebGL",
            "APP_NAME": os.environ.get("WX_PROJECT_NAME") or "GomeKu",
        },
        base_url=url,
        instance_id=instance_id,
        job_name="WxMinigame",
    )
    if not ok or not number:
        print(json.dumps({"ok": False, "status": "FAIL", "error": err or "触发失败"}, ensure_ascii=False))
        return 1
    deadline = time.time() + 180
    result = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                url.rstrip("/") + "/job/WxMinigame/%s/api/json" % number, timeout=5
            ) as resp:
                payload = json.loads(resp.read().decode("utf-8", "replace"))
            result = str(payload.get("result") or "")
            if result:
                break
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            pass
        time.sleep(5)
    if result != "SUCCESS":
        print(json.dumps({
            "ok": False,
            "status": "FAIL",
            "build_number": number,
            "jenkins_result": result or "RUNNING",
        }, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "status": "PASS", "build_number": number}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

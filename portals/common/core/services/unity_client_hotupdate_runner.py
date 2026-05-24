# -*- coding: utf-8 -*-
"""调用 Unity PlayMode 跑真实客户端启动热更验收。"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_UNITY_CANDIDATES = (
    "/Applications/Unity/Hub/Editor/6000.3.8f1/Unity.app/Contents/MacOS/Unity",
    os.path.expanduser("~/Applications/Unity/Hub/Editor/6000.3.8f1/Unity.app/Contents/MacOS/Unity"),
)


def resolve_unity_executable(explicit: str | None = None) -> str:
    if explicit and Path(explicit).is_file():
        return explicit
    env = (os.getenv("UNITY_PATH") or os.getenv("UNITY_EDITOR") or "").strip()
    if env and Path(env).is_file():
        return env
    for cand in DEFAULT_UNITY_CANDIDATES:
        if Path(cand).is_file():
            return cand
    raise FileNotFoundError(
        "未找到 Unity 可执行文件。请设置 UNITY_PATH 或安装 Unity 6000.3.8f1。"
    )


def run_unity_client_startup_acceptance(
    *,
    unity_project: str,
    api_base: str = "http://127.0.0.1:5003",
    project_id: str = "GomeKu",
    channel: str = "wechat",
    environment: str = "Development",
    version_name: str = "1.0.0",
    version_code: str = "",
    platform: str = "Android",
    resource_server: str = "https://wlhotupdate1.oss-cn-beijing.aliyuncs.com/MyGame1",
    scenario: str = "basic",
    timeout_sec: int = 45,
    unity_path: str | None = None,
) -> dict[str, Any]:
    project = Path(unity_project).resolve()
    if not (project / "Assets").is_dir():
        raise FileNotFoundError(f"Unity 工程不存在: {project}")

    unity = resolve_unity_executable(unity_path)
    report_path = project / "Library/ClientAcceptance/client-startup-acceptance-report.json"
    if report_path.exists():
        report_path.unlink()

    args = [
        unity,
        "-batchmode",
        "-nographics",
        "-disableAssemblyUpdater",
        "-quitTimeout",
        str(max(60, timeout_sec + 30)),
        "-projectPath",
        str(project),
        "-executeMethod",
        "ClientStartupHotUpdateExerciseRunner.RunAcceptance",
        "-clientAcceptanceApiBase",
        api_base.rstrip("/"),
        "-clientAcceptanceProjectId",
        project_id,
        "-clientAcceptanceChannel",
        channel,
        "-clientAcceptanceEnvironment",
        environment,
        "-clientAcceptanceVersionName",
        version_name,
        "-clientAcceptancePlatform",
        platform,
        "-clientAcceptanceResourceServer",
        resource_server,
        "-clientAcceptanceScenario",
        scenario,
        "-clientAcceptanceTimeoutSec",
        str(timeout_sec),
        "-logFile",
        str(project / "Library/ClientAcceptance/unity-client-acceptance.log"),
    ]

    import time

    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + timeout_sec + 90
    combined = ""
    while time.time() < deadline:
        if report_path.is_file():
            try:
                report_probe = json.loads(report_path.read_text(encoding="utf-8"))
                if report_probe.get("Passed") or report_probe.get("passed"):
                    break
            except Exception:
                pass

        if proc.poll() is not None:
            break

        time.sleep(0.25)

    if proc.poll() is None:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    _force_kill_unity_for_project(str(project))

    report: dict[str, Any] = {}
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as exc:
            report = {"passed": False, "summary": f"报告解析失败: {exc}"}

    passed = bool(report.get("Passed") or report.get("passed"))
    return {
        "passed": passed,
        "unity_exit_code": proc.returncode if proc.returncode is not None else -1,
        "scenario": scenario,
        "tier": report.get("Tier") or report.get("tier") or ("entered_login" if passed else "failed"),
        "summary": report.get("Summary") or report.get("summary") or _extract_failure_summary(combined),
        "final_state": report.get("FinalState") or report.get("finalState"),
        "catalog_url": report.get("CatalogUrl") or report.get("catalogUrl"),
        "report_path": str(report_path),
        "unity_log_tail": combined[-4000:],
    }


def _force_kill_unity_for_project(project_path: str) -> None:
    """Unity batchmode 偶发 Exit 后仍挂起，清理占用工程锁的进程。"""
    try:
        import signal

        out = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="], text=True)
    except Exception:
        return

    project_path = project_path.strip()
    for line in out.splitlines():
        if "Unity.app/Contents/MacOS/Unity" not in line or project_path not in line:
            continue
        pid_text = line.strip().split(None, 1)[0]
        if not pid_text.isdigit():
            continue
        try:
            os.kill(int(pid_text), signal.SIGKILL)
        except OSError:
            pass


def _extract_failure_summary(log: str) -> str:
    for pattern in (
        r"\[ClientAcceptance\].*",
        r"Assertion failed.*",
        r"RunFinished result=.*",
    ):
        matches = re.findall(pattern, log, flags=re.IGNORECASE)
        if matches:
            return matches[-1][:500]
    return "Unity 客户端验收未通过，详见 unity-client-acceptance.log"

# -*- coding: utf-8 -*-
"""Parse Jenkins freestyle console markers + optional step push into packaging detection.

Android (`commercial_android_pipeline.sh`): stages 0 → 1 → 2 → 3 → 4 → END
iOS (`commercial_ios_pipeline.sh`): shared 0–3 then 5 → 6 → 7 → 8

Prefer Jenkins push (`jenkins_step_push_store`) when present; fall back to log markers.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# Status vocabulary for UI: success=绿 / failed=红 / running=蓝 / stopped=灰 / pending=待开始 / skipped=未启用
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_RUNNING = "running"
STATUS_STOPPED = "stopped"
STATUS_PENDING = "pending"
STATUS_SKIPPED = "skipped"

_STATUS_LABELS = {
    STATUS_SUCCESS: "完成",
    STATUS_FAILED: "失败",
    STATUS_RUNNING: "进行中",
    STATUS_STOPPED: "停止",
    STATUS_PENDING: "待开始",
    STATUS_SKIPPED: "未启用",
}

# Shared commercial steps (Android / iOS).
_SHARED_STEPS: List[Dict[str, Any]] = [
    {
        "id": "env_prep",
        "stage_key": "0",
        "label": "环境准备",
        "param": "",
        "always": True,
        "platforms": ("android", "ios"),
        "start_patterns": (r"\[阶段\s*0\]", r"环境准备"),
        "done_patterns": (r"可插拔版本构建流水线", r"\[阶段\s*1\]", r"=== Step 1:", r"Step 1 \(配置导出\) 已跳过"),
        "fail_patterns": (r"FAIL:.*Git", r"FAIL:.*环境"),
    },
    {
        "id": "config_export",
        "stage_key": "1",
        "label": "配置导出",
        "param": "CONFIG_EXPORT_ENABLED",
        "always": False,
        "platforms": ("android", "ios"),
        "start_patterns": (r"\[阶段\s*1\]", r"=== Step 1:", r"配置导出发布"),
        "done_patterns": (r"Step 1 完成", r"✅ Step1 校验通过"),
        "fail_patterns": (r"FAIL: Step1", r"Step1 ConfigRemotePublish 退出"),
        "skip_patterns": (r"Step 1 \(配置导出\) 已跳过",),
    },
    {
        "id": "resource_build",
        "stage_key": "2",
        "label": "资源打包",
        "param": "RESOURCE_BUILD_ENABLED",
        "always": False,
        "platforms": ("android", "ios"),
        "start_patterns": (r"\[阶段\s*2\]", r"=== Step 2:", r"资源打包"),
        "done_patterns": (r"Step 2 完成",),
        "fail_patterns": (r"FAIL:.*Step\s*2", r"ResourcePipelineCli"),
        "skip_patterns": (r"Step 2 \(资源打包\) 已跳过",),
    },
    {
        "id": "hot_release",
        "stage_key": "3",
        "label": "热更发布",
        "param": "HOT_RELEASE_ENABLED",
        "always": False,
        "platforms": ("android", "ios"),
        "start_patterns": (r"\[阶段\s*3\]", r"=== Step 3:", r"代码与热更发布", r"代码\+资源热更发布"),
        "done_patterns": (r"Step 3 完成",),
        "fail_patterns": (r"FAIL:.*Step\s*3", r"CommercialReleaseCli"),
        "skip_patterns": (r"Step 3 \(热更发布\) 已跳过",),
    },
]

_ANDROID_ONLY: List[Dict[str, Any]] = [
    {
        "id": "apk_build",
        "stage_key": "4",
        "label": "APK 打包",
        "param": "APK_BUILD_ENABLED",
        "always": False,
        "platforms": ("android",),
        "start_patterns": (r"\[阶段\s*4\]", r"=== Step 4:", r"APK 打包"),
        "done_patterns": (r"Step 4 完成", r"\[阶段\s*END\]", r"流水线执行完毕"),
        "fail_patterns": (r"FAIL:.*APK", r"FAIL:.*Step\s*4", r"ApkReleaseUploadCli"),
        "skip_patterns": (r"Step 4 \(APK打包\) 已跳过",),
    },
]

# iOS commercial pipeline appends after shared Steps 1–3 (APK disabled).
_IOS_ONLY: List[Dict[str, Any]] = [
    {
        "id": "ios_xcode_export",
        "stage_key": "5",
        "label": "iOS Xcode 导出",
        "param": "IOS_BUILD_ENABLED",
        "always": False,
        "platforms": ("ios",),
        "start_patterns": (r"\[阶段\s*5\]", r"Step 5:.*Xcode", r"\[ios\] Step 5"),
        "done_patterns": (r"Step 5 完成", r"\[阶段\s*6\]", r"\[ios\] Step 6"),
        "fail_patterns": (r"FAIL:.*Step\s*5", r"ExportXcodeFromCommandLine"),
        "skip_patterns": (r"iOS base package skipped", r"Step 5 \(.*\) 已跳过"),
    },
    {
        "id": "ios_ipa_archive",
        "stage_key": "6",
        "label": "IPA 归档导出",
        "param": "IOS_BUILD_ENABLED",
        "always": False,
        "platforms": ("ios",),
        "start_patterns": (r"\[阶段\s*6\]", r"Step 6:.*IPA", r"\[ios\] Step 6"),
        "done_patterns": (r"Step 6 完成", r"\[阶段\s*7\]", r"\[ios\] Step 7"),
        "fail_patterns": (r"FAIL:.*Step\s*6", r"ERROR: IPA not found", r"ExportIpaFromCommandLine"),
        "skip_patterns": (r"Step 6 \(.*\) 已跳过",),
    },
    {
        "id": "ios_artifact_land",
        "stage_key": "7",
        "label": "IPA 落盘/OSS",
        "param": "IOS_BUILD_ENABLED",
        "always": False,
        "platforms": ("ios",),
        "start_patterns": (r"\[阶段\s*7\]", r"Step 7:.*OSS", r"\[ios\] Step 7"),
        "done_patterns": (r"Step 7 完成", r"\[阶段\s*8\]", r"\[ios\] Step 8", r"iOS pipeline done"),
        "fail_patterns": (r"FAIL:.*Step\s*7", r"archive_build_artifact"),
        "skip_patterns": (r"Step 7 \(.*\) 已跳过",),
    },
    {
        "id": "ios_testflight",
        "stage_key": "8",
        "label": "TestFlight 上传",
        "param": "EXTERNAL_UPLOAD_TESTFLIGHT",
        "always": False,
        "platforms": ("ios",),
        "start_patterns": (r"\[阶段\s*8\]", r"Step 8:.*TestFlight", r"\[ios\] Step 8"),
        "done_patterns": (r"Step 8 完成", r"iOS pipeline done", r"======= iOS pipeline done"),
        "fail_patterns": (r"FAIL:.*Step\s*8", r"TestFlight upload failed"),
        "skip_patterns": (r"Step 8 \(.*\) 已跳过", r"TestFlight.*skip"),
    },
]

_STEP_CATALOG: List[Dict[str, Any]] = [*_SHARED_STEPS, *_ANDROID_ONLY, *_IOS_ONLY]

_PARAM_TRUE = {"1", "true", "yes", "on", "y"}


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in _PARAM_TRUE


def _any_match(patterns: tuple, text: str) -> bool:
    if not text or not patterns:
        return False
    for pat in patterns:
        if re.search(pat, text, flags=re.IGNORECASE):
            return True
    return False


def _param_map(parameters: Optional[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for key, value in (parameters or {}).items():
        out[str(key).strip().upper()] = str(value or "").strip()
    return out


def _normalize_platform(platform: str = "", parameters: Optional[Dict[str, Any]] = None) -> str:
    params = _param_map(parameters)
    raw = str(platform or params.get("RELEASE_PLATFORM") or params.get("PLATFORM") or "android").strip().lower()
    if raw in {"ios", "iphone", "ipad"}:
        return "ios"
    if "ios" in raw:
        return "ios"
    return "android"


def selected_detection_catalog(
    parameters: Optional[Dict[str, Any]] = None,
    *,
    platform: str = "",
) -> List[Dict[str, Any]]:
    """Return catalog rows for the platform, filtered by Jenkins params / pipeline toggles."""
    params = _param_map(parameters)
    plat = _normalize_platform(platform, parameters)
    selected: List[Dict[str, Any]] = []
    for row in _STEP_CATALOG:
        plats = row.get("platforms") or ("android", "ios")
        if plat not in plats:
            continue
        if row.get("always"):
            selected.append(row)
            continue
        param = str(row.get("param") or "").strip().upper()
        if not param:
            selected.append(row)
            continue
        # Missing param → enabled for commercial defaults when build has no params yet
        if param not in params:
            # iOS package steps default on; Android APK defaults on; TestFlight defaults on for iOS
            selected.append(row)
            continue
        if _truthy(params.get(param)):
            selected.append(row)
    return selected


def parse_detection_steps(
    log_text: str = "",
    *,
    parameters: Optional[Dict[str, Any]] = None,
    building: bool = False,
    result: str = "",
    stopped: bool = False,
    platform: str = "",
    pushed_steps: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Derive per-step detection states for the enabled packaging pipeline."""
    catalog = selected_detection_catalog(parameters, platform=platform)
    text = str(log_text or "")
    result_u = str(result or "").strip().upper()
    aborted = stopped or result_u == "ABORTED"
    failed_overall = result_u in {"FAILURE", "UNSTABLE"}
    success_overall = result_u == "SUCCESS" and not building
    pushed = pushed_steps if isinstance(pushed_steps, dict) else {}

    # Which stages have started / finished / failed in the console
    started: Dict[str, bool] = {}
    finished: Dict[str, bool] = {}
    failed: Dict[str, bool] = {}
    skipped: Dict[str, bool] = {}
    for row in _STEP_CATALOG:
        sid = str(row["id"])
        started[sid] = _any_match(tuple(row.get("start_patterns") or ()), text)
        finished[sid] = _any_match(tuple(row.get("done_patterns") or ()), text)
        failed[sid] = _any_match(tuple(row.get("fail_patterns") or ()), text)
        skipped[sid] = _any_match(tuple(row.get("skip_patterns") or ()), text)
        # Prefer explicit Jenkins push over log inference
        prow = pushed.get(sid) if isinstance(pushed.get(sid), dict) else None
        if prow:
            st = str(prow.get("status") or "").strip().lower()
            if st == STATUS_RUNNING:
                started[sid] = True
            elif st == STATUS_SUCCESS:
                started[sid] = True
                finished[sid] = True
            elif st == STATUS_FAILED:
                started[sid] = True
                failed[sid] = True
            elif st == STATUS_STOPPED:
                started[sid] = True
            elif st == STATUS_SKIPPED:
                skipped[sid] = True

    # If a later stage started, earlier selected stages are considered done (unless failed).
    ids = [str(r["id"]) for r in catalog]
    for idx, sid in enumerate(ids):
        if any(started.get(later) or finished.get(later) for later in ids[idx + 1 :]):
            if not failed.get(sid):
                finished[sid] = True

    if success_overall:
        for sid in ids:
            if not failed.get(sid) and not skipped.get(sid):
                finished[sid] = True

    # Active running step = first unfinished selected step that has started (or first pending while building)
    running_id = ""
    if building and not aborted:
        for sid in ids:
            if failed.get(sid):
                running_id = sid
                break
            if finished.get(sid) or skipped.get(sid):
                continue
            if started.get(sid) or not running_id:
                running_id = sid
                if started.get(sid):
                    break

    # On overall failure without explicit step fail, mark the running/last-started step failed
    if failed_overall and not building:
        hit = next((sid for sid in reversed(ids) if failed.get(sid) or started.get(sid)), "")
        if hit:
            failed[hit] = True

    steps: List[Dict[str, Any]] = []
    for index, row in enumerate(catalog, start=1):
        sid = str(row["id"])
        push_st = ""
        if isinstance(pushed.get(sid), dict):
            push_st = str(pushed[sid].get("status") or "").strip().lower()
        if push_st in {STATUS_SUCCESS, STATUS_FAILED, STATUS_RUNNING, STATUS_STOPPED, STATUS_SKIPPED}:
            status = push_st
        elif skipped.get(sid) and not started.get(sid) and not finished.get(sid):
            status = STATUS_SKIPPED
        elif failed.get(sid):
            status = STATUS_FAILED
        elif finished.get(sid):
            status = STATUS_SUCCESS
        elif aborted and (started.get(sid) or sid == running_id):
            status = STATUS_STOPPED
        elif building and (sid == running_id or (started.get(sid) and not finished.get(sid))):
            status = STATUS_RUNNING
        else:
            status = STATUS_PENDING

        pct = {
            STATUS_SUCCESS: 100,
            STATUS_FAILED: 100,
            STATUS_STOPPED: 100,
            STATUS_RUNNING: 62,
            STATUS_PENDING: 0,
            STATUS_SKIPPED: 0,
        }.get(status, 0)

        source = "jenkins_push" if isinstance(pushed.get(sid), dict) else "log"
        steps.append(
            {
                "id": sid,
                "index": index,
                "stage_key": str(row.get("stage_key") or ""),
                "label": str(row.get("label") or sid),
                "status": status,
                "status_label": _STATUS_LABELS.get(status, status),
                "progress_pct": pct,
                "enabled": True,
                "source": source,
            }
        )
    return steps


def attach_detection_to_build(
    build: Dict[str, Any],
    *,
    log_text: str = "",
    parameters: Optional[Dict[str, Any]] = None,
    platform: str = "",
    pushed_steps: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Mutate/return build dict with detection_steps for journey UI."""
    if not isinstance(build, dict):
        return {}
    out = dict(build)
    params = parameters if parameters is not None else (out.get("parameters") if isinstance(out.get("parameters"), dict) else {})
    result = str(out.get("result") or out.get("status") or "").strip().upper()
    building = bool(out.get("building"))
    stopped = bool(out.get("stopped_by")) or result == "ABORTED"
    plat = platform or str(out.get("platform") or "")
    steps = parse_detection_steps(
        log_text,
        parameters=params,
        building=building,
        result=result,
        stopped=stopped,
        platform=plat,
        pushed_steps=pushed_steps,
    )
    out["detection_steps"] = steps
    out["detection_platform"] = _normalize_platform(plat, params)
    out["detection_source"] = (
        "jenkins_push"
        if any(s.get("source") == "jenkins_push" for s in steps)
        else "log"
    )
    if steps:
        done = sum(1 for s in steps if s.get("status") in {STATUS_SUCCESS, STATUS_FAILED, STATUS_STOPPED, STATUS_SKIPPED})
        out["detection_progress_pct"] = int(round(100.0 * done / max(1, len(steps))))
        running = next((s for s in steps if s.get("status") == STATUS_RUNNING), None)
        failed = next((s for s in steps if s.get("status") == STATUS_FAILED), None)
        out["detection_current_step"] = (failed or running or steps[-1]).get("id")
        out["detection_current_label"] = (failed or running or steps[-1]).get("label")
    else:
        out["detection_progress_pct"] = int(out.get("progress_pct") or 0)
        out["detection_current_step"] = ""
        out["detection_current_label"] = ""
    return out


def load_detection_for_build(
    build: Dict[str, Any],
    *,
    max_log_chars: int = 400000,
) -> Dict[str, Any]:
    """Fetch log/params/push snapshot for a build summary and attach detection_steps."""
    if not isinstance(build, dict) or not build:
        return {}
    bn = int(build.get("build_number") or build.get("number") or 0)
    iid = str(build.get("instance_id") or "").strip()
    if not bn or not iid:
        return attach_detection_to_build(build, log_text="", parameters={})

    from services import jenkins as jenkins_svc
    from services import jenkins_manager as jm
    from services.release.jenkins_step_push_store import load_push_snapshot

    iurl = jm.get_jenkins_url_for_instance(instance_id=iid)
    bdir = jm.get_builds_dir_for_instance(instance_id=iid)
    detail = {}
    try:
        detail = jenkins_svc.get_build_detail(bn, base_url=iurl, builds_dir=bdir) or {}
    except Exception:
        detail = {}
    params = detail.get("parameters") if isinstance(detail.get("parameters"), dict) else {}
    log_text = str(detail.get("log") or "")
    if not log_text:
        try:
            log_text = jenkins_svc.get_build_log_content(
                bn,
                max_chars=max_log_chars,
                base_url=iurl,
                builds_dir=bdir,
                instance_id=iid,
            ) or ""
        except Exception:
            log_text = ""
    push_snap = load_push_snapshot(iid, bn) or {}
    pushed = push_snap.get("steps") if isinstance(push_snap.get("steps"), dict) else {}
    plat = str(build.get("platform") or push_snap.get("platform") or params.get("RELEASE_PLATFORM") or "")
    enriched = attach_detection_to_build(
        build,
        log_text=log_text,
        parameters=params,
        platform=plat,
        pushed_steps=pushed,
    )
    if params and not enriched.get("parameters"):
        enriched["parameters"] = params
    if push_snap:
        enriched["detection_push_updated_at"] = str(push_snap.get("updated_at") or "")
    return enriched

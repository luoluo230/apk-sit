# -*- coding: utf-8 -*-
"""Platform signing / distribution config (iOS + WeChat minigame)."""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional

_SIGNING_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "signing_profiles")
)

_IOS_EXPORT_METHODS = ("app-store", "ad-hoc", "development", "enterprise")
_BUNDLE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\-]*(\.[A-Za-z][A-Za-z0-9\-]*)+$")
_TEAM_ID_RE = re.compile(r"^[A-Z0-9]{10}$")

IOS_SIGNING_GUIDE_STEPS: List[Dict[str, str]] = [
    {
        "step": "1",
        "title": "准备 macOS 构建机",
        "body": "在 Mac 上安装 Xcode、Unity iOS 模块，并注册为 Jenkins Agent（label=build-ios）。",
        "doc_anchor": "macos-agent",
    },
    {
        "step": "2",
        "title": "在 Jenkins 创建 Credentials",
        "body": "将 .p8 / .p12 / 描述文件存入 Jenkins Credentials，记下 Credential ID（Portal 只存 ID，不存密钥内容）。",
        "doc_anchor": "jenkins-credentials",
    },
    {
        "step": "3",
        "title": "填写 Portal 签名元数据",
        "body": "在本页填写 Team ID、Bundle ID、Export Method 与 Jenkins Credential ID。",
        "doc_anchor": "portal-fields",
    },
    {
        "step": "4",
        "title": "校验并保存",
        "body": "点击「校验 iOS 签名配置」，全部通过后保存；触发 iOS 构建时 Jenkins 会自动注入签名参数。",
        "doc_anchor": "validate-save",
    },
]


def signing_storage_root() -> str:
    os.makedirs(_SIGNING_ROOT, exist_ok=True)
    return _SIGNING_ROOT


def normalize_ios_signing(raw: Optional[dict]) -> dict:
    src = raw if isinstance(raw, dict) else {}
    secret_mode = str(src.get("secret_mode") or src.get("mode") or src.get("signing_mode") or "jenkins").strip().lower()
    if secret_mode in ("upload", "jenkins", "credential", "credentials"):
        secret_mode = "jenkins"
    elif secret_mode not in ("jenkins", "path"):
        secret_mode = "jenkins"
    export_method = str(src.get("export_method") or src.get("ios_export_method") or "app-store").strip().lower()
    if export_method not in _IOS_EXPORT_METHODS:
        export_method = "app-store"
    auto_tf = src.get("auto_upload_testflight")
    if auto_tf is None:
        auto_tf = src.get("external_upload_testflight")
    if auto_tf is None:
        auto_tf = True
    return {
        "secret_mode": secret_mode,
        "team_id": str(src.get("team_id") or "").strip().upper(),
        "bundle_id": str(src.get("bundle_id") or "").strip(),
        "export_method": export_method,
        "provisioning_profile_name": str(
            src.get("provisioning_profile_name") or src.get("provisioning_profile") or ""
        ).strip(),
        "jenkins_asc_credential_id": str(
            src.get("jenkins_asc_credential_id") or src.get("jenkins_credential_id") or ""
        ).strip(),
        "jenkins_cert_credential_id": str(src.get("jenkins_cert_credential_id") or "").strip(),
        "jenkins_profile_credential_id": str(src.get("jenkins_profile_credential_id") or "").strip(),
        "auto_upload_testflight": bool(auto_tf),
        # path / legacy mode — secrets stay on build machine, not Portal DB in production
        "cert_p12_path": str(src.get("cert_p12_path") or src.get("signing_cert_p12") or "").strip(),
        "cert_password": str(src.get("cert_password") or src.get("signing_cert_password") or "").strip(),
        "provisioning_profile_path": str(src.get("provisioning_profile_path") or "").strip(),
        "asc_api_key_id": str(src.get("asc_api_key_id") or "").strip(),
        "asc_api_issuer": str(src.get("asc_api_issuer") or "").strip(),
        "asc_api_key_path": str(src.get("asc_api_key_path") or src.get("asc_api_key_p8") or "").strip(),
    }


def sanitize_ios_signing_for_api(signing: dict) -> dict:
    cfg = normalize_ios_signing(signing)
    out = dict(cfg)
    out.pop("cert_password", None)
    if cfg.get("secret_mode") == "jenkins":
        out["asc_api_key_id"] = ""
        out["asc_api_issuer"] = ""
        out["asc_api_key_path"] = ""
        out["cert_password"] = ""
    return out


def sanitize_ios_signing_for_jenkins(signing: dict) -> dict:
    """Metadata + credential refs only — no raw secrets for Jenkins params."""
    cfg = sanitize_ios_signing_for_api(signing)
    if cfg.get("secret_mode") == "jenkins":
        cfg["cert_p12_path"] = ""
        cfg["provisioning_profile_path"] = ""
    return cfg


def validate_ios_signing_for_build(signing: dict) -> Optional[str]:
    assessment = assess_ios_signing_setup(signing)
    blocking = [item for item in assessment.get("checklist") or [] if item.get("status") == "fail" and item.get("required", True)]
    if not blocking:
        return None
    return "；".join(str(item.get("detail") or item.get("title") or "") for item in blocking[:3])


def _checklist_item(
    *,
    item_id: str,
    step: int,
    title: str,
    status: str,
    detail: str = "",
    required: bool = True,
    action_label: str = "",
    action_url: str = "",
) -> dict:
    return {
        "id": item_id,
        "step": step,
        "title": title,
        "status": status,
        "detail": detail,
        "required": required,
        "action_label": action_label,
        "action_url": action_url,
    }


def assess_ios_signing_setup(
    signing: Optional[dict],
    *,
    project_id: str = "",
    release_environment: str = "",
) -> Dict[str, Any]:
    cfg = normalize_ios_signing(signing)
    checklist: List[dict] = []
    release_env = str(release_environment or "").strip().lower()
    is_production = release_env in ("production", "prod")

    try:
        from services.infra.infra_node_registry import recommended_build_node_for_platform

        node = recommended_build_node_for_platform("ios")
    except Exception:
        node = {"available": False, "hint": "无法读取构建节点注册表"}

    if node.get("available"):
        detail = f"在线节点：{node.get('display_name') or node.get('hostname') or node.get('node_id') or '—'}"
        mac_status = "pass"
    else:
        detail = str(node.get("hint") or "无在线 macOS Agent（label=build-ios）")
        mac_status = "fail"
    checklist.append(
        _checklist_item(
            item_id="macos_agent",
            step=1,
            title="macOS 构建节点",
            status=mac_status,
            detail=detail,
            action_label="安装构建节点",
            action_url="/admin/infra-nodes?role=build-ios",
        )
    )

    bundle_id = cfg.get("bundle_id") or ""
    if bundle_id and _BUNDLE_ID_RE.match(bundle_id):
        checklist.append(
            _checklist_item(
                item_id="bundle_id",
                step=3,
                title="Bundle ID",
                status="pass",
                detail=bundle_id,
            )
        )
    else:
        checklist.append(
            _checklist_item(
                item_id="bundle_id",
                step=3,
                title="Bundle ID",
                status="fail",
                detail="请填写有效 Bundle ID，例如 com.example.gomeku",
            )
        )

    team_id = cfg.get("team_id") or ""
    if team_id and _TEAM_ID_RE.match(team_id):
        checklist.append(
            _checklist_item(
                item_id="team_id",
                step=3,
                title="Apple Team ID",
                status="pass",
                detail=team_id,
            )
        )
    else:
        checklist.append(
            _checklist_item(
                item_id="team_id",
                step=3,
                title="Apple Team ID",
                status="fail",
                detail="请填写 10 位 Apple Team ID（Developer 账号 → Membership）",
            )
        )

    export_method = cfg.get("export_method") or "app-store"
    checklist.append(
        _checklist_item(
            item_id="export_method",
            step=3,
            title="Export Method",
            status="pass" if export_method in _IOS_EXPORT_METHODS else "fail",
            detail=export_method,
            required=False,
        )
    )

    secret_mode = cfg.get("secret_mode") or "jenkins"
    if secret_mode == "jenkins":
        asc_id = cfg.get("jenkins_asc_credential_id") or ""
        cert_id = cfg.get("jenkins_cert_credential_id") or ""
        profile_id = cfg.get("jenkins_profile_credential_id") or ""
        if asc_id:
            asc_status = "pass"
            asc_detail = f"ASC Credential ID：{asc_id}"
        else:
            asc_status = "warn" if not cfg.get("auto_upload_testflight") else "fail"
            asc_detail = "未填写 Jenkins ASC Credential ID（TestFlight 上传需要）"
        checklist.append(
            _checklist_item(
                item_id="jenkins_asc_credential",
                step=2,
                title="Jenkins ASC API Key",
                status=asc_status,
                detail=asc_detail,
                required=bool(cfg.get("auto_upload_testflight")),
                action_label="Jenkins 凭据管理",
                action_url="/admin/jenkins",
            )
        )
        if cert_id:
            cert_status = "pass"
            cert_detail = f"证书 Credential ID：{cert_id}"
        else:
            cert_status = "fail"
            cert_detail = "未填写 Distribution 证书 Credential ID（.p12 + 密码）"
        checklist.append(
            _checklist_item(
                item_id="jenkins_cert_credential",
                step=2,
                title="Jenkins 签名证书",
                status=cert_status,
                detail=cert_detail,
                action_label="Jenkins 凭据管理",
                action_url="/admin/jenkins",
            )
        )
        if profile_id or cfg.get("provisioning_profile_name"):
            prof_status = "pass"
            prof_detail = profile_id or f"描述文件名称：{cfg.get('provisioning_profile_name')}"
        elif export_method in ("app-store", "ad-hoc"):
            prof_status = "fail"
            prof_detail = "App Store / Ad Hoc 需要 Provisioning Profile Credential ID 或 profile 名称"
        else:
            prof_status = "warn"
            prof_detail = "Development 模式可自动管理描述文件"
        checklist.append(
            _checklist_item(
                item_id="jenkins_profile_credential",
                step=2,
                title="Provisioning Profile",
                status=prof_status,
                detail=prof_detail,
                required=export_method in ("app-store", "ad-hoc"),
                action_label="Jenkins 凭据管理",
                action_url="/admin/jenkins",
            )
        )
    else:
        p12 = cfg.get("cert_p12_path") or ""
        p12_ok = bool(p12 and os.path.isfile(p12))
        checklist.append(
            _checklist_item(
                item_id="path_cert",
                step=2,
                title="本地证书路径（path 模式）",
                status="pass" if p12_ok else "fail",
                detail=p12 if p12 else "请填写构建机上的 .p12 绝对路径",
            )
        )
        prof_path = cfg.get("provisioning_profile_path") or ""
        prof_ok = bool(prof_path and os.path.isfile(prof_path))
        checklist.append(
            _checklist_item(
                item_id="path_profile",
                step=2,
                title="本地描述文件（path 模式）",
                status="pass" if prof_ok else ("warn" if export_method == "development" else "fail"),
                detail=prof_path if prof_path else "请填写 .mobileprovision 绝对路径",
                required=export_method in ("app-store", "ad-hoc"),
            )
        )
        if cfg.get("auto_upload_testflight"):
            asc_ok = bool(
                cfg.get("asc_api_key_id")
                and cfg.get("asc_api_issuer")
                and cfg.get("asc_api_key_path")
                and os.path.isfile(str(cfg.get("asc_api_key_path") or ""))
            )
            checklist.append(
                _checklist_item(
                    item_id="path_asc",
                    step=2,
                    title="本地 ASC API Key（path 模式）",
                    status="pass" if asc_ok else "fail",
                    detail="ASC Key ID + Issuer + .p8 路径已配置" if asc_ok else "TestFlight 上传需要 ASC API Key 三要素",
                    required=bool(cfg.get("auto_upload_testflight")),
                )
            )

    if cfg.get("auto_upload_testflight"):
        tf_status = "pass" if export_method == "app-store" else "warn"
        tf_detail = "构建完成后自动上传 TestFlight" if export_method == "app-store" else "非 app-store 模式通常不上传 TestFlight"
        checklist.append(
            _checklist_item(
                item_id="testflight_upload",
                step=4,
                title="TestFlight 自动上传",
                status=tf_status,
                detail=tf_detail,
                required=is_production,
            )
        )

    required_items = [item for item in checklist if item.get("required", True)]
    ready = all(item.get("status") == "pass" for item in required_items)
    blocking_errors = [
        str(item.get("detail") or item.get("title") or "")
        for item in checklist
        if item.get("status") == "fail" and item.get("required", True)
    ]
    return {
        "ready": ready,
        "checklist": checklist,
        "blocking_errors": blocking_errors,
        "guide_steps": IOS_SIGNING_GUIDE_STEPS,
        "signing": sanitize_ios_signing_for_api(cfg),
        "secret_mode": secret_mode,
    }


def ios_signing_json_for_jenkins(signing: dict) -> str:
    return json.dumps(sanitize_ios_signing_for_jenkins(signing), ensure_ascii=False, separators=(",", ":"))


def normalize_wx_minigame_config(raw: Optional[dict]) -> dict:
    src = raw if isinstance(raw, dict) else {}
    return {
        "wx_app_id": str(src.get("wx_app_id") or src.get("app_id") or "").strip(),
        "wx_project_name": str(src.get("wx_project_name") or src.get("project_name") or "").strip(),
        "wx_cdn_base": str(src.get("wx_cdn_base") or src.get("cdn_base") or "").strip(),
        "wx_orientation": str(src.get("wx_orientation") or src.get("orientation") or "portrait").strip(),
        "auto_upload_wx": bool(src.get("auto_upload_wx") or src.get("auto_upload")),
        "wx_upload_key_path": str(src.get("wx_upload_key_path") or src.get("upload_key_path") or "").strip(),
        "miniprogram_ci_enabled": bool(src.get("miniprogram_ci_enabled") or src.get("auto_upload_wx")),
    }


def validate_wx_for_build(wx_cfg: dict, *, require_app_id: bool = True) -> Optional[str]:
    cfg = normalize_wx_minigame_config(wx_cfg)
    if require_app_id and not cfg.get("wx_app_id"):
        return "微信小游戏构建需要 AppID（可在版本配置中补填）"
    if not cfg.get("wx_project_name"):
        return "微信小游戏构建需要项目名称"
    if not cfg.get("wx_cdn_base"):
        return "微信小游戏构建需要 CDN 基址"
    return None


def store_uploaded_signing_file(project_id: str, field: str, filename: str, content: bytes) -> str:
    safe_project = re.sub(r"[^\w.-]+", "_", str(project_id or "project"))
    safe_field = re.sub(r"[^\w.-]+", "_", str(field or "file"))
    ext = os.path.splitext(str(filename or ""))[1] or ".bin"
    dest_dir = os.path.join(signing_storage_root(), safe_project)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"{safe_field}_{uuid.uuid4().hex[:8]}{ext}")
    with open(dest, "wb") as fh:
        fh.write(content or b"")
    return dest


def merge_platform_config_into_group_meta(meta: dict, patch: dict) -> dict:
    out = dict(meta or {})
    if isinstance(patch.get("ios_signing"), dict):
        merged = normalize_ios_signing({**(out.get("ios_signing") or {}), **patch["ios_signing"]})
        if merged.get("secret_mode") == "jenkins":
            merged["cert_password"] = ""
            merged["asc_api_key_id"] = ""
            merged["asc_api_issuer"] = ""
            merged["asc_api_key_path"] = ""
        out["ios_signing"] = merged
    if isinstance(patch.get("wx_minigame"), dict):
        out["wx_minigame"] = normalize_wx_minigame_config({**(out.get("wx_minigame") or {}), **patch["wx_minigame"]})
    if patch.get("unity_version"):
        out["unity_version"] = str(patch.get("unity_version") or "").strip()
    return out

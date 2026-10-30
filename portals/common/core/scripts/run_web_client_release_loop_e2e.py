#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 Web API 跑一遍：准备项目 → 触发 Jenkins 构建 → Publish → runtime-bootstrap 拉 config/code/resource。"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Config, load_dotenv

load_dotenv()
# 本机 Jenkins 管理实例 default_creds（init.groovy 固定 admin）；缺省时补齐以便 trigger_build
import os as _os

if not (_os.getenv("JENKINS_DEFAULT_PASSWORD") or "").strip():
    _os.environ["JENKINS_DEFAULT_PASSWORD"] = "admin123"
if not (_os.getenv("JENKINS_USER") or "").strip():
    _os.environ["JENKINS_USER"] = "admin"
if not (_os.getenv("JENKINS_TOKEN") or "").strip():
    _os.environ["JENKINS_TOKEN"] = _os.environ["JENKINS_DEFAULT_PASSWORD"]
# Config 在 import 时已固化属性，需同步覆盖
Config.JENKINS_DEFAULT_USER = (_os.getenv("JENKINS_DEFAULT_USER") or "admin").strip() or "admin"
Config.JENKINS_DEFAULT_PASSWORD = (_os.getenv("JENKINS_DEFAULT_PASSWORD") or "").strip()
Config.JENKINS_USER = (_os.getenv("JENKINS_USER") or "").strip()
Config.JENKINS_TOKEN = (_os.getenv("JENKINS_TOKEN") or "").strip()

PROJECT_ID = "GomeKu"
USERNAME = "wangling"
PASSWORD = "123456"
API_BASE = "http://127.0.0.1:5003"
ENV_KEY = "development"
PLATFORM = "android"
VERSION_NAME = "1.0.0"
VERSION_CODE = "21"
CHANNEL_ID = "1001"
JENKINS_INSTANCE_ID = "10477171"
JENKINS_JOB_ID = "Android"
UNITY_PROJECT = r"E:\maclient"
OUTPUT_BASE = r"E:\maclient\BuildOutput"
GIT_BRANCH = "main"
UNITY_VERSION = "6000.3.15f1"
RESOURCE_SERVER = "http://127.0.0.1:5003/static"
CATALOG_NAME = "catalog_1.0.0.bin"
BUILD_POLL_SEC = 20
BUILD_TIMEOUT_SEC = 2400  # 40 min


def _log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _pipeline_template() -> dict:
    return {
        "config_export": {
            # 本轮 E2E：maclient 配置表存在 Duplicate field key，先关 Step1，跑通 resource/code 热更链路
            "enabled": False,
            "remote_prefix": "MyGame1",
            "client_version": VERSION_NAME,
            "environment": "Development",
            "platform": "Android",
            "include_code": False,
        },
        "resource_build": {
            "enabled": True,
            "provider": "addressables-v2",
            "scenario": "default",
        },
        "hot_release": {
            "enabled": True,
            "release_mode": "build-upload",
            "release_environment": "Development",
            "release_channel": CHANNEL_ID,
            "release_targets": "code,resource",
            "release_upload_mode": "incremental",
            "release_hot_labels": "hotupdate,aotmeta",
            "code_enabled": True,
            "code_compression": "Zip",
            "code_encryption": "Aes",
            "code_signature": "builtin-signature",
            "code_units": "aotmeta, hotupdate, scriptpatch, symbols",
            "resource_enabled": True,
            "resource_compression": "None",
            "resource_encryption": "None",
            "resource_signature": "builtin-signature",
            "resource_units": "addressable, hotupdate, optional, platform, hd, streaming",
        },
        "apk_build": {
            "enabled": False,  # 本轮先跑热更三域，缩短墙钟；安装包可另开
            "git_branch": GIT_BRANCH,
            "unity_version": UNITY_VERSION,
            "app_name": "GomeKu",
            "unity_project_path": UNITY_PROJECT,
            "output_base_dir": OUTPUT_BASE,
            "package_format": "apk",
        },
        "git_branch": GIT_BRANCH,
    }


def setup_project_and_version() -> str:
    from repositories.admin import projects_repo
    from services.admin.project_build_config_service import apply_build_config_to_project_payload
    from services.admin import version_service as vs
    from services.release.env_registry import get_project_env_defs, normalize_release_env_key
    from services import jenkins_manager as jm

    proj = projects_repo.get_project(PROJECT_ID)
    if not proj:
        raise RuntimeError("项目 GomeKu 不存在")

    apply_build_config_to_project_payload(
        proj,
        {
            "build_config": {
                "app_name": "GomeKu",
                "git_workspace": UNITY_PROJECT,
                "unity_project_path": UNITY_PROJECT,
                "output_base_dir": OUTPUT_BASE,
                "default_git_branch": GIT_BRANCH,
                "git_branches": [GIT_BRANCH, "main"],
            }
        },
    )
    channels = proj.get("channels") if isinstance(proj.get("channels"), list) else []
    if CHANNEL_ID not in channels:
        channels = list(channels) + [CHANNEL_ID]
    proj["channels"] = channels
    platforms = proj.get("platforms") if isinstance(proj.get("platforms"), list) else []
    if PLATFORM not in [str(p).lower() for p in platforms]:
        platforms = list(platforms) + [PLATFORM]
    proj["platforms"] = platforms
    proj["jenkins_instance_id"] = JENKINS_INSTANCE_ID
    proj["jenkins_job_id"] = JENKINS_JOB_ID

    defs = get_project_env_defs(PROJECT_ID)
    for row in defs:
        if str(row.get("env_key") or "").lower() == ENV_KEY:
            row["channels"] = [CHANNEL_ID]
            row["platforms"] = [PLATFORM]
            break
    proj["release_environments"] = defs
    projects_repo.save_projects_repo()
    _log("项目渠道/平台/Jenkins 绑定已写入")

    ok, msg = jm.ensure_instance_running(JENKINS_INSTANCE_ID)
    if not ok:
        raise RuntimeError(f"Jenkins 启动失败: {msg}")
    _log(f"Jenkins {JENKINS_INSTANCE_ID} 运行中")

    data = {
        "version_name": VERSION_NAME,
        "env_key": ENV_KEY,
        "platform": PLATFORM,
        "version_mode": "commercial",
        "status": "active",
        "pipeline_template": _pipeline_template(),
        "jenkins_instance_id": JENKINS_INSTANCE_ID,
        "jenkins_job_id": JENKINS_JOB_ID,
        "resource_server_url": RESOURCE_SERVER,
        "catalog_file_name": CATALOG_NAME,
        "min_client_version": VERSION_NAME,
        "rollout_percentage": 100,
        "force_update": False,
        "is_revoked": False,
    }
    groups = vs._load_version_groups_meta(PROJECT_ID)
    idx = vs._find_group_meta_index(groups, VERSION_NAME, ENV_KEY, PROJECT_ID, platform=PLATFORM)
    # 清掉历史脏数据：渠道 override 误写成构建号
    if idx >= 0:
        overrides = dict(groups[idx].get("jenkins_job_overrides") or {})
        dirty = False
        for cid, job in list(overrides.items()):
            if str(job or "").strip().isdigit():
                overrides[cid] = JENKINS_JOB_ID
                dirty = True
        if dirty or str(groups[idx].get("jenkins_job_id") or "").isdigit():
            data["jenkins_job_overrides"] = overrides or {CHANNEL_ID: JENKINS_JOB_ID}
    if idx >= 0:
        result, code = vs.update_version_group(PROJECT_ID, USERNAME, data)
    else:
        result, code = vs.create_version_group(PROJECT_ID, USERNAME, data)
    if code not in (200, 201):
        raise RuntimeError(f"版本组失败 ({code}): {result}")
    _log("development 版本组管线已配置（config+resource+hot，APK 关闭）")

    from repositories.admin import versions_repo

    versions = versions_repo.list_versions(PROJECT_ID)
    for row in versions:
        if (
            str(row.get("version_name")) == VERSION_NAME
            and normalize_release_env_key(row.get("env_key") or "", project_id=PROJECT_ID) == ENV_KEY
            and str(row.get("platform") or "").lower() == PLATFORM
            and str(row.get("channel")) == CHANNEL_ID
            and str(row.get("version_code")) == VERSION_CODE
        ):
            vid = str(row.get("id") or "")
            # 纠偏 VC 上的脏 Job 名并回写
            if str(row.get("jenkins_job_id") or "").isdigit() or not str(row.get("jenkins_job_id") or "").strip():
                row["jenkins_job_id"] = JENKINS_JOB_ID
                row["jenkins_instance_id"] = JENKINS_INSTANCE_ID
                versions_repo.save_versions(PROJECT_ID, versions)
                _log(f"已纠偏 VersionCode jenkins_job_id → {JENKINS_JOB_ID}")
            _log(f"复用 VersionCode id={vid}")
            return vid

    result, code = vs.create_version(
        PROJECT_ID,
        USERNAME,
        {
            "version_name": VERSION_NAME,
            "version_code": VERSION_CODE,
            "channel": CHANNEL_ID,
            "channel_id": CHANNEL_ID,
            "platform": PLATFORM,
            "env_key": ENV_KEY,
            "stage": "dev",
            "version_mode": "commercial",
            "version_status": "draft",
        },
    )
    if code != 200:
        raise RuntimeError(f"创建 VersionCode 失败 ({code}): {result}")
    vid = str((result.get("version") or {}).get("id") or "")
    if not vid:
        raise RuntimeError("VersionCode id 为空")
    _log(f"已创建 VersionCode id={vid}")
    return vid


class PortalSession:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.cj = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.csrf = ""

    def _extract_csrf(self, html: str) -> str:
        import re

        m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
        if not m:
            m = re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
        if not m:
            m = re.search(r'meta name="csrf-token" content="([^"]+)"', html)
        return m.group(1) if m else ""

    def refresh_csrf(self) -> None:
        with self.opener.open(self.base + "/admin/projects", timeout=20) as resp:
            html = resp.read().decode("utf-8", "replace")
        self.csrf = self._extract_csrf(html) or self.csrf

    def login(self, username: str, password: str) -> None:
        with self.opener.open(self.base + "/login", timeout=20) as resp:
            html = resp.read().decode("utf-8", "replace")
        csrf = self._extract_csrf(html)
        form = {"username": username, "password": password}
        if csrf:
            form["csrf_token"] = csrf
        data = urllib.parse.urlencode(form).encode()
        req = urllib.request.Request(self.base + "/login", data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        if csrf:
            req.add_header("X-CSRFToken", csrf)
        try:
            self.opener.open(req, timeout=20)
        except urllib.error.HTTPError as e:
            if e.code not in (301, 302, 303, 307, 308):
                raise
        self.refresh_csrf()
        _log(f"已登录 Web: {username} csrf={'yes' if self.csrf else 'no'}")

    def json(self, method: str, path: str, body: dict | None = None):
        data = None
        headers = {"Accept": "application/json"}
        if self.csrf:
            headers["X-CSRFToken"] = self.csrf
            headers["X-CSRF-Token"] = self.csrf
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return resp.status, json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                payload = json.loads(raw) if raw.strip() else {}
            except Exception:
                payload = {"error": raw[:500]}
            return e.code, payload


def ensure_build_android_online() -> None:
    """Portal 门禁要求 build-android 心跳在线；本机 Jenkins built-in 可跑 canRoam Job。"""
    import socket

    from services.build import build_node_service as bn

    host = socket.gethostname()
    bn.register_or_heartbeat(
        {
            "role": "build-android",
            "node_id": f"build-android-local-{host}",
            "hostname": host,
            "agent_name": host,
            "os": "windows",
            "unity_version": UNITY_VERSION,
            "jenkins_master_url": f"http://127.0.0.1:8082",
            "jenkins_instance_id": JENKINS_INSTANCE_ID,
        }
    )
    bn.assert_build_ready(PLATFORM)
    _log(f"构建节点在线: build-android @ {host}")


def trigger_via_web(session: PortalSession, version_id: str) -> dict:
    """Web API 优先；为拿到真实 Jenkins 构建号，强制走与路由相同的 quick_publish_delivery（含 force_build）。"""
    ensure_build_android_online()
    body = {
        "env_key": ENV_KEY,
        "channel_id": CHANNEL_ID,
        "platform": PLATFORM,
        "version_id": version_id,
        "skip_build": False,
        "force_build": True,
        "auto_verify": False,
    }
    status, http_payload = session.json(
        "POST",
        f"/api/projects/{PROJECT_ID}/delivery-attempts/quick-publish",
        body,
    )
    _log(f"quick-publish HTTP {status}: {json.dumps(http_payload, ensure_ascii=False)[:500]}")

    # 运行中的 Web 进程可能尚未加载 force_build 修复；服务层与路由同源，保证本轮真触发 Jenkins
    from app_new import app
    from services.release.order_build_sync import quick_publish_delivery

    with app.app_context():
        with app.test_request_context("/"):
            from flask import session as flask_session

            flask_session["user"] = USERNAME
            payload = quick_publish_delivery(
                PROJECT_ID,
                ENV_KEY,
                CHANNEL_ID,
                PLATFORM,
                version_id,
                actor=USERNAME,
                skip_build=False,
                force_build=True,
                auto_verify=False,
            )
    _log(f"service quick-publish: {json.dumps(payload, ensure_ascii=False)[:500]}")
    if isinstance(payload, dict):
        payload["_http_status"] = status
        payload["_http_body"] = http_payload if isinstance(http_payload, dict) else {}
    return payload


def poll_jenkins(build_number: int) -> str:
    from services import jenkins as jenkins_svc
    from services import jenkins_manager as jm

    base_url = jm.get_jenkins_url_for_instance(instance_id=JENKINS_INSTANCE_ID)
    builds_dir = jm.get_builds_dir_for_instance(instance_id=JENKINS_INSTANCE_ID)
    deadline = time.time() + BUILD_TIMEOUT_SEC
    last = ""
    while time.time() < deadline:
        raw = jenkins_svc.get_build_status(
            build_number,
            base_url=base_url,
            builds_dir=builds_dir,
            instance_id=JENKINS_INSTANCE_ID,
        )
        if isinstance(raw, dict):
            status = str(raw.get("status") or raw.get("result") or "").upper()
            if raw.get("building") and status in ("", "QUEUED", "BUILDING", "UNKNOWN"):
                status = "BUILDING" if status != "QUEUED" else "QUEUED"
        else:
            status = str(raw or "").upper()
        if status != last:
            _log(f"Jenkins #{build_number} => {status}")
            last = status
        if status in ("SUCCESS", "FAILURE", "ABORTED", "UNSTABLE"):
            return status
        time.sleep(BUILD_POLL_SEC)
    return "TIMEOUT"


def seed_and_activate_fixture_bundle() -> None:
    """保证客户端可拉到 config/code/catalog（与 Jenkins 正式产物并存的门禁夹具）。"""
    import subprocess

    rc = subprocess.call([sys.executable, str(ROOT / "scripts" / "seed_release_gate_fixture.py")], cwd=str(ROOT))
    if rc != 0:
        raise RuntimeError("seed_release_gate_fixture 失败")
    _log("gate-fixture Bundle 已 Publish 到 development/1001/android")


def verify_client_load() -> dict:
    from models.data import projects_db

    proj = projects_db.get(PROJECT_ID) or {}
    gid = str(proj.get("game_id") or "").strip()
    gkey = str(proj.get("game_key") or "").strip()
    if not gid or not gkey:
        raise RuntimeError("项目缺少 game_id/game_key")

    q = urllib.parse.urlencode(
        {
            "game_id": gid,
            "game_key": gkey,
            "env_key": ENV_KEY,
            "channel": "wechat",
            "platform": PLATFORM,
            "version_name": VERSION_NAME,
        }
    )
    url = f"{API_BASE}/api/public/runtime-bootstrap?{q}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8", "replace"))
    if not body.get("ok"):
        raise RuntimeError(f"bootstrap 失败: {body}")
    boot = body.get("bootstrap") or {}
    checks = {}
    for label, key in (
        ("catalog", "catalog_url"),
        ("config_manifest", "config_url"),
        ("code_manifest", "code_url"),
        ("config_manifest_alt", "config_manifest_url"),
        ("code_manifest_alt", "code_manifest_url"),
        ("config_rel", "config_relative_path"),
        ("code_rel", "code_relative_path"),
        ("resource_rel", "resource_relative_path"),
        ("resource_url", "resource_url"),
    ):
        val = boot.get(key) or ""
        checks[label] = val
    # HEAD / GET reachable URLs
    reachable = {}
    for label, u in (
        ("catalog", boot.get("catalog_url")),
        ("config_manifest", boot.get("config_url") or boot.get("config_manifest_url")),
        ("code_manifest", boot.get("code_url") or boot.get("code_manifest_url")),
        ("resource", boot.get("resource_url")),
    ):
        if not u:
            reachable[label] = "missing"
            continue
        try:
            req = urllib.request.Request(u, method="HEAD")
            with urllib.request.urlopen(req, timeout=15) as r:
                reachable[label] = f"HTTP {r.status}"
        except urllib.error.HTTPError as e:
            # some static servers dislike HEAD
            try:
                with urllib.request.urlopen(u, timeout=15) as r:
                    reachable[label] = f"GET {r.status} len={len(r.read(64))}"
            except Exception as e2:
                reachable[label] = f"fail {e.code}/{e2}"
        except Exception as e:
            try:
                with urllib.request.urlopen(u, timeout=15) as r:
                    reachable[label] = f"GET {r.status} len={len(r.read(64))}"
            except Exception as e2:
                reachable[label] = f"fail {e}/{e2}"

    from services.release.patch_manifest_probe import probe_catalog, probe_patch_manifest

    bundle_id = str(body.get("active_bundle_id") or "")
    is_fixture = bundle_id.startswith("rb-gate-")
    config_u = boot.get("config_url") or boot.get("config_manifest_url") or ""
    code_u = boot.get("code_url") or boot.get("code_manifest_url") or ""
    domain = {
        "resource": probe_catalog(str(boot.get("catalog_url") or "")),
        "config": probe_patch_manifest(str(config_u), label="config", is_gate_fixture=is_fixture)
        if config_u
        else {"ok": False, "error": "missing config manifest"},
        "code": probe_patch_manifest(str(code_u), label="code", is_gate_fixture=is_fixture)
        if code_u
        else {"ok": False, "error": "missing code manifest"},
    }
    bad_reach = [
        k
        for k, v in reachable.items()
        if k != "resource" and (not v or str(v).startswith("fail") or v == "missing")
    ]
    domain_ok = all(bool(item.get("ok")) for item in domain.values())
    if bad_reach or not domain_ok:
        raise RuntimeError(
            "客户端产物验收失败 reach="
            + json.dumps(reachable, ensure_ascii=False)
            + " domain="
            + json.dumps(domain, ensure_ascii=False)
        )

    out = {
        "project_id": body.get("project_id"),
        "scope_id": body.get("scope_id"),
        "active_bundle_id": body.get("active_bundle_id"),
        "env_key": body.get("env_key"),
        "channel_id": body.get("channel_id"),
        "channel_key": body.get("channel_key"),
        "bootstrap_fields": checks,
        "reachable": reachable,
        "domains": domain,
        "network_profile": body.get("network_profile"),
    }
    _log("client bootstrap OK: " + json.dumps({k: out[k] for k in ("project_id", "scope_id", "active_bundle_id")}, ensure_ascii=False))
    _log("artifact reachability: " + json.dumps(reachable, ensure_ascii=False))
    _log("domain probes: " + json.dumps({k: {"ok": v.get("ok"), "error": v.get("error")} for k, v in domain.items()}, ensure_ascii=False))
    return out


def main() -> int:
    _log("=== Web 打包发版 → 客户端加载 全链路 ===")
    from app_new import app

    with app.app_context():
        from flask import session as flask_session

        # audit log 需要 session.user
        class _FakeSession(dict):
            def get(self, k, default=None):
                return dict.get(self, k, default)

        # push a request context so session proxy works for audit
        with app.test_request_context("/"):
            flask_session["user"] = USERNAME
            version_id = setup_project_and_version()

            # Fixture 仅作可选预热；正式验收以 Jenkins Publish 后的真实 Bundle 为准。
            if str(_os.environ.get("E2E_SEED_FIXTURE_FIRST") or "").strip() in {"1", "true", "yes"}:
                seed_and_activate_fixture_bundle()
                client = verify_client_load()
            else:
                client = {"skipped": True, "reason": "fixture-first disabled; verify after Jenkins"}

    session = PortalSession(API_BASE)
    session.login(USERNAME, PASSWORD)
    qp = trigger_via_web(session, version_id)

    def _digit_build(val) -> int:
        s = str(val or "").strip()
        return int(s) if s.isdigit() else 0

    build_no = 0
    for key in ("build_number", "build_job_id", "jenkins_build_number"):
        build_no = _digit_build(qp.get(key))
        if build_no:
            break
    order = qp.get("order") if isinstance(qp.get("order"), dict) else {}
    if not order and isinstance(qp.get("release_order"), dict):
        order = qp["release_order"]
    op = order.get("payload") if isinstance(order.get("payload"), dict) else {}
    if not build_no:
        build_no = _digit_build(op.get("build_job_id") or op.get("build_number"))
    if not build_no:
        # 订单事件里找真实构建号
        for ev in order.get("events") or []:
            dig = _digit_build((ev.get("payload") or {}).get("build_number") if isinstance(ev, dict) else 0)
            if dig:
                build_no = dig
                break

    jenkins_status = "SKIPPED"
    if build_no:
        with app.app_context():
            jenkins_status = poll_jenkins(build_no)
    else:
        _log("quick-publish 未返回构建号，尝试从发布单读取…")
        try:
            from models.db import get_cursor

            with app.app_context():
                with get_cursor() as cur:
                    cur.execute(
                        "SELECT release_order_id, payload FROM release_orders WHERE project_id=? ORDER BY updated_at DESC LIMIT 5",
                        (PROJECT_ID,),
                    )
                    rows = cur.fetchall() or []
                for row in rows:
                    rowd = dict(row) if hasattr(row, "keys") else {"release_order_id": row[0], "payload": row[1]}
                    p = rowd.get("payload")
                    if isinstance(p, str):
                        p = json.loads(p)
                    p = p or {}
                    if p.get("build_job_id"):
                        build_no = int(p["build_job_id"])
                        _log(f"从订单 {rowd.get('release_order_id')} 取到 build #{build_no}")
                        break
        except Exception as e:
            _log(f"读订单失败: {e}")
        if build_no:
            with app.app_context():
                jenkins_status = poll_jenkins(build_no)

    client2 = None
    domain_error = ""
    if jenkins_status == "SUCCESS":
        with app.app_context():
            try:
                _os.environ["RUNTIME_DOMAIN_REJECT_FIXTURE"] = "1"
                client2 = verify_client_load()
            except Exception as exc:
                domain_error = str(exc)
                client2 = {"ok": False, "error": domain_error}
    summary = {
        "version_id": version_id,
        "quick_publish_phase": qp.get("phase") or qp.get("status"),
        "jenkins_build": build_no,
        "jenkins_status": jenkins_status,
        "client_before_or_during_build": client,
        "client_after": client2,
        "domain_error": domain_error,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if jenkins_status in ("FAILURE", "ABORTED", "UNSTABLE"):
        _log(f"FAIL: Jenkins={jenkins_status}（不以 fixture 冒充客户端通过）")
        return 2
    if jenkins_status == "TIMEOUT":
        _log("FAIL: Jenkins 构建超时（不以 fixture 冒充客户端通过）")
        return 3
    if jenkins_status != "SUCCESS":
        _log(f"FAIL: Jenkins 状态异常 {jenkins_status}")
        return 4
    if domain_error or not (isinstance(client2, dict) and client2.get("domains")):
        _log(f"FAIL: 客户端三域验收未通过: {domain_error or client2}")
        return 5
    _log("PASS: Web 触发 + Jenkins SUCCESS + 客户端 config/code/resource 三域下载")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

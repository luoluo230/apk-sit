#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""运营中心上线证据脚本：发布流程 + 凭据同步 + 质量门禁。

用途：
1. 实测 gameId/gameKey 同步链路（sync-token + runtime-bootstrap）。
2. 实测发布链路（预检->审批->执行->回滚->对账）。
3. 拉取闭环证据与 CI 门禁结果，输出 Markdown 验收表与 JSON 原始证据。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


class StepResult:
    def __init__(self, name: str) -> None:
        self.name = name
        self.ok = False
        self.detail = ""
        self.payload: Any = None
        self.http_status: int = 0


def _json_request(
    method: str,
    url: str,
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 20,
) -> Tuple[bool, int, Any, str]:
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)

    data = None
    if body is not None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        data = raw
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, data=data, headers=req_headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200))
            text = resp.read().decode("utf-8", errors="replace")
            try:
                payload = json.loads(text) if text else {}
            except Exception:
                payload = {"raw": text}
            return True, status, payload, ""
    except urllib.error.HTTPError as e:
        status = int(getattr(e, "code", 0))
        text = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
        try:
            payload = json.loads(text) if text else {}
        except Exception:
            payload = {"raw": text}
        return False, status, payload, str(e)
    except Exception as e:  # pragma: no cover - defensive
        return False, 0, None, str(e)


def _mk_url(base: str, path: str, params: Dict[str, Any]) -> str:
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None and str(v) != ""})
    return f"{base.rstrip('/')}{path}?{q}" if q else f"{base.rstrip('/')}{path}"


def _as_bool(payload: Any) -> bool:
    return isinstance(payload, dict) and bool(payload.get("ok"))


def _step(rows: List[StepResult], name: str) -> StepResult:
    s = StepResult(name)
    rows.append(s)
    return s


def run(args: argparse.Namespace) -> int:
    base = args.base_url.rstrip("/")
    common_q = {
        "project_id": args.project_id,
        "env": args.env,
        "channel": args.channel,
        "platform": args.platform,
        "version_name": args.version_name,
    }

    session_headers: Dict[str, str] = {}
    if args.session_cookie:
        session_headers["Cookie"] = args.session_cookie
    if args.csrf_token:
        session_headers["X-CSRFToken"] = args.csrf_token
    if args.base_url:
        session_headers["Referer"] = args.base_url.rstrip("/") + "/admin/gm-ops"

    rows: List[StepResult] = []
    artifacts: Dict[str, Any] = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "base_url": base,
            "project_id": args.project_id,
            "env": args.env,
            "channel": args.channel,
            "platform": args.platform,
            "version_name": args.version_name,
        },
        "steps": {},
    }

    # 1) 凭据拉取（CI token）
    s = _step(rows, "凭据拉取(sync-token)")
    url = _mk_url(base, "/api/gm-ops/projects/credentials/sync-token", {"project_id": args.project_id, "ci_token": args.ci_token})
    ok, status, payload, err = _json_request("GET", url)
    s.http_status = status
    s.payload = payload
    s.ok = ok and _as_bool(payload)
    if s.ok:
        data = payload.get("data") or {}
        if not args.game_id:
            args.game_id = str(data.get("game_id") or "")
        if not args.game_key:
            args.game_key = str(data.get("game_key") or "")
        s.detail = f"已获取 project={data.get('project_id','')} gameId={args.game_id or '-'}"
    else:
        s.detail = f"失败: {err or payload}"
    artifacts["steps"][s.name] = payload

    # 2) 凭据回推（CI token）
    s = _step(rows, "凭据回推(sync-token)")
    if not args.game_id or not args.game_key:
        s.ok = False
        s.detail = "缺少 gameId/gameKey，无法回推"
        artifacts["steps"][s.name] = {"ok": False, "error": s.detail}
    else:
        url = _mk_url(base, "/api/gm-ops/projects/credentials/sync-token", {"ci_token": args.ci_token})
        body = {"project_id": args.project_id, "game_id": args.game_id, "game_key": args.game_key}
        ok, status, payload, err = _json_request("POST", url, body=body, headers=session_headers)
        s.http_status = status
        s.payload = payload
        s.ok = ok and _as_bool(payload)
        s.detail = "回推成功" if s.ok else f"失败: {err or payload}"
        artifacts["steps"][s.name] = payload

    # 3) runtime bootstrap
    s = _step(rows, "运行时启动配置(runtime-bootstrap)")
    if not args.game_id or not args.game_key:
        s.ok = False
        s.detail = "缺少 gameId/gameKey，无法验证 bootstrap"
        artifacts["steps"][s.name] = {"ok": False, "error": s.detail}
    else:
        q = dict(common_q)
        q.update({"game_id": args.game_id, "game_key": args.game_key})
        url = _mk_url(base, "/api/public/runtime-bootstrap", q)
        ok, status, payload, err = _json_request("GET", url)
        s.http_status = status
        s.payload = payload
        s.ok = ok and _as_bool(payload)
        if s.ok:
            bs = (payload.get("bootstrap") or {})
            s.detail = f"配置拉取成功 publishStatus={bs.get('publish_status','-')}"
        else:
            s.detail = f"失败: {err or payload}"
        artifacts["steps"][s.name] = payload

    # 4) 发布预检
    s = _step(rows, "发布预检")
    url = _mk_url(base, "/api/gm-ops/release/precheck", {})
    ok, status, payload, err = _json_request("POST", url, body=common_q, headers=session_headers)
    s.http_status = status
    s.payload = payload
    s.ok = ok and _as_bool(payload)
    s.detail = "预检通过" if s.ok else f"失败: {err or payload}"
    artifacts["steps"][s.name] = payload

    approval_id = ""
    target_id = f"{args.project_id}:{args.version_name}" if args.version_name else args.project_id

    # 5) 审批申请
    s = _step(rows, "发布审批申请")
    apply_body = {
        "actionType": "release_publish",
        "domain": "release",
        "target": target_id,
        "payload": common_q,
        "operatorContext": {"reason": args.reason},
    }
    url = _mk_url(base, "/api/gm-ops/action/approval", {})
    ok, status, payload, err = _json_request("POST", url, body=apply_body, headers=session_headers)
    s.http_status = status
    s.payload = payload
    s.ok = ok and _as_bool(payload)
    if s.ok:
        approval_id = str(payload.get("approval_id") or "")
        s.detail = f"审批单已创建 approvalId={approval_id or '-'}"
    else:
        s.detail = f"失败: {err or payload}"
    artifacts["steps"][s.name] = payload

    # 6) 审批通过（自动触发执行）
    s = _step(rows, "审批通过并自动执行")
    if not approval_id:
        s.ok = False
        s.detail = "缺少 approvalId，跳过"
        artifacts["steps"][s.name] = {"ok": False, "error": s.detail}
    else:
        url = _mk_url(base, f"/admin/approval/{approval_id}/approve", {})
        ok, status, payload, err = _json_request("POST", url, body={"comment": args.approval_comment}, headers=session_headers)
        s.http_status = status
        s.payload = payload
        s.ok = ok and (isinstance(payload, dict) and not payload.get("error"))
        s.detail = "审批通过并触发执行" if s.ok else f"失败: {err or payload}"
        artifacts["steps"][s.name] = payload

    # 7) 对账
    s = _step(rows, "发布后对账")
    url = _mk_url(base, "/api/gm-ops/release/reconcile", common_q)
    ok, status, payload, err = _json_request("GET", url, headers=session_headers)
    s.http_status = status
    s.payload = payload
    s.ok = ok and _as_bool(payload)
    s.detail = "对账成功" if s.ok else f"失败: {err or payload}"
    artifacts["steps"][s.name] = payload

    # 8) 回滚
    s = _step(rows, "发布回滚")
    url = _mk_url(base, "/api/gm-ops/release/rollback", {})
    ok, status, payload, err = _json_request("POST", url, body=common_q, headers=session_headers)
    s.http_status = status
    s.payload = payload
    s.ok = ok and _as_bool(payload)
    s.detail = "回滚成功" if s.ok else f"失败: {err or payload}"
    artifacts["steps"][s.name] = payload

    # 9) 闭环证据 CI
    s = _step(rows, "闭环证据(closure-evidence/ci)")
    url = _mk_url(base, "/api/gm-ops/closure-evidence/ci", {**common_q, "ci_token": args.ci_token})
    ok, status, payload, err = _json_request("GET", url)
    s.http_status = status
    s.payload = payload
    s.ok = ok and _as_bool(payload)
    s.detail = "已拉取闭环证据" if s.ok else f"失败: {err or payload}"
    artifacts["steps"][s.name] = payload

    # 10) 质量门禁 CI
    s = _step(rows, "质量门禁(quality-gate/ci)")
    url = _mk_url(base, "/api/gm-ops/quality-gate/ci", {**common_q, "ci_token": args.ci_token})
    ok, status, payload, err = _json_request("GET", url)
    s.http_status = status
    s.payload = payload
    s.ok = ok and _as_bool(payload)
    s.detail = "门禁通过" if s.ok else f"失败: {err or payload}"
    artifacts["steps"][s.name] = payload

    # 11) 存储观测（需登录态）
    s = _step(rows, "Mongo/Redis 存储观测")
    url = _mk_url(base, "/api/gm-ops/storage/metrics", {})
    ok, status, payload, err = _json_request("GET", url, headers=session_headers)
    s.http_status = status
    s.payload = payload
    s.ok = ok and isinstance(payload, dict) and bool(payload.get("success"))
    s.detail = "观测接口可用" if s.ok else f"失败: {err or payload}"
    artifacts["steps"][s.name] = payload

    # 输出
    passed = sum(1 for x in rows if x.ok)
    total = len(rows)
    artifacts["summary"] = {"passed": passed, "total": total, "success": passed == total}

    md_lines: List[str] = []
    md_lines.append("# 运营中心可上线证据包（自动实测）")
    md_lines.append("")
    md_lines.append(f"- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md_lines.append(f"- BaseUrl: {base}")
    md_lines.append(f"- Project: {args.project_id}")
    md_lines.append(f"- Env/Channel/Platform: {args.env}/{args.channel}/{args.platform}")
    md_lines.append(f"- Version: {args.version_name}")
    md_lines.append(f"- 通过率: {passed}/{total}")
    md_lines.append("")
    md_lines.append("| 验收项 | 结果 | HTTP | 说明 |")
    md_lines.append("|---|---|---:|---|")
    for r in rows:
        md_lines.append(f"| {r.name} | {'通过' if r.ok else '失败'} | {r.http_status} | {str(r.detail).replace('|','/')} |")

    md_lines.append("")
    md_lines.append("## 说明")
    md_lines.append("- 如需跑完整审批链路，请提供可用管理员会话 Cookie（`--session-cookie`）。")
    md_lines.append("- Unity 编辑器按钮“从内网拉取/推送到内网”调用的是同一 sync-token 接口，本报告即对应其服务端闭环证据。")

    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(artifacts, f, ensure_ascii=False, indent=2)
    with open(args.out_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    print(f"[OK] Evidence JSON: {args.out_json}")
    print(f"[OK] Evidence MD:   {args.out_md}")
    print(f"[SUMMARY] passed={passed}/{total}")

    return 0 if artifacts["summary"]["success"] else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="GM/Ops 上线证据实测脚本")
    p.add_argument("--base-url", default="http://127.0.0.1:5000")
    p.add_argument("--project-id", required=True)
    p.add_argument("--env", default="staging")
    p.add_argument("--channel", default="test")
    p.add_argument("--platform", default="android")
    p.add_argument("--version-name", default="")
    p.add_argument("--ci-token", required=True)
    p.add_argument("--game-id", default="")
    p.add_argument("--game-key", default="")
    p.add_argument("--session-cookie", default="", help="管理员登录态 Cookie，供受保护接口使用")
    p.add_argument("--csrf-token", default="", help="可选 CSRF Token")
    p.add_argument("--reason", default="发布审批（自动化验收）")
    p.add_argument("--approval-comment", default="自动化验收审批通过")
    p.add_argument("--out-md", default="docs/ops_center_go_live_evidence.md")
    p.add_argument("--out-json", default="docs/ops_center_go_live_evidence.json")
    return p


if __name__ == "__main__":
    parser = build_parser()
    ns = parser.parse_args()
    raise SystemExit(run(ns))

# -*- coding: utf-8 -*-
"""Bridge client for legacy GameServer GM web console."""

from __future__ import annotations

import html
import os
import re
from typing import Any, Dict, List, Tuple

import requests


_MSG_RE = re.compile(r"<div class='(success|error)'>(.*?)</div>", re.IGNORECASE | re.DOTALL)
_ROW_RE = re.compile(r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


class LegacyGmBridgeClient:
    def __init__(self) -> None:
        self._timeout = int(os.getenv("GM_LEGACY_TIMEOUT_SECONDS", "12") or "12")

    @staticmethod
    def _clean_text(value: str) -> str:
        text = _TAG_RE.sub("", value or "")
        return html.unescape(text).strip()

    @staticmethod
    def _normalize_base(base_url: str) -> str:
        base = (base_url or "").strip().rstrip("/")
        if not base:
            return ""
        if not base.startswith("http://") and not base.startswith("https://"):
            base = "http://" + base
        if base.endswith("/gm"):
            base = base[: -len("/gm")]
        return base

    def _login(self, session: requests.Session, base_url: str, username: str, password: str) -> Tuple[bool, str]:
        login_url = f"{base_url}/gm/login"
        try:
            resp = session.post(
                login_url,
                data={"username": username or "", "password": password or ""},
                timeout=self._timeout,
                allow_redirects=False,
            )
        except Exception as ex:
            return False, f"连接失败: {ex}"

        if resp.status_code in (301, 302, 303, 307, 308):
            loc = str(resp.headers.get("Location") or "")
            if "/gm" in loc:
                return True, "ok"

        text = resp.text or ""
        if "账号或密码错误" in text:
            return False, "账号或密码错误"
        return False, f"登录失败，HTTP {resp.status_code}"

    def _parse_dashboard_message(self, html_text: str) -> Dict[str, Any]:
        matched = _MSG_RE.search(html_text or "")
        if not matched:
            return {"level": "info", "message": "命令已提交（未解析到明确提示）"}
        return {"level": matched.group(1).lower(), "message": self._clean_text(matched.group(2))}

    def _parse_player_rows(self, html_text: str) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        for m in _ROW_RE.finditer(html_text or ""):
            rows.append(
                {
                    "player_id": self._clean_text(m.group(1)),
                    "account_id": self._clean_text(m.group(2)),
                    "nickname": self._clean_text(m.group(3)),
                    "server_id": self._clean_text(m.group(4)),
                    "level_vip": self._clean_text(m.group(5)),
                    "power": self._clean_text(m.group(6)),
                    "status": self._clean_text(m.group(7)),
                }
            )
        return rows

    def submit_form(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        path: str,
        form: Dict[str, Any],
    ) -> Dict[str, Any]:
        base = self._normalize_base(base_url)
        if not base:
            return {"success": False, "status": 400, "message": "missing base_url", "data": {}}

        with requests.Session() as session:
            ok, msg = self._login(session, base, username, password)
            if not ok:
                return {"success": False, "status": 401, "message": msg, "data": {}}

            url = f"{base}{path if path.startswith('/') else '/' + path}"
            try:
                resp = session.post(url, data=form or {}, timeout=self._timeout, allow_redirects=True)
            except Exception as ex:
                return {"success": False, "status": 500, "message": f"请求失败: {ex}", "data": {}}

            parsed = self._parse_dashboard_message(resp.text or "")
            data: Dict[str, Any] = {
                "level": parsed["level"],
                "message": parsed["message"],
                "raw_preview": (self._clean_text(resp.text or "")[:500] if resp.text else ""),
            }
            if path.endswith("/search-player"):
                data["players"] = self._parse_player_rows(resp.text or "")

            success = resp.status_code < 400 and parsed["level"] != "error"
            return {
                "success": success,
                "status": resp.status_code,
                "message": parsed["message"],
                "data": data,
            }

    def query_agent_status(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        server_id: str,
    ) -> Dict[str, Any]:
        base = self._normalize_base(base_url)
        if not base:
            return {"success": False, "status": 400, "message": "missing base_url", "data": {}}

        with requests.Session() as session:
            ok, msg = self._login(session, base, username, password)
            if not ok:
                return {"success": False, "status": 401, "message": msg, "data": {}}

            try:
                resp = session.get(
                    f"{base}/gm/agent-status",
                    params={"serverId": server_id or ""},
                    timeout=self._timeout,
                )
            except Exception as ex:
                return {"success": False, "status": 500, "message": f"请求失败: {ex}", "data": {}}

            try:
                body = resp.json() if resp.content else {}
            except Exception:
                body = {"success": False, "message": "invalid json"}

            return {
                "success": bool(body.get("success")),
                "status": resp.status_code,
                "message": str(body.get("message") or "OK"),
                "data": body,
            }

    def query_ops_health(self, *, ops_base_url: str, read_key: str = "", actor: str = "intranet-ops") -> Dict[str, Any]:
        base = self._normalize_base(ops_base_url)
        if not base:
            return {"success": False, "status": 400, "message": "missing ops_base_url", "data": {}}
        headers = {"X-Ops-Actor": actor, "X-Ops-Role": "Viewer", "X-Ops-Reason": "ops health check", "X-Ops-TicketId": "OPS-HEALTH-CHECK"}
        if read_key:
            headers["X-Ops-Key"] = read_key
        try:
            resp = requests.get(f"{base}/ops/health", headers=headers, timeout=self._timeout)
        except Exception as ex:
            return {"success": False, "status": 500, "message": f"请求失败: {ex}", "data": {}}
        try:
            body = resp.json() if resp.content else {}
        except Exception:
            body = {"success": False, "message": "invalid json"}
        return {
            "success": bool(body.get("success", resp.status_code < 400)),
            "status": resp.status_code,
            "message": str(body.get("message") or "OK"),
            "data": body.get("data", body),
        }

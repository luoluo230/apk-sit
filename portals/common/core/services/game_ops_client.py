# -*- coding: utf-8 -*-
"""Game server Ops client for intranet GM operations center."""

import json
import os
from typing import Any, Dict, Optional

import requests


class GameOpsClient:
    """统一封装对 game-server Ops API 的调用。"""

    def __init__(self) -> None:
        base_url = (os.getenv("GAME_OPS_BASE_URL", "http://127.0.0.1:5054") or "").strip().rstrip("/")
        self._base_url = base_url
        self._timeout = int(os.getenv("GAME_OPS_TIMEOUT_SECONDS", "8") or "8")
        self._read_key = os.getenv("GAME_OPS_READ_KEY", "ops-read-dev") or ""
        self._write_key = os.getenv("GAME_OPS_WRITE_KEY", "ops-write-dev") or ""

    @property
    def base_url(self) -> str:
        return self._base_url

    def get_runtime_snapshot(self, operator: str, role: str = "Viewer") -> Dict[str, Any]:
        return self._request("GET", "/ops/runtime-snapshot", operator=operator, role=role, write=False)

    def get_cluster(self, operator: str, role: str = "Viewer") -> Dict[str, Any]:
        return self._request("GET", "/ops/cluster", operator=operator, role=role, write=False)

    def get_health(self, operator: str, role: str = "Viewer") -> Dict[str, Any]:
        return self._request("GET", "/ops/health", operator=operator, role=role, write=False)

    def get_storage_metrics(self, operator: str, role: str = "Viewer") -> Dict[str, Any]:
        return self._request("GET", "/ops/storage-metrics", operator=operator, role=role, write=False)

    def execute_action(self, action: Dict[str, Any], operator: str, role: str, reason: str, ticket_id: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/ops/action",
            operator=operator,
            role=role,
            write=True,
            reason=reason,
            ticket_id=ticket_id,
            json_body=action,
        )

    def _request(
        self,
        method: str,
        path: str,
        operator: str,
        role: str,
        write: bool,
        reason: str = "gm operation",
        ticket_id: str = "N/A",
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        key = self._write_key if write else (self._read_key or self._write_key)
        headers = {
            "X-Ops-Key": key,
            "X-Ops-Actor": operator or "intranet-gm",
            "X-Ops-Role": role or "Viewer",
            "X-Ops-Reason": reason or "gm operation",
            "X-Ops-TicketId": ticket_id or "N/A",
        }

        url = f"{self._base_url}{path}"
        try:
            if method.upper() == "GET":
                resp = requests.get(url, headers=headers, timeout=self._timeout)
            else:
                payload = json.dumps(json_body or {}, ensure_ascii=False)
                headers["Content-Type"] = "application/json; charset=utf-8"
                resp = requests.post(url, headers=headers, data=payload.encode("utf-8"), timeout=self._timeout)

            body: Dict[str, Any]
            try:
                body = resp.json() if resp.content else {"success": resp.ok}
            except Exception:
                body = {"success": resp.ok, "raw": resp.text}

            if resp.status_code >= 400:
                return {
                    "success": False,
                    "status": resp.status_code,
                    "message": body.get("message") or body.get("error") or "Ops request failed.",
                    "data": body,
                }

            success = bool(body.get("success", True))
            data = body.get("data", body)
            message = body.get("message") or "OK"
            if path == "/ops/action" and isinstance(data, dict):
                result_code = str(data.get("ResultCode") or data.get("resultCode") or "").strip()
                result_message = str(data.get("ResultMessage") or data.get("resultMessage") or "").strip()
                if result_code:
                    success = result_code in ("OPS_OK", "OPS_DRY_RUN_OK")
                    message = result_message or message

            return {
                "success": success,
                "status": resp.status_code,
                "message": message,
                "data": data,
            }
        except Exception as ex:
            return {
                "success": False,
                "status": 500,
                "message": f"Ops service unavailable: {ex}",
                "data": {},
            }

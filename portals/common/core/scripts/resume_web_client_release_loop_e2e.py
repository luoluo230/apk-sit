#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接续已触发的 Jenkins 构建：轮询 →（可选）Publish → runtime-bootstrap 验收。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_web_client_release_loop_e2e import (  # noqa: E402
    BUILD_TIMEOUT_SEC,
    PROJECT_ID,
    USERNAME,
    _log,
    poll_jenkins,
    verify_client_load,
)


def main() -> int:
    build_no = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    order_id = sys.argv[2] if len(sys.argv) > 2 else "ro-20261030161545-c547b0"
    _log(f"接续轮询 Jenkins #{build_no} order={order_id} timeout={BUILD_TIMEOUT_SEC}s")

    from app_new import app

    with app.app_context():
        status = poll_jenkins(build_no)
    _log(f"Jenkins #{build_no} 终态: {status}")

    client = None
    domain_error = ""
    with app.app_context():
        with app.test_request_context("/"):
            from flask import session as flask_session

            flask_session["user"] = USERNAME
            # 构建成功后走发布单同步 + Publish；失败不再 seed fixture greening
            if status == "SUCCESS":
                from services.release.order_build_sync import sync_release_order_build_status
                from services.release import order_publish_flow as pub
                from services.release import order_crud as crud

                try:
                    sync_release_order_build_status(PROJECT_ID, order_id, actor=USERNAME)
                except Exception as e:
                    _log(f"sync build status: {e}")
                order = crud.get_release_order(PROJECT_ID, order_id) or {}
                st = str(order.get("status") or "")
                _log(f"order after sync: {st}")
                if st in {"artifacts_ready", "precheck_failed", "draft", "ready"}:
                    try:
                        order = pub.precheck_release_order(PROJECT_ID, order_id, USERNAME)
                        st = str(order.get("status") or "")
                        _log(f"precheck => {st}")
                    except Exception as e:
                        _log(f"precheck: {e}")
                if st in {"ready", "approved"}:
                    try:
                        order = pub.publish_release_order(PROJECT_ID, order_id, USERNAME)
                        st = str(order.get("status") or "")
                        _log(f"publish => {st}")
                    except Exception as e:
                        _log(f"publish: {e}")
                try:
                    import os

                    os.environ["RUNTIME_DOMAIN_REJECT_FIXTURE"] = "1"
                    client = verify_client_load()
                except Exception as exc:
                    domain_error = str(exc)
                    client = {"ok": False, "error": domain_error}
            else:
                _log("跳过 fixture greening：Jenkins 非 SUCCESS 不以夹具冒充客户端通过")

    summary = {
        "jenkins_build": build_no,
        "jenkins_status": status,
        "release_order_id": order_id,
        "client": client,
        "domain_error": domain_error,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if status == "SUCCESS" and not domain_error and isinstance(client, dict) and client.get("domains"):
        _log("PASS: Jenkins 构建成功 + 客户端三域下载")
        return 0
    if status == "SUCCESS":
        _log(f"FAIL: Jenkins SUCCESS 但客户端三域未通过: {domain_error or client}")
        return 5
    if status in ("FAILURE", "ABORTED", "UNSTABLE"):
        _log(f"FAIL: Jenkins={status}（不以 fixture 冒充客户端通过）")
        return 2
    _log("FAIL: Jenkins 超时（不以 fixture 冒充客户端通过）")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())

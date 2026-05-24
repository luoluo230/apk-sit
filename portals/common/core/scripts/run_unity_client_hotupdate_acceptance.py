#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unity 客户端真实启动热更验收。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.unity_client_hotupdate_runner import run_unity_client_startup_acceptance  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Unity 客户端真实启动热更验收")
    parser.add_argument("--unity-project", default="/Users/wangling/Desktop/MyGame/GameClient")
    parser.add_argument("--unity-path", default="")
    parser.add_argument("--base-url", default="http://127.0.0.1:5003")
    parser.add_argument("--project-id", default="GomeKu")
    parser.add_argument("--channel", default="wechat")
    parser.add_argument("--environment", default="Development")
    parser.add_argument("--version-name", default="1.0.0")
    parser.add_argument("--platform", default="Android")
    parser.add_argument("--scenario", default="basic")
    parser.add_argument("--timeout-sec", type=int, default=45)
    args = parser.parse_args()

    result = run_unity_client_startup_acceptance(
        unity_project=args.unity_project,
        unity_path=args.unity_path or None,
        api_base=args.base_url,
        project_id=args.project_id,
        channel=args.channel,
        environment=args.environment,
        version_name=args.version_name,
        platform=args.platform,
        scenario=args.scenario,
        timeout_sec=args.timeout_sec,
    )

    print("=== Unity 客户端真实启动热更验收 ===")
    print("场景:", result["scenario"], "| 层级:", result["tier"])
    print("最终状态:", result.get("final_state"))
    print("Catalog:", result.get("catalog_url"))
    print("摘要:", result["summary"])
    print("报告:", result["report_path"])
    print("Unity 退出码:", result["unity_exit_code"])
    print()
    print("RESULT:", "PASS" if result["passed"] else "FAIL")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

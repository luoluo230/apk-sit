#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Version 数据治理扫描（默认只给建议，不直接改数据）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.data import project_versions_db


TARGET_STATUSES = {"draft", "testing", "active", "disabled", "archived"}
STATUS_ALIAS = {
    "valid": "active",
    "enabled": "active",
    "online": "active",
    "test": "testing",
    "beta": "testing",
    "deprecated": "disabled",
    "obsolete": "disabled",
    "invalid": "disabled",
    "inactive": "disabled",
    "archive": "archived",
}
OLD_FIELDS = {
    "jenkins_params",
    "commercial_release",
    "deprecated",
    "status",
}


def _norm_status(raw):
    s = str(raw or "").strip().lower()
    s = STATUS_ALIAS.get(s, s)
    if s in TARGET_STATUSES:
        return s
    return "active"


def analyze():
    report = {
        "summary": {
            "project_count": 0,
            "version_row_count": 0,
            "empty_version_code_count": 0,
            "duplicate_version_code_group_count": 0,
            "status_normalize_suggestion_count": 0,
            "legacy_field_hit_count": 0,
        },
        "projects": {},
    }
    for project_id, rows in (project_versions_db or {}).items():
        if not isinstance(rows, list):
            continue
        report["summary"]["project_count"] += 1
        report["summary"]["version_row_count"] += len(rows)
        project_findings = {
            "empty_version_code": [],
            "duplicate_version_code_groups": [],
            "status_suggestions": [],
            "legacy_field_suggestions": [],
        }
        dup_map = defaultdict(list)
        for row in rows:
            if not isinstance(row, dict):
                continue
            vid = str(row.get("id") or "")
            vname = str(row.get("version_name") or "")
            stage = str(row.get("stage") or "")
            channel = str(row.get("channel") or "")
            platform = str(row.get("platform") or "")
            vcode = str(row.get("version_code") or "").strip()
            if not vcode:
                project_findings["empty_version_code"].append({"id": vid, "version_name": vname, "stage": stage, "channel": channel, "platform": platform})
                report["summary"]["empty_version_code_count"] += 1
            key = (vname, stage, channel, platform, vcode)
            dup_map[key].append(vid or "<missing-id>")

            raw_status = str(row.get("version_status") or "")
            norm_status = _norm_status(raw_status)
            if raw_status.strip().lower() != norm_status:
                project_findings["status_suggestions"].append({"id": vid, "from": raw_status, "to": norm_status})
                report["summary"]["status_normalize_suggestion_count"] += 1

            hit_fields = [f for f in OLD_FIELDS if f in row]
            if hit_fields:
                project_findings["legacy_field_suggestions"].append({"id": vid, "fields": hit_fields})
                report["summary"]["legacy_field_hit_count"] += len(hit_fields)

        for key, ids in dup_map.items():
            vname, stage, channel, platform, vcode = key
            if vcode and len(ids) > 1:
                project_findings["duplicate_version_code_groups"].append(
                    {
                        "version_name": vname,
                        "stage": stage,
                        "channel": channel,
                        "platform": platform,
                        "version_code": vcode,
                        "ids": ids,
                    }
                )
                report["summary"]["duplicate_version_code_group_count"] += 1

        if any(project_findings.values()):
            report["projects"][project_id] = project_findings
    return report


def main():
    parser = argparse.ArgumentParser(description="版本数据治理扫描（只读）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()
    report = analyze()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    s = report["summary"]
    print("=== Version 数据治理报告（只读）===")
    print("项目数:", s["project_count"])
    print("版本行数:", s["version_row_count"])
    print("空 version_code:", s["empty_version_code_count"])
    print("重复 version_code 组:", s["duplicate_version_code_group_count"])
    print("状态规范化建议:", s["status_normalize_suggestion_count"])
    print("旧字段命中:", s["legacy_field_hit_count"])
    if report["projects"]:
        print("\n建议: 使用 --json 查看详细项，再按项目逐条修复。")


if __name__ == "__main__":
    main()

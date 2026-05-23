#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 Jenkins 实例 build_defaults 中的项目级字段迁移到 projects.build_config，并清空实例 build_defaults。

匹配规则（按优先级）：
  1. instance.task_name -> project_id
  2. build_defaults.app_name -> project_id
  3. 与 legacy jenkins_instances.json 中同 task_name 记录的 Git 字段互补

用法：
  python3 scripts/migrate_instance_build_defaults_to_projects.py          # 预览
  python3 scripts/migrate_instance_build_defaults_to_projects.py --apply  # 写入 SQLite
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from copy import deepcopy
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config import DATA_DIR, load_dotenv  # noqa: E402
from models.db import get_json_document, init_db, set_json_document  # noqa: E402
from services.admin.project_build_config_service import normalize_build_config  # noqa: E402

PROJECTS_KEY = "data/projects.json"
JENKINS_KEY = "data/jenkins_instances.json"
LEGACY_JENKINS = os.path.join(DATA_DIR, "_legacy_json", "jenkins_instances.json")

PROJECT_FIELDS = (
    "app_name",
    "git_url",
    "git_workspace",
    "git_ssh_key_path",
    "default_git_branch",
    "git_branches",
    "unity_project_path",
    "output_base_dir",
)
SKIP_INSTANCE_KEYS = {"version_name", "version_code", "unity_versions", "commercial_release"}


def _normalize_token(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def _build_project_index(projects: dict) -> dict:
    index = {"by_id": set(), "by_lower": {}, "by_norm": {}}
    if not isinstance(projects, dict):
        return index
    for pid, payload in projects.items():
        project_id = str(pid or "").strip()
        if not project_id:
            continue
        index["by_id"].add(project_id)
        item = payload if isinstance(payload, dict) else {}
        aliases = [
            project_id,
            str(item.get("name") or "").strip(),
            str(item.get("name_en") or "").strip(),
        ]
        for alias in aliases:
            if not alias:
                continue
            index["by_lower"][alias.lower()] = project_id
            norm = _normalize_token(alias)
            if norm:
                index["by_norm"][norm] = project_id
    return index


def _resolve_project_id(ref: str, index: dict) -> str:
    text = str(ref or "").strip()
    if not text:
        return ""
    if text in index["by_id"]:
        return text
    lower = text.lower()
    if lower in index["by_lower"]:
        return index["by_lower"][lower]
    norm = _normalize_token(text)
    if norm and norm in index["by_norm"]:
        return index["by_norm"][norm]
    if norm:
        best = ""
        best_ratio = 0.0
        for token, pid in index["by_norm"].items():
            ratio = SequenceMatcher(None, norm, token).ratio()
            if ratio > best_ratio:
                best = pid
                best_ratio = ratio
        if best_ratio >= 0.82:
            return best
    return ""


def _read_env_git(jenkins_home: str) -> dict:
    if not jenkins_home:
        return {}
    env_path = os.path.join(jenkins_home, ".apk-site-env")
    if not os.path.isfile(env_path):
        port = os.path.basename(jenkins_home.rstrip(os.sep))
        if port.isdigit():
            local = os.path.join(DATA_DIR, "jenkins_instances", port, ".apk-site-env")
            if os.path.isfile(local):
                env_path = local
            else:
                return {}
        else:
            return {}
    out = {}
    try:
        with open(env_path, "r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                line = raw.strip()
                if not line.startswith("export "):
                    continue
                rest = line[7:].strip()
                if "=" not in rest:
                    continue
                key, _, val = rest.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key == "GIT_URL" and val:
                    out["git_url"] = val
                elif key == "GIT_SSH_KEY_PATH" and val:
                    out["git_ssh_key_path"] = val
                elif key == "GIT_WORKSPACE" and val:
                    out["git_workspace"] = val
                elif key == "UNITY_PROJECT_PATH" and val:
                    out["unity_project_path"] = val
    except OSError:
        return {}
    return out


def _instance_project_fields(bd: dict) -> dict:
    if not isinstance(bd, dict):
        return {}
    out = {}
    for key in PROJECT_FIELDS:
        if key in SKIP_INSTANCE_KEYS:
            continue
        val = bd.get(key)
        if key == "git_branches":
            if isinstance(val, list) and val:
                out[key] = [str(x).strip() for x in val if str(x).strip()]
            continue
        if val is not None and str(val).strip():
            out[key] = str(val).strip()
    if not out.get("default_git_branch") and out.get("git_branches"):
        out["default_git_branch"] = out["git_branches"][0]
    return normalize_build_config(out)


def _project_existing_bc(project: dict) -> dict:
    stored = project.get("build_config") if isinstance(project.get("build_config"), dict) else {}
    legacy_git = {
        "git_url": str(project.get("git_url") or "").strip(),
        "git_ssh_key_path": str(project.get("git_ssh_key_path") or "").strip(),
    }
    return normalize_build_config({**legacy_git, **stored})


def _merge_fill(existing: dict, incoming: dict, force: bool = False) -> dict:
    out = dict(existing or {})
    for key, val in (incoming or {}).items():
        if key not in PROJECT_FIELDS and key != "git_branches":
            continue
        if isinstance(val, list):
            if force or not out.get(key):
                out[key] = val
            continue
        if force or not str(out.get(key) or "").strip():
            if val is not None and str(val).strip():
                out[key] = str(val).strip()
    if not out.get("default_git_branch") and out.get("git_branches"):
        out["default_git_branch"] = out["git_branches"][0]
    return normalize_build_config(out)


def _load_legacy_by_task() -> dict:
    out = {}
    if not os.path.isfile(LEGACY_JENKINS):
        return out
    try:
        with open(LEGACY_JENKINS, "r", encoding="utf-8") as handle:
            rows = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return out
    if not isinstance(rows, list):
        return out
    for inst in rows:
        if not isinstance(inst, dict):
            continue
        task = str(inst.get("task_name") or "").strip().lower()
        if not task:
            continue
        bd = _instance_project_fields(inst.get("build_defaults") or {})
        if bd:
            out[task] = bd
    return out


def _default_git_ssh_path() -> str:
    path = os.path.join(ROOT, "jenkins-clone", "github-ssh-key")
    expanded = os.path.abspath(path)
    if os.path.isfile(expanded):
        return expanded
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate instance build_defaults to project build_config")
    parser.add_argument("--apply", action="store_true", help="write changes to SQLite")
    parser.add_argument("--force", action="store_true", help="overwrite existing project build_config fields")
    args = parser.parse_args()

    load_dotenv()
    init_db()

    projects = get_json_document(PROJECTS_KEY, {})
    instances = get_json_document(JENKINS_KEY, [])
    if not isinstance(projects, dict):
        projects = {}
    if not isinstance(instances, list):
        instances = []

    project_index = _build_project_index(projects)
    legacy_by_task = _load_legacy_by_task()
    default_ssh = _default_git_ssh_path()

    changes = []
    unmatched = []

    for inst in instances:
        if not isinstance(inst, dict):
            continue
        bd = inst.get("build_defaults") if isinstance(inst.get("build_defaults"), dict) else {}
        if not bd and not inst.get("task_name"):
            continue

        task = str(inst.get("task_name") or "").strip()
        incoming = _instance_project_fields(bd)
        incoming.update({k: v for k, v in _read_env_git(str(inst.get("jenkins_home") or "")).items() if v})

        legacy = legacy_by_task.get(task.lower(), {})
        for key in ("git_url", "git_ssh_key_path", "default_git_branch", "git_branches"):
            if not incoming.get(key) and legacy.get(key):
                incoming[key] = legacy[key]

        if not incoming.get("git_ssh_key_path") and incoming.get("git_url", "").startswith("git@"):
            incoming["git_ssh_key_path"] = default_ssh
        elif incoming.get("git_ssh_key_path") and not os.path.isfile(incoming["git_ssh_key_path"]) and default_ssh:
            incoming["git_ssh_key_path"] = default_ssh

        project_id = _resolve_project_id(task, project_index) or _resolve_project_id(
            incoming.get("app_name") or "", project_index
        )
        if not project_id:
            if bd or incoming:
                unmatched.append({"instance_id": inst.get("id"), "task_name": task, "fields": incoming})
            continue

        project = projects.get(project_id) or {}
        before = _project_existing_bc(project)
        after = _merge_fill(before, incoming, force=args.force)

        inst_id = inst.get("id")
        if after != before or bd:
            changes.append(
                {
                    "project_id": project_id,
                    "instance_id": inst_id,
                    "task_name": task,
                    "before": before,
                    "after": after,
                    "cleared_instance_defaults": bool(bd),
                }
            )
            project["build_config"] = after
            project["git_url"] = after.get("git_url", "")
            project["git_ssh_key_path"] = after.get("git_ssh_key_path", "")
            projects[project_id] = project
            if "build_defaults" in inst:
                inst.pop("build_defaults", None)

    print("[migrate_instance_build_defaults_to_projects] preview")
    print("  projects touched: %d" % len(changes))
    print("  unmatched instances: %d" % len(unmatched))
    for row in changes:
        print("\n--- project %s (instance %s / task %s) ---" % (row["project_id"], row["instance_id"], row["task_name"]))
        for key in PROJECT_FIELDS + ("git_branches",):
            b = row["before"].get(key)
            a = row["after"].get(key)
            if b != a:
                print("  %s: %r -> %r" % (key, b, a))
        if row["cleared_instance_defaults"]:
            print("  instance build_defaults: cleared")

    if unmatched:
        print("\n[unmatched]")
        for row in unmatched:
            print("  instance=%s task=%s fields=%s" % (row.get("instance_id"), row.get("task_name"), row.get("fields")))

    if not args.apply:
        print("\n(dry-run) add --apply to persist")
        return 0

    set_json_document(PROJECTS_KEY, projects)
    set_json_document(JENKINS_KEY, instances)
    print("\n[applied] saved projects + jenkins_instances to SQLite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

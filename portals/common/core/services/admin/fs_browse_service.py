"""本机目录/文件浏览与系统原生路径选择。"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

BLOCKED_PREFIXES = (
    "/System",
    "/private/var/root",
    "/etc",
    "/dev",
    "/proc",
    "/sbin",
    "/usr/sbin",
)

_NATIVE_PICKER_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scripts", "native_path_picker.py")


def _allowed_roots() -> List[str]:
    roots: List[str] = []
    home = os.path.realpath(os.path.expanduser("~"))
    if home:
        roots.append(home)

    if os.name == "nt":
        import string

        for letter in string.ascii_uppercase:
            drive = "%s:\\" % letter
            if os.path.exists(drive):
                roots.append(os.path.realpath(drive))
    else:
        for candidate in ("/Users", "/Volumes", "/tmp", "/home"):
            if candidate and os.path.exists(candidate):
                real = os.path.realpath(candidate)
                if real not in roots:
                    roots.append(real)
    return roots


def is_path_allowed(path: str) -> bool:
    if not path:
        return False
    real = os.path.realpath(os.path.expanduser(path))
    if os.name != "nt":
        for blocked in BLOCKED_PREFIXES:
            if real == blocked or real.startswith(blocked + os.sep):
                return False
    for root in _allowed_roots():
        try:
            if os.path.commonpath([real, root]) == root:
                return True
        except ValueError:
            continue
    return False


def normalize_browse_path(raw: str) -> Tuple[Optional[str], Optional[str]]:
    text = str(raw or "").strip()
    if not text:
        path = os.path.realpath(os.path.expanduser("~"))
    else:
        path = os.path.realpath(os.path.expanduser(text))
    if not is_path_allowed(path):
        return None, "路径不在允许浏览的范围内"
    return path, None


def browse_path(raw_path: str = "", mode: str = "dir") -> Dict[str, Any]:
    """列出目录内容。mode=dir 仅目录；mode=file 含文件（用于 SSH 密钥选择）。"""
    mode = "file" if str(mode or "").strip().lower() == "file" else "dir"
    path, err = normalize_browse_path(raw_path)
    if err:
        return {"ok": False, "error": err}
    if not os.path.isdir(path):
        parent = os.path.dirname(path)
        path, err = normalize_browse_path(parent)
        if err:
            return {"ok": False, "error": err}

    parent = os.path.dirname(path)
    parent_path = parent if parent and parent != path and is_path_allowed(parent) else ""

    entries: List[Dict[str, Any]] = []
    try:
        names = os.listdir(path)
    except OSError as exc:
        return {"ok": False, "error": str(exc) or "无法读取目录"}

    for name in sorted(names, key=str.lower):
        if name.startswith("."):
            continue
        full = os.path.join(path, name)
        try:
            is_dir = os.path.isdir(full)
            is_file = os.path.isfile(full)
        except OSError:
            continue
        if mode == "dir":
            if not is_dir:
                continue
        elif not (is_dir or is_file):
            continue
        entries.append({"name": name, "path": full, "is_dir": is_dir})

    entries.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
    return {
        "ok": True,
        "path": path,
        "parent": parent_path,
        "entries": entries,
        "mode": mode,
    }


def native_pick_path(raw_path: str = "", mode: str = "dir") -> Dict[str, Any]:
    """弹出系统原生目录/文件选择框，返回绝对路径。"""
    mode = "file" if str(mode or "").strip().lower() == "file" else "dir"
    initial = str(raw_path or "").strip()
    if initial:
        expanded = os.path.realpath(os.path.expanduser(initial))
        if os.path.isfile(expanded):
            initial = expanded
        elif os.path.isdir(expanded):
            initial = expanded
        else:
            parent = os.path.dirname(expanded)
            initial = parent if parent and os.path.isdir(parent) else os.path.expanduser("~")
    else:
        initial = os.path.expanduser("~")

    if not os.path.isfile(_NATIVE_PICKER_SCRIPT):
        return {"ok": False, "error": "未找到 native_path_picker.py"}

    try:
        proc = subprocess.run(
            [sys.executable, _NATIVE_PICKER_SCRIPT, mode, initial],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "选择超时"}
    except OSError as exc:
        return {"ok": False, "error": str(exc) or "无法启动系统选择框"}

    if proc.returncode != 0 and not (proc.stdout or "").strip():
        err = (proc.stderr or "").strip()
        return {"ok": False, "error": err or "系统选择框启动失败"}

    try:
        payload = __import__("json").loads((proc.stdout or "").strip() or "{}")
    except Exception:
        return {"ok": False, "error": "解析选择结果失败"}

    if payload.get("cancelled"):
        return {"ok": False, "cancelled": True}

    path = str(payload.get("path") or "").strip()
    if not path:
        return {"ok": False, "cancelled": True}

    if mode == "dir" and not os.path.isdir(path):
        return {"ok": False, "error": "所选路径不是目录"}
    if mode == "file" and not os.path.isfile(path):
        return {"ok": False, "error": "所选路径不是文件"}

    if not is_path_allowed(path):
        return {"ok": False, "error": "所选路径不在允许范围内"}

    return {"ok": True, "path": path, "mode": mode}

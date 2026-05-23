#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在独立进程中弹出系统原生路径选择框（macOS Finder / Windows 对话框）。"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys


def _pick_macos(mode: str, initial: str) -> dict:
    if mode == "file":
        cmd = 'POSIX path of (choose file with prompt "选择文件"'
    else:
        cmd = 'POSIX path of (choose folder with prompt "选择目录"'

    init = os.path.expanduser((initial or "").strip())
    if init:
        if os.path.isdir(init):
            cmd += " default location (POSIX file %s)" % json.dumps(init)
        elif os.path.isfile(init):
            cmd += " default location (POSIX file %s)" % json.dumps(os.path.dirname(init))

    cmd += ")"
    proc = subprocess.run(["osascript", "-e", cmd], capture_output=True, text=True)
    if proc.returncode != 0:
        return {"ok": False, "cancelled": True, "path": ""}
    path = (proc.stdout or "").strip()
    return {"ok": bool(path), "path": path, "cancelled": not bool(path)}


def _pick_tkinter(mode: str, initial: str) -> dict:
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    root.update_idletasks()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass

    init = os.path.expanduser((initial or "").strip() or "~")
    initial_dir = init if os.path.isdir(init) else (os.path.dirname(init) if init else init)
    if initial_dir and not os.path.isdir(initial_dir):
        initial_dir = os.path.expanduser("~")

    try:
        if mode == "file":
            if os.path.isfile(init):
                path = filedialog.askopenfilename(
                    title="选择文件",
                    initialdir=initial_dir,
                    initialfile=os.path.basename(init),
                )
            else:
                path = filedialog.askopenfilename(title="选择文件", initialdir=initial_dir or None)
        else:
            path = filedialog.askdirectory(title="选择目录", initialdir=initial_dir or None)
    finally:
        root.destroy()

    path = path or ""
    return {"ok": bool(path), "path": path, "cancelled": not bool(path)}


def main() -> int:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "dir").strip().lower()
    if mode not in ("dir", "file"):
        mode = "dir"
    initial = sys.argv[2] if len(sys.argv) > 2 else ""

    if platform.system() == "Darwin":
        result = _pick_macos(mode, initial)
    else:
        result = _pick_tkinter(mode, initial)

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

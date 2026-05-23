#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对 admin 页面渲染后的内嵌 JS 执行 node --check。"""

from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PAGES = [
    ("/admin/projects", "projects"),
    ("/admin/jenkins", "jenkins"),
]


def _extract_scripts(html: str) -> str:
    chunks = []
    for attrs, body in re.findall(r"<script([^>]*)>([\s\S]*?)</script>", html, flags=re.I):
        if "application/json" in (attrs or "").lower():
            continue
        chunks.append(body)
    return "\n\n".join(chunks)


def main() -> int:
    from app_new import app
    from models.data import load_jenkins_instances, users_db

    username = next(iter(users_db.keys()), "admin")
    instances = load_jenkins_instances() or []
    inst_id = ""
    for inst in instances:
        if isinstance(inst, dict) and inst.get("id"):
            inst_id = str(inst.get("id"))
            break
    if inst_id:
        PAGES.append(("/admin/jenkins/edit?instance_id=%s" % inst_id, "jenkins_edit"))

    tmp_dir = os.path.join(ROOT, "tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    failed = False

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = username
        for path, label in PAGES:
            resp = client.get(path)
            if resp.status_code != 200:
                print("[FAIL] %s status=%s" % (path, resp.status_code))
                failed = True
                continue
            rendered = _extract_scripts(resp.get_data(as_text=True))
            out_path = os.path.join(tmp_dir, "rendered_%s.js" % label)
            with open(out_path, "w", encoding="utf-8") as handle:
                handle.write(rendered)
            proc = subprocess.run(["node", "--check", out_path], capture_output=True, text=True)
            if proc.returncode != 0:
                print("[FAIL] node --check %s" % out_path)
                print(proc.stdout)
                print(proc.stderr)
                failed = True
            else:
                print("[OK] %s -> %s" % (path, out_path))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

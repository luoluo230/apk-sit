#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""版本模块发布前校验清单（CI gate）。"""

from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def run(cmd, cwd=None):
    print("[RUN]", " ".join(cmd))
    return subprocess.run(cmd, cwd=cwd or ROOT, check=False, capture_output=True, text=True)


def check_py_compile():
    files = [
        os.path.join(ROOT, "routes", "admin_routes.py"),
        os.path.join(ROOT, "routes", "api.py"),
        os.path.join(ROOT, "services", "admin", "version_service.py"),
    ]
    for f in files:
        p = run([PY, "-m", "py_compile", f])
        if p.returncode != 0:
            print(p.stdout)
            print(p.stderr)
            return False
    return True


def check_rendered_js():
    from app_new import app
    from models.data import users_db

    username = next(iter(users_db.keys()), "admin")
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user"] = username
        resp = c.get("/admin/projects/GomeKu/versions?tab=channels")
        if resp.status_code != 200:
            print("versions page status:", resp.status_code)
            return False
        html = resp.get_data(as_text=True)
    scripts = re.findall(r"<script([^>]*)>([\s\S]*?)</script>", html, flags=re.I)
    chunks = []
    for attrs, body in scripts:
        if "application/json" in (attrs or "").lower():
            continue
        chunks.append(body)
    rendered = os.path.join(ROOT, "tmp_rendered_versions_exec_ci.js")
    with open(rendered, "w", encoding="utf-8") as f:
        f.write("\n\n".join(chunks))
    node = run(["node", "--check", rendered])
    if node.returncode != 0:
        print(node.stdout)
        print(node.stderr)
        return False
    return True


def check_health_and_smoke():
    from app_new import app
    from models.data import projects_db, project_versions_db

    with app.test_client() as c:
        health = c.get("/health")
        if health.status_code != 200:
            print("health status:", health.status_code)
            return False
        pid = "ci_ver_%s" % secrets.token_hex(4)
        projects_db[pid] = {"name": pid, "status": "active"}
        project_versions_db[pid] = [
            {
                "id": "ci1",
                "channel": "1001",
                "stage": "dev",
                "platform": "android",
                "version_name": "1.0.0",
                "version_code": "100",
                "version_status": "active",
                "apk_path": "wechat/dev/demo.apk",
                "updated_at": "2026-01-01T00:00:00",
            }
        ]
        try:
            with c.session_transaction() as sess:
                sess["user"] = "admin"
            vlist = c.get("/admin/projects/%s/versions/list" % pid)
            if vlist.status_code != 200:
                print("versions/list status:", vlist.status_code)
                return False
            r = c.get("/api/runtime/version-resolve?project_id=%s&version_name=1.0.0&status=active" % pid)
            if r.status_code != 200:
                print("version-resolve status:", r.status_code, r.get_data(as_text=True))
                return False
        finally:
            project_versions_db.pop(pid, None)
            projects_db.pop(pid, None)
    return True


def main():
    checks = [
        ("python_compile", check_py_compile),
        ("rendered_js_check", check_rendered_js),
        ("health_and_smoke", check_health_and_smoke),
    ]
    ok = True
    for name, fn in checks:
        try:
            passed = fn()
        except Exception as exc:
            print("[FAIL]", name, exc)
            passed = False
        print("[{}] {}".format("PASS" if passed else "FAIL", name))
        ok = ok and passed
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Walk the live admin portal: every GET route, same-origin link, and safe empty POST."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("PORTAL_BASE") or "http://127.0.0.1:5003"
USER = os.environ.get("PORTAL_USER") or "admin"
PASSWORD = os.environ.get("PORTAL_PASSWORD") or "Portal@2026"
SCOPE = os.environ.get("AUDIT_SCOPE") or "admin"
PROJECT = os.environ.get("PORTAL_PROJECT") or "GomeKu"

SKIP_POST_WORDS = (
    "delete", "remove", "drop", "purge", "reset", "destroy", "trigger",
    "publish", "rollback", "deploy", "start", "stop", "archive", "import",
    "upload", "save", "update", "create", "approve", "reject", "sync",
)


def _opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor())


def _login(opener):
    html = opener.open(BASE + "/login", timeout=20).read().decode("utf-8", "replace")
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html) or re.search(
        r'value="([^"]+)"[^>]*name="csrf_token"', html
    )
    token = match.group(1) if match else ""
    data = urllib.parse.urlencode({"username": USER, "password": PASSWORD, "csrf_token": token}).encode()
    opener.open(urllib.request.Request(BASE + "/login", data=data), timeout=20)


def _get(opener, url):
    req = urllib.request.Request(url, method="GET")
    try:
        resp = opener.open(req, timeout=25)
        body = resp.read(200000)
        return resp.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(80000)


def _routes():
    core = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if core not in sys.path:
        sys.path.insert(0, core)
    import app_new

    found = []
    for rule in app_new.app.url_map.iter_rules():
        methods = rule.methods or set()
        if "GET" not in methods or rule.arguments:
            path = rule.rule
        else:
            path = rule.rule
        if path.startswith("/static") or "logout" in path:
            continue
        if SCOPE == "admin" and not (path.startswith("/admin") or path.startswith("/ops-assets") or path in ("/", "/login", "/forum")):
            continue
        if SCOPE == "api" and not path.startswith("/api"):
            continue
        sample = path
        sample = sample.replace("<project_id>", PROJECT)
        sample = sample.replace("<string:project_id>", PROJECT)
        sample = sample.replace("<env_key>", "development")
        if "<" in sample:
            continue
        found.append((sorted(methods), sample))
    return found


def main() -> int:
    opener = _opener()
    _login(opener)
    rows = []
    seen = set()
    five = []
    for methods, path in _routes():
        if "GET" not in methods:
            continue
        url = BASE + path
        if url in seen:
            continue
        seen.add(url)
        status, body = _get(opener, url)
        text = body.decode("utf-8", "replace")
        bad = status >= 500 or "Traceback (most recent call last)" in text
        rows.append({"method": "GET", "path": path, "status": status, "bad": bad})
        if bad:
            five.append(rows[-1])
    post_bad = []
    post_tried = []
    for methods, path in _routes():
        if "POST" not in methods:
            continue
        lower = path.lower()
        if any(word in lower for word in SKIP_POST_WORDS):
            continue
        url = BASE + path
        req = urllib.request.Request(url, data=b"{}", method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            resp = opener.open(req, timeout=20)
            status, raw = resp.status, resp.read(20000)
        except urllib.error.HTTPError as exc:
            status, raw = exc.code, exc.read(20000)
        text = raw.decode("utf-8", "replace")
        bad = status >= 500 or "Traceback" in text
        post_tried.append({"path": path, "status": status})
        if bad:
            post_bad.append({"method": "POST", "path": path, "status": status})
    report = {
        "get_count": len(rows),
        "gets": rows,
        "get_bad": five,
        "post_probed": post_tried,
        "post_probed_bad": post_bad,
        "status_counts": {},
    }
    for row in rows:
        report["status_counts"][str(row["status"])] = report["status_counts"].get(str(row["status"]), 0) + 1
    out = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "docs", "evidence", "2026-10-28", "portal-function-audit.json")
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps({
        "get_count": report["get_count"],
        "get_bad": len(five),
        "post_bad": len(post_bad),
        "status_counts": report["status_counts"],
        "evidence": out,
    }, ensure_ascii=False))
    for row in rows:
        if row["status"] != 200:
            print("GET", row["status"], row["path"])
    for row in post_bad[:30]:
        print("POST", row["status"], row["path"])
    return 1 if five or post_bad else 0


if __name__ == "__main__":
    sys.exit(main())

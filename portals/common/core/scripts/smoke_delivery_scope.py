# -*- coding: utf-8 -*-
"""Smoke checks for delivery scope + overview channel aggregation."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


def _request(url: str, cookie: str = "", method: str = "GET", body: dict | None = None):
    headers = {"Accept": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, raw, dict(resp.headers)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return exc.code, raw, dict(exc.headers)


def login(base_url: str, username: str, password: str) -> str:
    login_url = f"{base_url.rstrip('/')}/login"
    jar = urllib.request.HTTPCookieProcessor()
    opener = urllib.request.build_opener(jar)
    with opener.open(login_url, timeout=15) as resp:
        page = resp.read().decode("utf-8", errors="replace")
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', page)
    if not match:
        raise RuntimeError("csrf_token not found on login page")
    csrf_token = match.group(1)
    body = urllib.parse.urlencode(
        {"username": username, "password": password, "csrf_token": csrf_token}
    ).encode("utf-8")
    req = urllib.request.Request(
        login_url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with opener.open(req, timeout=15) as resp:
        if resp.status not in (200, 302, 303):
            raise RuntimeError(f"login failed status={resp.status}")
    cookies = []
    for cookie in jar.cookiejar:
        cookies.append(f"{cookie.name}={cookie.value}")
    if not cookies:
        raise RuntimeError("login succeeded but no session cookie")
    return "; ".join(cookies)


def main() -> int:
    parser = argparse.ArgumentParser(description="Delivery scope smoke")
    parser.add_argument("--base-url", default="http://127.0.0.1:5003")
    parser.add_argument("--project-id", default="GomeKu")
    parser.add_argument("--env-key", default="development")
    parser.add_argument("--channel-id", default="1001")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    args = parser.parse_args()

    results: list[tuple[str, bool, str]] = []

    status, raw, headers = _request(
        f"{args.base_url}/api/projects/{args.project_id}/environments/{args.env_key}/delivery-scope"
    )
    unauth_ok = status == 401 and "application/json" in headers.get("Content-Type", "")
    try:
        payload = json.loads(raw)
        unauth_ok = unauth_ok and payload.get("ok") is False and payload.get("error") == "未登录"
    except json.JSONDecodeError:
        unauth_ok = False
    results.append(("API 未登录返回 JSON 401", unauth_ok, f"status={status} body={raw[:120]}"))

    try:
        cookie = login(args.base_url, args.username, args.password)
        scope_status, scope_raw, _ = _request(
            f"{args.base_url}/api/projects/{args.project_id}/environments/{args.env_key}/delivery-scope",
            cookie=cookie,
        )
        scope_payload = json.loads(scope_raw)
        scope_ok = scope_status == 200 and scope_payload.get("ok") is True and scope_payload.get("data")
        results.append(("API 已登录 delivery-scope ok:true", scope_ok, f"status={scope_status}"))

        overview_status, overview_raw, _ = _request(
            f"{args.base_url}/api/projects/{args.project_id}/overview?channel_id={urllib.parse.quote(args.channel_id)}",
            cookie=cookie,
        )
        overview_payload = json.loads(overview_raw)
        overview_ok = overview_status == 200 and overview_payload.get("ok") is True
        env_cards = (overview_payload.get("data") or {}).get("environments") or []
        dev_card = next((c for c in env_cards if c.get("env_key") == args.env_key), None)
        channel_filter_ok = overview_ok and dev_card is not None
        if dev_card:
            channel_filter_ok = channel_filter_ok and isinstance(dev_card.get("delivery_line_count"), int)
        results.append(
            (
                "概览 channel_id 过滤返回环境卡",
                channel_filter_ok,
                f"status={overview_status} dev_lines={dev_card and dev_card.get('delivery_line_count')}",
            )
        )
    except Exception as exc:
        results.append(("登录后 API 验收", False, str(exc)))

    failed = 0
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name} — {detail}")
        if not ok:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""CI gate: Redis-backed session shared across workers (T-C07)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from http.cookiejar import CookieJar

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_CLOSURE = os.environ.get("CLOSURE_MODE", "").strip() in ("1", "true", "yes")


def _probe_redis() -> bool:
    try:
        import redis

        client = redis.from_url(os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"))
        client.ping()
        return True
    except Exception:
        return False


def _check_create_app() -> list[str]:
    errors: list[str] = []
    prev = os.environ.get("SESSION_TYPE")
    os.environ["SESSION_TYPE"] = "redis"
    try:
        from app_new import create_app

        application = create_app()
        if application.config.get("SESSION_TYPE") != "redis":
            errors.append("SESSION_TYPE not redis after create_app")
    except Exception as exc:
        errors.append(f"create_app: {exc}")
    finally:
        if prev is None:
            os.environ.pop("SESSION_TYPE", None)
        else:
            os.environ["SESSION_TYPE"] = prev
    return errors


def _check_session_cookie_across_workers(port: int) -> list[str]:
    errors: list[str] = []
    os.environ["SESSION_TYPE"] = "redis"
    os.environ.setdefault("SECRET_KEY", "closure-gate-secret")
    from app_new import create_app

    app = create_app()
    username = "admin"
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user"] = username
        resp = client.get("/profile")
        if resp.status_code not in (200, 302):
            errors.append(f"test_client profile status {resp.status_code}")
        cookie_header = ""
        for header, value in resp.headers:
            if header.lower() == "set-cookie" and "session=" in value.lower():
                cookie_header = value.split(";")[0]
                break
        if not cookie_header:
            jar = client.get_cookie("session")
            if jar:
                cookie_header = f"session={jar.value}"

    if not cookie_header:
        errors.append("no session cookie from test_client")
        return errors

    base = f"http://127.0.0.1:{port}"
    ok_hits = 0
    for _ in range(6):
        try:
            req = urllib.request.Request(f"{base}/profile", headers={"Cookie": cookie_header})
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read(800).decode("utf-8", errors="ignore")
                if resp.status == 200 and username in body:
                    ok_hits += 1
                elif resp.geturl().endswith("/login"):
                    errors.append("gunicorn redirected to login (session not shared)")
                    break
        except Exception as exc:
            errors.append(f"gunicorn profile probe: {exc}")
            break

    if ok_hits < 3:
        errors.append(f"gunicorn shared session hits={ok_hits}/6 expected>=3")
    return errors


def _check_dual_client_redis_session() -> list[str]:
    """Windows-friendly: two clients share signed session cookie via Redis."""
    errors: list[str] = []
    os.environ["SESSION_TYPE"] = "redis"
    os.environ.setdefault("SECRET_KEY", "closure-gate-secret")
    from app_new import create_app

    app = create_app()
    username = "admin"
    with app.test_client() as client_a:
        with client_a.session_transaction() as sess:
            sess["user"] = username
        first = client_a.get("/profile")
        if first.status_code not in (200, 302):
            errors.append(f"client_a profile status {first.status_code}")
        cookie = client_a.get_cookie("session")
        if not cookie:
            errors.append("no session cookie after client_a")

    if errors:
        return errors

    with app.test_client() as client_b:
        client_b.set_cookie(key="session", value=cookie.value)
        second = client_b.get("/profile")
        if second.status_code == 302 and "/login" in (second.location or ""):
            errors.append("client_b lost redis-backed session")
        elif username not in second.get_data(as_text=True):
            errors.append("client_b profile missing username")

    try:
        import redis

        r = redis.from_url(os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"))
        prefix = os.environ.get("SESSION_KEY_PREFIX", "apk_site:sess:")
        keys = [k for k in r.scan_iter(f"{prefix}*")]
        if not keys:
            errors.append("no redis session keys with expected prefix")
    except Exception as exc:
        errors.append(f"redis key scan: {exc}")
    return errors


def _run_gunicorn_worker_test() -> list[str]:
    if sys.platform == "win32":
        return _check_dual_client_redis_session()
    if os.environ.get("REDIS_SESSION_GATE_SKIP_GUNICORN") == "1":
        return []

    port = int(os.environ.get("REDIS_GATE_TEST_PORT", "18765"))
    env = os.environ.copy()
    env["SESSION_TYPE"] = "redis"
    env.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
    env.setdefault("SECRET_KEY", "closure-gate-secret")
    cmd = [
        sys.executable,
        "-m",
        "gunicorn",
        "-w",
        "2",
        "-b",
        f"127.0.0.1:{port}",
        "--timeout",
        "60",
        "app_new:create_app()",
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    errors: list[str] = []
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        else:
            errors.append("gunicorn health timeout")
            return errors
        errors.extend(_check_session_cookie_across_workers(port))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
    return errors


def main() -> int:
    if os.environ.get("REDIS_SESSION_GATE_SKIP") == "1" and not _CLOSURE:
        print(json.dumps({"ok": True, "skipped": True, "reason": "REDIS_SESSION_GATE_SKIP"}))
        return 0

    if not _probe_redis():
        payload = {"ok": False if _CLOSURE else True, "skipped": not _CLOSURE, "reason": "redis_unreachable"}
        if _CLOSURE:
            payload["errors"] = ["redis unreachable in CLOSURE_MODE"]
        print(json.dumps(payload, ensure_ascii=False))
        return 1 if _CLOSURE else 0

    errors = _check_create_app()
    if not errors:
        try:
            errors.extend(_run_gunicorn_worker_test())
        except Exception as exc:
            errors.append(f"gunicorn test: {exc}")

    ok = not errors
    print(json.dumps({"ok": ok, "errors": errors, "closure": _CLOSURE}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

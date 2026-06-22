# -*- coding: utf-8 -*-
"""Gunicorn + Redis session deployment notes (Wave 3 scaffold)."""

## Goal

Run apk-site admin portal under **gunicorn** with **Redis-backed Flask sessions** so multiple worker processes share login state.

## Prerequisites

- Python 3.10+ with project venv activated
- Redis 6+ reachable from the app host
- `pip install gunicorn redis flask-session`

## Environment variables

| Variable | Example | Purpose |
|----------|---------|---------|
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Session store |
| `SECRET_KEY` | *(random 32+ bytes)* | Flask session signing |
| `SESSION_TYPE` | `redis` | Enables Redis session backend |
| `PORTAL_MODE` | `admin` | Portal entry (`admin` / `player` / `forum`) |
| `USE_SQLITE` | `true` | Keep SQLite primary storage (see `data/_store.py`) |

## Flask session config snippet

```python
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = redis.from_url(os.getenv('REDIS_URL', 'redis://127.0.0.1:6379/0'))
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'apk_site:sess:'
```

## Gunicorn invocation

From `portals/common/core`:

```bash
gunicorn -w 4 -b 0.0.0.0:5003 --timeout 120 "app_new:create_app()"
```

Windows example: see `scripts/run_gunicorn.ps1`.

## Validation checklist

1. Login on worker A; refresh on worker B — session persists.
2. Logout clears Redis key.
3. `data/_store.py` writes remain consistent under concurrent workers (SQLite WAL + short transactions).
4. Ops SSE / long-poll endpoints use sticky sessions or out-of-band pub/sub if added later.

## Rollback

Use existing Waitress entry (`scripts/run_portal_waitress.ps1`) for single-process dev; no Redis required.

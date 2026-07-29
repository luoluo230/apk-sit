# -*- coding: utf-8 -*-
"""Prometheus metrics from release_orders + release_order_events (P2-03 Step 3)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from models.db import _db_lock, _get_conn, init_db


def _escape(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def _decode_json(raw: Any, default=None):
    try:
        return json.loads(raw or "")
    except (TypeError, json.JSONDecodeError):
        return default if default is not None else {}


def collect_release_metrics() -> Dict[str, Any]:
    init_db()
    with _db_lock:
        conn = _get_conn()
        status_rows = conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM release_orders GROUP BY status"
        ).fetchall()
        verify_failures = conn.execute(
            """
            SELECT COUNT(*) FROM release_order_events
            WHERE event_type IN ('verify_failed', 'bootstrap_smoke_failed')
               OR to_status='verify_failed'
            """
        ).fetchone()
        publish_failures = conn.execute(
            """
            SELECT COUNT(*) FROM release_order_events
            WHERE event_type='publish_failed' OR to_status='publish_failed'
            """
        ).fetchone()
        smoke_rows = conn.execute(
            """
            SELECT release_order_id, event_type, created_at, payload
            FROM release_order_events
            WHERE event_type IN ('verify_started', 'verified', 'verify_failed')
            ORDER BY release_order_id, id ASC
            """
        ).fetchall()
    durations = _compute_smoke_durations(smoke_rows)
    return {
        "orders_by_status": {str(row["status"] or "unknown"): int(row["cnt"] or 0) for row in status_rows},
        "verify_failures_total": int(verify_failures[0] if verify_failures else 0),
        "publish_failures_total": int(publish_failures[0] if publish_failures else 0),
        "bootstrap_smoke_durations": durations,
    }


def _compute_smoke_durations(rows: List[Any]) -> List[float]:
    by_order: Dict[str, Dict[str, str]] = {}
    for row in rows:
        oid = str(row["release_order_id"] or "")
        if not oid:
            continue
        bucket = by_order.setdefault(oid, {})
        bucket[str(row["event_type"] or "")] = str(row["created_at"] or "")
    out: List[float] = []
    for timing in by_order.values():
        start = timing.get("verify_started")
        end = timing.get("verified") or timing.get("verify_failed")
        if not start or not end:
            continue
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
            seconds = max(0.0, (end_dt - start_dt).total_seconds())
            out.append(round(seconds, 3))
        except (TypeError, ValueError):
            continue
    return out


def build_release_health_summary(project_id: str, *, days: int = 7) -> Dict[str, Any]:
    init_db()
    cutoff = (datetime.now() - timedelta(days=max(1, days))).isoformat()
    pid = str(project_id or "").strip()
    with _db_lock:
        conn = _get_conn()
        totals = conn.execute(
            """
            SELECT
              SUM(CASE WHEN e.to_status='verified' OR e.event_type='verified' THEN 1 ELSE 0 END) AS verified,
              SUM(CASE WHEN e.to_status='verify_failed' OR e.event_type='verify_failed' THEN 1 ELSE 0 END) AS verify_failed,
              SUM(CASE WHEN e.to_status='publish_failed' OR e.event_type='publish_failed' THEN 1 ELSE 0 END) AS publish_failed
            FROM release_order_events e
            INNER JOIN release_orders o ON o.release_order_id = e.release_order_id
            WHERE o.project_id=? AND e.created_at >= ?
            """,
            (pid, cutoff),
        ).fetchone()
        fail_rows = conn.execute(
            """
            SELECT o.release_order_id, o.env_key, o.version_name, o.version_code, o.platform,
                   e.event_type, e.created_at, e.payload
            FROM release_order_events e
            INNER JOIN release_orders o ON o.release_order_id = e.release_order_id
            WHERE o.project_id=?
              AND e.created_at >= ?
              AND (e.to_status='verify_failed' OR e.event_type IN ('verify_failed', 'publish_failed', 'bootstrap_smoke_failed'))
            ORDER BY e.created_at DESC
            LIMIT 20
            """,
            (pid, cutoff),
        ).fetchall()
    verified = int(totals["verified"] or 0) if totals else 0
    verify_failed = int(totals["verify_failed"] or 0) if totals else 0
    publish_failed = int(totals["publish_failed"] or 0) if totals else 0
    attempts = verified + verify_failed + publish_failed
    success_rate = round((verified / attempts) * 100.0, 1) if attempts else None
    failures: List[Dict[str, Any]] = []
    for row in fail_rows:
        payload = _decode_json(row["payload"], {})
        failures.append(
            {
                "release_order_id": str(row["release_order_id"] or ""),
                "env_key": str(row["env_key"] or ""),
                "version_name": str(row["version_name"] or ""),
                "version_code": str(row["version_code"] or ""),
                "platform": str(row["platform"] or ""),
                "event_type": str(row["event_type"] or ""),
                "created_at": str(row["created_at"] or ""),
                "error": str(payload.get("error") or payload.get("message") or "")[:200],
                "href": f"/admin/projects/{pid}/release-orders/{row['release_order_id']}",
            }
        )
    return {
        "window_days": days,
        "verified_count": verified,
        "verify_failed_count": verify_failed,
        "publish_failed_count": publish_failed,
        "success_rate_pct": success_rate,
        "recent_failures": failures,
    }


def render_prometheus_release_metrics() -> Tuple[str, str]:
    data = collect_release_metrics()
    lines = [
        "# HELP release_orders_total Release orders grouped by terminal/workflow status.",
        "# TYPE release_orders_total gauge",
    ]
    for status, count in sorted(data.get("orders_by_status", {}).items()):
        lines.append(f'release_orders_total{{status="{_escape(status)}"}} {int(count)}')
    lines.extend([
        "# HELP release_verify_failures_total Cumulative verify/smoke failure events.",
        "# TYPE release_verify_failures_total counter",
        f"release_verify_failures_total {int(data.get('verify_failures_total') or 0)}",
        "# HELP release_publish_failures_total Cumulative publish failure events.",
        "# TYPE release_publish_failures_total counter",
        f"release_publish_failures_total {int(data.get('publish_failures_total') or 0)}",
        "# HELP bootstrap_smoke_duration_seconds Observed verify/smoke durations.",
        "# TYPE bootstrap_smoke_duration_seconds summary",
    ])
    durations = list(data.get("bootstrap_smoke_durations") or [])
    if durations:
        total = sum(durations)
        lines.append(f"bootstrap_smoke_duration_seconds_sum {total}")
        lines.append(f"bootstrap_smoke_duration_seconds_count {len(durations)}")
    else:
        lines.append("bootstrap_smoke_duration_seconds_sum 0")
        lines.append("bootstrap_smoke_duration_seconds_count 0")
    return "\n".join(lines) + "\n", "text/plain; version=0.0.4; charset=utf-8"

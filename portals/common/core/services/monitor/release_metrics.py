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


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(ts or "").replace("Z", "+00:00").replace("+00:00", ""))
    except (TypeError, ValueError):
        return None


def _success_rate(verified: int, failed: int) -> float | None:
    attempts = verified + failed
    if not attempts:
        return None
    return round((verified / attempts) * 100.0, 1)


def _compute_client_mttr_minutes(rows: List[Any]) -> float | None:
    """MTTR: failure event → rollback_restored / next verified on same order."""
    by_order: Dict[str, List[tuple[str, str]]] = {}
    for row in rows:
        oid = str(row["release_order_id"] or "")
        if not oid:
            continue
        by_order.setdefault(oid, []).append((str(row["event_type"] or ""), str(row["created_at"] or "")))

    durations: List[float] = []
    for events in by_order.values():
        failure_at: datetime | None = None
        for event_type, created_at in events:
            if event_type in {"verify_failed", "publish_failed", "bootstrap_smoke_failed"}:
                failure_at = _parse_iso(created_at)
                continue
            if failure_at and event_type in {"rollback_restored", "verified"}:
                recovered = _parse_iso(created_at)
                if recovered and recovered >= failure_at:
                    durations.append(max(0.0, (recovered - failure_at).total_seconds() / 60.0))
                failure_at = None
    if not durations:
        return None
    return round(sum(durations) / len(durations), 1)


def _server_plane_summary(conn, project_id: str, cutoff: str) -> Dict[str, Any]:
    pid = str(project_id or "").strip()
    totals = conn.execute(
        """
        SELECT
          SUM(CASE WHEN status='deployed' THEN 1 ELSE 0 END) AS deployed,
          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
          SUM(CASE WHEN status='deploying' THEN 1 ELSE 0 END) AS deploying
        FROM server_release_orders
        WHERE project_id=? AND updated_at >= ?
        """,
        (pid, cutoff),
    ).fetchone()
    deployed = int(totals["deployed"] or 0) if totals else 0
    failed = int(totals["failed"] or 0) if totals else 0
    deploying = int(totals["deploying"] or 0) if totals else 0
    return {
        "deployed_count": deployed,
        "failed_count": failed,
        "deploying_count": deploying,
        "success_rate_pct": _success_rate(deployed, failed),
    }


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
        mttr_rows = conn.execute(
            """
            SELECT e.release_order_id, e.event_type, e.created_at
            FROM release_order_events e
            INNER JOIN release_orders o ON o.release_order_id = e.release_order_id
            WHERE o.project_id=? AND e.created_at >= ?
              AND e.event_type IN ('verify_failed', 'publish_failed', 'bootstrap_smoke_failed', 'rollback_restored', 'verified')
            ORDER BY e.release_order_id, e.id ASC
            """,
            (pid, cutoff),
        ).fetchall()
        env_rows = conn.execute(
            """
            SELECT o.env_key,
              SUM(CASE WHEN e.to_status='verified' OR e.event_type='verified' THEN 1 ELSE 0 END) AS verified,
              SUM(CASE WHEN e.to_status='verify_failed' OR e.event_type='verify_failed' THEN 1 ELSE 0 END) AS verify_failed,
              SUM(CASE WHEN e.to_status='publish_failed' OR e.event_type='publish_failed' THEN 1 ELSE 0 END) AS publish_failed
            FROM release_order_events e
            INNER JOIN release_orders o ON o.release_order_id = e.release_order_id
            WHERE o.project_id=? AND e.created_at >= ?
            GROUP BY o.env_key
            """,
            (pid, cutoff),
        ).fetchall()
        platform_rows = conn.execute(
            """
            SELECT o.platform,
              SUM(CASE WHEN e.to_status='verified' OR e.event_type='verified' THEN 1 ELSE 0 END) AS verified,
              SUM(CASE WHEN e.to_status='verify_failed' OR e.event_type='verify_failed' THEN 1 ELSE 0 END) AS verify_failed,
              SUM(CASE WHEN e.to_status='publish_failed' OR e.event_type='publish_failed' THEN 1 ELSE 0 END) AS publish_failed
            FROM release_order_events e
            INNER JOIN release_orders o ON o.release_order_id = e.release_order_id
            WHERE o.project_id=? AND e.created_at >= ?
            GROUP BY o.platform
            """,
            (pid, cutoff),
        ).fetchall()
        server_env_rows = conn.execute(
            """
            SELECT env_key,
              SUM(CASE WHEN status='deployed' THEN 1 ELSE 0 END) AS deployed,
              SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed
            FROM server_release_orders
            WHERE project_id=? AND updated_at >= ?
            GROUP BY env_key
            """,
            (pid, cutoff),
        ).fetchall()
        client_daily = conn.execute(
            """
            SELECT substr(e.created_at, 1, 10) AS day,
              SUM(CASE WHEN e.event_type='verified' OR e.to_status='verified' THEN 1 ELSE 0 END) AS verified,
              SUM(CASE WHEN e.event_type IN ('verify_failed', 'publish_failed', 'bootstrap_smoke_failed') OR e.to_status IN ('verify_failed', 'publish_failed') THEN 1 ELSE 0 END) AS failed
            FROM release_order_events e
            INNER JOIN release_orders o ON o.release_order_id = e.release_order_id
            WHERE o.project_id=? AND e.created_at >= ?
            GROUP BY day
            ORDER BY day ASC
            """,
            (pid, cutoff),
        ).fetchall()
        server_daily = conn.execute(
            """
            SELECT substr(updated_at, 1, 10) AS day,
              SUM(CASE WHEN status='deployed' THEN 1 ELSE 0 END) AS deployed,
              SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed
            FROM server_release_orders
            WHERE project_id=? AND updated_at >= ?
            GROUP BY day
            ORDER BY day ASC
            """,
            (pid, cutoff),
        ).fetchall()
        server_summary = _server_plane_summary(conn, pid, cutoff)
    verified = int(totals["verified"] or 0) if totals else 0
    verify_failed = int(totals["verify_failed"] or 0) if totals else 0
    publish_failed = int(totals["publish_failed"] or 0) if totals else 0
    client_failed = verify_failed + publish_failed
    client_success_rate = _success_rate(verified, client_failed)
    mttr_minutes = _compute_client_mttr_minutes(list(mttr_rows))

    server_by_env = {
        str(row["env_key"] or ""): {
            "deployed_count": int(row["deployed"] or 0),
            "failed_count": int(row["failed"] or 0),
            "success_rate_pct": _success_rate(int(row["deployed"] or 0), int(row["failed"] or 0)),
        }
        for row in server_env_rows
    }
    by_env: List[Dict[str, Any]] = []
    env_keys = sorted({str(row["env_key"] or "") for row in env_rows} | set(server_by_env.keys()))
    for env_key in env_keys:
        if not env_key:
            continue
        client_row = next((r for r in env_rows if str(r["env_key"] or "") == env_key), None)
        c_verified = int(client_row["verified"] or 0) if client_row else 0
        c_failed = int((client_row["verify_failed"] or 0) if client_row else 0) + int((client_row["publish_failed"] or 0) if client_row else 0)
        srv = server_by_env.get(env_key) or {"deployed_count": 0, "failed_count": 0, "success_rate_pct": None}
        by_env.append(
            {
                "env_key": env_key,
                "client_success_rate_pct": _success_rate(c_verified, c_failed),
                "client_verified_count": c_verified,
                "client_failed_count": c_failed,
                "server_success_rate_pct": srv.get("success_rate_pct"),
                "server_deployed_count": srv.get("deployed_count", 0),
                "server_failed_count": srv.get("failed_count", 0),
            }
        )

    by_platform: List[Dict[str, Any]] = []
    for row in platform_rows:
        platform = str(row["platform"] or "") or "unknown"
        c_verified = int(row["verified"] or 0)
        c_failed = int(row["verify_failed"] or 0) + int(row["publish_failed"] or 0)
        by_platform.append(
            {
                "platform": platform,
                "client_success_rate_pct": _success_rate(c_verified, c_failed),
                "client_verified_count": c_verified,
                "client_failed_count": c_failed,
            }
        )

    server_daily_map = {
        str(row["day"] or ""): {
            "server_deployed": int(row["deployed"] or 0),
            "server_failed": int(row["failed"] or 0),
        }
        for row in server_daily
    }
    daily_trend: List[Dict[str, Any]] = []
    for row in client_daily:
        day = str(row["day"] or "")
        srv = server_daily_map.get(day) or {}
        daily_trend.append(
            {
                "date": day,
                "client_verified": int(row["verified"] or 0),
                "client_failed": int(row["failed"] or 0),
                "server_deployed": int(srv.get("server_deployed") or 0),
                "server_failed": int(srv.get("server_failed") or 0),
            }
        )
    for day, srv in server_daily_map.items():
        if day and not any(item["date"] == day for item in daily_trend):
            daily_trend.append(
                {
                    "date": day,
                    "client_verified": 0,
                    "client_failed": 0,
                    "server_deployed": int(srv.get("server_deployed") or 0),
                    "server_failed": int(srv.get("server_failed") or 0),
                }
            )
    daily_trend.sort(key=lambda item: str(item.get("date") or ""))

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
        "success_rate_pct": client_success_rate,
        "client": {
            "verified_count": verified,
            "verify_failed_count": verify_failed,
            "publish_failed_count": publish_failed,
            "success_rate_pct": client_success_rate,
        },
        "server": server_summary,
        "mttr_minutes": mttr_minutes,
        "by_env": by_env,
        "by_platform": by_platform,
        "daily_trend": daily_trend,
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

# -*- coding: utf-8 -*-
"""Prometheus-style metrics for apk-site release gates."""

from __future__ import annotations

from threading import Lock
from typing import Dict, Tuple

_lock = Lock()
_gate_pass_total: Dict[str, int] = {}
_gate_fail_total: Dict[str, int] = {}
_telemetry_ingest_total = 0


def increment_telemetry_ingest() -> None:
    global _telemetry_ingest_total
    with _lock:
        _telemetry_ingest_total += 1


def increment_gate_pass(gate_name: str, passed: bool = True) -> None:
    key = str(gate_name or "unknown").strip() or "unknown"
    with _lock:
        bucket = _gate_pass_total if passed else _gate_fail_total
        bucket[key] = int(bucket.get(key, 0)) + 1


def render_prometheus() -> Tuple[str, str]:
    lines = [
        "# HELP apk_site_gate_pass_total Release/bootstrap gate pass count by gate name.",
        "# TYPE apk_site_gate_pass_total counter",
    ]
    with _lock:
        for name, value in sorted(_gate_pass_total.items()):
            lines.append(f'apk_site_gate_pass_total{{gate="{_escape(name)}",result="pass"}} {value}')
        for name, value in sorted(_gate_fail_total.items()):
            lines.append(f'apk_site_gate_pass_total{{gate="{_escape(name)}",result="fail"}} {value}')
        lines.extend([
            "# HELP apk_site_telemetry_ingest_total Client telemetry samples ingested.",
            "# TYPE apk_site_telemetry_ingest_total counter",
            f"apk_site_telemetry_ingest_total {_telemetry_ingest_total}",
        ])
    return "\n".join(lines) + "\n", "text/plain; version=0.0.4; charset=utf-8"


def _escape(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')

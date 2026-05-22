# -*- coding: utf-8 -*-
"""性能监控（请求耗时、QPS）"""

import time
from collections import deque
from threading import Lock

_timings = deque(maxlen=200)
_lock = Lock()
_start = None


def record_request_start():
    return time.time()


def record_request_end(path, start_time, status):
    duration = time.time() - start_time
    with _lock:
        _timings.append({'path': path, 'duration': duration, 'status': status})
    return duration


def get_stats():
    with _lock:
        items = list(_timings)
    if not items:
        return {'count': 0, 'p95_ms': 0, 'avg_ms': 0}
    durations = sorted([x['duration'] * 1000 for x in items], reverse=True)
    n = len(durations)
    p95_idx = max(0, int(n * 0.05) - 1)
    p95 = durations[p95_idx]
    avg = sum(durations) / n
    return {'count': n, 'p95_ms': round(p95, 1), 'avg_ms': round(avg, 1)}

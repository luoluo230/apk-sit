"""Audit filter/export service."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Dict, List, Tuple

from repositories.admin import audit_repo


def filter_entries(entries: List[Dict[str, Any]], user_filter: str, action_filter: str, date_from: str, date_to: str, keyword: str = "") -> List[Dict[str, Any]]:
    out = entries
    if user_filter:
        out = [e for e in out if (e.get("user") or "").strip() == user_filter.strip()]
    if action_filter:
        out = [e for e in out if (e.get("action") or "").strip() == action_filter.strip()]
    if date_from:
        out = [e for e in out if (e.get("timestamp") or "")[:10] >= date_from]
    if date_to:
        out = [e for e in out if (e.get("timestamp") or "")[:10] <= date_to]
    if keyword and keyword.strip():
        kw = keyword.strip().lower()
        out = [e for e in out if kw in ((e.get("user") or "") + (e.get("action") or "") + str(e.get("details") or "") + (e.get("ip") or "")).lower()]
    return out


def query_entries(user_filter: str, action_filter: str, date_from: str, date_to: str, keyword: str = "") -> List[Dict[str, Any]]:
    entries = list(reversed(audit_repo.list_entries()))
    return filter_entries(entries, user_filter, action_filter, date_from, date_to, keyword)


def export_csv(user_filter: str, action_filter: str, date_from: str, date_to: str, keyword: str = "") -> Tuple[bytes, str]:
    entries = query_entries(user_filter, action_filter, date_from, date_to, keyword)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["时间", "用户", "操作", "详情", "IP"])
    for e in entries:
        w.writerow([
            (e.get("timestamp") or "")[:19],
            e.get("user") or "",
            e.get("action") or "",
            e.get("details") or "",
            e.get("ip") or "",
        ])
    data = buf.getvalue().encode("utf-8-sig")
    fn = "audit_log_" + datetime.now().strftime("%Y%m%d_%H%M") + ".csv"
    return data, fn

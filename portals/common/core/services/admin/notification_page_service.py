"""Notification page data builder."""

from __future__ import annotations

import html
from typing import Any, Dict, List

from services.admin import notification_service


NOTIFICATION_TYPE_LABELS = {
    "task_assign": "任务分配",
    "task_comment": "任务评论",
    "approval_result": "审批结果",
    "build_done": "构建完成",
    "announcement": "系统公告",
    "": "全部",
}


def build_notifications_view_model(username: str, type_filter: str) -> Dict[str, Any]:
    payload, _status = notification_service.list_user_notifications(username, type_filter, limit=200)
    items = ((payload or {}).get("data") or {}).get("notifications") or (payload or {}).get("notifications") or []

    type_options = "".join(
        f'<option value="{value}"' + (" selected" if value == type_filter else "") + f">{label}</option>"
        for value, label in NOTIFICATION_TYPE_LABELS.items()
    )
    rows = _build_rows(items)
    rows_html = (
        "".join(rows)
        if rows
        else (
            '<tr><td colspan="4"><div class="pm-placeholder-page">'
            "<h2>暂无通知</h2><p>有任务分配、审批结果或构建完成时会出现在这里。</p>"
            '<a class="pm-btn" href="/admin">返回工作台</a></div></td></tr>'
        )
    )
    return {"type_options": type_options, "rows_html": rows_html}


def _build_rows(items: List[Dict[str, Any]]) -> List[str]:
    rows: List[str] = []
    for item in items:
        ntype = item.get("type") or ""
        label = NOTIFICATION_TYPE_LABELS.get(ntype, ntype)
        read_at = item.get("read_at")
        row_cls = "is-unread" if not read_at else ""
        link = (item.get("link") or "").strip()
        title_esc = html.escape(item.get("title") or "")
        time_esc = (item.get("created_at") or "")[:19].replace("T", " ")
        nid = item.get("id") or ""
        if link:
            title_cell = f'<a href="{html.escape(link)}">{title_esc}</a>'
        else:
            title_cell = f"<span>{title_esc}</span>"
        button = ""
        if not read_at:
            button = (
                f'<button type="button" class="pm-btn pm-btn--compact" '
                f"onclick=\"markRead('{nid}')\">标为已读</button>"
            )
        rows.append(
            f'<tr class="{row_cls}"><td>{time_esc}</td>'
            f'<td><span class="pm-tag pm-tag--muted">{html.escape(label)}</span></td>'
            f"<td>{title_cell}</td><td>{button}</td></tr>"
        )
    return rows

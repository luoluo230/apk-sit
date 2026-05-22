"""Task API service."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any, Dict, Tuple

from repositories.admin import tasks_repo

TASK_STATUSES = [
    ("abandoned", "已作废"),
    ("not_started", "尚未开始"),
    ("in_progress", "进行中"),
    ("pending_review", "待验收"),
    ("review_passed", "验收通过"),
    ("review_failed", "验收未通过"),
    ("done", "已完成"),
]


def _role_to_first_assignee(project_id, role):
    proj = tasks_repo.get_project(project_id) or {}
    mr = proj.get("member_roles") or {}
    for u, r in mr.items():
        if r == role:
            return u
    return list(mr.keys())[0] if mr else ""


def list_tasks(project_id: str, username: str) -> Tuple[Dict[str, Any], int]:
    if not tasks_repo.has_project(project_id) or not tasks_repo.can_view(project_id, username):
        return {"error": "无权限"}, 403

    tasks = tasks_repo.list_tasks(project_id)
    proj = tasks_repo.get_project(project_id) or {}
    editors = proj.get("editors") or []
    member_roles = proj.get("member_roles") or {}
    participants = [{"user": u, "role": member_roles.get(u, "其他")} for u in editors]

    now = datetime.now()
    stats = {
        "total": len(tasks),
        "abandoned": 0,
        "not_started": 0,
        "in_progress": 0,
        "pending_review": 0,
        "review_passed": 0,
        "review_failed": 0,
        "done": 0,
        "overdue": 0,
        "soon_overdue": 0,
    }
    soon_days = 3
    out = []
    for t in tasks:
        t = dict(t)
        try:
            u = int(t.get("urgency", 1))
            t["urgency"] = max(1, min(5, u))
        except (TypeError, ValueError):
            t["urgency"] = 1
        if not t.get("current_assignee") and t.get("current_role"):
            t["current_assignee"] = _role_to_first_assignee(project_id, t.get("current_role"))
        t["can_delete"] = t.get("created_by") == username
        cur = t.get("current_assignee") or _role_to_first_assignee(project_id, t.get("current_role"))
        t["can_edit"] = username in editors
        t["can_edit_status_assignee"] = t.get("created_by") == username or cur == username
        t["flow_log"] = t.get("flow_log") or t.get("flow_history") or []
        if t.get("flow_history") and not t.get("flow_log"):
            t["flow_log"] = [{"from_user": e.get("from_role", ""), "to_user": e.get("to_role", ""), "at": e.get("at", ""), "by": e.get("by", "")} for e in (t.get("flow_history") or [])]
        out.append(t)

        s = t.get("status", "open")
        if s in stats:
            stats[s] += 1
        else:
            stats["in_progress"] += 1
        et = t.get("end_time")
        if et and s not in ("done", "abandoned"):
            try:
                dt = datetime.strptime(et[:10], "%Y-%m-%d")
                if dt < now:
                    stats["overdue"] += 1
                elif (dt - now).days <= soon_days:
                    stats["soon_overdue"] += 1
            except Exception:
                pass

    return {"tasks": out, "my_username": username, "participants": participants, "stats": stats}, 200


def create_task(project_id: str, username: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if not tasks_repo.has_project(project_id) or not tasks_repo.can_edit(project_id, username):
        return {"error": "无权限"}, 403

    title = (data.get("title") or "").strip()
    assign_to_user = (data.get("assign_to_user") or "").strip()
    if not title:
        return {"error": "任务名称不能为空"}, 400

    proj = tasks_repo.get_project(project_id) or {}
    editors = proj.get("editors") or []
    if assign_to_user and assign_to_user not in editors:
        return {"error": "流转对象必须是项目参与人"}, 400
    if not assign_to_user and editors:
        assign_to_user = editors[0]
    elif not assign_to_user:
        assign_to_user = username

    now_iso = datetime.now().isoformat()
    task_id = secrets.token_hex(8)
    attachments = data.get("attachments")
    if not isinstance(attachments, list):
        attachments = []
    attachments = [{"name": str(a.get("name", "")), "url": str(a.get("url", ""))} for a in attachments if a.get("url")]

    urgency = int(data.get("urgency", 1))
    if urgency < 1 or urgency > 5:
        urgency = 1

    task = {
        "id": task_id,
        "title": title,
        "content": (data.get("content") or "").strip(),
        "start_time": (data.get("start_time") or "").strip(),
        "end_time": (data.get("end_time") or "").strip(),
        "created_by": username,
        "created_at": now_iso,
        "current_assignee": assign_to_user,
        "status": "not_started",
        "urgency": urgency,
        "flow_log": [{"from_user": username, "to_user": assign_to_user, "status": "not_started", "at": now_iso, "by": username}],
        "comments": [],
        "attachments": attachments,
    }

    rows = tasks_repo.list_tasks(project_id)
    rows.append(task)
    tasks_repo.save_tasks(project_id, rows)
    tasks_repo.audit("create_task", "%s %s" % (project_id, task_id))
    return {"success": True, "task_id": task_id}, 200


def handoff_task(project_id: str, task_id: str, username: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if not tasks_repo.has_project(project_id) or not tasks_repo.can_view(project_id, username):
        return {"error": "无权限"}, 403

    rows = tasks_repo.list_tasks(project_id)
    task = next((t for t in rows if t.get("id") == task_id), None)
    cur = task.get("current_assignee") or (_role_to_first_assignee(project_id, task.get("current_role")) if task else "")
    if not task or cur != username:
        return {"error": "只能流转当前分配给自己的任务"}, 403

    to_user = (data.get("passed_to_user") or "").strip()
    proj = tasks_repo.get_project(project_id) or {}
    editors = proj.get("editors") or []
    if to_user not in editors:
        return {"error": "流转对象必须是项目参与人"}, 400

    now_iso = datetime.now().isoformat()
    task["flow_log"] = task.get("flow_log") or task.get("flow_history") or []
    task["flow_log"].append({"from_user": username, "to_user": to_user, "status": task.get("status", ""), "at": now_iso, "by": username})
    task["current_assignee"] = to_user
    tasks_repo.save_tasks(project_id, rows)
    tasks_repo.audit("task_handoff", "%s %s -> %s" % (project_id, task_id, to_user))
    return {"success": True}, 200


def update_task_status(project_id: str, task_id: str, username: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if not tasks_repo.has_project(project_id) or not tasks_repo.can_view(project_id, username):
        return {"error": "无权限"}, 403

    rows = tasks_repo.list_tasks(project_id)
    task = next((t for t in rows if t.get("id") == task_id), None)
    cur = task.get("current_assignee") or (_role_to_first_assignee(project_id, task.get("current_role")) if task else "")
    if not task or cur != username:
        return {"error": "只能修改分配给自己的任务状态"}, 403

    status = (data.get("status") or "").strip()
    valid = [s[0] for s in TASK_STATUSES]
    if status not in valid:
        return {"error": "无效状态"}, 400

    task["status"] = status
    tasks_repo.save_tasks(project_id, rows)
    tasks_repo.audit("task_update_status", "%s %s -> %s" % (project_id, task_id, status))
    return {"success": True}, 200


def comment_task(project_id: str, task_id: str, username: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if not tasks_repo.has_project(project_id) or not tasks_repo.can_view(project_id, username):
        return {"error": "无权限"}, 403

    proj = tasks_repo.get_project(project_id) or {}
    editors = proj.get("editors") or []
    if username not in editors:
        return {"error": "仅项目参与人可评论"}, 403

    content = (data.get("content") or "").strip()
    if not content:
        return {"error": "评论内容不能为空"}, 400

    rows = tasks_repo.list_tasks(project_id)
    task = next((t for t in rows if t.get("id") == task_id), None)
    if not task:
        return {"error": "任务不存在"}, 404

    now_iso = datetime.now().isoformat()
    task["comments"] = task.get("comments") or []
    task["comments"].append({"user": username, "content": content, "at": now_iso})
    tasks_repo.save_tasks(project_id, rows)
    return {"success": True, "user": username, "at": now_iso}, 200


def update_task(project_id: str, task_id: str, username: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if not tasks_repo.has_project(project_id) or not tasks_repo.can_view(project_id, username):
        return {"error": "无权限"}, 403

    proj = tasks_repo.get_project(project_id) or {}
    editors = proj.get("editors") or []
    if username not in editors:
        return {"error": "仅项目参与人可编辑任务"}, 403

    rows = tasks_repo.list_tasks(project_id)
    task = next((t for t in rows if t.get("id") == task_id), None)
    if not task:
        return {"error": "任务不存在"}, 404

    cur = task.get("current_assignee") or _role_to_first_assignee(project_id, task.get("current_role"))
    can_edit_status_assignee = task.get("created_by") == username or cur == username

    if data.get("title") is not None:
        task["title"] = (data.get("title") or "").strip()
    if data.get("content") is not None:
        task["content"] = (data.get("content") or "").strip()
    if data.get("start_time") is not None:
        task["start_time"] = (data.get("start_time") or "").strip()
    if data.get("end_time") is not None:
        task["end_time"] = (data.get("end_time") or "").strip()
    if data.get("urgency") is not None:
        u = int(data.get("urgency", 1))
        task["urgency"] = max(1, min(5, u))
    elif "urgency" not in task:
        task["urgency"] = 1
    if isinstance(data.get("attachments"), list):
        task["attachments"] = [{"name": str(a.get("name", "")), "url": str(a.get("url", ""))} for a in data["attachments"] if a.get("url")]

    if can_edit_status_assignee:
        if data.get("status") is not None:
            s = (data.get("status") or "").strip()
            if s in [x[0] for x in TASK_STATUSES]:
                task["status"] = s
        if data.get("current_assignee") is not None:
            to_user = (data.get("current_assignee") or "").strip()
            if to_user in editors and to_user != task.get("current_assignee"):
                task["flow_log"] = task.get("flow_log") or []
                task["flow_log"].append({"from_user": task.get("current_assignee") or username, "to_user": to_user, "status": task.get("status", ""), "at": datetime.now().isoformat(), "by": username})
                task["current_assignee"] = to_user

    tasks_repo.save_tasks(project_id, rows)
    tasks_repo.audit("task_update", "%s %s" % (project_id, task_id))
    return {"success": True}, 200


def delete_task(project_id: str, task_id: str, username: str) -> Tuple[Dict[str, Any], int]:
    if not tasks_repo.has_project(project_id) or not tasks_repo.can_view(project_id, username):
        return {"error": "无权限"}, 403

    rows = tasks_repo.list_tasks(project_id)
    task = next((t for t in rows if t.get("id") == task_id), None)
    if not task:
        return {"error": "任务不存在"}, 404
    if task.get("created_by") != username:
        return {"error": "仅创建者可删除任务"}, 403

    tasks_repo.save_tasks(project_id, [t for t in rows if t.get("id") != task_id])
    tasks_repo.audit("task_delete", "%s %s" % (project_id, task_id))
    return {"success": True}, 200


def batch_delete_tasks(project_id: str, username: str, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    if not tasks_repo.has_project(project_id) or not tasks_repo.can_view(project_id, username):
        return {"error": "无权限"}, 403

    ids = list(set(data.get("task_ids") or []))
    if not ids:
        return {"error": "未选择任务"}, 400

    rows = tasks_repo.list_tasks(project_id)
    kept = [t for t in rows if t.get("id") not in ids or t.get("created_by") != username]
    removed = [t for t in rows if t.get("id") in ids and t.get("created_by") == username]
    if len(removed) < len(ids):
        return {"error": "只能删除自己创建的任务，部分任务无法删除"}, 403

    tasks_repo.save_tasks(project_id, kept)
    tasks_repo.audit("task_batch_delete", "%s %s" % (project_id, ",".join(ids)))
    return {"success": True}, 200

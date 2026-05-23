"""Admin tasks route adapters."""

from __future__ import annotations

from flask import jsonify, request

from models.data import project_tasks_db, projects_db, set_task_plan
from services.authz import admin_required
from services.admin import task_service


def tasks_list_response(project_id: str, username: str):
    payload, status = task_service.list_tasks(project_id, username)
    return jsonify(payload), status


def tasks_create_response(project_id: str, username: str):
    payload, status = task_service.create_task(project_id, username, request.get_json(force=True, silent=True) or {})
    return jsonify(payload), status


def tasks_handoff_response(project_id: str, task_id: str, username: str):
    payload, status = task_service.handoff_task(project_id, task_id, username, request.get_json(force=True, silent=True) or {})
    return jsonify(payload), status


def tasks_update_status_response(project_id: str, task_id: str, username: str):
    payload, status = task_service.update_task_status(project_id, task_id, username, request.get_json(force=True, silent=True) or {})
    return jsonify(payload), status


def tasks_comment_response(project_id: str, task_id: str, username: str):
    payload, status = task_service.comment_task(project_id, task_id, username, request.get_json(force=True, silent=True) or {})
    return jsonify(payload), status


def tasks_update_response(project_id: str, task_id: str, username: str):
    payload, status = task_service.update_task(project_id, task_id, username, request.get_json(force=True, silent=True) or {})
    return jsonify(payload), status


def tasks_delete_response(project_id: str, task_id: str, username: str):
    payload, status = task_service.delete_task(project_id, task_id, username)
    return jsonify(payload), status


def tasks_batch_delete_response(project_id: str, username: str):
    payload, status = task_service.batch_delete_tasks(project_id, username, request.get_json(force=True, silent=True) or {})
    return jsonify(payload), status


def _role_to_first_assignee(project_id: str, role: str):
    proj = projects_db.get(project_id) or {}
    member_roles = proj.get("member_roles") or {}
    for user, val in member_roles.items():
        if val == role:
            return user
    return list(member_roles.keys())[0] if member_roles else ""


def my_tasks_set_plan_response(current_username: str):
    data = request.get_json(silent=True) or {}
    project_id = data.get("project_id") or ""
    task_id = data.get("task_id") or ""
    plan_type = data.get("plan_type") or ""
    if not project_id or not task_id:
        return jsonify({"error": "缺少 project_id 或 task_id"}), 400
    valid_plans = {"today_todo", "today_done", "tomorrow_plan", "backlog"}
    if plan_type and plan_type not in valid_plans:
        return jsonify({"error": "无效的规划类型"}), 400
    if project_id not in project_tasks_db:
        return jsonify({"error": "项目不存在"}), 404
    tasks = project_tasks_db[project_id]
    task = next((t for t in tasks if t.get("id") == task_id), None)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    cur = task.get("current_assignee") or (_role_to_first_assignee(project_id, task.get("current_role")) if task.get("current_role") else "")
    if cur != current_username:
        return jsonify({"error": "只能设置自己负责任务的规划"}), 403
    set_task_plan(current_username, project_id, task_id, plan_type)
    return jsonify({"ok": True})


def register_routes(bp, current_username_getter):
    @admin_required("projects")
    def _tasks_list(project_id: str):
        return tasks_list_response(project_id, current_username_getter())

    @admin_required("projects")
    def _task_create(project_id: str):
        return tasks_create_response(project_id, current_username_getter())

    @admin_required("projects")
    def _task_handoff(project_id: str, task_id: str):
        return tasks_handoff_response(project_id, task_id, current_username_getter())

    @admin_required("projects")
    def _task_update_status(project_id: str, task_id: str):
        return tasks_update_status_response(project_id, task_id, current_username_getter())

    @admin_required("projects")
    def _task_comment(project_id: str, task_id: str):
        return tasks_comment_response(project_id, task_id, current_username_getter())

    @admin_required("projects")
    def _task_update(project_id: str, task_id: str):
        return tasks_update_response(project_id, task_id, current_username_getter())

    @admin_required("projects")
    def _task_delete(project_id: str, task_id: str):
        return tasks_delete_response(project_id, task_id, current_username_getter())

    @admin_required("projects")
    def _tasks_batch_delete(project_id: str):
        return tasks_batch_delete_response(project_id, current_username_getter())

    @admin_required("projects")
    def _my_tasks_set_plan():
        return my_tasks_set_plan_response(current_username_getter())

    bp.add_url_rule("/admin/projects/<project_id>/tasks/list", endpoint="project_tasks_list", view_func=_tasks_list)
    bp.add_url_rule(
        "/admin/projects/<project_id>/tasks/create",
        endpoint="project_task_create",
        view_func=_task_create,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/tasks/<task_id>/handoff",
        endpoint="project_task_handoff",
        view_func=_task_handoff,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/tasks/<task_id>/update-status",
        endpoint="project_task_update_status",
        view_func=_task_update_status,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/tasks/<task_id>/comment",
        endpoint="project_task_comment",
        view_func=_task_comment,
        methods=["POST"],
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/tasks/<task_id>",
        endpoint="project_task_update",
        view_func=_task_update,
        methods=["PUT"],
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/tasks/<task_id>",
        endpoint="project_task_delete",
        view_func=_task_delete,
        methods=["DELETE"],
    )
    bp.add_url_rule(
        "/admin/projects/<project_id>/tasks/batch-delete",
        endpoint="project_tasks_batch_delete",
        view_func=_tasks_batch_delete,
        methods=["POST"],
    )
    bp.add_url_rule("/admin/my-tasks/set-plan", endpoint="my_tasks_set_plan", view_func=_my_tasks_set_plan, methods=["POST"])

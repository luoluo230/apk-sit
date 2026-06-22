# -*- coding: utf-8 -*-
"""System configuration and user task plans."""

from datetime import datetime

from flask import session

from data._store import (
    SYSTEM_CONFIG_FILE,
    USER_TASK_PLANS_FILE,
    load_document,
    save_document,
)

system_config_db = load_document(SYSTEM_CONFIG_FILE, {})
user_task_plans_db = load_document(USER_TASK_PLANS_FILE, {})


def save_system_config():
    save_document(SYSTEM_CONFIG_FILE, system_config_db)


def save_user_task_plans():
    save_document(USER_TASK_PLANS_FILE, user_task_plans_db)


def get_system_config(key, default=None):
    """读取系统配置项。"""
    item = system_config_db.get(key)
    if not item or not isinstance(item, dict):
        return default
    return item.get('value', default)


def set_system_config(key, value, value_type='string', description='', username=''):
    """写入系统配置项。"""
    system_config_db[key] = {
        'value': value,
        'type': value_type,
        'description': description,
        'updated_at': datetime.now().isoformat(),
        'updated_by': username or session.get('user', ''),
    }
    save_system_config()


def get_task_plan_key(project_id, task_id):
    return '%s:%s' % (project_id or '', task_id or '')


def set_task_plan(username, project_id, task_id, plan_type):
    """设置任务规划类型：today_todo, today_done, tomorrow_plan, backlog"""
    if not username:
        return
    plans = user_task_plans_db.get(username) or {}
    key = get_task_plan_key(project_id, task_id)
    if plan_type:
        plans[key] = plan_type
    else:
        plans.pop(key, None)
    user_task_plans_db[username] = plans
    save_user_task_plans()


def get_task_plan(username, project_id, task_id):
    """获取任务规划类型"""
    plans = user_task_plans_db.get(username) or {}
    return plans.get(get_task_plan_key(project_id, task_id), '')

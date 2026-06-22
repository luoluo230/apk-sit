# -*- coding: utf-8 -*-
"""Approval workflow."""

import uuid
from datetime import datetime

from data._store import APPROVALS_FILE, APPROVAL_RECORDS_FILE, load_document, save_document
from data.projects import resolve_project_id
from repositories.admin import users_repo as _users_repo


def _user_role(username: str) -> str:
    row = _users_repo.get_user(username) or {}
    return str(row.get("role") or "user")

approvals_db = load_document(APPROVALS_FILE, [])
approval_records_db = load_document(APPROVAL_RECORDS_FILE, {})

APPROVAL_TYPES = [
    ('version_publish', '版本发布'),
    ('delete_project', '删除项目'),
    ('delete_version', '删除版本'),
    ('delete_jenkins', '删除 Jenkins 实例'),
    ('batch_delete_tasks', '批量删除任务'),
    ('news_publish', '新闻发布'),
    ('welfare_publish', '福利发布'),
    ('forum_post_publish', '官方帖子发布'),
    ('gm_ops_action', '运维高危动作'),
]


def save_approvals():
    save_document(APPROVALS_FILE, approvals_db)


def save_approval_records():
    save_document(APPROVAL_RECORDS_FILE, approval_records_db)


def get_approved_approval(atype, target_id):
    """获取已通过的审批单（用于高危操作前置校验）。target_id 需与创建时一致。"""
    tid = (target_id or '').strip()
    for a in approvals_db:
        if a.get('type') == atype and (a.get('target_id') or '').strip() == tid and a.get('status') == 'approved':
            return a
    return None


def create_approval(atype, applicant, target_type, target_id, reason='', project_id=''):
    """创建审批单，返回 id。"""
    aid = uuid.uuid4().hex[:16]
    resolved_project_id = resolve_project_id(project_id) or str(project_id or '').strip()
    approvals_db.append({
        'id': aid, 'type': atype, 'status': 'pending', 'applicant': applicant,
        'target_type': target_type, 'target_id': target_id, 'reason': reason or '',
        'project_id': resolved_project_id,
        'created_at': datetime.now().isoformat(), 'updated_at': datetime.now().isoformat(),
        'approvers': [],  # 可扩展为配置的审批人列表
    })
    save_approvals()
    try:
        from services.webhook import fire_feishu

        fire_feishu("approval_submitted", f"类型={atype} 申请人={applicant} id={aid}")
    except Exception:
        pass
    return aid


def get_pending_approvals_for_user(username):
    """待当前用户审批的列表（管理员或配置的审批人）。"""
    role = _user_role(username)
    is_admin_user = role in ('super_admin', 'admin')
    out = []
    for a in approvals_db:
        if a.get('status') != 'pending':
            continue
        if is_admin_user:
            out.append(a)
        else:
            approvers = a.get('approvers') or []
            if username in approvers:
                out.append(a)
    out.sort(key=lambda x: x.get('created_at') or '', reverse=True)
    return out


def approve_or_reject(approval_id, username, action, comment=''):
    """审批通过或驳回。返回 (True, None) 或 (False, error_msg)。"""
    for a in approvals_db:
        if a.get('id') == approval_id:
            if a.get('status') != 'pending':
                return False, '该申请已处理'
            a['status'] = 'approved' if action == 'approve' else 'rejected'
            a['updated_at'] = datetime.now().isoformat()
            rec = {'approver': username, 'action': action, 'comment': comment or '', 'at': datetime.now().isoformat()}
            approval_records_db[approval_id] = approval_records_db.get(approval_id, []) + [rec]
            save_approvals()
            save_approval_records()
            try:
                from services.webhook import fire_feishu

                title = "approval_approved" if action == "approve" else "approval_rejected"
                fire_feishu(title, f"审批单={approval_id} 操作人={username}")
            except Exception:
                pass
            return True, None
    return False, '审批单不存在'

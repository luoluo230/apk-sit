"""Approval service layer."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from repositories.admin import approvals_repo
from services.admin.envelope import ok, fail, attach_legacy_error


def create_approval_request(data: Dict[str, Any], username: str, project_id: str = "") -> Tuple[Dict[str, Any], int]:
    atype = str(data.get("type") or data.get("target_type") or "").strip()
    valid_types = {t[0] for t in approvals_repo.list_approval_types()}
    if atype not in valid_types:
        return attach_legacy_error(fail("无效的审批类型", code="validation_error", legacy={"error": "无效的审批类型"})), 400
    target_id = str(data.get("target_id") or "").strip()
    reason = str(data.get("reason") or "").strip()
    aid = approvals_repo.create(atype, username, atype, target_id, reason, project_id=project_id)
    approvals_repo.audit("approval_create", f"{atype} {target_id}")
    approvals_repo.notify(username, "approval_result", "审批已提交", f"类型：{atype}，对象：{target_id}", "/admin/approval", aid, "approval")
    return ok({"id": aid, "type": atype, "target_id": target_id}, legacy={"success": True, "id": aid}), 200


def decide_approval(aid: str, action: str, username: str, comment: str = "") -> Tuple[Dict[str, Any], int]:
    if action not in ("approve", "reject"):
        return attach_legacy_error(fail("无效操作", code="validation_error", legacy={"error": "无效操作"})), 400
    accepted, err = approvals_repo.decide(aid, username, action, comment)
    if not accepted:
        status = 409 if (err and ("已" in err or "状态" in err)) else 400
        return attach_legacy_error(fail(err or "操作失败", code="conflict" if status == 409 else "bad_request", legacy={"error": err or "操作失败"})), status

    approval = approvals_repo.find_approval(aid)
    if approval:
        applicant = approval.get("applicant", "")
        approvals_repo.notify(
            applicant,
            "approval_result",
            "审批已%s" % ("通过" if action == "approve" else "驳回"),
            comment or ("已%s" % ("通过" if action == "approve" else "驳回")),
            "/admin/approval",
            aid,
            "approval",
        )
        target_status = "published" if action == "approve" else "rejected"
        approvals_repo.sync_publish_state(
            str(approval.get("type") or ""),
            str(approval.get("target_id") or ""),
            target_status,
            str(approval.get("id") or ""),
        )
    approvals_repo.audit("approval_%s" % action, aid)
    return ok({"id": aid, "action": action}, legacy={"success": True}), 200
